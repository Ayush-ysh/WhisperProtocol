"""Audio input/capture for WhisperProtocol."""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

from .devices import AudioDevice, check_sample_rate_support, get_default_input_device

logger = logging.getLogger(__name__)


class CaptureError(Exception):
    """Raised when audio capture fails."""

    pass


def record_audio(
    duration: float,
    input_device: Optional[int] = None,
    sample_rate: int = 44100,
    channels: int = 1,
    dtype: str = "float32",
) -> np.ndarray:
    """
    Record audio from microphone for a fixed duration.

    Args:
        duration: Recording duration in seconds
        input_device: Input device index, None for default
        sample_rate: Sample rate in Hz
        channels: Number of channels to record
        dtype: Data type for recording

    Returns:
        Float32 numpy array of shape (n_samples, channels) or (n_samples,) for mono

    Raises:
        CaptureError: If recording fails
        ValueError: If parameters are invalid
    """
    if duration <= 0:
        raise ValueError("Duration must be positive")
    if sample_rate <= 0:
        raise ValueError("Sample rate must be positive")
    if channels <= 0:
        raise ValueError("Channels must be positive")

    if input_device is not None:
        if not check_sample_rate_support(input_device, sample_rate, is_input=True):
            raise CaptureError(
                f"Device {input_device} does not support {sample_rate} Hz sample rate for input"
            )

    n_samples = int(duration * sample_rate)
    logger.info("Recording %.2fs (%d samples) at %d Hz on device %s", duration, n_samples, sample_rate, input_device)

    try:
        recording = sd.rec(
            n_samples,
            samplerate=sample_rate,
            channels=channels,
            dtype=dtype,
            device=input_device,
        )
        sd.wait()
    except sd.PortAudioError as e:
        raise CaptureError(f"Recording failed: {e}") from e

    if recording.shape[0] != n_samples:
        logger.warning(
            "Recorded %d samples, expected %d", recording.shape[0], n_samples
        )

    if channels == 1 and recording.ndim == 2:
        recording = recording[:, 0]

    logger.debug("Recording complete: shape=%s, dtype=%s", recording.shape, recording.dtype)
    return recording.astype(np.float32)


def save_recording(
    samples: np.ndarray,
    path: str | Path,
    sample_rate: int,
    subtype: str = "FLOAT",
) -> Path:
    """
    Save audio samples to WAV file.

    Args:
        samples: Float32 audio samples
        path: Output file path
        sample_rate: Sample rate in Hz
        subtype: WAV subtype (FLOAT, PCM_16, PCM_24, etc.)

    Returns:
        Path to saved file
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if samples.dtype != np.float32:
        samples = samples.astype(np.float32)

    if samples.ndim == 1:
        samples = samples[:, np.newaxis]

    logger.info("Saving recording to %s (%d Hz, %s)", path, sample_rate, subtype)
    sf.write(path, samples, sample_rate, subtype=subtype)
    logger.debug("Saved %d samples", samples.shape[0])
    return path


def load_recording(path: str | Path) -> tuple[np.ndarray, int]:
    """
    Load audio from WAV file.

    Args:
        path: Input file path

    Returns:
        Tuple of (samples, sample_rate)
    """
    path = Path(path)
    logger.info("Loading recording from %s", path)
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    logger.debug("Loaded %d samples at %d Hz, shape=%s", samples.shape[0], sample_rate, samples.shape)
    return samples, sample_rate


def get_input_device_info(device_index: Optional[int] = None) -> Optional[AudioDevice]:
    """Get info about input device."""
    from .devices import get_device_by_index, get_default_input_device

    if device_index is not None:
        return get_device_by_index(device_index)
    return get_default_input_device()


def test_input_device(
    device_index: int,
    sample_rate: int = 44100,
    test_duration: float = 0.5,
) -> bool:
    """
    Test if an input device works correctly.

    Args:
        device_index: Device to test
        sample_rate: Sample rate to test
        test_duration: Duration of test recording

    Returns:
        True if device works, False otherwise
    """
    try:
        samples = record_audio(test_duration, device_index, sample_rate)
        rms = np.sqrt(np.mean(samples**2))
        logger.info("Input device %d test: RMS=%.6f", device_index, rms)
        return rms > 0.0
    except CaptureError as e:
        logger.error("Input device %d test failed: %s", device_index, e)
        return False