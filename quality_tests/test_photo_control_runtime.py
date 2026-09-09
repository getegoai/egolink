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
  uint8_t capture_blob[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES];
  assert(photo_control_capture_journal_encode(&capture_journal,capture_blob,&bytes));
  photo_control_capture_journal_t capture_restored;
  assert(photo_control_capture_journal_decode(capture_blob,bytes,&capture_restored));
  assert(!photo_control_capture_journal_allows_new_command(&capture_restored));
  assert(capture_restored.phase==PHOTO_CONTROL_CAPTURE_RESULT);
  assert(capture_restored.capture_boot_count==7U&&capture_restored.capture_sequence_id==42U);
  assert(capture_restored.source_event_monotonic_ns==987654321ULL);
  assert(capture_restored.media_saved&&!strcmp(capture_restored.photo_id,"timer-photo-001"));
  capture_blob[bytes-1U]^=1U;
  assert(!photo_control_capture_journal_decode(capture_blob,bytes,&capture_restored));
  photo_control_capture_journal_default(&capture_restored);
  assert(photo_control_capture_journal_allows_new_command(&capture_restored));

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
