"""Signal generation for WhisperProtocol tones."""

import logging
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

TONE_FREQUENCY_BIT_0: float = 18000.0
TONE_FREQUENCY_BIT_1: float = 19000.0

DEFAULT_SAMPLE_RATE: int = 44100
FADE_DURATION_MS: float = 5.0
MAX_AMPLITUDE: float = 0.8


def generate_tone(
    frequency: float,
    duration: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
    fade_ms: float = FADE_DURATION_MS,
) -> np.ndarray:
    """
    Generate a clean sine wave tone with fade-in/out.

    Args:
        frequency: Tone frequency in Hz
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        amplitude: Peak amplitude (0.0 to 1.0)
        fade_ms: Fade in/out duration in milliseconds

    Returns:
        Float32 numpy array of shape (n_samples,)
    """
    if frequency <= 0:
        raise ValueError("Frequency must be positive")
    if duration <= 0:
        raise ValueError("Duration must be positive")
    if sample_rate <= 0:
        raise ValueError("Sample rate must be positive")
    if not 0 < amplitude <= 1.0:
        raise ValueError("Amplitude must be in (0, 1.0]")
    if fade_ms < 0:
        raise ValueError("Fade duration cannot be negative")

    n_samples = int(duration * sample_rate)
    t = np.arange(n_samples, dtype=np.float32) / sample_rate

    tone = np.sin(2 * np.pi * frequency * t, dtype=np.float32)
    tone *= amplitude

    fade_samples = int(fade_ms / 1000.0 * sample_rate)
    fade_samples = min(fade_samples, n_samples // 2)

    if fade_samples > 1:
        fade_in = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fade_samples, dtype=np.float32)))
        tone[:fade_samples] *= fade_in
        tone[-fade_samples:] *= fade_in[::-1]
    elif fade_samples == 1:
        tone[0] = 0.0
        tone[-1] = 0.0

    # Ensure no clipping
    tone = np.clip(tone, -1.0, 1.0)

    return tone.astype(np.float32)


def generate_18khz_tone(
    duration: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
) -> np.ndarray:
    """Generate 18 kHz tone (BIT 0)."""
    return generate_tone(TONE_FREQUENCY_BIT_0, duration, sample_rate, amplitude)


def generate_19khz_tone(
    duration: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
) -> np.ndarray:
    """Generate 19 kHz tone (BIT 1)."""
    return generate_tone(TONE_FREQUENCY_BIT_1, duration, sample_rate, amplitude)


def generate_tone_sequence(
    bits: str,
    bit_duration: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
    gap_duration: float = 0.0,
) -> np.ndarray:
    """
    Generate a sequence of tones representing bits.

    Args:
        bits: String of '0' and '1' characters
        bit_duration: Duration of each bit in seconds
        sample_rate: Sample rate in Hz
        amplitude: Peak amplitude
        gap_duration: Silent gap between bits in seconds

    Returns:
        Concatenated tone sequence
    """
    tones = []
    gap_samples = int(gap_duration * sample_rate)
    gap = np.zeros(gap_samples, dtype=np.float32)

    for i, bit in enumerate(bits):
        if bit == "0":
            tone = generate_18khz_tone(bit_duration, sample_rate, amplitude)
        elif bit == "1":
            tone = generate_19khz_tone(bit_duration, sample_rate, amplitude)
        else:
            raise ValueError(f"Invalid bit: {bit}. Must be '0' or '1'")
        tones.append(tone)
        if i < len(bits) - 1 and gap_samples > 0:
            tones.append(gap)

    return np.concatenate(tones) if tones else np.array([], dtype=np.float32)