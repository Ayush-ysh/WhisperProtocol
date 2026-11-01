"""Comprehensive unit tests for Canonical Protocol Framing (Milestone C)."""

import pytest

from whisper.protocol.frames import (
    FrameType,
    ProtocolFrame,
    ProtocolFrameError,
    InvalidFrameTypeError,
    FrameTruncatedError,
    ChecksumMismatchError,
    encode_protocol_frame,
    decode_protocol_frame,
    create_discovery_ping,
    create_discovery_response,
    create_transfer_offer,
    create_transfer_accept,
    create_transfer_decline,
    create_data_frame,
    create_transfer_ack,
    create_transfer_error,
    FrameSequenceTracker,
    MAX_PAYLOAD_BYTES,
)


class TestCanonicalProtocolFraming:
    """Tests for canonical 8-type frame serialization and deserialization."""

    @pytest.mark.parametrize("frame_type", list(FrameType))
    def test_all_eight_frame_types_roundtrip(self, frame_type):
        frame = ProtocolFrame(
            frame_type=frame_type,
            session_id=0xAABBCCDD,
            seq_num=42,
            payload=f"PAYLOAD_FOR_{frame_type.name}".encode("utf-8"),
        )

        bits = encode_protocol_frame(frame)
        assert isinstance(bits, list)
        assert all(b in (0, 1) for b in bits)

        decoded = decode_protocol_frame(bits)
        assert decoded.frame_type == frame_type
        assert decoded.session_id == 0xAABBCCDD
        assert decoded.seq_num == 42
        assert decoded.payload == f"PAYLOAD_FOR_{frame_type.name}".encode("utf-8")
        assert decoded.valid is True

    def test_empty_payload_frame_roundtrip(self):
        ack = create_transfer_ack(session_id=0x12345678, seq_num=101)
        bits = encode_protocol_frame(ack)
        decoded = decode_protocol_frame(bits)

        assert decoded.frame_type == FrameType.TRANSFER_ACK
        assert decoded.session_id == 0x12345678
        assert decoded.seq_num == 101
        assert decoded.payload == b""

    def test_discovery_ping_and_response_builders(self):
        ping = create_discovery_ping(alias="Alice-MacBook", session_id=0x01)
        decoded_ping = decode_protocol_frame(encode_protocol_frame(ping))
        assert decoded_ping.frame_type == FrameType.DISCOVERY_PING
        assert decoded_ping.payload == b"Alice-MacBook"

        resp = create_discovery_response(alias="Bob-ThinkPad", session_id=0x01)
        decoded_resp = decode_protocol_frame(encode_protocol_frame(resp))
        assert decoded_resp.frame_type == FrameType.DISCOVERY_RESPONSE
        assert decoded_resp.payload == b"Bob-ThinkPad"

    def test_transfer_offer_and_accept_builders(self):
        pubkey = b"\x01" * 32
        offer = create_transfer_offer(
            file_name="secret.txt",
            file_size=2048,
            session_id=0x9999,
            public_key=pubkey,
        )
        decoded_offer = decode_protocol_frame(encode_protocol_frame(offer))
        assert decoded_offer.frame_type == FrameType.TRANSFER_OFFER

        accept = create_transfer_accept(session_id=0x9999, public_key=pubkey)
        decoded_accept = decode_protocol_frame(encode_protocol_frame(accept))
        assert decoded_accept.frame_type == FrameType.TRANSFER_ACCEPT
        assert decoded_accept.payload == pubkey

    def test_transfer_error_builder(self):
        err_frame = create_transfer_error(session_id=0x5555, error_code=404, message="FILE_NOT_FOUND")
        decoded_err = decode_protocol_frame(encode_protocol_frame(err_frame))
        assert decoded_err.frame_type == FrameType.TRANSFER_ERROR
        assert b"FILE_NOT_FOUND" in decoded_err.payload

    def test_truncated_frame_rejection(self):
        frame = create_data_frame(session_id=1, seq_num=0, data=b"LARGE_DATA_PAYLOAD_BYTES")
        bits = encode_protocol_frame(frame)

        # Truncate 32 bits from the end
        truncated_bits = bits[:-32]

        with pytest.raises(FrameTruncatedError):
            decode_protocol_frame(truncated_bits)

    def test_crc_tampering_rejection(self):
        frame = create_data_frame(session_id=1, seq_num=0, data=b"AUTHENTIC_DATA")
        bits = encode_protocol_frame(frame)

        # Flip one bit in the payload area
        tampered_bits = list(bits)
        tampered_bits[-25] ^= 1  # inside payload/CRC

        with pytest.raises((ChecksumMismatchError, FrameTruncatedError)):
            decode_protocol_frame(tampered_bits)

    def test_excessive_payload_size_rejection(self):
        oversized = b"X" * (MAX_PAYLOAD_BYTES + 1)
        frame = ProtocolFrame(
            frame_type=FrameType.DATA_FRAME,
            session_id=1,
            seq_num=0,
            payload=oversized,
        )

        with pytest.raises(ProtocolFrameError):
            encode_protocol_frame(frame)

    def test_preamble_and_sync_error_tolerance(self):
        frame = create_transfer_ack(session_id=10, seq_num=1)
        bits = encode_protocol_frame(frame)

        # Corrupt 2 bits in preamble (within tolerance)
        bits[0] ^= 1
        bits[2] ^= 1

        # Corrupt 1 bit in sync (within tolerance)
        bits[32] ^= 1

        decoded = decode_protocol_frame(bits, max_preamble_errors=2, max_sync_errors=1)
        assert decoded.frame_type == FrameType.TRANSFER_ACK
        assert decoded.session_id == 10

    def test_excessive_sync_error_rejection(self):
        frame = create_transfer_ack(session_id=10, seq_num=1)
        bits = encode_protocol_frame(frame)

        # Corrupt 3 bits in sync (exceeds max_sync_errors=1)
        bits[32] ^= 1
        bits[33] ^= 1
        bits[34] ^= 1

        with pytest.raises(ProtocolFrameError):
            decode_protocol_frame(bits, max_preamble_errors=2, max_sync_errors=1)


