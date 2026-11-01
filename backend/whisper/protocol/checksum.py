"""CRC-16 checksum for WhisperProtocol frames."""

import binascii
from typing import Union

from .bitstream import bytes_to_bits, bits_to_bytes, BitstreamError


class ChecksumError(Exception):
    """Raised when checksum operations fail."""

    pass


# CRC-16-CCITT (polynomial 0x1021)
CRC16_POLYNOMIAL: int = 0x1021
CRC16_INIT: int = 0xFFFF


def compute_crc16(data: bytes) -> int:
    """
    Compute CRC-16-CCITT checksum.

    Args:
        data: Input bytes

    Returns:
        16-bit CRC value
    """
    return binascii.crc_hqx(data, CRC16_INIT) & 0xFFFF


def compute_crc16_from_bits(bits: list[int]) -> int:
    """
    Compute CRC-16 from bit list.

    Args:
        bits: List of bits (0 or 1)

    Returns:
        16-bit CRC value
    """
    data = bits_to_bytes(bits)
    return compute_crc16(data)


def crc16_to_bits(crc: int) -> list[int]:
    """
    Convert 16-bit CRC to 16 bits (MSB first).

    Args:
        crc: 16-bit integer

    Returns:
        List of 16 bits
    """
    if not 0 <= crc <= 0xFFFF:
        raise ChecksumError(f"CRC value out of range: {crc}")

    bits = []
    for i in range(15, -1, -1):
        bits.append((crc >> i) & 1)
    return bits


def bits_to_crc16(bits: list[int]) -> int:
    """
    Convert 16 bits to CRC value.

    Args:
        bits: List of 16 bits (MSB first)

    Returns:
        16-bit CRC value
    """
    if len(bits) != 16:
        raise ChecksumError(f"Expected 16 bits for CRC, got {len(bits)}")

    crc = 0
    for bit in bits:
        crc = (crc << 1) | bit
    return crc


def verify_checksum(payload_bits: list[int], checksum_bits: list[int]) -> bool:
    """
    Verify checksum against payload.

    Args:
        payload_bits: Payload bits (without checksum)
        checksum_bits: 16-bit checksum

    Returns:
        True if checksum matches
    """
    expected = compute_crc16_from_bits(payload_bits)
    actual = bits_to_crc16(checksum_bits)
    return expected == actual


def add_checksum(payload_bits: list[int]) -> list[int]:
    """
    Append CRC-16 checksum to payload bits.

    Args:
        payload_bits: Payload bits

    Returns:
        Payload bits with checksum appended
    """
    crc = compute_crc16_from_bits(payload_bits)
    checksum_bits = crc16_to_bits(crc)
    return payload_bits + checksum_bits


def strip_and_verify(frame_bits: list[int]) -> tuple[list[int], bool]:
    """
    Strip checksum from frame and verify.

    Args:
        frame_bits: Complete frame bits including checksum

    Returns:
        Tuple of (payload_bits, valid)
    """
    if len(frame_bits) < 16:
        raise ChecksumError(f"Frame too short for checksum: {len(frame_bits)} bits")

    payload_bits = frame_bits[:-16]
    checksum_bits = frame_bits[-16:]
    valid = verify_checksum(payload_bits, checksum_bits)
    return payload_bits, valid