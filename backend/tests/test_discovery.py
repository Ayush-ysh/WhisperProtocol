"""Unit tests for WhisperProtocol Acoustic Discovery Engine (Milestone E)."""

import time
import pytest
from unittest.mock import MagicMock, patch

from whisper.engine.discovery import DiscoveryEngine, DiscoveredDevice, COLLISION_AVOIDANCE_SLOT_SECONDS
from whisper.protocol.frames import (
    create_discovery_ping,
    create_discovery_response,
    FrameType,
    ProtocolFrame,
)
from whisper.protocol.demodulator import FrameDecodeResult


class MockCoordinator:
    """Mock HalfDuplexAudioCoordinator for fast unit testing."""

    def __init__(self):
        self.transmitted_frames = []
        self.is_listening = False
        self.on_frame_received = None

    def start_listening(self):
        self.is_listening = True

    def stop_listening(self):
        self.is_listening = False

    def transmit(self, waveform, sample_rate, output_device=None, blocking=True):
        self.transmitted_frames.append(waveform)


class TestDiscoveryEngine:
    """Tests for DiscoveryEngine ping/response and collision avoidance."""

    def setup_method(self):
        self.mock_coord = MockCoordinator()
        self.engine = DiscoveryEngine(
            local_alias="AliceNode",
            coordinator=self.mock_coord,
        )

    def test_receiver_mode_toggle(self):
        assert self.engine.is_receiver_mode is False
        assert self.mock_coord.is_listening is False

        # Enable
        active = self.engine.set_receiver_mode(True, alias="AliceReceiver")
        assert active is True
        assert self.engine.is_receiver_mode is True
        assert self.engine.local_alias == "AliceReceiver"
        assert self.mock_coord.is_listening is True

        # Disable
        active = self.engine.set_receiver_mode(False)
        assert active is False
        assert self.engine.is_receiver_mode is False
        assert self.mock_coord.is_listening is False

    def test_start_and_stop_discovery(self):
        self.engine.start_discovery(alias="AliceScanner")
        assert self.engine.is_discovering is True
        assert self.mock_coord.is_listening is True
        assert len(self.mock_coord.transmitted_frames) == 1  # Broadcasted DISCOVERY_PING

        self.engine.stop_discovery()
        assert self.engine.is_discovering is False
        assert self.mock_coord.is_listening is False

    def test_ping_triggers_collision_avoidance_reply(self):
        self.engine.set_receiver_mode(True, alias="BobNode")

        # Mock random.choice to select slot 0 (0 delay) for deterministic test
        with patch("random.choice", return_value=0):
            ping_frame = create_discovery_ping(alias="AliceNode", session_id=0x12345678)
            decode_result = FrameDecodeResult(
                success=True,
                payload=ping_frame.payload,
                checksum_valid=True,
                protocol_frame=ping_frame,
            )

            # Route incoming ping frame to discovery engine
            self.engine._on_frame_received(decode_result)
            time.sleep(0.05)  # Allow worker thread to fire

            assert len(self.mock_coord.transmitted_frames) == 1

    def test_self_ping_ignored(self):
        self.engine.set_receiver_mode(True, alias="AliceNode")
        self.mock_coord.transmitted_frames.clear()

        # Ping from self
        ping_frame = create_discovery_ping(alias="AliceNode", session_id=0x99)
        decode_result = FrameDecodeResult(
            success=True,
            payload=ping_frame.payload,
            checksum_valid=True,
            protocol_frame=ping_frame,
        )

        self.engine._on_frame_received(decode_result)
        time.sleep(0.02)

        # Must NOT trigger reply
        assert len(self.mock_coord.transmitted_frames) == 0

    def test_discovery_response_registers_device(self):
        discovered_list = []
        self.engine.on_device_discovered = lambda dev: discovered_list.append(dev)

        resp_frame = create_discovery_response(alias="CharlieNode", session_id=0xABCDEF)
        decode_result = FrameDecodeResult(
            success=True,
            payload=resp_frame.payload,
            checksum_valid=True,
            protocol_frame=resp_frame,
        )

        self.engine._on_frame_received(decode_result)

        devices = self.engine.get_discovered_devices()
        assert len(devices) == 1
        assert devices[0]["alias"] == "CharlieNode"
        assert devices[0]["session_id"] == 0xABCDEF
        assert len(discovered_list) == 1
        assert discovered_list[0].alias == "CharlieNode"
