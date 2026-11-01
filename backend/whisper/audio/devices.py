"""Audio device discovery and management."""

import logging
from dataclasses import dataclass
from typing import Optional

import sounddevice as sd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDevice:
    """Represents an audio input or output device."""

    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    hostapi: str

    def __str__(self) -> str:
        ch_in = self.max_input_channels
        ch_out = self.max_output_channels
        return f"[{self.index}] {self.name} (in:{ch_in} out:{ch_out} @ {self.default_sample_rate:.0f}Hz)"

    @property
    def is_input_capable(self) -> bool:
        return self.max_input_channels > 0

    @property
    def is_output_capable(self) -> bool:
        return self.max_output_channels > 0


def _device_from_sd(device_dict: dict, index: int) -> AudioDevice:
    """Convert sounddevice device dict to AudioDevice."""
    hostapi_info = sd.query_hostapis(device_dict["hostapi"])
    return AudioDevice(
        index=index,
        name=device_dict["name"],
        max_input_channels=device_dict["max_input_channels"],
        max_output_channels=device_dict["max_output_channels"],
        default_sample_rate=device_dict["default_samplerate"],
        hostapi=hostapi_info["name"],
    )


def list_input_devices() -> list[AudioDevice]:
    """List all available audio input devices."""
    devices = []
    for idx, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            devices.append(_device_from_sd(device, idx))
    logger.debug("Found %d input devices", len(devices))
    return devices


def list_output_devices() -> list[AudioDevice]:
    """List all available audio output devices."""
    devices = []
    for idx, device in enumerate(sd.query_devices()):
        if device["max_output_channels"] > 0:
            devices.append(_device_from_sd(device, idx))
    logger.debug("Found %d output devices", len(devices))
    return devices


def get_default_input_device() -> Optional[AudioDevice]:
    """Get the default audio input device."""
    try:
        default_idx = sd.default.device[0]
        if default_idx == -1:
            logger.warning("No default input device configured")
            return None
        device = sd.query_devices(default_idx)
        if device["max_input_channels"] == 0:
            logger.warning("Default device %d has no input channels", default_idx)
            return None
        return _device_from_sd(device, default_idx)
    except (IndexError, sd.PortAudioError) as e:
        logger.error("Failed to get default input device: %s", e)
        return None


def get_default_output_device() -> Optional[AudioDevice]:
    """Get the default audio output device."""
    try:
        default_idx = sd.default.device[1]
        if default_idx == -1:
            logger.warning("No default output device configured")
            return None
        device = sd.query_devices(default_idx)
        if device["max_output_channels"] == 0:
            logger.warning("Default device %d has no output channels", default_idx)
            return None
        return _device_from_sd(device, default_idx)
    except (IndexError, sd.PortAudioError) as e:
        logger.error("Failed to get default output device: %s", e)
        return None


def check_sample_rate_support(
    device_index: int,
    sample_rate: int,
    is_input: bool = False,
) -> bool:
    """
    Check if a device supports a specific sample rate.

    Probes the hardware via sounddevice settings check to verify the device
    supports the requested sample rate. Falls back to checking against default
    and common sample rates if the check raises an unexpected error.

    Args:
        device_index: Device index to check
        sample_rate: Sample rate to test (e.g., 44100)
        is_input: True to test input, False for output

    Returns:
        True if supported, False otherwise
    """
    try:
        if is_input:
            sd.check_input_settings(device=device_index, samplerate=sample_rate)
        else:
            sd.check_output_settings(device=device_index, samplerate=sample_rate)
        return True
    except sd.PortAudioError:
        return False
    except Exception as e:
        logger.debug(
            "Unexpected error checking sample rate %d on device %d (is_input=%s): %s; falling back to heuristic",
            sample_rate,
            device_index,
            is_input,
            e,
        )

    # Fallback to heuristic approach
    try:
        device = sd.query_devices(device_index)
        default_sr = device["default_samplerate"]

        # If sample rate matches default, assume supported
        if abs(sample_rate - default_sr) < 1.0:
            return True

        # For common rates, check if they're likely supported
        common_rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 88200, 96000, 192000]
        if sample_rate in common_rates:
            # Many devices support common rates even if not default
            return True

        # For other rates, assume not supported to be safe
        return False
    except (IndexError, sd.PortAudioError) as e:
        logger.debug("Failed to query device %d for sample rate %d: %s", device_index, sample_rate, e)
        return False


def get_device_by_index(index: int) -> Optional[AudioDevice]:
    """Get device info by index."""
    try:
        device = sd.query_devices(index)
        return _device_from_sd(device, index)
    except (IndexError, sd.PortAudioError) as e:
        logger.error("Failed to query device %d: %s", index, e)
        return None