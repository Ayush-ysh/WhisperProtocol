"""Canonical Protocol Framing for WhisperProtocol.

Frame Structure:
+------------------------------------------------------------------------------------------------+
| PREAMBLE | SYNC   | VERSION | FRAME_TYPE | SESSION_ID | SEQ_NUM | PAYLOAD_LEN | PAYLOAD | CRC16 |
| 32 bits  | 16 bits| 8 bits  | 8 bits     | 32 bits    | 16 bits | 16 bits     | N bytes | 16 bits|
+------------------------------------------------------------------------------------------------+

CRC-16 protects: VERSION + FRAME_TYPE + SESSION_ID + SEQ_NUM + PAYLOAD_LEN + PAYLOAD.
"""

from enum import IntEnum
import struct
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .constants import (
    PREAMBLE_BITS,
    SYNC_BITS,
    PREAMBLE_LENGTH,
    SYNC_LENGTH,
)
from .bitstream import bytes_to_bits, bits_to_bytes, BitstreamError
from .checksum import compute_crc16

PROTOCOL_VERSION: int = 1
MAX_PAYLOAD_BYTES: int = 4096

# Header size in bytes: VERSION(1) + FRAME_TYPE(1) + SESSION_ID(4) + SEQ_NUM(2) + PAYLOAD_LEN(2)
HEADER_BYTES_COUNT: int = 1 + 1 + 4 + 2 + 2  # 10 bytes = 80 bits
CRC_BYTES_COUNT: int = 2  # 16 bits
MIN_FRAME_BITS: int = PREAMBLE_LENGTH + SYNC_LENGTH + (HEADER_BYTES_COUNT + CRC_BYTES_COUNT) * 8


class FrameType(IntEnum):
    """Canonical frame types."""
    DISCOVERY_PING = 0x01
    DISCOVERY_RESPONSE = 0x02
    TRANSFER_OFFER = 0x03
    TRANSFER_ACCEPT = 0x04
    TRANSFER_DECLINE = 0x05
    DATA_FRAME = 0x06
    TRANSFER_ACK = 0x07
    TRANSFER_ERROR = 0x08


class ProtocolFrameError(Exception):
    """Base exception for protocol frame errors."""
    pass


class InvalidFrameTypeError(ProtocolFrameError):
    """Raised when an unknown or invalid frame type is encountered."""
    pass


class FrameTruncatedError(ProtocolFrameError):
    """Raised when frame bits are truncated or payload length exceeds received bits."""
    pass


class ChecksumMismatchError(ProtocolFrameError):
    """Raised when the calculated CRC-16 does not match the received CRC."""
    pass


@dataclass(frozen=True)
class ProtocolFrame:
    """Canonical WhisperProtocol frame."""
    frame_type: FrameType
    session_id: int
    seq_num: int = 0
    payload: bytes = b""
    version: int = PROTOCOL_VERSION
    valid: bool = True

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    def __str__(self) -> str:
        return (
            f"ProtocolFrame(type={self.frame_type.name}, "
            f"session={self.session_id:#010x}, seq={self.seq_num}, "
            f"len={len(self.payload)}B, valid={self.valid})"
        )


