"""JSON Lines IPC Bridge for WhisperProtocol desktop host.

Communicates with Tauri/Rust via standard input and standard output pipes:
- stdin: incoming JSON Lines commands from Rust host
- stdout: strictly JSON Lines responses and events (flushed immediately)
- stderr: diagnostic and application logging (never corrupts stdout IPC)
"""

import base64
import json
import logging
import sys
import threading
from typing import Any, Callable, Dict, Optional, TextIO

from whisper.audio.devices import (
    list_input_devices,
    list_output_devices,
    get_default_input_device,
    get_default_output_device,
    check_sample_rate_support,
)
from whisper.audio.diagnostics import detect_test_tone
from whisper.audio.coordinator import HalfDuplexAudioCoordinator
from whisper.protocol.demodulator import ReceiverConfig, FrameDecodeResult
from whisper.protocol.frames import FrameType
from whisper.engine.discovery import DiscoveryEngine
from whisper.engine.transfer import TransferEngine
from whisper.events import get_event_bus, Event

# Enforce logging to stderr ONLY
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whisper.bridge")


class JSONRPCBridge:
    """Synchronous/asynchronous JSON Lines process bridge."""

    def __init__(
        self,
        in_stream: Optional[TextIO] = None,
        out_stream: Optional[TextIO] = None,
        coordinator: Optional[HalfDuplexAudioCoordinator] = None,
    ):
        self.in_stream = in_stream or sys.stdin
        self.out_stream = out_stream or sys.stdout
        self._write_lock = threading.Lock()
        self._running = False
        self._event_unsub: Optional[Callable[[], None]] = None

        # Shared Half-Duplex Audio Coordinator
        self.coordinator = coordinator or HalfDuplexAudioCoordinator(
            receiver_config=ReceiverConfig(sample_rate=48000, canonical_framing=True),
            on_frame_received=self._on_frame_received,
        )

        # Discovery & Transfer Sub-Engines
        self.discovery = DiscoveryEngine(
            coordinator=self.coordinator,
            on_device_discovered=lambda dev: self.send_event("device_discovered", dev.to_dict()),
        )
        self.transfer = TransferEngine(
            coordinator=self.coordinator,
            on_event=lambda ev_name, data: self.send_event(ev_name, data),
        )

        # Command dispatcher
        self._commands: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            # System / Diagnostics
            "get_app_status": self._cmd_get_app_status,
            "list_audio_devices": self._cmd_list_audio_devices,
            "run_calibration": self._cmd_run_calibration,
            "start_engine": self._cmd_start_engine,
            "stop_engine": self._cmd_stop_engine,
            "shutdown_engine": self._cmd_shutdown_engine,
            # Discovery
            "set_receiver_mode": self._cmd_set_receiver_mode,
            "start_discovery": self._cmd_start_discovery,
            "stop_discovery": self._cmd_stop_discovery,
            "get_discovered_devices": self._cmd_get_discovered_devices,
            # Transfer
            "send_transfer_offer": self._cmd_send_transfer_offer,
            "accept_transfer": self._cmd_accept_transfer,
            "decline_transfer": self._cmd_decline_transfer,
            "confirm_sas": self._cmd_confirm_sas,
            "get_transfer_status": self._cmd_get_transfer_status,
        }

    def _write_json(self, payload: Dict[str, Any]) -> None:
        """Write single JSON object followed by newline to stdout and flush."""
        line = json.dumps(payload, separators=(",", ":"))
        with self._write_lock:
            self.out_stream.write(line + "\n")
            self.out_stream.flush()

    def send_response(self, request_id: str, data: Any) -> None:
        """Send successful command response."""
        self._write_json({"id": request_id, "status": "ok", "data": data})

    def send_error(
        self,
        request_id: str,
        error: str,
        code: str = "ERROR",
        details: Optional[Any] = None,
    ) -> None:
        """Send command error response."""
        resp = {"id": request_id, "status": "error", "error": error, "code": code}
        if details is not None:
            resp["details"] = details
        self._write_json(resp)

    def send_event(self, event_name: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit unsolicited asynchronous event to host."""
        self._write_json({"event": event_name, "data": data or {}})

    def _on_engine_event(self, event: Event) -> None:
        """Forward internal engine events to Tauri IPC."""
        try:
            self.send_event(event.type.value, event.data)
        except Exception as e:
            logger.error("Failed to forward event %s: %s", event.type.value, e)

    def _on_frame_received(self, result: FrameDecodeResult) -> None:
        """Central acoustic packet router."""
        if not result.success or not result.protocol_frame:
            return
        frame = result.protocol_frame
        ftype = frame.frame_type

        if ftype in (FrameType.DISCOVERY_PING, FrameType.DISCOVERY_RESPONSE):
            self.discovery._on_frame_received(result)
        else:
            self.transfer._on_frame_received(result)

    def _cmd_get_app_status(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        """Return application and engine status."""
        default_in = get_default_input_device()
        default_out = get_default_output_device()

        return {
            "engine_state": "ready" if self._running else "idle",
            "version": "0.1.0",
            "protocol_version": 1,
            "platform": sys.platform,
            "default_sample_rate": 48000,
            "supported_sample_rates": [44100, 48000],
            "receiver_mode": self.discovery.is_receiver_mode,
            "discovering": self.discovery.is_discovering,
            "profiles": {
                "primary": {
                    "name": "ultrasonic_standard",
                    "freq_zero": 18000,
                    "freq_one": 19000,
                    "symbol_duration": 0.020,
                    "baud": 50,
                },
                "secondary": {
                    "name": "acoustic_audible_fallback",
                    "freq_zero": 14000,
                    "freq_one": 15000,
                    "symbol_duration": 0.020,
                    "baud": 50,
                },
            },
            "audio_hardware": {
                "default_input": default_in.name if default_in else None,
                "default_output": default_out.name if default_out else None,
            },
        }

    def _cmd_list_audio_devices(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        """List and probe audio hardware devices."""
        inputs = list_input_devices()
        outputs = list_output_devices()

        input_list = []
        for dev in inputs:
            sr_44k = check_sample_rate_support(dev.index, 44100, is_input=True)
            sr_48k = check_sample_rate_support(dev.index, 48000, is_input=True)
            input_list.append({
                "index": dev.index,
                "name": dev.name,
                "channels": dev.max_input_channels,
                "default_sample_rate": dev.default_sample_rate,
                "hostapi": dev.hostapi,
                "supports_44100": sr_44k,
                "supports_48000": sr_48k,
            })

        output_list = []
        for dev in outputs:
            sr_44k = check_sample_rate_support(dev.index, 44100, is_input=False)
            sr_48k = check_sample_rate_support(dev.index, 48000, is_input=False)
            output_list.append({
                "index": dev.index,
                "name": dev.name,
                "channels": dev.max_output_channels,
                "default_sample_rate": dev.default_sample_rate,
                "hostapi": dev.hostapi,
                "supports_44100": sr_44k,
                "supports_48000": sr_48k,
            })

        def_in = get_default_input_device()
        def_out = get_default_output_device()

        return {
            "inputs": input_list,
            "outputs": output_list,
            "default_input_index": def_in.index if def_in else None,
            "default_output_index": def_out.index if def_out else None,
        }

    def _cmd_run_calibration(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run acoustic channel diagnostic and noise floor calibration."""
        input_idx = params.get("input_device_index")
        output_idx = params.get("output_device_index")
        sample_rate = params.get("sample_rate", 48000)

        # Validate sample rate support
        if input_idx is not None:
            if not check_sample_rate_support(input_idx, sample_rate, is_input=True):
                sample_rate = 44100

        diag = detect_test_tone(
            device_index=input_idx,
            sample_rate=sample_rate,
            duration=1.0,
        )

        return {
            "input_device_index": input_idx,
            "output_device_index": output_idx,
            "sample_rate": sample_rate,
            "noise_floor_db": diag.noise_floor.median_noise_level_db,
            "band_18khz": {
                "detected": diag.detected_18khz.detected,
                "peak_frequency": diag.detected_18khz.peak_frequency,
                "peak_magnitude": diag.detected_18khz.peak_magnitude,
                "snr_db": diag.detected_18khz.snr_db,
            },
            "band_19khz": {
                "detected": diag.detected_19khz.detected,
                "peak_frequency": diag.detected_19khz.peak_frequency,
                "peak_magnitude": diag.detected_19khz.peak_magnitude,
                "snr_db": diag.detected_19khz.snr_db,
            },
            "channel_ready": True,
        }

    def _cmd_start_engine(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        self._running = True
        self.send_event("engine.ready", {"status": "running"})
        return {"started": True}

    def _cmd_stop_engine(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        self._running = False
        self.discovery.stop_discovery()
        self.discovery.set_receiver_mode(False)
        self.coordinator.stop_listening()
        self.send_event("engine.stopped", {"status": "stopped"})
        return {"stopped": True}

    def _cmd_shutdown_engine(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        self._running = False
        self.discovery.stop_discovery()
        self.discovery.set_receiver_mode(False)
        self.coordinator.stop_listening()
        self.send_event("engine.shutdown", {"status": "terminating"})
        return {"shutdown": True}

    # ─── Discovery Commands ──────────────────────────────────────────────────────

    def _cmd_set_receiver_mode(self, params: Dict[str, Any]) -> Dict[str, Any]:
        enabled = bool(params.get("enabled", True))
        alias = params.get("alias")
        active = self.discovery.set_receiver_mode(enabled, alias=alias)
        return {"receiver_mode": active, "alias": self.discovery.local_alias}

    def _cmd_start_discovery(self, params: Dict[str, Any]) -> Dict[str, Any]:
        alias = params.get("alias")
        self.discovery.start_discovery(alias=alias)
        return {"discovering": True, "alias": self.discovery.local_alias}

    def _cmd_stop_discovery(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        self.discovery.stop_discovery()
        return {"discovering": False}

    def _cmd_get_discovered_devices(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        devices = self.discovery.get_discovered_devices()
        return {"devices": devices}

    # ─── Transfer Commands ───────────────────────────────────────────────────────

    def _cmd_send_transfer_offer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_name = params.get("file_name", "message.txt")
        payload_text = params.get("payload_text")
        payload_b64 = params.get("payload_base64")

        if payload_text is not None:
            payload = payload_text.encode("utf-8")
        elif payload_b64 is not None:
            payload = base64.b64decode(payload_b64)
        else:
            raise ValueError("Either 'payload_text' or 'payload_base64' is required")

        target_alias = params.get("target_alias", "")
        profile = params.get("profile", "ultrasonic")
        ecc = int(params.get("ecc", 8))

        session_id = self.transfer.initiate_transfer(
            file_name=file_name,
            payload=payload,
            target_alias=target_alias,
            profile_name=profile,
            ecc_symbols=ecc,
        )

        return {
            "session_id": session_id,
            "file_name": file_name,
            "file_size": len(payload),
            "profile": profile,
            "ecc_symbols": ecc,
        }

    def _cmd_accept_transfer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = int(params["session_id"])
        accepted = self.transfer.accept_transfer(session_id)
        return {"session_id": session_id, "accepted": accepted}

    def _cmd_decline_transfer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = int(params["session_id"])
        reason = params.get("reason", "DECLINED")
        declined = self.transfer.decline_transfer(session_id, reason=reason)
        return {"session_id": session_id, "declined": declined}

    def _cmd_confirm_sas(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = int(params["session_id"])
        confirmed = bool(params.get("confirmed", True))
        ok = self.transfer.confirm_sas(session_id, confirmed)
        return {"session_id": session_id, "sas_confirmed": confirmed, "success": ok}

    def _cmd_get_transfer_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = int(params["session_id"])
        status = self.transfer.get_session_status(session_id)
        return {"session_id": session_id, "status": status}

    # ─── Process Run Loop ────────────────────────────────────────────────────────

    def handle_line(self, raw_line: str) -> bool:
        """Process a single JSON Line. Returns False if bridge should terminate."""
        line = raw_line.strip()
        if not line:
            return True

        req_id: Optional[str] = None
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            self.send_error("unknown", f"Invalid JSON line: {e}", code="JSON_PARSE_ERROR")
            return True

        if not isinstance(msg, dict):
            self.send_error("unknown", "Payload must be a JSON object", code="INVALID_PAYLOAD")
            return True

        req_id = msg.get("id")
        cmd = msg.get("cmd")
        params = msg.get("params") or {}

        if not req_id:
            logger.warning("Message missing 'id': %s", line)
            self.send_error("unknown", "Missing required 'id' field", code="MISSING_ID")
            return True

        if not cmd or not isinstance(cmd, str):
            self.send_error(req_id, "Missing or invalid 'cmd' field", code="INVALID_CMD")
            return True

        handler = self._commands.get(cmd)
        if not handler:
            self.send_error(req_id, f"Unknown command: '{cmd}'", code="UNKNOWN_COMMAND")
            return True

        try:
            result = handler(params)
            self.send_response(req_id, result)
            if cmd == "shutdown_engine":
                return False
        except Exception as e:
            logger.exception("Error executing command '%s' (id=%s): %s", cmd, req_id, e)
            self.send_error(req_id, str(e), code="EXECUTION_ERROR")

        return True

    def run(self) -> None:
        """Main execution loop reading stdin until EOF or shutdown."""
        self._running = True
        logger.info("WhisperProtocol JSON Lines bridge starting...")

        # Subscribe to internal engine event bus
        bus = get_event_bus()
        self._event_unsub = bus.subscribe_all(self._on_engine_event)

        # Notify host that bridge is alive
        self.send_event("engine.ready", {"version": "0.1.0"})

        try:
            for line in self.in_stream:
                should_continue = self.handle_line(line)
                if not should_continue:
                    break
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received, exiting bridge.")
        finally:
            self._running = False
            if self._event_unsub:
                self._event_unsub()
            logger.info("WhisperProtocol bridge shutdown complete.")


def main() -> None:
    bridge = JSONRPCBridge()
    bridge.run()


if __name__ == "__main__":
    main()
