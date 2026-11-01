"""Unit tests for WhisperProtocol encoder."""

import numpy as np
import pytest

from whisper.protocol import (
    encode_message,
    save_waveform,
    EncodeResult,
    generate_symbol,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    DEFAULT_AMPLITUDE,
    FREQ_ZERO,
    FREQ_ONE,
)


class TestEncodeMessage:
    """Tests for full message encoding."""

    def test_encode_empty_string(self):
        """Test encoding empty string."""
        result = encode_message("")
        assert isinstance(result, EncodeResult)
        assert result.payload == ""
        assert result.payload_bytes == 0
        assert result.bit_count > 0  # Preamble + sync + length + checksum

    def test_encode_hello(self):
        """Test encoding 'HELLO'."""
        result = encode_message("HELLO")
        assert result.payload == "HELLO"
        assert result.payload_bytes == 5
        # Frame: 32 preamble + 16 sync + 16 length + 40 payload + 16 checksum = 120 bits
        assert result.frame_bits == 120
        assert result.bit_count == 120
        assert result.symbol_count == 120
        assert result.duration_seconds == pytest.approx(120 * DEFAULT_SYMBOL_DURATION, rel=0.01)

    def test_encode_unicode(self):
        """Test encoding unicode string."""
        result = encode_message("Hello 世界")
        assert result.payload == "Hello 世界"
        # UTF-8: Hello (5) + space (1) + 世 (3) + 界 (3) = 12 bytes
        assert result.payload_bytes == 12

    def test_encode_special_chars(self):
        """Test encoding with special characters."""
        result = encode_message("Test\n\r\t!")
        assert result.payload_bytes > 0

    def test_waveform_properties(self):
        """Test generated waveform properties."""
        result = encode_message("TEST")
        wf = result.waveform
        assert wf.dtype == np.float32
        assert np.max(np.abs(wf)) <= 1.0  # No clipping
        assert len(wf) == result.bit_count * int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)

    def test_custom_parameters(self):
        """Test encoding with custom parameters."""
        sr = 48000
        dur = 0.01
        amp = 0.5
        result = encode_message("TEST", sample_rate=sr, symbol_duration=dur, amplitude=amp)
        assert result.sample_rate == sr
        assert result.symbol_duration == dur
        assert np.max(np.abs(result.waveform)) <= amp + 1e-6

    def test_deterministic_output(self):
        """Test deterministic encoding."""
        r1 = encode_message("DETERMINISTIC")
        r2 = encode_message("DETERMINISTIC")
        np.testing.assert_array_equal(r1.waveform, r2.waveform)


class TestSaveWaveform:
    """Tests for WAV saving."""

    def test_save_pcm16(self, tmp_path):
        """Test saving as PCM_16."""
        result = encode_message("TEST")
        path = tmp_path / "test_pcm16.wav"
        save_waveform(result.waveform, path, DEFAULT_SAMPLE_RATE, subtype="PCM_16")
        assert path.exists()
        # Verify can load
        import soundfile as sf
        data, sr = sf.read(path)
        assert sr == DEFAULT_SAMPLE_RATE
        assert len(data) == len(result.waveform)

    def test_save_float(self, tmp_path):
        """Test saving as FLOAT."""
        result = encode_message("TEST")
        path = tmp_path / "test_float.wav"
        save_waveform(result.waveform, path, DEFAULT_SAMPLE_RATE, subtype="FLOAT")
        assert path.exists()
        import soundfile as sf
        data, sr = sf.read(path, dtype='float32')
        assert sr == DEFAULT_SAMPLE_RATE
        np.testing.assert_array_almost_equal(data.flatten(), result.waveform)

    def test_save_creates_directory(self, tmp_path):
        """Test save creates parent directories."""
        result = encode_message("TEST")
        path = tmp_path / "subdir" / "test.wav"
        save_waveform(result.waveform, path, DEFAULT_SAMPLE_RATE)
        assert path.exists()


class TestEncodeResult:
    """Tests for EncodeResult dataclass."""

    def test_encode_result_str(self):
        """Test EncodeResult string representation."""
        result = encode_message("HELLO")
        s = str(result)
        assert "HELLO" in s
        assert "payload_bytes=5" in s
        assert "frame_bits" in s

    def test_encode_result_fields(self):
        """Test EncodeResult has all required fields."""
        result = encode_message("TEST")
        assert hasattr(result, 'waveform')
        assert hasattr(result, 'sample_rate')
        assert hasattr(result, 'symbol_duration')
        assert hasattr(result, 'payload')
        assert hasattr(result, 'payload_bytes')
        assert hasattr(result, 'frame_bits')
        assert hasattr(result, 'bit_count')
        assert hasattr(result, 'symbol_count')
        assert hasattr(result, 'duration_seconds')


class TestFrequencyContent:
    """Tests for frequency content of generated waveforms."""

    def test_18khz_energy_present(self):
        """Test 18 kHz energy present for bit 0."""
        symbol = generate_symbol(0)
        from scipy.fft import rfft, rfftfreq
        mags = np.abs(rfft(symbol))
        freqs = rfftfreq(len(symbol), 1/DEFAULT_SAMPLE_RATE)
        # Find 18 kHz bin
        idx = np.argmin(np.abs(freqs - FREQ_ZERO))
        assert mags[idx] > 0.1  # Significant energy

    def test_19khz_energy_present(self):
        """Test 19 kHz energy present for bit 1."""
        symbol = generate_symbol(1)
        from scipy.fft import rfft, rfftfreq
        mags = np.abs(rfft(symbol))
        freqs = rfftfreq(len(symbol), 1/DEFAULT_SAMPLE_RATE)
        idx = np.argmin(np.abs(freqs - FREQ_ONE))
        assert mags[idx] > 0.1

    def test_message_has_both_frequencies(self):
        """Test encoded message has both frequencies."""
        # Message with both 0 and 1 bits
        result = encode_message("AB")  # A=0x41, B=0x42 have both 0 and 1 bits
        from scipy.fft import rfft, rfftfreq
        mags = np.abs(rfft(result.waveform))
        freqs = rfftfreq(len(result.waveform), 1/DEFAULT_SAMPLE_RATE)
        # Should have energy at both frequencies
        idx18 = np.argmin(np.abs(freqs - FREQ_ZERO))
        idx19 = np.argmin(np.abs(freqs - FREQ_ONE))
        assert mags[idx18] > 0.1
        assert mags[idx19] > 0.1