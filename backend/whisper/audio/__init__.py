"""Audio module for WhisperProtocol."""

from .devices import (
    AudioDevice,
    list_input_devices,
    list_output_devices,
    get_default_input_device,
    get_default_output_device,
    check_sample_rate_support,
)
from .signal import (
    generate_tone,
    TONE_FREQUENCY_BIT_0,
    TONE_FREQUENCY_BIT_1,
    DEFAULT_SAMPLE_RATE,
)
from .output import (
    play_tone,
    play_18khz_test,
    play_19khz_test,
)
from .input import (
    record_audio,
    save_recording,
    load_recording,
)
from .diagnostics import (
    analyze_spectrum,
    detect_test_tone,
    NoiseFloorEstimate,
    DetectionResult,
    SpectrumAnalysis,
    ToneDetection,
    FREQUENCY_BAND_18KHZ,
    FREQUENCY_BAND_19KHZ,
    TARGET_FREQ_18KHZ,
    TARGET_FREQ_19KHZ,
    TARGET_TOLERANCE_HZ,
    DEFAULT_DETECTION_THRESHOLD_DB,
    DEFAULT_MIN_SNR_DB,
)

__all__ = [
    "AudioDevice",
    "list_input_devices",
    "list_output_devices",
    "get_default_input_device",
    "get_default_output_device",
    "check_sample_rate_support",
    "generate_tone",
    "TONE_FREQUENCY_BIT_0",
    "TONE_FREQUENCY_BIT_1",
    "DEFAULT_SAMPLE_RATE",
    "play_tone",
    "play_18khz_test",
    "play_19khz_test",
    "record_audio",
    "save_recording",
    "load_recording",
    "analyze_spectrum",
    "detect_test_tone",
    "NoiseFloorEstimate",
    "DetectionResult",
    "SpectrumAnalysis",
    "ToneDetection",
    "FREQUENCY_BAND_18KHZ",
    "FREQUENCY_BAND_19KHZ",
    "TARGET_FREQ_18KHZ",
    "TARGET_FREQ_19KHZ",
    "TARGET_TOLERANCE_HZ",
    "DEFAULT_DETECTION_THRESHOLD_DB",
    "DEFAULT_MIN_SNR_DB",
]