class TestFrameSequenceTracker:
    """Tests for sequence number tracking, duplicate detection, and ordering."""

    def test_in_order_frames(self):
        tracker = FrameSequenceTracker(session_id=0x100)

        f0 = create_data_frame(session_id=0x100, seq_num=0, data=b"P0")
        f1 = create_data_frame(session_id=0x100, seq_num=1, data=b"P1")
        f2 = create_data_frame(session_id=0x100, seq_num=2, data=b"P2")

        assert tracker.process_frame(f0)["status"] == "valid"
        assert tracker.process_frame(f1)["status"] == "valid"
        assert tracker.process_frame(f2)["status"] == "valid"

    def test_duplicate_frame_detection(self):
        tracker = FrameSequenceTracker(session_id=0x200)

        f0 = create_data_frame(session_id=0x200, seq_num=0, data=b"P0")
        assert tracker.process_frame(f0)["status"] == "valid"

        # Duplicate submission of frame 0
        dup_res = tracker.process_frame(f0)
        assert dup_res["status"] == "duplicate"
        assert dup_res["seq"] == 0

    def test_out_of_order_frame_detection(self):
        tracker = FrameSequenceTracker(session_id=0x300)

        # Jump straight to seq=5
        f5 = create_data_frame(session_id=0x300, seq_num=5, data=b"P5")
        res = tracker.process_frame(f5)

        assert res["status"] == "out_of_order"
        assert res["seq"] == 5
        assert res["expected"] == 0

    def test_wrong_session_rejection(self):
        tracker = FrameSequenceTracker(session_id=0x400)
        alien_frame = create_data_frame(session_id=0x999, seq_num=0, data=b"ALIEN")

        res = tracker.process_frame(alien_frame)
        assert res["status"] == "wrong_session"
