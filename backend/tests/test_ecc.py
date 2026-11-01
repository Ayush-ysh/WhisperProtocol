"""Unit tests for WhisperProtocol Reed-Solomon Error Correction Codec."""

import pytest
from whisper.protocol.ecc import rs_encode, rs_decode, ECCUncorrectableError


class TestReedSolomonECC:
    """Tests for Reed-Solomon forward error correction."""

    @pytest.mark.parametrize("n_ecc", [8, 16, 32])
    def test_clean_roundtrip(self, n_ecc):
        original = b"CONFIDENTIAL_WHISPER_PAYLOAD_TEST_12345"
        encoded = rs_encode(original, n_ecc_symbols=n_ecc)

        assert len(encoded) == len(original) + n_ecc
        decoded, corrected = rs_decode(encoded, n_ecc_symbols=n_ecc)

        assert decoded == original
        assert corrected == 0

    def test_single_symbol_correction(self):
        original = b"WHISPER_ACOUSTIC_TRANSMISSION"
        encoded = bytearray(rs_encode(original, n_ecc_symbols=8))

        # Corrupt 1 byte
        encoded[5] ^= 0xFF

        decoded, corrected = rs_decode(bytes(encoded), n_ecc_symbols=8)
        assert decoded == original
        assert corrected == 1

    def test_max_capacity_correction_8_symbols(self):
        # 8 parity symbols can correct up to 4 byte errors
        original = b"RESILIENT_ERROR_CORRECTION_PAYLOAD_DATA"
        encoded = bytearray(rs_encode(original, n_ecc_symbols=8))

        # Corrupt 4 distinct bytes
        for idx in [2, 7, 12, 19]:
            encoded[idx] ^= 0xAA

        decoded, corrected = rs_decode(bytes(encoded), n_ecc_symbols=8)
        assert decoded == original
        assert corrected == 4

    def test_max_capacity_correction_16_symbols(self):
        # 16 parity symbols can correct up to 8 byte errors
        original = b"THIS_IS_A_ROBUST_WHISPER_PACKET_FOR_AIR_GAP"
        encoded = bytearray(rs_encode(original, n_ecc_symbols=16))

        # Corrupt 8 distinct bytes
        for idx in [1, 4, 8, 12, 16, 20, 24, 28]:
            encoded[idx] ^= 0x55

        decoded, corrected = rs_decode(bytes(encoded), n_ecc_symbols=16)
        assert decoded == original
        assert corrected == 8

    def test_uncorrectable_error_raises_exception(self):
        # 8 parity symbols can only correct 4 errors. Corrupt 5 errors!
        original = b"TEST_PAYLOAD_WITH_EXCESSIVE_CORRUPTION"
        encoded = bytearray(rs_encode(original, n_ecc_symbols=8))

        for idx in [2, 5, 8, 11, 14]:
            encoded[idx] ^= 0xFF

        with pytest.raises(ECCUncorrectableError):
            rs_decode(bytes(encoded), n_ecc_symbols=8)

    def test_empty_payload(self):
        encoded = rs_encode(b"", n_ecc_symbols=8)
        assert encoded == b""
        decoded, corrected = rs_decode(b"", n_ecc_symbols=8)
        assert decoded == b""
        assert corrected == 0

    def test_invalid_ecc_length(self):
        with pytest.raises(ValueError):
            rs_encode(b"test", n_ecc_symbols=1)  # Minimum is 2
        with pytest.raises(ValueError):
            rs_encode(b"test", n_ecc_symbols=128)  # Max is 64
