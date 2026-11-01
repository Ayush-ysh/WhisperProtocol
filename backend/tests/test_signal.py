"""Unit tests for WhisperProtocol signal generation."""

import numpy as np
import pytest

from whisper.audio.signal import (
    TONE_FREQUENCY_BIT_0,
    TONE_FREQUENCY_BIT_1,
    DEFAULT_SAMPLE_RATE,
    MAX_AMPLITUDE,
    FADE_DURATION_MS,
    generate_tone,
    generate_18khz_tone,
    generate_19khz_tone,
    generate_tone_sequence,
)


class TestToneGeneration:
    """Tests for tone generation functions."""

    def test_generate_tone_basic(self):
        """Test basic tone generation."""
        duration = 1.0
        freq = 1000.0
        sr = DEFAULT_SAMPLE_RATE

        tone = generate_tone(freq, duration, sr)

        expected_samples = int(duration * sr)
        assert len(tone) == expected_samples
        assert tone.dtype == np.float32

    def test_generate_tone_amplitude_range(self):
        """Test that tone amplitude is within bounds."""
        tone = generate_tone(1000.0, 1.0, DEFAULT_SAMPLE_RATE, amplitude=0.5)
        assert np.max(np.abs(tone)) <= 0.5 + 1e-6

    def test_generate_tone_max_amplitude(self):
        """Test tone at maximum amplitude."""
        tone = generate_tone(1000.0, 1.0, DEFAULT_SAMPLE_RATE, amplitude=1.0)
        assert np.max(np.abs(tone)) <= 1.0 + 1e-6

    def test_generate_tone_fade_in_out(self):
        """Test that fade in/out is applied."""
        duration = 1.0
        fade_ms = 10.0
        sr = DEFAULT_SAMPLE_RATE
        fade_samples = int(fade_ms / 1000.0 * sr)

        tone = generate_tone(1000.0, duration, sr, fade_ms=fade_ms)

        assert tone[0] == 0.0
        # Check that fade region is not zero (has some signal)
        assert np.any(tone[:fade_samples] != 0.0)
        assert tone[-1] == 0.0
        assert np.any(tone[-fade_samples:] != 0.0)

    def test_generate_tone_no_fade(self):
        """Test tone without fade."""
        tone = generate_tone(1000.0, 1.0, DEFAULT_SAMPLE_RATE, fade_ms=0.0)
        assert tone[0] != 0.0 or tone[-1] != 0.0

    def test_generate_18khz_tone(self):
        """Test 18 kHz tone generation."""
        tone = generate_18khz_tone(0.5, DEFAULT_SAMPLE_RATE)
        assert len(tone) == int(0.5 * DEFAULT_SAMPLE_RATE)
        assert tone.dtype == np.float32
        # Check it's not silent
        assert np.max(np.abs(tone)) > 0.1

    def test_generate_19khz_tone(self):
        """Test 19 kHz tone generation."""
        tone = generate_19khz_tone(0.5, DEFAULT_SAMPLE_RATE)
        assert len(tone) == int(0.5 * DEFAULT_SAMPLE_RATE)
        assert tone.dtype == np.float32
        assert np.max(np.abs(tone)) > 0.1

    def test_generate_tone_sequence(self):
        """Test bit sequence generation."""
        bits = "0101"
        bit_duration = 0.1
        sr = DEFAULT_SAMPLE_RATE

        seq = generate_tone_sequence(bits, bit_duration, sr)

        expected_samples = len(bits) * int(bit_duration * sr)
        assert len(seq) == expected_samples

    def test_generate_tone_sequence_with_gap(self):
        """Test bit sequence with gaps."""
        bits = "01"
        bit_duration = 0.1
        gap = 0.05
        sr = DEFAULT_SAMPLE_RATE

        seq = generate_tone_sequence(bits, bit_duration, sr, gap_duration=gap)

        bit_samples = int(bit_duration * sr)
        gap_samples = int(gap * sr)
        expected = 2 * bit_samples + gap_samples
        assert len(seq) == expected

    def test_generate_tone_invalid_frequency(self):
        """Test that invalid frequency raises error."""
        with pytest.raises(ValueError):
            generate_tone(0, 1.0, DEFAULT_SAMPLE_RATE)

    def test_generate_tone_invalid_duration(self):
        """Test that invalid duration raises error."""
        with pytest.raises(ValueError):
            generate_tone(1000.0, 0, DEFAULT_SAMPLE_RATE)

    def test_generate_tone_invalid_amplitude(self):
        """Test that invalid amplitude raises error."""
        with pytest.raises(ValueError):
            generate_tone(1000.0, 1.0, DEFAULT_SAMPLE_RATE, amplitude=1.5)

    def test_generate_tone_no_clipping(self):
        """Test that output is clipped to [-1, 1]."""
        tone = generate_tone(1000.0, 1.0, DEFAULT_SAMPLE_RATE, amplitude=1.0)
        assert np.max(tone) <= 1.0
        assert np.min(tone) >= -1.0