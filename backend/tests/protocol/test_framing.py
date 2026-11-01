"""Unit tests for WhisperProtocol framing."""

import pytest

from whisper.protocol import (
    encode_frame,
    decode_frame,
    encode_length,
    decode_length,
    Frame,
    FrameError,
    get_frame_info,
    PREAMBLE_LENGTH,
    SYNC_LENGTH,
    LENGTH_FIELD_BITS,
    CHECKSUM_BITS,
)


class TestLengthEncoding:
    """Tests for length field encoding/decoding."""

    def test_encode_decode_zero(self):
        """Test zero length."""
        bits = encode_length(0)
        assert bits == [0] * 16
        assert decode_length(bits) == 0

    def test_encode_decode_max(self):
        """Test max length (65535)."""
        bits = encode_length(0xFFFF)
        assert bits == [1] * 16
        assert decode_length(bits) == 0xFFFF

    def test_encode_decode_roundtrip(self):
        """Test round-trip for various lengths."""
        for length in [0, 1, 10, 100, 1000, 65535]:
            bits = encode_length(length)
            assert decode_length(bits) == length

    def test_encode_invalid_length(self):
        """Test encoding invalid length."""
        with pytest.raises(FrameError):
            encode_length(-1)
        with pytest.raises(FrameError):
            encode_length(0x10000)


class TestFrameEncoding:
    """Tests for frame encoding."""

    def test_encode_empty_payload(self):
        """Test encoding empty payload."""
        frame_bits = encode_frame(b'')
        expected_min = PREAMBLE_LENGTH + SYNC_LENGTH + LENGTH_FIELD_BITS + CHECKSUM_BITS
        assert len(frame_bits) == expected_min
        # Verify preamble
        assert frame_bits[:PREAMBLE_LENGTH] == [1, 0] * 16
        # Verify sync
        assert frame_bits[PREAMBLE_LENGTH:PREAMBLE_LENGTH+SYNC_LENGTH] == [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0]

    def test_encode_single_byte(self):
        """Test encoding single byte payload."""
        frame_bits = encode_frame(b'A')
        # Preamble(32) + Sync(16) + Length(16) + Payload(8) + Checksum(16) = 88 bits
        assert len(frame_bits) == 88

    def test_encode_hello(self):
        """Test encoding 'HELLO'."""
        frame_bits = encode_frame(b'HELLO')
        # 5 bytes = 40 bits payload
        # Total: 32 + 16 + 16 + 40 + 16 = 120 bits
        assert len(frame_bits) == 120

    def test_encode_large_payload(self):
        """Test encoding larger payload."""
        payload = b'X' * 1000
        frame_bits = encode_frame(payload)
        expected = PREAMBLE_LENGTH + SYNC_LENGTH + LENGTH_FIELD_BITS + 8000 + CHECKSUM_BITS
        assert len(frame_bits) == expected


class TestFrameDecoding:
    """Tests for frame decoding."""

    def test_decode_valid_frame(self):
        """Test decoding valid frame."""
        payload = b'HELLO WORLD'
        frame_bits = encode_frame(payload)
        frame = decode_frame(frame_bits)
        assert frame.payload == payload
        assert frame.payload_length == len(payload)
        assert frame.valid is True

    def test_decode_empty_payload(self):
        """Test decoding empty payload."""
        frame_bits = encode_frame(b'')
        frame = decode_frame(frame_bits)
        assert frame.payload == b''
        assert frame.payload_length == 0
        assert frame.valid is True

    def test_decode_invalid_preamble(self):
        """Test decoding frame with invalid preamble."""
        payload = b'TEST'
        frame_bits = encode_frame(payload)
        # Corrupt preamble
        frame_bits[0] ^= 1
        with pytest.raises(FrameError):
            decode_frame(frame_bits)

    def test_decode_invalid_sync(self):
        """Test decoding frame with invalid sync."""
        payload = b'TEST'
        frame_bits = encode_frame(payload)
        # Corrupt sync
        frame_bits[PREAMBLE_LENGTH] ^= 1
        with pytest.raises(FrameError):
            decode_frame(frame_bits)

    def test_decode_truncated_frame(self):
        """Test decoding truncated frame."""
        payload = b'TEST'
        frame_bits = encode_frame(payload)
        # Truncate
        truncated = frame_bits[:-5]
        with pytest.raises(FrameError):
            decode_frame(truncated)

    def test_decode_corrupted_checksum(self):
        """Test decoding frame with corrupted checksum."""
        payload = b'TEST'
        frame_bits = encode_frame(payload)
        # Corrupt checksum (last 16 bits)
        frame_bits[-1] ^= 1
        frame = decode_frame(frame_bits)
        assert frame.valid is False
        # But payload should still be decoded
        assert frame.payload == payload


class TestFrameInfo:
    """Tests for frame info utility."""

    def test_get_frame_info(self):
        """Test get_frame_info."""
        info = get_frame_info(b'HELLO')
        assert info['payload_bytes'] == 5
        assert info['payload_bits'] == 40
        assert info['total_bits'] == 120
        assert info['total_symbols'] == 120