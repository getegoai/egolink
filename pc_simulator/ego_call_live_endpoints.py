"""Explicit CALL-020 wearable/Guardian hardware entries, inert without execute.

No fallback device selection, recording or reconnect. Relay credentials and route are supplied
through a private configuration file. Source clocks are sampled at acquisition.
"""
from __future__ import annotations

import argparse
import hmac
import json
import queue
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from pc_simulator import ego_call_operator_control as control
from pc_simulator.ego_call_live_connector import guardian_join, make_connector
from pc_simulator.ego_call_media_io import FramedEndpoint, MediaFrame
from pc_simulator.ego_call_os_serial_wrapper import LazyPySerialFactory
from pc_simulator.ego_call_single_usb_phase_connector import SingleUsbPhaseConfig, SingleUsbPhaseConnector


class _CliIntentVerifier:
    """Checks the explicit CLI invocation scope, not remote endpoint identity."""

    def __init__(self, run_id: str, token: bytearray):
        self.run_id, self.token = run_id, bytearray(token)
        self.used = False
        self.lock = threading.Lock()

    def authorize_once(self, *, token: memoryview, run_id: str, action: str, timeout_ms: int) -> bool:
        with self.lock:
            if self.used:
                return False
            self.used = True
            try:
                return (run_id == self.run_id and action == control.AUTHORIZATION_ACTION
                        and timeout_ms > 0 and hmac.compare_digest(token, self.token))
            finally:
                self.token[:] = b"\x00" * len(self.token)


def run_wearable(values: dict[str, Any]) -> dict[str, Any]:
    config = control.HostControlConfig(**values["host"], enabled=True, plan_only=False)
    config.validate_for_execution()
    if not 2 <= config.frame_count <= 600 or config.max_runtime_ms > 15000:
        raise ValueError("convergence host is limited to 600 frames and 15 seconds")
    route = control.HostTlsConnectorConfig(**values["tls"], enabled=True)
    connector = make_connector(route, cert_file=values["cert_file"], key_file=values["key_file"])
    # The operator verifies the exact 15-second image before invoking this
    # command. No serial console or second handle is opened to guess identity.
    if values.get("verified_device_runtime_limit_seconds") != 15:
        raise ValueError("operator-verified 15-second image required")
    driver = LazyPySerialFactory().open_explicit(
        port_name=config.exact_port, baudrate=config.serial_baudrate,
        read_timeout_ms=config.transport_call_timeout_ms,
        write_timeout_ms=config.transport_call_timeout_ms, exclusive=True,
    )
    phase = None
    host = None
    try:
        phase = SingleUsbPhaseConnector(
            SingleUsbPhaseConfig(config.exact_port, enabled=True,
                                 baudrate=config.serial_baudrate,
                                 read_timeout_ms=config.transport_call_timeout_ms,
                                 write_timeout_ms=config.transport_call_timeout_ms),
            opened_driver=driver,
        )
        host = control.HostControlSession(config)
        token = bytearray(secrets.token_bytes(32))
        verifier = _CliIntentVerifier(config.run_id, token)
        authorization = control.OneShotOperatorAuthorization(
            run_id=config.run_id, token=token, operator_authorized=True,
            expires_at_monotonic_ns=time.monotonic_ns() + 5_000_000_000,
        )
        host.prepare(authorization=authorization, verifier=verifier)
        host.preflight(
            wearable_control=phase,
            wearable_attestation=control.WearableControlAttestation(
                control.WEARABLE_RUNNER_VERSION, control.WEARABLE_RUNNER_API_VERSION,
                True, True, False, True, True, config.control_timeout_ms,
                logically_separate_and_not_interleaved_with_media=True,
            ),
            tls_connector=connector,
            tls_connector_attestation=control.TlsConnectorAttestation(
                True, True, True, True, True, False, True,
                max_connect_timeout_ms=route.overall_timeout_ms,
                retains_partial_open_for_bounded_retry=True,
            ), serial_factory=phase,
        )
        host.open()
        host.start()
        deadline = time.monotonic() + config.max_runtime_ms / 1000
        while not host.audit()["media_thread_done"] and time.monotonic() < deadline:
            time.sleep(.02)
        host.stop()
        return host.close()
    finally:
        if host is not None:
            host.close()
        if phase is None or phase.phase_snapshot()["state"] == "dormant":
            driver.close()
        # All other states retain the existing M/P single-owner cleanup rules.


def _exact_audio_device(audio_api: Any, name: str, direction: str,
                        hostapi_name: str | None = None) -> int:
    if not isinstance(name, str) or not name or direction not in {"input", "output"}:
        raise ValueError("exact audio endpoint required")
    apis = audio_api.query_hostapis()
    matching = [index for index, entry in enumerate(audio_api.query_devices())
                if entry["name"] == name and entry["max_" + direction + "_channels"] >= 1
                and (hostapi_name is None or apis[entry["hostapi"]]["name"] == hostapi_name)]
    if len(matching) != 1:
        raise ValueError("audio endpoint missing or ambiguous")
    return matching[0]