def encode_protocol_frame(frame: ProtocolFrame) -> List[int]:
    """
    Serialize a ProtocolFrame into acoustic physical-layer bit sequence.

    Args:
        frame: ProtocolFrame to encode.

    Returns:
        List of integer bits (0 or 1) ready for AFSK modulation.
    """
    if len(frame.payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolFrameError(
            f"Payload size {len(frame.payload)} exceeds max limit of {MAX_PAYLOAD_BYTES} bytes"
        )

    # 1. Pack Header (10 bytes)
    # Format: > B (version), B (frame_type), I (session_id uint32), H (seq_num uint16), H (payload_len uint16)
    try:
        header_bytes = struct.pack(
            ">BBIHH",
            frame.version,
            int(frame.frame_type),
            frame.session_id & 0xFFFFFFFF,
            frame.seq_num & 0xFFFF,
            len(frame.payload),
        )
    except struct.error as e:
        raise ProtocolFrameError(f"Failed to pack frame header: {e}") from e

    # 2. Protected body = Header + Payload
    protected_body = header_bytes + frame.payload

    # 3. Compute CRC-16 CCITT over protected body
    crc16 = compute_crc16(protected_body)
    crc_bytes = struct.pack(">H", crc16)

    # 4. Serialize to bit sequence
    body_bits = bytes_to_bits(protected_body + crc_bytes)

    # 5. Prepend physical Preamble and Sync patterns
    return PREAMBLE_BITS + SYNC_BITS + body_bits


def decode_protocol_frame(
    bits: List[int],
    max_preamble_errors: int = 2,
    max_sync_errors: int = 1,
) -> ProtocolFrame:
    """
    Deserialize and validate an acoustic physical-layer bit sequence into a ProtocolFrame.

    Args:
        bits: Received bit sequence.
        max_preamble_errors: Permitted bit error tolerance in preamble.
        max_sync_errors: Permitted bit error tolerance in sync pattern.

    Returns:
        Validated ProtocolFrame.

    Raises:
        ProtocolFrameError, FrameTruncatedError, ChecksumMismatchError, InvalidFrameTypeError
    """
    if len(bits) < MIN_FRAME_BITS:
        raise FrameTruncatedError(
            f"Bit sequence too short: got {len(bits)} bits, minimum required is {MIN_FRAME_BITS}"
        )

    # 1. Preamble & Sync validation
    preamble_recv = bits[:PREAMBLE_LENGTH]
    preamble_errors = sum(a != b for a, b in zip(preamble_recv, PREAMBLE_BITS))
    if preamble_errors > max_preamble_errors:
        raise ProtocolFrameError(f"Preamble mismatch ({preamble_errors} errors exceed max {max_preamble_errors})")

    sync_recv = bits[PREAMBLE_LENGTH : PREAMBLE_LENGTH + SYNC_LENGTH]
    sync_errors = sum(a != b for a, b in zip(sync_recv, SYNC_BITS))
    if sync_errors > max_sync_errors:
        raise ProtocolFrameError(f"Sync pattern mismatch ({sync_errors} errors exceed max {max_sync_errors})")

    body_bits = bits[PREAMBLE_LENGTH + SYNC_LENGTH :]
    if len(body_bits) % 8 != 0:
        # Truncate to whole bytes
        body_bits = body_bits[: (len(body_bits) // 8) * 8]

    try:
        body_bytes = bits_to_bytes(body_bits)
    except BitstreamError as e:
        raise ProtocolFrameError(f"Failed to convert frame body bits to bytes: {e}") from e

    if len(body_bytes) < HEADER_BYTES_COUNT + CRC_BYTES_COUNT:
        raise FrameTruncatedError("Frame body bytes shorter than header + CRC")

    # 2. Unpack Header
    header_bytes = body_bytes[:HEADER_BYTES_COUNT]
    version, frame_type_int, session_id, seq_num, payload_len = struct.unpack(">BBIHH", header_bytes)

    if version != PROTOCOL_VERSION:
        raise ProtocolFrameError(f"Unsupported protocol version: {version}")

    try:
        frame_type = FrameType(frame_type_int)
    except ValueError:
        raise InvalidFrameTypeError(f"Unknown frame type identifier: {frame_type_int:#04x}")

    if payload_len > MAX_PAYLOAD_BYTES:
        raise ProtocolFrameError(f"Payload length {payload_len} exceeds max {MAX_PAYLOAD_BYTES}")

    expected_total_bytes = HEADER_BYTES_COUNT + payload_len + CRC_BYTES_COUNT
    if len(body_bytes) < expected_total_bytes:
        raise FrameTruncatedError(
            f"Frame payload truncated: expected {expected_total_bytes} bytes, received {len(body_bytes)}"
        )

    # 3. Extract Payload and CRC
    payload = body_bytes[HEADER_BYTES_COUNT : HEADER_BYTES_COUNT + payload_len]
    received_crc = struct.unpack(
        ">H", body_bytes[HEADER_BYTES_COUNT + payload_len : expected_total_bytes]
    )[0]

    # 4. Verify CRC-16
    calculated_crc = compute_crc16(body_bytes[: HEADER_BYTES_COUNT + payload_len])
    if received_crc != calculated_crc:
        raise ChecksumMismatchError(
            f"CRC-16 mismatch: received {received_crc:#06x}, calculated {calculated_crc:#06x}"
        )

    return ProtocolFrame(
        version=version,
        frame_type=frame_type,
        session_id=session_id,
        seq_num=seq_num,
        payload=payload,
        valid=True,
    )


# ─── Frame Builders ──────────────────────────────────────────────────────────

def create_discovery_ping(alias: str, session_id: int = 0) -> ProtocolFrame:
    """Build a DISCOVERY_PING frame carrying local alias."""
    payload = alias.encode("utf-8")[:128]
    return ProtocolFrame(
        frame_type=FrameType.DISCOVERY_PING,
        session_id=session_id,
        seq_num=0,
        payload=payload,
    )


def create_discovery_response(alias: str, session_id: int = 0) -> ProtocolFrame:
    """Build a DISCOVERY_RESPONSE frame answering a ping."""
    payload = alias.encode("utf-8")[:128]
    return ProtocolFrame(
        frame_type=FrameType.DISCOVERY_RESPONSE,
        session_id=session_id,
        seq_num=0,
        payload=payload,
    )


def create_transfer_offer(
    file_name: str,
    file_size: int,
    session_id: int,
    public_key: bytes = b"",
) -> ProtocolFrame:
    """
    Build a TRANSFER_OFFER frame with metadata and optional public key.
    Payload: name_len(1B) + name(N B) + size(4B) + public_key(32B)
    """
    name_bytes = file_name.encode("utf-8")[:128]
    payload = struct.pack(">B", len(name_bytes)) + name_bytes + struct.pack(">I", file_size) + public_key[:32]
    return ProtocolFrame(
        frame_type=FrameType.TRANSFER_OFFER,
        session_id=session_id,
        seq_num=0,
        payload=payload,
    )


def create_transfer_accept(session_id: int, public_key: bytes = b"") -> ProtocolFrame:
    """Build a TRANSFER_ACCEPT frame with optional recipient public key."""
    return ProtocolFrame(
        frame_type=FrameType.TRANSFER_ACCEPT,
        session_id=session_id,
        seq_num=0,
        payload=public_key[:32],
    )


def create_transfer_decline(session_id: int, reason: str = "DECLINED") -> ProtocolFrame:
    """Build a TRANSFER_DECLINE frame."""
    return ProtocolFrame(
        frame_type=FrameType.TRANSFER_DECLINE,
        session_id=session_id,
        seq_num=0,
        payload=reason.encode("utf-8")[:64],
    )


def create_data_frame(session_id: int, seq_num: int, data: bytes) -> ProtocolFrame:
    """Build a DATA_FRAME carrying encrypted & ECC protected packet data."""
    return ProtocolFrame(
        frame_type=FrameType.DATA_FRAME,
        session_id=session_id,
        seq_num=seq_num,
        payload=data,
    )


def create_transfer_ack(session_id: int, seq_num: int) -> ProtocolFrame:
    """Build an acoustic TRANSFER_ACK confirming successful receipt."""
    return ProtocolFrame(
        frame_type=FrameType.TRANSFER_ACK,
        session_id=session_id,
        seq_num=seq_num,
        payload=b"",
    )


def create_transfer_error(
    session_id: int,
    error_code: int,
    message: str = "",
    error_message: Optional[str] = None,
) -> ProtocolFrame:
    """Build a TRANSFER_ERROR frame."""
    msg = error_message if error_message is not None else message
    payload = struct.pack(">H", error_code & 0xFFFF) + msg.encode("utf-8")[:128]
    return ProtocolFrame(
        frame_type=FrameType.TRANSFER_ERROR,
        session_id=session_id,
        seq_num=0,
        payload=payload,
    )


class FrameSequenceTracker:
    """
    Manages frame sequencing, duplicate detection, and ordering.
    """

    def __init__(self, session_id: int):
        self.session_id = session_id
        self.expected_seq = 0
        self.seen_seqs: set[int] = set()

    def process_frame(self, frame: ProtocolFrame) -> Dict[str, Any]:
        """
        Validate sequence number and detect duplicates.

        Returns dict with status: 'valid', 'duplicate', or 'out_of_order'.
        """
        if frame.session_id != self.session_id:
            return {"status": "wrong_session", "expected": self.session_id, "actual": frame.session_id}

        seq = frame.seq_num
        if seq in self.seen_seqs:
            return {"status": "duplicate", "seq": seq}

        self.seen_seqs.add(seq)

        if seq == self.expected_seq:
            self.expected_seq += 1
            return {"status": "valid", "seq": seq}

        return {"status": "out_of_order", "seq": seq, "expected": self.expected_seq}
