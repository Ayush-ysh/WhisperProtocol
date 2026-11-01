"""Frame encoding and decoding for WhisperProtocol."""

from dataclasses import dataclass
from typing import Optional

from .constants import (
    PREAMBLE_PATTERN,
    SYNC_PATTERN,
    LENGTH_FIELD_BITS,
    CHECKSUM_BITS,
)
from .bitstream import string_to_bits, bits_to_string, bytes_to_bits, bits_to_bytes, BitstreamError
from .checksum import add_checksum, strip_and_verify, ChecksumError


class FrameError(Exception):
    """Raised when frame operations fail."""

    pass


# Precomputed bit patterns
PREAMBLE_BITS: list[int] = string_to_bits(PREAMBLE_PATTERN)
SYNC_BITS: list[int] = string_to_bits(SYNC_PATTERN)

PREAMBLE_LENGTH: int = len(PREAMBLE_BITS)
SYNC_LENGTH: int = len(SYNC_BITS)
HEADER_LENGTH: int = PREAMBLE_LENGTH + SYNC_LENGTH + LENGTH_FIELD_BITS


@dataclass(frozen=True)
class Frame:
    """Decoded frame structure."""

    preamble: list[int]
    sync: list[int]
    payload_length: int
    payload: bytes
    checksum: list[int]
    valid: bool

    def __str__(self) -> str:
        return (
            f"Frame(payload_len={self.payload_length}, "
            f"valid={self.valid}, "
            f"total_bits={PREAMBLE_LENGTH + SYNC_LENGTH + LENGTH_FIELD_BITS + len(self.payload) * 8 + CHECKSUM_BITS})"
        )


def encode_length(length: int) -> list[int]:
    """
    Encode payload length as 16-bit big-endian.

    Args:
        length: Payload length in bytes

    Returns:
        16 bits representing length
    """
    if not 0 <= length <= 0xFFFF:
        raise FrameError(f"Length {length} exceeds 16-bit limit")
    bits = []
    for i in range(15, -1, -1):
        bits.append((length >> i) & 1)
    return bits


def decode_length(bits: list[int]) -> int:
    """
    Decode 16-bit big-endian length.

    Args:
        bits: 16 bits

    Returns:
        Decoded length
    """
    if len(bits) != 16:
        raise FrameError(f"Expected 16 bits for length, got {len(bits)}")
    length = 0
    for bit in bits:
        length = (length << 1) | bit
    return length


def encode_frame(payload: bytes) -> list[int]:
    """
    Encode payload into complete frame.

    Frame structure:
    PREAMBLE (32 bits) + SYNC (16 bits) + LENGTH (16 bits) + PAYLOAD (8*len bits) + CHECKSUM (16 bits)

    Args:
        payload: Payload bytes

    Returns:
        Complete frame as list of bits
    """
    if not isinstance(payload, bytes):
        raise FrameError(f"Expected bytes, got {type(payload).__name__}")

    length_bits = encode_length(len(payload))
    payload_bits = bytes_to_bits(payload)

    # Build frame without checksum first
    frame_bits = PREAMBLE_BITS + SYNC_BITS + length_bits + payload_bits

    # Add CRC-16 checksum over everything except preamble and sync
    checksummed_bits = frame_bits[PREAMBLE_LENGTH + SYNC_LENGTH :]
    frame_with_checksum = add_checksum(checksummed_bits)

    # Reconstruct with preamble and sync
    return PREAMBLE_BITS + SYNC_BITS + frame_with_checksum


def decode_frame(bits: list[int]) -> Frame:
    """
    Decode frame from bit list.

    Args:
        bits: Complete frame bits

    Returns:
        Decoded Frame object
    """
    min_length = PREAMBLE_LENGTH + SYNC_LENGTH + LENGTH_FIELD_BITS + CHECKSUM_BITS
    if len(bits) < min_length:
        raise FrameError(f"Frame too short: {len(bits)} bits, minimum {min_length}")

    # Extract preamble
    preamble = bits[:PREAMBLE_LENGTH]
    if preamble != PREAMBLE_BITS:
        raise FrameError("Preamble mismatch")

    # Extract sync
    sync_start = PREAMBLE_LENGTH
    sync = bits[sync_start : sync_start + SYNC_LENGTH]
    if sync != SYNC_BITS:
        raise FrameError("Sync pattern mismatch")

    # Extract length
    length_start = sync_start + SYNC_LENGTH
    length_bits = bits[length_start : length_start + LENGTH_FIELD_BITS]
    payload_length = decode_length(length_bits)

    # Extract payload
    payload_start = length_start + LENGTH_FIELD_BITS
    payload_bit_count = payload_length * 8
    payload_end = payload_start + payload_bit_count

    if len(bits) < payload_end + CHECKSUM_BITS:
        raise FrameError(f"Frame truncated: expected {payload_end + CHECKSUM_BITS} bits, got {len(bits)}")

    payload_bits = bits[payload_start:payload_end]

    # Extract checksum
    checksum_start = payload_end
    checksum_bits = bits[checksum_start : checksum_start + CHECKSUM_BITS]

    # Verify checksum over length + payload
    checksummed = length_bits + payload_bits
    valid = False
    try:
        _, valid = strip_and_verify(checksummed + checksum_bits)
    except ChecksumError:
        valid = False

    # Decode payload
    try:
        payload = bits_to_bytes(payload_bits)
    except BitstreamError as e:
        raise FrameError(f"Invalid payload bits: {e}")

    return Frame(
        preamble=preamble,
        sync=sync,
        payload_length=payload_length,
        payload=payload,
        checksum=checksum_bits,
        valid=valid,
    )


def frame_to_string(frame_bits: list[int]) -> str:
    """Convert frame bits to readable string."""
    return bits_to_string(frame_bits)


def get_frame_info(payload: bytes) -> dict:
    """Get information about frame that would be generated."""
    frame_bits = encode_frame(payload)
    return {
        "payload_bytes": len(payload),
        "payload_bits": len(payload) * 8,
        "preamble_bits": PREAMBLE_LENGTH,
        "sync_bits": SYNC_LENGTH,
        "length_bits": LENGTH_FIELD_BITS,
        "checksum_bits": CHECKSUM_BITS,
        "total_bits": len(frame_bits),
        "total_symbols": len(frame_bits),
        "estimated_duration_ms": len(frame_bits) * 20,  # at 20ms per symbol
    }