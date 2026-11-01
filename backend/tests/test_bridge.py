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

    def test_discovery_ipc_commands(self):
        # 1. Toggle receiver mode
        msg1 = json.dumps({"id": "req-disc-1", "cmd": "set_receiver_mode", "params": {"enabled": True, "alias": "BridgeNode"}})
        self.bridge.handle_line(msg1)
        resp1 = [o for o in self._read_output_lines() if o.get("id") == "req-disc-1"][0]
        assert resp1["status"] == "ok"
        assert resp1["data"]["receiver_mode"] is True
        assert resp1["data"]["alias"] == "BridgeNode"

        # 2. Get discovered devices (initially empty)
        msg2 = json.dumps({"id": "req-disc-2", "cmd": "get_discovered_devices", "params": {}})
        self.bridge.handle_line(msg2)
        resp2 = [o for o in self._read_output_lines() if o.get("id") == "req-disc-2"][0]
        assert resp2["status"] == "ok"
        assert resp2["data"]["devices"] == []

        # 3. Stop discovery
        msg3 = json.dumps({"id": "req-disc-3", "cmd": "stop_discovery", "params": {}})
        self.bridge.handle_line(msg3)
        resp3 = [o for o in self._read_output_lines() if o.get("id") == "req-disc-3"][0]
        assert resp3["status"] == "ok"
        assert resp3["data"]["discovering"] is False

    def test_transfer_ipc_commands(self):
        # Mock transmit to prevent actual speaker playback during unit test
        self.bridge.coordinator.transmit = lambda *args, **kwargs: None

        # 1. Send transfer offer
        msg = json.dumps({
            "id": "req-xfer-1",
            "cmd": "send_transfer_offer",
            "params": {
                "file_name": "test_doc.txt",
                "payload_text": "Acoustic payload over IPC",
                "target_alias": "PeerNode",
            }
        })
        self.bridge.handle_line(msg)
        resp = [o for o in self._read_output_lines() if o.get("id") == "req-xfer-1"][0]
        assert resp["status"] == "ok"
        session_id = resp["data"]["session_id"]
        assert session_id > 0
        assert resp["data"]["file_name"] == "test_doc.txt"
        assert resp["data"]["file_size"] == len(b"Acoustic payload over IPC")

        # 2. Get status
        msg_status = json.dumps({
            "id": "req-xfer-status",
            "cmd": "get_transfer_status",
            "params": {"session_id": session_id}
        })
        self.bridge.handle_line(msg_status)
        resp_status = [o for o in self._read_output_lines() if o.get("id") == "req-xfer-status"][0]
        assert resp_status["status"] == "ok"
        assert resp_status["data"]["status"]["session_id"] == session_id
        assert resp_status["data"]["status"]["state"] == "offer_sent"

    def test_storage_ipc_commands(self):
        # 1. Get settings
        msg_s = json.dumps({"id": "req-s-1", "cmd": "get_settings", "params": {}})
        self.bridge.handle_line(msg_s)
        resp_s = [o for o in self._read_output_lines() if o.get("id") == "req-s-1"][0]
        assert resp_s["status"] == "ok"
        assert "alias" in resp_s["data"]["settings"]

        # 2. Update setting
        msg_u = json.dumps({"id": "req-s-2", "cmd": "update_setting", "params": {"key": "alias", "value": "NewBridgeAlias"}})
        self.bridge.handle_line(msg_u)
        resp_u = [o for o in self._read_output_lines() if o.get("id") == "req-s-2"][0]
        assert resp_u["status"] == "ok"
        assert resp_u["data"]["value"] == "NewBridgeAlias"

        # 3. Get history
        msg_h = json.dumps({"id": "req-s-3", "cmd": "get_transfer_history", "params": {}})
        self.bridge.handle_line(msg_h)
        resp_h = [o for o in self._read_output_lines() if o.get("id") == "req-s-3"][0]
        assert resp_h["status"] == "ok"
        assert isinstance(resp_h["data"]["history"], list)

    def test_broadcast_ipc_commands(self):
        self.bridge.coordinator.transmit = lambda *args, **kwargs: None

        msg_b = json.dumps({
            "id": "req-bcast-1",
            "cmd": "send_broadcast",
            "params": {
                "file_name": "bcast.txt",
                "payload_text": "Meeting at noon",
                "targets": ["NodeX", "NodeY"],
            }
        })
        self.bridge.handle_line(msg_b)
        resp_b = [o for o in self._read_output_lines() if o.get("id") == "req-bcast-1"][0]
        assert resp_b["status"] == "ok"
        session_id = resp_b["data"]["session_id"]
        assert session_id > 0
        assert resp_b["data"]["targets"] == ["NodeX", "NodeY"]


