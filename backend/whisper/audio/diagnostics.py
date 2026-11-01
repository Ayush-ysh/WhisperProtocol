"""FFT analysis and tone detection for WhisperProtocol."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
from scipy.signal import get_window
from scipy.fft import rfft, rfftfreq

logger = logging.getLogger(__name__)

FREQUENCY_BAND_18KHZ: tuple[float, float] = (17500.0, 18500.0)
FREQUENCY_BAND_19KHZ: tuple[float, float] = (18500.0, 19500.0)

TARGET_FREQ_18KHZ: float = 18000.0
TARGET_FREQ_19KHZ: float = 19000.0
TARGET_TOLERANCE_HZ: float = 200.0

DEFAULT_DETECTION_THRESHOLD_DB: float = 20.0
DEFAULT_MIN_SNR_DB: float = 12.0


class DetectionStatus(Enum):
    """Status of tone detection."""

    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NO_RELIABLE_DETECTION = "NO_RELIABLE_DETECTION"


@dataclass(frozen=True)
class NoiseFloorEstimate:
    """Noise floor estimation results."""

    mean_magnitude: float
    median_magnitude: float
    std_magnitude: float
    percentile_10: float
    percentile_90: float
    estimated_db: float

    def __str__(self) -> str:
        return (
            f"NoiseFloor(mean={self.mean_magnitude:.6f}, "
            f"median={self.median_magnitude:.6f}, "
            f"est_db={self.estimated_db:.1f}dB)"
        )


@dataclass(frozen=True)
class ToneDetection:
    """Detection result for a single frequency band."""

    band_name: str
    band_range: tuple[float, float]
    status: DetectionStatus
    peak_frequency: Optional[float]
    peak_magnitude: Optional[float]
    band_energy: float
    noise_floor: float
    snr_db: Optional[float]
    relative_energy: float

    def __str__(self) -> str:
        if self.status == DetectionStatus.DETECTED:
            return (
                f"{self.band_name}: {self.status.value} "
                f"(Peak: {self.peak_frequency:.1f} Hz, "
                f"SNR: {self.snr_db:.1f} dB, "
                f"RelEnergy: {self.relative_energy:.3f})"
            )
        return f"{self.band_name}: {self.status.value}"


@dataclass(frozen=True)
class SpectrumAnalysis:
    """Complete spectrum analysis results."""

    frequencies: np.ndarray
    magnitudes: np.ndarray
    peak_frequency: float
    peak_magnitude: float
    noise_floor: NoiseFloorEstimate
    detection_18khz: ToneDetection
    detection_19khz: ToneDetection

    def __str__(self) -> str:
        lines = [
            f"Peak Frequency: {self.peak_frequency:.1f} Hz",
            f"Peak Magnitude: {self.peak_magnitude:.6f}",
            str(self.noise_floor),
            str(self.detection_18khz),
            str(self.detection_19khz),
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class DetectionResult:
    """Overall detection result."""

    channel_ready: bool
    analysis: SpectrumAnalysis
    summary: str

    def __str__(self) -> str:
        return f"{self.summary}\n{self.analysis}"


def estimate_noise_floor(magnitudes: np.ndarray) -> NoiseFloorEstimate:
    """
    Estimate noise floor from magnitude spectrum.

    Uses robust statistics (median, percentiles) to avoid
    contamination from signal peaks.
    """
    if len(magnitudes) == 0:
        return NoiseFloorEstimate(0, 0, 0, 0, 0, -np.inf)

    mean_mag = float(np.mean(magnitudes))
    median_mag = float(np.median(magnitudes))
    std_mag = float(np.std(magnitudes))
    p10 = float(np.percentile(magnitudes, 10))
    p90 = float(np.percentile(magnitudes, 90))

    estimated_db = 20 * np.log10(median_mag) if median_mag > 0 else -np.inf

    return NoiseFloorEstimate(
        mean_magnitude=mean_mag,
        median_magnitude=median_mag,
        std_magnitude=std_mag,
        percentile_10=p10,
        percentile_90=p90,
        estimated_db=estimated_db,
    )


def analyze_band(
    frequencies: np.ndarray,
    magnitudes: np.ndarray,
    band_range: tuple[float, float],
    band_name: str,
    noise_floor: NoiseFloorEstimate,
    detection_threshold_db: float = DEFAULT_DETECTION_THRESHOLD_DB,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
    target_frequency: Optional[float] = None,
    target_tolerance_hz: float = TARGET_TOLERANCE_HZ,
) -> ToneDetection:
    """
    Analyze a specific frequency band for tone presence.
    """
    f_low, f_high = band_range
    band_mask = (frequencies >= f_low) & (frequencies <= f_high)

    if not np.any(band_mask):
        return ToneDetection(
            band_name=band_name,
            band_range=band_range,
            status=DetectionStatus.NOT_DETECTED,
            peak_frequency=None,
            peak_magnitude=None,
            band_energy=0.0,
            noise_floor=noise_floor.median_magnitude,
            snr_db=None,
            relative_energy=0.0,
        )

    band_freqs = frequencies[band_mask]
    band_mags = magnitudes[band_mask]

    peak_idx = np.argmax(band_mags)
    peak_freq = float(band_freqs[peak_idx])
    peak_mag = float(band_mags[peak_idx])
    band_energy = float(np.sum(band_mags**2))

    noise_level = noise_floor.median_magnitude
    if noise_level > 0 and peak_mag > 0:
        snr_db = 20 * np.log10(peak_mag / noise_level)
        relative_energy = peak_mag / noise_level
    else:
        snr_db = None
        relative_energy = 0.0

    threshold_linear = 10 ** (detection_threshold_db / 20.0)
    min_snr_linear = 10 ** (min_snr_db / 20.0)

    # Check if peak is near expected target frequency
    target_match = True
    if target_frequency is not None:
        target_match = abs(peak_freq - target_frequency) <= target_tolerance_hz

    if (
        snr_db is not None
        and snr_db >= min_snr_db
        and peak_mag > noise_level * threshold_linear
        and target_match
    ):
        status = DetectionStatus.DETECTED
    elif snr_db is not None and snr_db >= (min_snr_db / 2) and target_match:
        status = DetectionStatus.LOW_CONFIDENCE
    else:
        status = DetectionStatus.NO_RELIABLE_DETECTION if snr_db is None else DetectionStatus.NOT_DETECTED

    return ToneDetection(
        band_name=band_name,
        band_range=band_range,
        status=status,
        peak_frequency=peak_freq,
        peak_magnitude=peak_mag,
        band_energy=band_energy,
        noise_floor=noise_level,
        snr_db=snr_db,
        relative_energy=relative_energy,
    )


def analyze_spectrum(
    samples: np.ndarray,
    sample_rate: int,
    window_type: str = "hann",
    detection_threshold_db: float = DEFAULT_DETECTION_THRESHOLD_DB,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
) -> SpectrumAnalysis:
    """
    Perform FFT analysis on audio samples.

    Args:
        samples: Audio samples (mono, float32)
        sample_rate: Sample rate in Hz
        window_type: Window function to apply
        detection_threshold_db: Minimum dB above noise floor for detection
        min_snr_db: Minimum SNR in dB for reliable detection

    Returns:
        SpectrumAnalysis with frequencies, magnitudes, and detections
    """
    if samples.ndim > 1:
        samples = samples[:, 0] if samples.shape[1] > 0 else samples.flatten()

    if len(samples) == 0:
        raise ValueError("Empty samples array")

    window = get_window(window_type, len(samples), fftbins=True)
    windowed = samples * window

    magnitudes = np.abs(rfft(windowed))
    frequencies = rfftfreq(len(samples), 1.0 / sample_rate)

    peak_idx = np.argmax(magnitudes)
    peak_freq = float(frequencies[peak_idx])
    peak_mag = float(magnitudes[peak_idx])

    noise_floor = estimate_noise_floor(magnitudes)

    detection_18khz = analyze_band(
        frequencies,
        magnitudes,
        FREQUENCY_BAND_18KHZ,
        "18 kHz",
        noise_floor,
        detection_threshold_db=detection_threshold_db,
        min_snr_db=min_snr_db,
        target_frequency=TARGET_FREQ_18KHZ,
    )
    detection_19khz = analyze_band(
        frequencies,
        magnitudes,
        FREQUENCY_BAND_19KHZ,
        "19 kHz",
        noise_floor,
        detection_threshold_db=detection_threshold_db,
        min_snr_db=min_snr_db,
        target_frequency=TARGET_FREQ_19KHZ,
    )

    return SpectrumAnalysis(
        frequencies=frequencies,
        magnitudes=magnitudes,
        peak_frequency=peak_freq,
        peak_magnitude=peak_mag,
        noise_floor=noise_floor,
        detection_18khz=detection_18khz,
        detection_19khz=detection_19khz,
    )


def detect_test_tone(
    samples: np.ndarray,
    sample_rate: int,
    detection_threshold_db: float = DEFAULT_DETECTION_THRESHOLD_DB,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
) -> DetectionResult:
    """
    Detect 18 kHz and 19 kHz test tones in recorded audio.

    Args:
        samples: Audio samples (mono, float32)
        sample_rate: Sample rate in Hz
        detection_threshold_db: Minimum dB above noise floor for detection
        min_snr_db: Minimum SNR in dB for reliable detection

    Returns:
        DetectionResult with channel readiness assessment
    """
    analysis = analyze_spectrum(
        samples,
        sample_rate,
        detection_threshold_db=detection_threshold_db,
        min_snr_db=min_snr_db,
    )

    detections = [analysis.detection_18khz, analysis.detection_19khz]
    detected_count = sum(1 for d in detections if d.status == DetectionStatus.DETECTED)
    low_confidence_count = sum(1 for d in detections if d.status == DetectionStatus.LOW_CONFIDENCE)

    if detected_count == 2:
        channel_ready = True
        summary = "CHANNEL READY - Both tones detected reliably"
    elif detected_count == 1 and low_confidence_count == 0:
        channel_ready = False
        summary = "CHANNEL PARTIAL - One tone detected, other not present"
    elif detected_count == 1 and low_confidence_count == 1:
        channel_ready = False
        summary = "CHANNEL UNCLEAR - One tone detected, one low confidence"
    elif low_confidence_count >= 1:
        channel_ready = False
        summary = "CHANNEL UNCLEAR - Low confidence detections only"
    else:
        channel_ready = False
        summary = "CHANNEL NOT READY - No reliable tone detection"

    return DetectionResult(
        channel_ready=channel_ready,
        analysis=analysis,
        summary=summary,
    )


def find_peak_in_band(
    frequencies: np.ndarray,
    magnitudes: np.ndarray,
    band_range: tuple[float, float],
) -> tuple[Optional[float], Optional[float]]:
    """
    Find peak frequency and magnitude within a band.

    Returns:
        (peak_frequency, peak_magnitude) or (None, None) if band empty
    """
    f_low, f_high = band_range
    mask = (frequencies >= f_low) & (frequencies <= f_high)

    if not np.any(mask):
        return None, None

    band_freqs = frequencies[mask]
    band_mags = magnitudes[mask]
    peak_idx = np.argmax(band_mags)

    return float(band_freqs[peak_idx]), float(band_mags[peak_idx])