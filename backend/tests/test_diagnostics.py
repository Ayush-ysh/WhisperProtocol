"""Unit tests for WhisperProtocol diagnostics and FFT analysis."""

import numpy as np
import pytest

from whisper.audio.diagnostics import (
    FREQUENCY_BAND_18KHZ,
    FREQUENCY_BAND_19KHZ,
    DEFAULT_DETECTION_THRESHOLD_DB,
    DEFAULT_MIN_SNR_DB,
    DetectionStatus,
    NoiseFloorEstimate,
    ToneDetection,
    SpectrumAnalysis,
    DetectionResult,
    estimate_noise_floor,
    analyze_band,
    analyze_spectrum,
    detect_test_tone,
    find_peak_in_band,
)
from whisper.audio.signal import (
    TONE_FREQUENCY_BIT_0,
    TONE_FREQUENCY_BIT_1,
    DEFAULT_SAMPLE_RATE,
    generate_tone,
)


class TestNoiseFloorEstimation:
    """Tests for noise floor estimation."""

    def test_estimate_noise_floor_silent(self):
        """Test noise floor on silent signal."""
        magnitudes = np.zeros(1000, dtype=np.float32)
        nf = estimate_noise_floor(magnitudes)
        assert nf.mean_magnitude == 0.0
        assert nf.median_magnitude == 0.0
        assert nf.estimated_db == -np.inf

    def test_estimate_noise_floor_constant(self):
        """Test noise floor on constant magnitude."""
        magnitudes = np.ones(1000, dtype=np.float32) * 0.01
        nf = estimate_noise_floor(magnitudes)
        assert nf.mean_magnitude == pytest.approx(0.01, rel=1e-5)
        assert nf.median_magnitude == pytest.approx(0.01, rel=1e-5)
        assert nf.estimated_db == pytest.approx(20 * np.log10(0.01), rel=1e-5)

    def test_estimate_noise_floor_with_peaks(self):
        """Test noise floor robust to signal peaks."""
        magnitudes = np.ones(1000, dtype=np.float32) * 0.01
        magnitudes[500] = 1.0
        nf = estimate_noise_floor(magnitudes)
        assert nf.median_magnitude == pytest.approx(0.01, rel=1e-3)


class TestBandAnalysis:
    """Tests for frequency band analysis."""

    def test_analyze_band_empty(self):
        """Test analysis of empty band."""
        freqs = np.array([1000.0, 2000.0, 3000.0])
        mags = np.array([0.1, 0.2, 0.3])
        nf = NoiseFloorEstimate(0.1, 0.1, 0.0, 0.1, 0.1, -20.0)

        result = analyze_band(freqs, mags, (5000.0, 6000.0), "Test", nf)

        assert result.status == DetectionStatus.NOT_DETECTED
        assert result.peak_frequency is None

    def test_analyze_band_with_signal(self):
        """Test analysis with signal in band."""
        freqs = np.linspace(17000, 20000, 1000)
        mags = np.ones(1000) * 0.01
        peak_idx = np.argmin(np.abs(freqs - 18000))
        mags[peak_idx] = 1.0
        nf = NoiseFloorEstimate(0.01, 0.01, 0.0, 0.01, 0.01, -40.0)

        result = analyze_band(freqs, mags, FREQUENCY_BAND_18KHZ, "18 kHz", nf)

        assert result.status == DetectionStatus.DETECTED
        assert result.peak_frequency == pytest.approx(18000, abs=50)
        assert result.snr_db is not None
        assert result.snr_db > 20


