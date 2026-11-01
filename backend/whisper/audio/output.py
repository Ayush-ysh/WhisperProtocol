"""Audio output/playback for WhisperProtocol."""

import logging
from typing import Optional

import numpy as np
import sounddevice as sd

from .devices import AudioDevice, check_sample_rate_support, get_default_output_device
from .signal import (
    DEFAULT_SAMPLE_RATE,
    MAX_AMPLITUDE,
    TONE_FREQUENCY_BIT_0,
    TONE_FREQUENCY_BIT_1,
    generate_tone,
)

logger = logging.getLogger(__name__)


class PlaybackError(Exception):
    """Raised when audio playback fails."""

    pass


def _play_samples(
    samples: np.ndarray,
    sample_rate: int,
    device: Optional[int] = None,
    blocking: bool = True,
) -> None:
    """
    Play audio samples through output device.

    Args:
        samples: Float32 audio samples, shape (n_samples,) or (n_samples, channels)
        sample_rate: Sample rate in Hz
        device: Output device index, None for default
        blocking: If True, wait for playback to complete
    """
    if samples.dtype != np.float32:
        samples = samples.astype(np.float32)

    if samples.ndim == 1:
        samples = samples[:, np.newaxis]

    try:
        sd.play(samples, samplerate=sample_rate, device=device, blocking=blocking)
    except sd.PortAudioError as e:
        raise PlaybackError(f"Playback failed: {e}") from e


def play_tone(
    frequency: float,
    duration: float,
    output_device: Optional[int] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
    blocking: bool = True,
) -> None:
    """
    Generate and play a sine wave tone.

    Args:
        frequency: Tone frequency in Hz
        duration: Duration in seconds
        output_device: Output device index, None for default
        sample_rate: Sample rate in Hz
        amplitude: Peak amplitude (0.0 to 1.0)
        blocking: If True, wait for playback to complete

    Raises:
        PlaybackError: If playback fails
        ValueError: If parameters are invalid
    """
    if output_device is not None:
        if not check_sample_rate_support(output_device, sample_rate, is_input=False):
            raise PlaybackError(
                f"Device {output_device} does not support {sample_rate} Hz sample rate"
            )

    logger.info("Playing %.1f Hz tone for %.2fs on device %s", frequency, duration, output_device)
    samples = generate_tone(frequency, duration, sample_rate, amplitude)
    _play_samples(samples, sample_rate, device=output_device, blocking=blocking)
    logger.debug("Playback complete")


def play_18khz_test(
    duration: float = 1.0,
    output_device: Optional[int] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
    blocking: bool = True,
) -> None:
    """Play 18 kHz test tone (BIT 0)."""
    play_tone(TONE_FREQUENCY_BIT_0, duration, output_device, sample_rate, amplitude, blocking)


def play_19khz_test(
    duration: float = 1.0,
    output_device: Optional[int] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
    blocking: bool = True,
) -> None:
    """Play 19 kHz test tone (BIT 1)."""
    play_tone(TONE_FREQUENCY_BIT_1, duration, output_device, sample_rate, amplitude, blocking)


def play_tone_sequence(
    bits: str,
    bit_duration: float,
    output_device: Optional[int] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = MAX_AMPLITUDE,
    gap_duration: float = 0.0,
    blocking: bool = True,
) -> None:
    """
    Play a sequence of tones representing bits.

    Args:
        bits: String of '0' and '1' characters
        bit_duration: Duration of each bit in seconds
        output_device: Output device index
        sample_rate: Sample rate in Hz
        amplitude: Peak amplitude
        gap_duration: Silent gap between bits in seconds
        blocking: If True, wait for playback to complete
    """
    from .signal import generate_tone_sequence

    if output_device is not None:
        if not check_sample_rate_support(output_device, sample_rate, is_input=False):
            raise PlaybackError(
                f"Device {output_device} does not support {sample_rate} Hz sample rate"
            )

    logger.info("Playing bit sequence: %s", bits)
    samples = generate_tone_sequence(bits, bit_duration, sample_rate, amplitude, gap_duration)
    _play_samples(samples, sample_rate, device=output_device, blocking=blocking)


def stop_playback() -> None:
    """Stop any ongoing playback immediately."""
    sd.stop()
    logger.debug("Playback stopped")


def get_output_device_info(device_index: Optional[int] = None) -> Optional[AudioDevice]:
    """Get info about output device."""
    from .devices import get_device_by_index, get_default_output_device

    if device_index is not None:
        return get_device_by_index(device_index)
    return get_default_output_device()