import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .constants import (
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    DEFAULT_AMPLITUDE,
    DEFAULT_FADE_MS,
    FREQ_ZERO,
    FREQ_ONE,
)
from .framing import encode_frame, get_frame_info
from .modulation import modulate_bits, get_waveform_info
from .ecc import rs_encode
from whisper.events import (
    emit_transmission_started,
    emit_transmission_completed,
    emit_transmission_error,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncodeResult:
    """Result of message encoding."""

    waveform: np.ndarray
    sample_rate: int
    symbol_duration: float
    payload: str
    payload_bytes: int
    frame_bits: int
    bit_count: int
    symbol_count: int
    duration_seconds: float

    def __str__(self) -> str:
        return (
            f"EncodeResult(payload='{self.payload}', "
            f"payload_bytes={self.payload_bytes}, "
            f"frame_bits={self.frame_bits}, "
            f"bit_count={self.bit_count}, "
            f"symbol_count={self.symbol_count}, "
            f"duration={self.duration_seconds:.3f}s)"
        )


def encode_message(
    message: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    symbol_duration: float = DEFAULT_SYMBOL_DURATION,
    amplitude: float = DEFAULT_AMPLITUDE,
    fade_ms: float = DEFAULT_FADE_MS,
    freq_zero: float = FREQ_ZERO,
    freq_one: float = FREQ_ONE,
    ecc_symbols: int = 0,
    phase_continuous: bool = False,
) -> EncodeResult:
    """
    Encode text message into AFSK waveform.

    Pipeline:
    STRING -> UTF-8 BYTES -> [ECC] -> FRAME -> BITS -> AFSK MODULATION -> WAVEFORM

    Args:
        message: Text message to encode
        sample_rate: Sample rate in Hz
        symbol_duration: Duration of one symbol in seconds
        amplitude: Peak amplitude (0.0 to 1.0)
        fade_ms: Fade in/out duration in milliseconds
        freq_zero: Frequency for bit 0 in Hz
        freq_one: Frequency for bit 1 in Hz
        ecc_symbols: Number of Reed-Solomon parity symbols (0 = disabled)
        phase_continuous: Generate continuous-phase CPFSK waveform

    Returns:
        EncodeResult with waveform and metadata
    """
    if not isinstance(message, str):
        raise ValueError(f"Expected string, got {type(message).__name__}")

    try:
        emit_transmission_started(
            message=message,
            sample_rate=sample_rate,
            symbol_duration=symbol_duration,
            amplitude=amplitude,
        )
    except Exception as e:
        logger.debug("Failed to emit transmission_started: %s", e)

    try:
        # String -> UTF-8 bytes
        payload_bytes = message.encode("utf-8")

        # Optional Reed-Solomon FEC protection
        if ecc_symbols > 0:
            payload_bytes = rs_encode(payload_bytes, n_ecc_symbols=ecc_symbols)

        # Bytes -> Frame -> Bits
        frame_bits = encode_frame(payload_bytes)

        # Bits -> AFSK waveform
        waveform = modulate_bits(
            frame_bits,
            sample_rate=sample_rate,
            symbol_duration=symbol_duration,
            amplitude=amplitude,
            fade_ms=fade_ms,
            freq_zero=freq_zero,
            freq_one=freq_one,
            phase_continuous=phase_continuous,
        )


        # Calculate metadata
        frame_info = get_frame_info(payload_bytes)
        waveform_info = get_waveform_info(frame_bits, sample_rate, symbol_duration)

        result = EncodeResult(
            waveform=waveform,
            sample_rate=sample_rate,
            symbol_duration=symbol_duration,
            payload=message,
            payload_bytes=len(payload_bytes),
            frame_bits=frame_info["total_bits"],
            bit_count=waveform_info["bit_count"],
            symbol_count=waveform_info["bit_count"],  # 1 symbol per bit
            duration_seconds=waveform_info["duration_seconds"],
        )

        try:
            emit_transmission_completed(
                message=message,
                duration=result.duration_seconds,
            )
        except Exception as e:
            logger.debug("Failed to emit transmission_completed: %s", e)

        return result
    except Exception as e:
        try:
            emit_transmission_error(message=str(message), error=str(e))
        except Exception:
            pass
        raise


def save_waveform(
    waveform: np.ndarray,
    path: str | Path,
    sample_rate: int,
    subtype: str = "PCM_16",
) -> Path:
    """
    Save waveform to WAV file.

    Args:
        waveform: Float32 audio samples
        path: Output file path
        sample_rate: Sample rate in Hz
        subtype: WAV subtype (PCM_16, FLOAT, etc.)

    Returns:
        Path to saved file
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to appropriate format
    if subtype == "PCM_16":
        # Scale float32 [-1, 1] to int16
        if waveform.dtype != np.float32:
            waveform = waveform.astype(np.float32)
        # Clip to prevent overflow
        waveform = np.clip(waveform, -1.0, 1.0)
        int_waveform = (waveform * 32767).astype(np.int16)
        sf.write(path, int_waveform, sample_rate, subtype=subtype)
    else:
        if waveform.dtype != np.float32:
            waveform = waveform.astype(np.float32)
        sf.write(path, waveform, sample_rate, subtype=subtype)

    return path


def encode_and_save(
    message: str,
    output_path: str | Path,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    symbol_duration: float = DEFAULT_SYMBOL_DURATION,
    amplitude: float = DEFAULT_AMPLITUDE,
    fade_ms: float = DEFAULT_FADE_MS,
    subtype: str = "PCM_16",
) -> EncodeResult:
    """
    Encode message and save to WAV file.

    Args:
        message: Text message to encode
        output_path: Output WAV file path
        sample_rate: Sample rate in Hz
        symbol_duration: Duration of one symbol in seconds
        amplitude: Peak amplitude (0.0 to 1.0)
        fade_ms: Fade in/out duration in milliseconds
        subtype: WAV subtype

    Returns:
        EncodeResult with waveform and metadata
    """
    result = encode_message(
        message,
        sample_rate=sample_rate,
        symbol_duration=symbol_duration,
        amplitude=amplitude,
        fade_ms=fade_ms,
    )
    save_waveform(result.waveform, output_path, sample_rate, subtype=subtype)
    return result