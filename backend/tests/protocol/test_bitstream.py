"""Unit tests for WhisperProtocol bitstream utilities."""

import pytest

from whisper.protocol import (
    bytes_to_bits,
    bits_to_bytes,
    bits_to_string,
    string_to_bits,
    BitstreamError,
    round_trip_test,
)


class TestBytesToBits:
    """Tests for bytes_to_bits conversion."""

    def test_single_byte(self):
        """Test conversion of single byte."""
        # 0x41 = 'A' = 01000001
        bits = bytes_to_bits(b'A')
        assert bits == [0, 1, 0, 0, 0, 0, 0, 1]

    def test_zero_byte(self):
        """Test zero byte."""
        bits = bytes_to_bits(b'\x00')
        assert bits == [0, 0, 0, 0, 0, 0, 0, 0]

    def test_max_byte(self):
        """Test 0xFF byte."""
        bits = bytes_to_bits(b'\xFF')
        assert bits == [1, 1, 1, 1, 1, 1, 1, 1]

    def test_multiple_bytes(self):
        """Test multiple bytes."""
        # "AB" = 0x41 0x42
        bits = bytes_to_bits(b'AB')
        expected = [0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0]
        assert bits == expected

    def test_empty_bytes(self):
        """Test empty bytes."""
        bits = bytes_to_bits(b'')
        assert bits == []

    def test_hello(self):
        """Test 'HELLO' encoding."""
        bits = bytes_to_bits(b'HELLO')
        # H=0x48, E=0x45, L=0x4C, L=0x4C, O=0x4F
        assert len(bits) == 40


class TestBitsToBytes:
    """Tests for bits_to_bytes conversion."""

    def test_round_trip(self):
        """Test round-trip bytes -> bits -> bytes."""
        test_data = [b'', b'A', b'Hello', b'Test\x00\xFF', bytes(range(256))]
        for data in test_data:
            bits = bytes_to_bits(data)
            recovered = bits_to_bytes(bits)
            assert recovered == data, f"Round-trip failed for {data}"

    def test_invalid_bit_value(self):
        """Test that invalid bit values raise error."""
        with pytest.raises(BitstreamError):
            bits_to_bytes([0, 1, 2, 0])

    def test_invalid_bit_value_negative(self):
        """Test that negative bit values raise error."""
        with pytest.raises(BitstreamError):
            bits_to_bytes([0, 1, -1, 0])

    def test_length_not_multiple_of_8(self):
        """Test that non-multiple-of-8 length raises error."""
        with pytest.raises(BitstreamError):
            bits_to_bytes([0, 1, 0, 1, 0])


class TestBitsToString:
    """Tests for bit string conversion."""

    def test_bits_to_string(self):
        """Test bits to string."""
        bits = [0, 1, 0, 1, 1, 0]
        assert bits_to_string(bits) == "010110"

    def test_string_to_bits(self):
        """Test string to bits."""
        bits = string_to_bits("010110")
        assert bits == [0, 1, 0, 1, 1, 0]

    def test_string_to_bits_invalid(self):
        """Test invalid string raises error."""
        with pytest.raises(BitstreamError):
            string_to_bits("010120")


class TestRoundTrip:
    """Tests for round-trip validation."""

    def test_round_trip_test(self):
        """Test round_trip_test function."""
        assert round_trip_test(b'HELLO') is True
        assert round_trip_test(b'') is True
        assert round_trip_test(bytes(range(256))) is True