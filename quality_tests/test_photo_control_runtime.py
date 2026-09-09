from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from quality_tests.native_convergence import run_c
from server.message_hub import (
    build_raw_command_frame,
    initial_raw_frame_record,
    parse_raw_frame_record,
    utc_now,
    validate_photo_timer_ack,
)


def utc_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


class PhotoControlRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        now_ms = 1_800_000_000_000
        retention = "2027-01-15T10:00:00.123Z"
        retention_ms = int(
            datetime.fromisoformat(retention[:-1] + "+00:00").timestamp() * 1000
        )
        capture = build_raw_command_frame(
            "collector-001",
            {
                "cmd": "capture_photo_once",
                "cmd_id": "capture-command-001",
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "photo-session-001",
                    "retention_expires_at": retention,
                    "training_allowed": False,
                    "trigger_reason": "web_manual",
                },
            },
        )
        timer = build_raw_command_frame(
            "collector-001",
            {
                "cmd": "configure_photo_timer",
                "cmd_id": "timer-command-001",
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "photo-session-001",
                    "config_version": "timer-config-001",
                    "enabled": True,
                    "interval_seconds": 300,
                    "session_expires_at_unix_ms": now_ms + 3_600_000,
                    "retention_expires_at": retention,
                    "max_photos": 12,
                    "training_allowed": False,
                },
            },
        )
        empty = build_raw_command_frame("collector-001", None)
        harness = r'''
#include "photo_control_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const unsigned char CAPTURE[]={__CAPTURE__};
static const unsigned char TIMER[]={__TIMER__};
static const unsigned char EMPTY[]={__EMPTY__};

static uint32_t legacy_crc_update(uint32_t crc,const void *data,size_t bytes)
{
  const uint8_t *p=data;
  for(size_t i=0U;i<bytes;++i){
    crc^=p[i];
    for(unsigned bit=0U;bit<8U;++bit)
      crc=(crc>>1U)^(UINT32_C(0xedb88320)&(0U-(crc&1U)));
  }
  return crc;
}
static void legacy_put32(uint8_t *p,uint32_t value)
{ for(unsigned i=0U;i<4U;++i)p[i]=(uint8_t)(value>>(i*8U)); }
static uint32_t legacy_capture_crc(const uint8_t *blob,size_t bytes)
{
  uint32_t crc=legacy_crc_update(UINT32_MAX,blob,28U);
  if(bytes>32U)crc=legacy_crc_update(crc,blob+32U,bytes-32U);
  return ~crc;
}
static size_t convert_current_capture_journal_to_legacy_v1(
    uint8_t blob[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES],size_t current_bytes)
{
  assert(current_bytes>68U);
  size_t at=68U;
  /* v1 ended after the same first seven one-byte-length-prefixed strings. */
  for(unsigned field=0U;field<7U;++field){
    assert(at<current_bytes&&blob[at]>0U);
    at+=1U+(size_t)blob[at];
    assert(at<=current_bytes);
  }
  legacy_put32(blob+4U,1U);
  legacy_put32(blob+28U,legacy_capture_crc(blob,at));
  return at;
}

int main(void){
  photo_control_command_t c;
  assert(photo_control_parse_raw_command(CAPTURE,sizeof(CAPTURE),&c)==PHOTO_CONTROL_PARSE_OK);
  assert(c.kind==PHOTO_CONTROL_COMMAND_CAPTURE_ONCE);
  assert(strcmp(c.cmd_id,"capture-command-001")==0);
  assert(strcmp(c.authorization_session_id,"photo-session-001")==0);
  assert(strcmp(c.trigger_reason,"web_manual")==0);
  assert(!c.training_allowed&&c.retention_expires_at_unix_ms==__RETENTION_MS__ULL);
  assert(!photo_control_command_is_live(&c,false,__NOW_MS__ULL));
  assert(photo_control_command_is_live(&c,true,__NOW_MS__ULL));
  assert(!photo_control_command_is_live(&c,true,__NOW_MS__ULL+60000ULL));
  assert(photo_control_parse_raw_command(EMPTY,sizeof(EMPTY),&c)==PHOTO_CONTROL_PARSE_EMPTY);
  unsigned char damaged[sizeof(CAPTURE)];memcpy(damaged,CAPTURE,sizeof(damaged));damaged[sizeof(damaged)-2]^=1U;
  assert(photo_control_parse_raw_command(damaged,sizeof(damaged),&c)==PHOTO_CONTROL_PARSE_BAD_CRC);

  assert(photo_control_parse_raw_command(TIMER,sizeof(TIMER),&c)==PHOTO_CONTROL_PARSE_OK);
  assert(c.kind==PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER&&c.timer_enabled);
  assert(c.interval_seconds==300U&&c.max_photos==12U);
  photo_control_timer_t state;photo_control_timer_default(&state);
  assert(photo_control_timer_apply(&state,&c,true,__NOW_MS__ULL,1000U));
  assert(photo_control_timer_tick(&state,true,__NOW_MS__ULL,300999U)==PHOTO_CONTROL_TIMER_WAITING);
  assert(photo_control_timer_tick(&state,true,__NOW_MS__ULL,301000U)==PHOTO_CONTROL_TIMER_DUE);
  photo_control_timer_complete_attempt(&state,true,301100U);
  assert(state.captured_photos==1U&&state.next_due_monotonic_ms==601100U);

  uint8_t blob[PHOTO_CONTROL_TIMER_BLOB_BYTES];size_t bytes=0U;
  assert(photo_control_timer_encode(&state,blob,&bytes));
  photo_control_timer_t reboot;assert(photo_control_timer_decode(blob,bytes,&reboot));
  assert(reboot.enabled&&!reboot.schedule_armed&&reboot.captured_photos==1U);
  assert(strcmp(reboot.command_id,"timer-command-001")==0);
  assert(photo_control_timer_tick(&reboot,false,__NOW_MS__ULL,900000U)==PHOTO_CONTROL_TIMER_WAITING_FOR_TRUSTED_UTC);
  assert(photo_control_timer_tick(&reboot,true,__NOW_MS__ULL,900000U)==PHOTO_CONTROL_TIMER_WAITING);
  assert(reboot.next_due_monotonic_ms==1200000U); /* restart interval; no catch-up */
  blob[bytes-1U]^=1U;assert(!photo_control_timer_decode(blob,bytes,&reboot));

  photo_control_timer_t conflict=state;photo_control_command_t changed=c;changed.interval_seconds=301U;
  assert(!photo_control_timer_apply(&conflict,&changed,true,__NOW_MS__ULL,1U));
  state.captured_photos=state.max_photos;
  assert(photo_control_timer_tick(&state,true,__NOW_MS__ULL,1U)==PHOTO_CONTROL_TIMER_LIMIT_REACHED);

  photo_control_journal_t journal={.phase=PHOTO_CONTROL_JOURNAL_EXECUTING,.kind=PHOTO_CONTROL_COMMAND_CAPTURE_ONCE};
  strcpy(journal.cmd_id,"capture-command-001");strcpy(journal.status,"pending");
  strcpy(journal.message,"capture started");strcpy(journal.photo_id,"photo-001");
  uint8_t journal_blob[PHOTO_CONTROL_JOURNAL_BLOB_BYTES];
  assert(photo_control_journal_encode(&journal,journal_blob,&bytes));
  photo_control_journal_t restored;assert(photo_control_journal_decode(journal_blob,bytes,&restored));
  assert(restored.phase==PHOTO_CONTROL_JOURNAL_EXECUTING&&!strcmp(restored.photo_id,"photo-001"));

  photo_control_capture_journal_t capture_journal={
    .phase=PHOTO_CONTROL_CAPTURE_RESULT,
    .kind=PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER,
    .execution_expires_at_unix_ms=1800003600000ULL,
    .retention_expires_at_unix_ms=__RETENTION_MS__ULL,
    .source_event_utc_ms=__NOW_MS__ULL,
    .source_event_monotonic_ns=987654321ULL,
    .capture_boot_count=7U,.capture_sequence_id=42U,
    .timer_captured_count_before=3U,
    .attempted=true,.frame_acquired=true,.media_saved=true
  };
  strcpy(capture_journal.photo_id,"timer-photo-001");
  strcpy(capture_journal.trigger_reason,"device_timer");
  strcpy(capture_journal.command_id,"timer-command-001");
  strcpy(capture_journal.config_version,"timer-config-001");
  strcpy(capture_journal.authorization_session_id,"photo-session-001");
  strcpy(capture_journal.retention_expires_at,"2027-01-15T10:00:00.123Z");
  strcpy(capture_journal.failure_reason,"none");
  strcpy(capture_journal.camera_shared_i2c_state,"trial_unverified");
  strcpy(capture_journal.camera_driver_profile,
      "qvga-jpeg-q12-v1-shared-i2c-trial_unverified");
  strcpy(capture_journal.runtime_config_id,
      "collector-v1-camera-shared-i2c-trial_unverified");
  strcpy(capture_journal.capture_fw_version,"camera-runtime-test");
  memset(capture_journal.capture_firmware_elf_sha256,'a',64U);
  capture_journal.capture_firmware_elf_sha256[64U]=0;
  uint8_t capture_blob[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES];
  assert(photo_control_capture_journal_encode(&capture_journal,capture_blob,&bytes));
  photo_control_capture_journal_t capture_restored;
  assert(photo_control_capture_journal_decode(capture_blob,bytes,&capture_restored));
  assert(!photo_control_capture_journal_allows_new_command(&capture_restored));
  assert(capture_restored.phase==PHOTO_CONTROL_CAPTURE_RESULT);
  assert(capture_restored.capture_boot_count==7U&&capture_restored.capture_sequence_id==42U);
  assert(capture_restored.source_event_monotonic_ns==987654321ULL);
  assert(capture_restored.media_saved&&!strcmp(capture_restored.photo_id,"timer-photo-001"));
  assert(!strcmp(capture_restored.camera_shared_i2c_state,"trial_unverified"));
  assert(!strcmp(capture_restored.camera_driver_profile,
      "qvga-jpeg-q12-v1-shared-i2c-trial_unverified"));
  assert(!strcmp(capture_restored.runtime_config_id,
      "collector-v1-camera-shared-i2c-trial_unverified"));
  assert(!strcmp(capture_restored.capture_fw_version,"camera-runtime-test"));
  assert(!strcmp(capture_restored.capture_firmware_elf_sha256,
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"));

  /* A syntactically valid but contradictory gate/profile pair is rejected
   * before persistence. */
  strcpy(capture_journal.camera_shared_i2c_state,"verified");
  assert(!photo_control_capture_journal_encode(
      &capture_journal,capture_blob,&bytes));
  strcpy(capture_journal.camera_shared_i2c_state,"trial_unverified");
  capture_blob[bytes-1U]^=1U;
  assert(!photo_control_capture_journal_decode(capture_blob,bytes,&capture_restored));

  /* A real v1 byte layout remains readable, but its absent capture-time gate
   * facts stay explicitly unknown rather than inheriting the current image. */
  assert(photo_control_capture_journal_encode(&capture_journal,capture_blob,&bytes));
  bytes=convert_current_capture_journal_to_legacy_v1(capture_blob,bytes);
  assert(photo_control_capture_journal_decode(capture_blob,bytes,&capture_restored));
  assert(capture_restored.phase==PHOTO_CONTROL_CAPTURE_RESULT);
  assert(!strcmp(capture_restored.photo_id,"timer-photo-001"));
  assert(!strcmp(capture_restored.camera_shared_i2c_state,"unknown_legacy"));
  assert(!strcmp(capture_restored.camera_driver_profile,
      "qvga-jpeg-q12-v1-shared-i2c-unknown_legacy"));
  assert(!strcmp(capture_restored.runtime_config_id,"unknown_legacy"));
  assert(!strcmp(capture_restored.capture_fw_version,"unknown_legacy"));
  assert(!strcmp(capture_restored.capture_firmware_elf_sha256,
      "0000000000000000000000000000000000000000000000000000000000000000"));
  assert(strcmp(capture_restored.camera_shared_i2c_state,"verified"));
  assert(!strstr(capture_restored.camera_driver_profile,"-verified"));
  assert(photo_control_capture_journal_encode(
      &capture_restored,capture_blob,&bytes));
  photo_control_capture_journal_t migrated;
  assert(photo_control_capture_journal_decode(capture_blob,bytes,&migrated));
  assert(!strcmp(migrated.camera_shared_i2c_state,"unknown_legacy"));
  assert(!strcmp(migrated.camera_driver_profile,
      "qvga-jpeg-q12-v1-shared-i2c-unknown_legacy"));
  assert(!strcmp(migrated.runtime_config_id,"unknown_legacy"));
  assert(!strcmp(migrated.capture_fw_version,"unknown_legacy"));
  assert(!strcmp(migrated.capture_firmware_elf_sha256,
      "0000000000000000000000000000000000000000000000000000000000000000"));

  photo_control_capture_journal_default(&capture_restored);
  assert(photo_control_capture_journal_allows_new_command(&capture_restored));

  /* Retention expiry may pre-empt a future retry once. After that attempt
   * fails, repeated expiry observations must respect the short monotonic
   * deadline instead of spinning on every uploader pass. */
  photo_control_capture_settle_retry_t settle_retry;
  photo_control_capture_settle_retry_reset(&settle_retry,1000U);
  assert(photo_control_capture_settle_retry_schedule_failure(
      &settle_retry,1000U,false,250U,60000U));
  assert(settle_retry.next_retry_monotonic_ms==2000U);
  assert(settle_retry.backoff_ms==2000U);
  assert(!photo_control_capture_settle_retry_due(
      &settle_retry,1500U,false));
  assert(photo_control_capture_settle_retry_due(
      &settle_retry,1500U,true));
  assert(settle_retry.retention_deadline_bypass_used);
  assert(photo_control_capture_settle_retry_schedule_failure(
      &settle_retry,1500U,true,250U,60000U));
  assert(settle_retry.next_retry_monotonic_ms==1750U);
  assert(!photo_control_capture_settle_retry_due(
      &settle_retry,1501U,true));
  assert(!photo_control_capture_settle_retry_due(
      &settle_retry,1749U,true));
  assert(photo_control_capture_settle_retry_due(
      &settle_retry,1750U,true));
  assert(photo_control_capture_settle_retry_schedule_failure(
      &settle_retry,1750U,true,250U,60000U));
  assert(!photo_control_capture_settle_retry_due(
      &settle_retry,1751U,true));

  /* Reset represents a different durable journal and restores exactly one
   * expiry bypass. */
  photo_control_capture_settle_retry_reset(&settle_retry,1000U);
  assert(photo_control_capture_settle_retry_schedule_failure(
      &settle_retry,3000U,false,250U,60000U));
  assert(photo_control_capture_settle_retry_due(
      &settle_retry,3500U,true));
  assert(!photo_control_capture_settle_retry_due(
      &settle_retry,3500U,true));

  /* Normal failures keep capped exponential backoff, and deadline arithmetic
   * saturates instead of wrapping near UINT64_MAX. */
  photo_control_capture_settle_retry_reset(&settle_retry,40000U);
  assert(photo_control_capture_settle_retry_schedule_failure(
      &settle_retry,0U,false,250U,60000U));
  assert(settle_retry.next_retry_monotonic_ms==40000U);
  assert(settle_retry.backoff_ms==60000U);
  assert(photo_control_capture_settle_retry_schedule_failure(
      &settle_retry,UINT64_MAX-100U,true,250U,60000U));
  assert(settle_retry.next_retry_monotonic_ms==UINT64_MAX);
  assert(!photo_control_capture_settle_retry_due(
      &settle_retry,UINT64_MAX-1U,true));
  assert(photo_control_capture_settle_retry_due(
      &settle_retry,UINT64_MAX,true));

  char ack[1024];assert(photo_control_build_ack_frame("capture-command-001","ok","saved locally",
      "camera-runtime-test","lte",7U,true,ack,sizeof(ack),&bytes));
  assert(strstr(ack,"type=ack")&&strstr(ack,"status=ok")&&strstr(ack,"duplicate_local_execution_prevented=true"));
  fwrite(ack,1U,bytes,stdout);return 0;
}
'''
        harness = (
            harness.replace("__CAPTURE__", ",".join(map(str, capture)))
            .replace("__TIMER__", ",".join(map(str, timer)))
            .replace("__EMPTY__", ",".join(map(str, empty)))
            .replace("__RETENTION_MS__", str(retention_ms))
            .replace("__NOW_MS__", str(now_ms))
        )
        cls.ack = run_c(harness, components=("photo_control_runtime",)).encode()
        timer_ack_harness = r'''
#include "photo_control_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
  photo_control_timer_t timer = {
    .enabled=true, .interval_seconds=300U,
    .session_expires_at_unix_ms=1800003600000ULL,
    .max_photos=12U, .captured_photos=1U
  };
  strcpy(timer.command_id,"timer-command-001");
  strcpy(timer.authorization_session_id,"photo-session-001");
  strcpy(timer.config_version,"timer-config-001");
  strcpy(timer.retention_expires_at,"2027-01-15T10:00:00.123Z");
  strcpy(timer.state_reason,"active");
  char ack[2048]; size_t bytes=0U;
  assert(photo_control_build_timer_state_ack_frame("timer-command-001",
    "applied","timer_configuration_applied","camera-runtime-test","lte",
    8U,false,&timer,true,ack,sizeof(ack),&bytes));
  fwrite(ack,1U,bytes,stdout);
  return 0;
}
'''
        cls.timer_ack = run_c(
            timer_ack_harness, components=("photo_control_runtime",)
        ).encode()
        cls.timer_command = {
            "cmd": "configure_photo_timer",
            "cmd_id": "timer-command-001",
            "payload": {
                "authorization_session_id": "photo-session-001",
                "config_version": "timer-config-001",
                "enabled": True,
                "interval_seconds": 300,
                "session_expires_at_unix_ms": 1_800_003_600_000,
                "retention_expires_at": retention,
                "max_photos": 12,
                "training_allowed": False,
            },
        }

    def test_runtime_ack_is_a_valid_raw_frame(self):
        initial = initial_raw_frame_record(
            "collector-001", self.ack, "uplink", utc_now()
        )
        parsed = parse_raw_frame_record(
            initial,
            self.ack,
            expected_frame_type="ack",
            expected_cmd_id="capture-command-001",
        )
        self.assertEqual(parsed["parse_result"]["status"], "ok")
        derived = parsed["parse_result"]["derived_message"]
        self.assertEqual(derived["status"], "ok")
        self.assertEqual(
            derived["command"]["duplicate_local_execution_prevented"], True
        )

    def test_component_is_discovered_and_exercises_restart_timer_and_journal(self):
        self.assertIn(b"capture-command-001", self.ack)

    def test_capture_journal_preserves_v2_provenance_and_migrates_v1_as_unknown(self):
        # The native setUp harness performs the v2 byte-for-byte round trip,
        # constructs a genuine v1 layout, and rejects any verified inference.
        self.assertTrue(self.ack.startswith(b"EGLK/1"))

    def test_capture_settle_retry_policy_uses_simulated_time(self):
        # The native harness covers one-shot expiry pre-emption, mandatory
        # post-failure delay, per-journal reset, capped backoff, and overflow.
        self.assertTrue(self.ack.startswith(b"EGLK/1"))

    def test_timer_ack_projects_complete_applied_effective_state(self):
        initial = initial_raw_frame_record(
            "collector-001", self.timer_ack, "uplink", utc_now()
        )
        parsed = parse_raw_frame_record(
            initial,
            self.timer_ack,
            expected_frame_type="ack",
            expected_cmd_id="timer-command-001",
        )
        self.assertEqual(parsed["parse_result"]["status"], "ok")
        derived = parsed["parse_result"]["derived_message"]
        self.assertEqual(derived["status"], "applied")
        self.assertEqual(
            set(derived["timer_state"]),
            {
                "config_version",
                "enabled",
                "interval_seconds",
                "session_expires_at_unix_ms",
                "max_photos",
                "captured_count",
                "state_reason",
                "trusted_utc",
            },
        )
        validate_photo_timer_ack(self.timer_command, derived)


if __name__ == "__main__":
    unittest.main()
