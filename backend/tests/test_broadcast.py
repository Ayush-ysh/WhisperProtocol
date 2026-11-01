"""Unit tests for Multi-Device Acoustic Broadcast Engine (Milestone F)."""

import pytest
from unittest.mock import MagicMock
from whisper.engine.broadcast import BroadcastEngine, ACK_SLOT_INTERVAL_SECONDS
from whisper.protocol.frames import create_transfer_ack, decode_protocol_frame


class MockBroadcastCoordinator:
    def __init__(self):
        self.transmitted = []
        self.is_listening = True

    def start_listening(self):
        self.is_listening = True

    def stop_listening(self):
        self.is_listening = False

    def transmit(self, waveform, sample_rate, output_device=None, blocking=True):
        self.transmitted.append(waveform)


class TestBroadcastEngine:
    def setup_method(self):
        self.coord = MockBroadcastCoordinator()
        self.events = []
        self.engine = BroadcastEngine(
            local_alias="BroadcasterNode",
            coordinator=self.coord,
            on_event=lambda ev, data: self.events.append((ev, data)),
        )

    def test_initiate_broadcast_allocates_slots(self):
        nodes = ["NodeA", "NodeB", "NodeC"]
        session_id = self.engine.initiate_broadcast(
            file_name="broadcast.bin",
            payload=b"Acoustic broadcast payload to 3 nodes",
            target_aliases=nodes,
            ecc_symbols=8,
        )

        assert session_id > 0
        ctx = self.engine._sessions[session_id]
        assert ctx.file_name == "broadcast.bin"
        assert len(ctx.nodes) == 3
        assert ctx.nodes["NodeA"].slot_index == 0
        assert ctx.nodes["NodeA"].slot_delay_seconds == 0.0
        assert ctx.nodes["NodeB"].slot_index == 1
        assert ctx.nodes["NodeB"].slot_delay_seconds == ACK_SLOT_INTERVAL_SECONDS
        assert ctx.nodes["NodeC"].slot_index == 2
        assert ctx.nodes["NodeC"].slot_delay_seconds == 2 * ACK_SLOT_INTERVAL_SECONDS
        assert ctx.state == "awaiting_acks"
        assert len(self.coord.transmitted) == 1

    def test_receiver_decryption_and_per_node_ack_matrix(self):
        nodes = ["NodeA", "NodeB"]
        session_id = self.engine.initiate_broadcast(
            file_name="announcement.txt",
            payload=b"Meeting at 14:00 offline",
            target_aliases=nodes,
        )

        ctx = self.engine._sessions[session_id]
        group_key = ctx.group_key

        # Simulate NodeA sending TRANSFER_ACK in slot 0
        from whisper.protocol.demodulator import FrameDecodeResult
        ack_frame_0 = create_transfer_ack(session_id=session_id, seq_num=0)
        res_0 = FrameDecodeResult(success=True, payload=b"", checksum_valid=True, protocol_frame=ack_frame_0)
        self.engine._on_frame_received(res_0)

        assert ctx.nodes["NodeA"].status == "ack_received"
        assert ctx.nodes["NodeB"].status == "pending"
        assert ctx.state == "awaiting_acks"

        # Simulate NodeB sending TRANSFER_ACK in slot 1
        ack_frame_1 = create_transfer_ack(session_id=session_id, seq_num=1)
        res_1 = FrameDecodeResult(success=True, payload=b"", checksum_valid=True, protocol_frame=ack_frame_1)
        self.engine._on_frame_received(res_1)

        assert ctx.nodes["NodeB"].status == "ack_received"
        assert ctx.state == "completed"
        status = self.engine.get_broadcast_status(session_id)
        assert status["delivery_count"] == 2
        assert status["total_nodes"] == 2