def run_guardian(values: dict[str, Any]) -> dict[str, Any]:
    route = control.HostTlsConnectorConfig(**values["tls"], enabled=True)
    route.validate_for_open()
    import sounddevice  # optional runtime dependency; never imported by plans

    frame_count = values["frame_count"]
    max_runtime_ms = values["max_runtime_ms"]
    if type(frame_count) is not int or not 2 <= frame_count <= 600:
        raise ValueError("Guardian convergence frame count outside bound")
    if type(max_runtime_ms) is not int or not frame_count * 20 < max_runtime_ms <= 15000:
        raise ValueError("Guardian convergence runtime outside bound")
    if not values.get("input_device") or not values.get("output_device"):
        raise ValueError("exact input and output device names required")
    capture: queue.Queue[tuple[bytearray, int]] = queue.Queue(8)
    playback: queue.Queue[bytearray] = queue.Queue(8)
    stop = threading.Event()
    failed = threading.Event()
    finished = threading.Event()
    counts = {"sent": 0, "played": 0, "received": 0, "input_overflow": 0,
              "output_underflow": 0, "queue_full": 0}

    def audio_callback(indata, outdata, frames, clock, status):
        outdata[:] = b"\x00" * len(outdata)
        if frames != 320 or len(indata) != 640 or len(outdata) != 640:
            failed.set()
            raise sounddevice.CallbackAbort
        if stop.is_set():
            raise sounddevice.CallbackAbort
        if status.input_overflow or status.output_underflow:
            counts["input_overflow"] += int(status.input_overflow)
            counts["output_underflow"] += int(status.output_underflow)
            failed.set()
            raise sounddevice.CallbackAbort
        # PortAudio's ADC timestamp is mapped into the same host monotonic
        # epoch used by the media source; receipt of a relay frame is not it.
        adc_age = float(clock.currentTime - clock.inputBufferAdcTime)
        if not 0 <= adc_age <= 1:
            failed.set()
            raise sounddevice.CallbackAbort
        if counts["sent"] < frame_count:
            media = bytearray(indata)
            try:
                capture.put_nowait((media, time.monotonic_ns() - int(adc_age * 1e9)))
            except queue.Full:
                media[:] = b"\x00" * len(media)
                counts["queue_full"] += 1
                failed.set()
                raise sounddevice.CallbackAbort
        try:
            incoming = playback.get_nowait()
        except queue.Empty:
            return  # startup silence is not reported as delivered audio
        outdata[:] = incoming
        incoming[:] = b"\x00" * len(incoming)
        counts["played"] += 1

    stream = None
    workers = []
    # Open the exact audio endpoint without starting capture before the TLS
    # pair is admitted, so device START need not wait for audio-device setup.
    audio = sounddevice.RawStream(
        samplerate=16000, blocksize=320, channels=1, dtype="int16",
        device=(_exact_audio_device(sounddevice, values["input_device"], "input", values.get("input_hostapi")),
                _exact_audio_device(sounddevice, values["output_device"], "output", values.get("output_hostapi"))),
        callback=audio_callback, finished_callback=finished.set,
    )
    try:
        identity, stream = guardian_join(route, run_id=values["run_id"],
                                         cert_file=values["cert_file"], key_file=values["key_file"])
        endpoint = FramedEndpoint(stream, identity, inbound_direction="uplink", outbound_direction="downlink")
        deadline = time.monotonic() + max_runtime_ms / 1000
        def transmit():
            try:
                for sequence in range(frame_count):
                    if stop.is_set():
                        return
                    media, timestamp = capture.get(timeout=.5)
                    frame = MediaFrame(identity.session_id, "downlink", "guardian", identity.guardian_id,
                                       "device", identity.device_id, sequence, identity.downlink_clock_id,
                                       timestamp, media)
                    try:
                        endpoint.send(frame, timeout_steps=25, attempts=1)
                        counts["sent"] += 1
                    finally:
                        frame.dispose()
            except Exception:
                failed.set()
        def receive():
            try:
                for _ in range(frame_count):
                    if stop.is_set():
                        return
                    frame, _ = endpoint.receive(timeout_steps=25, attempts=16)
                    pending = bytearray(frame.media)
                    try:
                        playback.put_nowait(pending)
                        pending = None
                        counts["received"] += 1
                    finally:
                        if pending is not None:
                            pending[:] = b"\x00" * len(pending)
                        frame.dispose()
            except Exception:
                failed.set()
        workers = [threading.Thread(target=fn, daemon=True) for fn in (transmit, receive)]
        for worker in workers:
            worker.start()
        audio.start()
        while time.monotonic() < deadline and not failed.is_set() and not finished.is_set():
            if counts["played"] == frame_count and counts["sent"] == frame_count:
                break
            time.sleep(.01)
        successful = not failed.is_set() and counts["played"] == frame_count and counts["sent"] == frame_count
    finally:
        stop.set()
        if stream is not None:
            stream.request_cancel()
        audio.abort()
        audio.close()
        for worker in workers:
            worker.join(1)
        if stream is not None:
            stream.close()
        for pending in (capture, playback):
            while not pending.empty():
                value = pending.get_nowait()
                media = value[0] if isinstance(value, tuple) else value
                media[:] = b"\x00" * len(media)
    return {"result": "PASS" if successful else "FAIL", "counts": counts,
            "workers_quiescent": not any(worker.is_alive() for worker in workers),
            "audio_recorded": False, "p0_call": "NOT_RUN"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit bounded CALL-020 hardware endpoint; default is inert plan.")
    parser.add_argument("role", choices=("wearable", "guardian"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execute-authorized-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        values = json.loads(args.config.read_text(encoding="utf-8"))
        if not args.execute_authorized_run:
            result = {"mode": "plan_only", "external_io_performed": False, "p0_call": "NOT_RUN"}
        else:
            result = (run_wearable if args.role == "wearable" else run_guardian)(values)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("result") != "FAIL" else 2
    except Exception:
        print(json.dumps({"result": "FAIL", "reason": "endpoint_run_failed", "p0_call": "NOT_RUN"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
