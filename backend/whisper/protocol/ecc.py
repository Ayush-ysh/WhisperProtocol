"""Reed-Solomon Error Correction Codec for WhisperProtocol.

Provides configurable forward error correction (FEC) at the frame payload layer.
Supports 8, 16, and 32 parity symbols:
- 8 parity symbols: corrects up to 4 symbol errors.
- 16 parity symbols (default): corrects up to 8 symbol errors.
- 32 parity symbols: corrects up to 16 symbol errors.
"""

import logging
from typing import Tuple
import reedsolo

logger = logging.getLogger(__name__)


class ECCError(Exception):
    """Base exception for ECC errors."""
    pass


class ECCUncorrectableError(ECCError):
    """Raised when data has more errors than the ECC capacity can correct."""
    pass


# Cache RS codecs for common parity lengths (8, 16, 32)
_CODEC_CACHE: dict[int, reedsolo.RSCodec] = {}


def _get_codec(n_ecc_symbols: int) -> reedsolo.RSCodec:
    """Retrieve or create cached RSCodec instance for given parity size."""
    if n_ecc_symbols not in _CODEC_CACHE:
        if n_ecc_symbols < 2 or n_ecc_symbols > 64:
            raise ValueError(f"Invalid n_ecc_symbols: {n_ecc_symbols}. Must be between 2 and 64.")
        _CODEC_CACHE[n_ecc_symbols] = reedsolo.RSCodec(n_ecc_symbols)
    return _CODEC_CACHE[n_ecc_symbols]


def rs_encode(data: bytes, n_ecc_symbols: int = 16) -> bytes:
    """
    Encode data with Reed-Solomon forward error correction parity.

    Args:
        data: Raw payload bytes to protect.
        n_ecc_symbols: Number of parity symbols (default: 16).

    Returns:
        Encoded bytes containing original data + parity bytes.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"data must be bytes or bytearray, got {type(data).__name__}")

    if len(data) == 0:
        return b""

    codec = _get_codec(n_ecc_symbols)
    # rs_encode returns bytearray containing data + ecc
    encoded = codec.encode(data)
    return bytes(encoded)


def rs_decode(data: bytes, n_ecc_symbols: int = 16) -> Tuple[bytes, int]:
    """
    Decode and correct Reed-Solomon encoded data.

    Args:
        data: Encoded bytes containing message + parity symbols.
        n_ecc_symbols: Number of parity symbols used during encoding.

    Returns:
        Tuple of (decoded_bytes, corrected_symbol_count).

    Raises:
        ECCUncorrectableError: If corrupted beyond error-correcting capacity.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"data must be bytes or bytearray, got {type(data).__name__}")

    if len(data) == 0:
        return b"", 0

    if len(data) <= n_ecc_symbols:
        raise ECCUncorrectableError(
            f"Data length ({len(data)}) must be strictly greater than ECC symbols ({n_ecc_symbols})"
        )

    codec = _get_codec(n_ecc_symbols)

    try:
        # decode returns (decoded_message, decoded_message_with_ecc, errata_pos)
        decoded_msg, _, errata_pos = codec.decode(data)
        num_corrected = len(errata_pos) if errata_pos else 0
        if num_corrected > 0:
            logger.info("Reed-Solomon successfully corrected %d symbol error(s)", num_corrected)
        return bytes(decoded_msg), num_corrected
    except reedsolo.ReedSolomonError as e:
        logger.warning("Reed-Solomon decoding failed: uncorrectable frame (%s)", e)
        raise ECCUncorrectableError(f"Frame corrupted beyond ECC recovery capacity: {e}") from e
