"""AFSK modulation for WhisperProtocol."""

import numpy as np

from .constants import (
    FREQ_ZERO,
    FREQ_ONE,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    DEFAULT_AMPLITUDE,
    DEFAULT_FADE_MS,
    get_samples_per_symbol,
)


def generate_symbol(
    bit: int,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    symbol_duration: float = DEFAULT_SYMBOL_DURATION,
    amplitude: float = DEFAULT_AMPLITUDE,
    fade_ms: float = DEFAULT_FADE_MS,
    freq_zero: float = FREQ_ZERO,
    freq_one: float = FREQ_ONE,
) -> np.ndarray:
    """
    Generate a single AFSK symbol.

    Args:
        bit: 0 or 1
        sample_rate: Sample rate in Hz
        symbol_duration: Duration of one symbol in seconds
        amplitude: Peak amplitude (0.0 to 1.0)
        fade_ms: Fade in/out duration in milliseconds
        freq_zero: Frequency for bit 0
        freq_one: Frequency for bit 1

    Returns:
        Float32 numpy array of shape (samples_per_symbol,)
    """
    if bit not in (0, 1):
        raise ValueError(f"Invalid bit: {bit}. Must be 0 or 1.")

    freq = freq_zero if bit == 0 else freq_one
    n_samples = get_samples_per_symbol(sample_rate, symbol_duration)

    t = np.arange(n_samples, dtype=np.float32) / sample_rate
    symbol = np.sin(2 * np.pi * freq * t, dtype=np.float32)
    symbol *= amplitude

    fade_samples = int(fade_ms / 1000.0 * sample_rate)
    fade_samples = min(fade_samples, n_samples // 2)

    if fade_samples > 0:
        fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
        fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
        symbol[:fade_samples] *= fade_in
        symbol[-fade_samples:] *= fade_out

    # Ensure no clipping
    symbol = np.clip(symbol, -1.0, 1.0)

    return symbol.astype(np.float32)


def modulate_bits(
    bits: list[int],
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    symbol_duration: float = DEFAULT_SYMBOL_DURATION,
    amplitude: float = DEFAULT_AMPLITUDE,
    fade_ms: float = DEFAULT_FADE_MS,
) -> np.ndarray:
    """
    Modulate bit sequence into AFSK waveform.

    Args:
        bits: List of bits (0 or 1)
        sample_rate: Sample rate in Hz
        symbol_duration: Duration of one symbol in seconds
        amplitude: Peak amplitude (0.0 to 1.0)
        fade_ms: Fade in/out duration in milliseconds

    Returns:
        Float32 numpy array containing concatenated symbols
    """
    if not bits:
        return np.array([], dtype=np.float32)

    symbols = []
    for bit in bits:
        symbol = generate_symbol(
            bit, sample_rate, symbol_duration, amplitude, fade_ms
        )
        symbols.append(symbol)

    waveform = np.concatenate(symbols) if symbols else np.array([], dtype=np.float32)
    return waveform.astype(np.float32)


def get_waveform_info(bits: list[int], sample_rate: int = DEFAULT_SAMPLE_RATE, symbol_duration: float = DEFAULT_SYMBOL_DURATION) -> dict:
    """
    Get information about waveform that would be generated.

    Args:
        bits: List of bits
        sample_rate: Sample rate in Hz
        symbol_duration: Duration of one symbol in seconds

    Returns:
        Dictionary with waveform info
    """
    samples_per_symbol = get_samples_per_symbol(sample_rate, symbol_duration)
    total_samples = len(bits) * samples_per_symbol
    duration = len(bits) * symbol_duration

    return {
        "bit_count": len(bits),
        "sample_rate": sample_rate,
        "symbol_duration_ms": symbol_duration * 1000,
        "samples_per_symbol": samples_per_symbol,
        "total_samples": total_samples,
        "duration_seconds": duration,
        "duration_ms": duration * 1000,
    }