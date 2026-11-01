"""Unit tests for WhisperProtocol checksum."""

import pytest

from whisper.protocol import (
    compute_crc16,
    compute_crc16_from_bits,
    crc16_to_bits,
    bits_to_crc16,
    verify_checksum,
    add_checksum,
    strip_and_verify,
    ChecksumError,
    bytes_to_bits,
)


class TestCRC16:
    """Tests for CRC-16 computation."""

    def test_known_values(self):
        """Test CRC-16 against known values from binascii.crc_hqx."""
        # binascii.crc_hqx uses CRC-16-CCITT variant with different bit ordering
        assert compute_crc16(b'') == 0xFFFF
        assert compute_crc16(b'123456789') == 0x29B1
        assert compute_crc16(b'A') == 0xB915
        assert compute_crc16(b'HELLO') == 0x49D6

    def test_crc16_from_bits(self):
        """Test CRC from bit list."""
        bits = [0, 1, 0, 0, 0, 0, 0, 1]  # 'A'
        crc = compute_crc16_from_bits(bits)
        assert crc == compute_crc16(b'A')

    def test_crc16_to_bits(self):
        """Test CRC to bits conversion."""
        crc = 0x1234
        bits = crc16_to_bits(crc)
        assert len(bits) == 16
        # MSB first: 0x12 = 00010010, 0x34 = 00110100
        assert bits[0] == 0   # bit 15
        assert bits[1] == 0   # bit 14
        assert bits[2] == 0   # bit 13
        assert bits[3] == 1   # bit 12
        assert bits[4] == 0   # bit 11
        assert bits[5] == 0   # bit 10
        assert bits[6] == 1   # bit 9
        assert bits[7] == 0   # bit 8
        assert bits[8] == 0   # bit 7
        assert bits[9] == 0   # bit 6
        assert bits[10] == 1  # bit 5
        assert bits[11] == 1  # bit 4
        assert bits[12] == 0  # bit 3
        assert bits[13] == 1  # bit 2
        assert bits[14] == 0  # bit 1
        assert bits[15] == 0  # bit 0

    def test_bits_to_crc16(self):
        """Test bits to CRC conversion."""
        crc = 0x1234
        bits = crc16_to_bits(crc)
        recovered = bits_to_crc16(bits)
        assert recovered == crc

    def test_bits_to_crc16_invalid_length(self):
        """Test bits_to_crc16 with wrong length."""
        with pytest.raises(ChecksumError):
            bits_to_crc16([0, 1, 0])  # Too short


class TestVerifyChecksum:
    """Tests for checksum verification."""

    def test_valid_checksum(self):
        """Test valid checksum verification."""
        payload = bytes_to_bits(b'HELLO')
        crc = compute_crc16_from_bits(payload)
        checksum_bits = crc16_to_bits(crc)
        assert verify_checksum(payload, checksum_bits) is True

    def test_invalid_checksum(self):
        """Test invalid checksum detection."""
        payload = bytes_to_bits(b'HELLO')
        # Corrupt one bit in checksum
        crc = compute_crc16_from_bits(payload)
        checksum_bits = crc16_to_bits(crc)
        checksum_bits[0] ^= 1  # Flip first bit
        assert verify_checksum(payload, checksum_bits) is False


class TestAddChecksum:
    """Tests for adding checksum to payload."""

    def test_add_checksum(self):
        """Test add_checksum function."""
        payload = bytes_to_bits(b'TEST')
        with_checksum = add_checksum(payload)
        # Should be payload + 16 bits
        assert len(with_checksum) == len(payload) + 16
        # Last 16 bits should be valid checksum
        assert verify_checksum(payload, with_checksum[-16:]) is True


class TestStripAndVerify:
    """Tests for stripping and verifying checksum."""

    def test_strip_and_verify_valid(self):
        """Test strip and verify with valid frame."""
        payload = bytes_to_bits(b'MESSAGE')
        with_checksum = add_checksum(payload)
        stripped, valid = strip_and_verify(with_checksum)
        assert valid is True
        assert stripped == payload

    def test_strip_and_verify_invalid(self):
        """Test strip and verify with corrupted frame."""
        payload = bytes_to_bits(b'MESSAGE')
        with_checksum = add_checksum(payload)
        # Corrupt payload
        corrupted = with_checksum.copy()
        corrupted[0] ^= 1
        stripped, valid = strip_and_verify(corrupted)
        assert valid is False

    def test_strip_and_verify_too_short(self):
        """Test strip and verify with too short frame."""
        with pytest.raises(ChecksumError):
            strip_and_verify([0, 1, 0, 1])