class TestSpectrumAnalysis:
    """Tests for full spectrum analysis."""

    def test_analyze_spectrum_sine_18khz(self):
        """Test FFT analysis detects 18 kHz tone."""
        duration = 1.0
        tone = generate_tone(TONE_FREQUENCY_BIT_0, duration, DEFAULT_SAMPLE_RATE)
        tone = tone * 0.5

        analysis = analyze_spectrum(tone, DEFAULT_SAMPLE_RATE)

        assert analysis.peak_frequency == pytest.approx(TONE_FREQUENCY_BIT_0, abs=10)
        assert analysis.detection_18khz.status == DetectionStatus.DETECTED
        assert analysis.detection_18khz.peak_frequency == pytest.approx(TONE_FREQUENCY_BIT_0, abs=50)
        assert analysis.detection_19khz.status != DetectionStatus.DETECTED

    def test_analyze_spectrum_sine_19khz(self):
        """Test FFT analysis detects 19 kHz tone."""
        duration = 1.0
        tone = generate_tone(TONE_FREQUENCY_BIT_1, duration, DEFAULT_SAMPLE_RATE)
        tone = tone * 0.5

        analysis = analyze_spectrum(tone, DEFAULT_SAMPLE_RATE)

        assert analysis.peak_frequency == pytest.approx(TONE_FREQUENCY_BIT_1, abs=10)
        assert analysis.detection_19khz.status == DetectionStatus.DETECTED
        assert analysis.detection_19khz.peak_frequency == pytest.approx(TONE_FREQUENCY_BIT_1, abs=50)
        assert analysis.detection_18khz.status != DetectionStatus.DETECTED

    def test_analyze_spectrum_noise_only(self):
        """Test FFT analysis on noise does not false detect."""
        np.random.seed(42)
        duration = 1.0
        noise = np.random.normal(0, 0.01, int(duration * DEFAULT_SAMPLE_RATE)).astype(np.float32)

        analysis = analyze_spectrum(noise, DEFAULT_SAMPLE_RATE)

        assert analysis.detection_18khz.status != DetectionStatus.DETECTED
        assert analysis.detection_19khz.status != DetectionStatus.DETECTED


class TestToneDetection:
    """Tests for test tone detection."""

    def test_detect_test_tone_18khz(self):
        """Test detection of 18 kHz tone."""
        duration = 1.0
        tone = generate_tone(TONE_FREQUENCY_BIT_0, duration, DEFAULT_SAMPLE_RATE)
        tone = tone * 0.5

        result = detect_test_tone(tone, DEFAULT_SAMPLE_RATE)

        assert result.analysis.detection_18khz.status == DetectionStatus.DETECTED
        assert "DETECTED" in result.summary or "PARTIAL" in result.summary

    def test_detect_test_tone_19khz(self):
        """Test detection of 19 kHz tone."""
        duration = 1.0
        tone = generate_tone(TONE_FREQUENCY_BIT_1, duration, DEFAULT_SAMPLE_RATE)
        tone = tone * 0.5

        result = detect_test_tone(tone, DEFAULT_SAMPLE_RATE)

        assert result.analysis.detection_19khz.status == DetectionStatus.DETECTED
        assert "DETECTED" in result.summary or "PARTIAL" in result.summary

    def test_detect_test_tone_both(self):
        """Test detection of both tones."""
        duration = 1.0
        tone18 = generate_tone(TONE_FREQUENCY_BIT_0, duration, DEFAULT_SAMPLE_RATE) * 0.5
        tone19 = generate_tone(TONE_FREQUENCY_BIT_1, duration, DEFAULT_SAMPLE_RATE) * 0.5
        both = tone18 + tone19

        result = detect_test_tone(both, DEFAULT_SAMPLE_RATE)

        assert result.analysis.detection_18khz.status == DetectionStatus.DETECTED
        assert result.analysis.detection_19khz.status == DetectionStatus.DETECTED
        assert result.channel_ready is True
        assert "READY" in result.summary

    def test_detect_test_tone_noise_only(self):
        """Test noise-only signal reports not ready."""
        np.random.seed(42)
        duration = 1.0
        noise = np.random.normal(0, 0.01, int(duration * DEFAULT_SAMPLE_RATE)).astype(np.float32)

        result = detect_test_tone(noise, DEFAULT_SAMPLE_RATE)

        assert result.channel_ready is False
        assert "NOT READY" in result.summary or "UNCLEAR" in result.summary


class TestPeakFinding:
    """Tests for peak finding in frequency bands."""

    def test_find_peak_in_band(self):
        """Test finding peak in band."""
        freqs = np.linspace(17000, 20000, 1000)
        mags = np.ones(1000) * 0.01
        peak_idx = np.argmin(np.abs(freqs - 18500))
        mags[peak_idx] = 1.0

        peak_freq, peak_mag = find_peak_in_band(freqs, mags, (18000, 19000))

        assert peak_freq == pytest.approx(18500, abs=50)
        assert peak_mag == pytest.approx(1.0, rel=1e-5)

    def test_find_peak_in_empty_band(self):
        """Test finding peak in empty band."""
        freqs = np.array([1000.0, 2000.0])
        mags = np.array([0.1, 0.2])

        peak_freq, peak_mag = find_peak_in_band(freqs, mags, (5000, 6000))

        assert peak_freq is None
        assert peak_mag is None