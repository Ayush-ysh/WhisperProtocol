"""Bitstream conversion utilities for WhisperProtocol."""

from typing import Iterator


class BitstreamError(Exception):
    """Raised when bitstream operations fail."""

    pass


def bytes_to_bits(data: bytes) -> list[int]:
    """
    Convert bytes to list of bits (MSB first).

    Args:
        data: Input bytes

    Returns:
        List of bits (0 or 1), 8 bits per byte, MSB first

    Example:
        >>> bytes_to_bits(b'A')  # 0x41 = 01000001
        [0, 1, 0, 0, 0, 0, 0, 1]
    """
    if not isinstance(data, bytes):
        raise BitstreamError(f"Expected bytes, got {type(data).__name__}")

    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def bits_to_bytes(bits: list[int]) -> bytes:
    """
    Convert list of bits to bytes (MSB first).

    Args:
        bits: List of bits (0 or 1), length must be multiple of 8

    Returns:
        Reconstructed bytes

    Raises:
        BitstreamError: If bit values are invalid or length not multiple of 8
    """
    if len(bits) % 8 != 0:
        raise BitstreamError(f"Bit length {len(bits)} not multiple of 8")

    for bit in bits:
        if bit not in (0, 1):
            raise BitstreamError(f"Invalid bit value: {bit}. Must be 0 or 1.")

    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)


def bits_to_string(bits: list[int]) -> str:
    """Convert bits to string representation."""
    return "".join(str(b) for b in bits)


def string_to_bits(s: str) -> list[int]:
    """Convert string of '0' and '1' to list of ints."""
    if not all(c in "01" for c in s):
        raise BitstreamError(f"Invalid bit string: {s}")
    return [int(c) for c in s]


def chunks(data: list[int], size: int) -> Iterator[list[int]]:
    """Yield successive chunks of given size from data."""
    for i in range(0, len(data), size):
        yield data[i : i + size]


def validate_bits(bits: list[int]) -> None:
    """Validate that all values are 0 or 1."""
    for i, bit in enumerate(bits):
        if bit not in (0, 1):
            raise BitstreamError(f"Invalid bit at index {i}: {bit}")


def round_trip_test(data: bytes) -> bool:
    """Test that bytes -> bits -> bytes preserves data."""
    bits = bytes_to_bits(data)
    recovered = bits_to_bytes(bits)
    return recovered == data