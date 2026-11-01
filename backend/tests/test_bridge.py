"""Unit tests for WhisperProtocol JSON Lines IPC bridge."""

import io
import json
import pytest

from whisper.engine.bridge import JSONRPCBridge
from whisper.events import get_event_bus, emit_transmission_started


class TestJSONRPCBridge:
    """Tests for JSONRPCBridge communication and command dispatching."""

    def setup_method(self):
        self.in_buf = io.StringIO()
        self.out_buf = io.StringIO()
        self.bridge = JSONRPCBridge(in_stream=self.in_buf, out_stream=self.out_buf)

    def _read_output_lines(self) -> list[dict]:
        lines = [l.strip() for l in self.out_buf.getvalue().split("\n") if l.strip()]
        return [json.loads(l) for l in lines]

    def test_get_app_status(self):
        msg = json.dumps({"id": "req-1", "cmd": "get_app_status", "params": {}})
        cont = self.bridge.handle_line(msg)

        assert cont is True
        outputs = self._read_output_lines()
        assert len(outputs) == 1
        resp = outputs[0]

        assert resp["id"] == "req-1"
        assert resp["status"] == "ok"
        data = resp["data"]
        assert "version" in data
        assert "default_sample_rate" in data
        assert data["default_sample_rate"] == 48000
        assert "profiles" in data
        assert "primary" in data["profiles"]
        assert "secondary" in data["profiles"]

    def test_list_audio_devices(self):
        msg = json.dumps({"id": "req-2", "cmd": "list_audio_devices", "params": {}})
        cont = self.bridge.handle_line(msg)

        assert cont is True
        outputs = self._read_output_lines()
        assert len(outputs) == 1
        resp = outputs[0]

        assert resp["id"] == "req-2"
        assert resp["status"] == "ok"
        data = resp["data"]
        assert "inputs" in data
        assert "outputs" in data
        assert isinstance(data["inputs"], list)
        assert isinstance(data["outputs"], list)

    def test_unknown_command_returns_error(self):
        msg = json.dumps({"id": "req-unknown", "cmd": "non_existent_command", "params": {}})
        cont = self.bridge.handle_line(msg)

        assert cont is True
        outputs = self._read_output_lines()
        assert len(outputs) == 1
        resp = outputs[0]

        assert resp["id"] == "req-unknown"
        assert resp["status"] == "error"
        assert resp["code"] == "UNKNOWN_COMMAND"

    def test_malformed_json_returns_parse_error(self):
        cont = self.bridge.handle_line("{not-valid-json}")

        assert cont is True
        outputs = self._read_output_lines()
        assert len(outputs) == 1
        resp = outputs[0]

        assert resp["status"] == "error"
        assert resp["code"] == "JSON_PARSE_ERROR"

    def test_missing_id_returns_error(self):
        msg = json.dumps({"cmd": "get_app_status"})
        cont = self.bridge.handle_line(msg)

        assert cont is True
        outputs = self._read_output_lines()
        assert len(outputs) == 1
        assert outputs[0]["code"] == "MISSING_ID"

    def test_shutdown_command_returns_false(self):
        msg = json.dumps({"id": "req-exit", "cmd": "shutdown_engine", "params": {}})
        cont = self.bridge.handle_line(msg)

        assert cont is False  # Instructs line loop to terminate
        outputs = self._read_output_lines()
        # Should have emitted shutdown event + command response
        assert any(o.get("event") == "engine.shutdown" for o in outputs)
        resp = next(o for o in outputs if o.get("id") == "req-exit")
        assert resp["status"] == "ok"
        assert resp["data"]["shutdown"] is True

    def test_event_forwarding(self):
        bus = get_event_bus()
        unsub = bus.subscribe_all(self.bridge._on_engine_event)

        try:
            emit_transmission_started(
                message="TEST_IPC",
                sample_rate=48000,
                symbol_duration=0.02,
                amplitude=0.8,
            )
            outputs = self._read_output_lines()
            assert any(
                o.get("event") == "transmission.started" and o.get("data", {}).get("message") == "TEST_IPC"
                for o in outputs
            )
        finally:
            unsub()
