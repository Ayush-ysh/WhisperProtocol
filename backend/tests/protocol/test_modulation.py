"""Unit tests for WhisperProtocol modulation."""

import numpy as np
import pytest
from scipy.fft import rfft, rfftfreq

from whisper.protocol import (
    generate_symbol,
    modulate_bits,
    get_waveform_info,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    DEFAULT_AMPLITUDE,
    FREQ_ZERO,
    FREQ_ONE,
    SAMPLES_PER_SYMBOL,
)



def _measure_frequency(symbol: np.ndarray, sample_rate: int) -> float:
    """Measure frequency using FFT peak detection."""
    magnitudes = np.abs(rfft(symbol))
    frequencies = rfftfreq(len(symbol), 1.0 / sample_rate)
    peak_idx = np.argmax(magnitudes)
    return float(frequencies[peak_idx])


class TestGenerateSymbol:
    """Tests for single symbol generation."""

    def test_bit_zero_frequency(self):
        """Test bit 0 generates 18 kHz."""
        symbol = generate_symbol(0)
        measured_freq = _measure_frequency(symbol, DEFAULT_SAMPLE_RATE)
        assert abs(measured_freq - FREQ_ZERO) < 50  # Within 50 Hz

    def test_bit_one_frequency(self):
        """Test bit 1 generates 19 kHz."""
        symbol = generate_symbol(1)
        measured_freq = _measure_frequency(symbol, DEFAULT_SAMPLE_RATE)
        assert abs(measured_freq - FREQ_ONE) < 50  # Within 50 Hz

    def test_symbol_sample_count(self):
        """Test correct number of samples per symbol."""
        expected = int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)
        symbol = generate_symbol(0)
        assert len(symbol) == expected

    def test_symbol_dtype(self):
        """Test symbol is float32."""
        symbol = generate_symbol(0)
        assert symbol.dtype == np.float32

    def test_amplitude_range(self):
        """Test symbol amplitude within bounds."""
        symbol = generate_symbol(0, amplitude=0.5)
        assert np.max(np.abs(symbol)) <= 0.5 + 1e-6

    def test_max_amplitude(self):
        """Test symbol at max amplitude."""
        symbol = generate_symbol(0, amplitude=1.0)
        assert np.max(np.abs(symbol)) <= 1.0 + 1e-6

    def test_fade_in_out(self):
        """Test fade in/out applied."""
        symbol = generate_symbol(0)
        # First and last samples should be near zero
        assert abs(symbol[0]) < 1e-5
        assert abs(symbol[-1]) < 1e-5
        # Check that fade region (first 2ms) is not silent
        fade_samples = int(2.0 / 1000.0 * DEFAULT_SAMPLE_RATE)
        assert np.any(np.abs(symbol[:fade_samples]) > 1e-5)
        assert np.any(np.abs(symbol[-fade_samples:]) > 1e-5)

    def test_invalid_bit(self):
        """Test invalid bit raises error."""
        with pytest.raises(ValueError):
            generate_symbol(2)
        with pytest.raises(ValueError):
            generate_symbol(-1)

    def test_custom_parameters(self):
        """Test custom sample rate and duration."""
        sr = 48000
        dur = 0.01
        symbol = generate_symbol(0, sample_rate=sr, symbol_duration=dur)
        expected = int(sr * dur)
        assert len(symbol) == expected


class TestModulateBits:
    """Tests for bit sequence modulation."""

    def test_empty_bits(self):
        """Test empty bit list."""
        waveform = modulate_bits([])
        assert len(waveform) == 0

    def test_single_bit(self):
        """Test single bit modulation."""
        waveform = modulate_bits([0])
        expected = int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)
        assert len(waveform) == expected

    def test_multiple_bits(self):
        """Test multiple bit modulation."""
        bits = [0, 1, 0, 1, 0]
        waveform = modulate_bits(bits)
        expected = len(bits) * int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)
        assert len(waveform) == expected

    def test_alternating_bits(self):
        """Test alternating 0/1 pattern."""
        bits = [0, 1] * 10
        waveform = modulate_bits(bits)
        assert len(waveform) == 20 * int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)

    def test_waveform_normalized(self):
        """Test waveform stays within [-1, 1]."""
        bits = [0, 1] * 100
        waveform = modulate_bits(bits, amplitude=1.0)
        assert np.max(waveform) <= 1.0
        assert np.min(waveform) >= -1.0

    def test_deterministic(self):
        """Test deterministic output."""
        bits = [0, 1, 0, 1, 1, 0, 0, 1]
        w1 = modulate_bits(bits)
        w2 = modulate_bits(bits)
        np.testing.assert_array_equal(w1, w2)

    def test_custom_parameters(self):
        """Test custom modulation parameters."""
        sr = 48000
        dur = 0.01
        bits = [0, 1]
        waveform = modulate_bits(bits, sample_rate=sr, symbol_duration=dur)
        expected = 2 * int(sr * dur)
        assert len(waveform) == expected


class TestWaveformInfo:
    """Tests for waveform info utility."""

    def test_get_waveform_info(self):
        """Test get_waveform_info."""
        bits = [0, 1] * 10  # 20 bits
        info = get_waveform_info(bits)
        assert info['bit_count'] == 20
        assert info['sample_rate'] == DEFAULT_SAMPLE_RATE
        assert info['symbol_duration_ms'] == 20.0
        assert info['total_samples'] == 20 * SAMPLES_PER_SYMBOL
        assert abs(info['duration_seconds'] - 0.4) < 0.01