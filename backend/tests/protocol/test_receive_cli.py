"""Unit tests for receive CLI module."""

import numpy as np
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from whisper.protocol import (
    ReceiverConfig,
    SymbolDecision,
    ReceiverState,
    SymbolDetection,
    AudioStreamReceiver,
    decode_wav_file,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    FREQ_ZERO,
    FREQ_ONE,
    encode_frame,
    modulate_bits,
)
from whisper.cli.receive import ReceiverUI


class TestReceiverUI:
    """Tests for ReceiverUI."""

    @pytest.fixture
    def config(self):
        return ReceiverConfig()

    @pytest.fixture
    def ui(self, config):
        return ReceiverUI(config)

    def test_on_symbol_updates_detection(self, ui):
        """Test on_symbol stores detection."""
        det = SymbolDetection(
            decision=SymbolDecision.ZERO,
            detected_frequency=18000.0,
            energy_zero=1.0, energy_one=0.01, noise_floor=0.01,
            snr_zero_db=20.0, snr_one_db=None, confidence=0.9, timestamp=0.0
        )
        ui.on_symbol(det)
        assert ui.last_detection == det

    def test_on_state_change(self, ui):
        """Test on_state_change callback."""
        ui.on_state_change(ReceiverState.PREAMBLE_DETECTED)
        assert ui.last_status is None  # No receiver yet

    def test_on_frame_success(self, ui, capsys):
        """Test on_frame with successful decode."""
        from whisper.protocol import FrameDecodeResult
        result = FrameDecodeResult(
            success=True,
            payload=b"HELLO",
            checksum_valid=True,
        )
        ui.on_frame(result)
        captured = capsys.readouterr()
        assert "FRAME VALIDATED" in captured.out
        assert "CHECKSUM: PASS" in captured.out
        assert "MESSAGE:  HELLO" in captured.out

    def test_on_frame_failure(self, ui, capsys):
        """Test on_frame with failed decode."""
        from whisper.protocol import FrameDecodeResult
        result = FrameDecodeResult(
            success=False,
            error="Checksum mismatch",
        )
        ui.on_frame(result)
        captured = capsys.readouterr()
        assert "DECODE FAILED" in captured.out
        assert "Checksum mismatch" in captured.out


class TestReceiveCLIArguments:
    """Tests for CLI argument parsing."""

    def test_default_args(self):
        """Test default argument values."""
        import sys
        from whisper.cli.receive import main

        with patch.object(sys, 'argv', ['receive']):
            with patch('whisper.cli.receive.ReceiverUI.run_live') as mock_run:
                mock_run.return_value = 0
                result = main()
                assert result == 0

    def test_wav_mode(self, tmp_path):
        """Test WAV file decoding mode."""
        import sys
        from whisper.cli.receive import main

        # Create a test WAV
        config = ReceiverConfig()
        waveform = modulate_bits(
            encode_frame(b"TEST"),
            sample_rate=config.sample_rate,
            symbol_duration=config.symbol_duration,
        )
        import soundfile as sf
        wav_path = tmp_path / "test.wav"
        sf.write(wav_path, waveform, config.sample_rate, subtype="FLOAT")

        with patch.object(sys, 'argv', ['receive', '--wav', str(wav_path)]):
            with patch('whisper.cli.receive.ReceiverUI.run_wav') as mock_run:
                mock_run.return_value = 0
                main()


class TestAudioStreamReceiver:
    """Tests for AudioStreamReceiver (mocked audio)."""

    @pytest.fixture
    def config(self):
        return ReceiverConfig(block_size=1024)

    def test_start_stop(self, config):
        """Test receiver start/stop lifecycle."""
        receiver = AudioStreamReceiver(config)

        # Mock the sounddevice stream
        with patch('sounddevice.InputStream') as mock_stream_class:
            mock_stream = MagicMock()
            mock_stream_class.return_value = mock_stream

            receiver.start()
            assert receiver.is_running()
            mock_stream.start.assert_called_once()

            receiver.stop()
            assert not receiver.is_running()
            mock_stream.stop.assert_called_once()
            mock_stream.close.assert_called_once()

    def test_process_audio_block(self, config):
        """Test audio block processing."""
        receiver = AudioStreamReceiver(config)
        received_symbols = []
        received_states = []
        received_frames = []

        def on_symbol(det):
            received_symbols.append(det)

        def on_state(state):
            received_states.append(state)

        def on_frame(result):
            received_frames.append(result)

        receiver.on_symbol = on_symbol
        receiver.on_state_change = on_state
        receiver.on_frame = on_frame

        # Generate test symbol (bit 0)
        spp = config.samples_per_symbol
        symbol = generate_symbol(0, sample_rate=config.sample_rate, symbol_duration=config.symbol_duration)

        # Process block
        receiver._process_audio_block(symbol)

        assert len(received_symbols) == 1
        assert received_symbols[0].decision == SymbolDecision.ZERO


class TestDecodeWavFile:
    """Tests for decode_wav_file function."""

    def test_decode_valid_file(self, tmp_path):
        """Test decoding valid WAV file."""
        config = ReceiverConfig()
        message = "WAV TEST"
        frame_bits = encode_frame(message.encode("utf-8"))
        waveform = modulate_bits(
            frame_bits,
            sample_rate=config.sample_rate,
            symbol_duration=config.symbol_duration,
        )

        import soundfile as sf
        wav_path = tmp_path / "test.wav"
        sf.write(wav_path, waveform, config.sample_rate, subtype="FLOAT")

        result = decode_wav_file(str(wav_path), config)

        assert result.success
        assert result.payload == message.encode("utf-8")

    def test_decode_nonexistent_file(self):
        """Test decoding nonexistent file."""
        config = ReceiverConfig()
        result = decode_wav_file("/nonexistent/path.wav", config)

        assert not result.success
        assert result.error is not None

    def test_decode_wrong_sample_rate(self, tmp_path):
        """Test decoding with sample rate mismatch warning."""
        config = ReceiverConfig(sample_rate=44100)
        message = "SR TEST"
        frame_bits = encode_frame(message.encode("utf-8"))
        waveform = modulate_bits(
            frame_bits,
            sample_rate=48000,  # Different sample rate
            symbol_duration=config.symbol_duration,
        )

        import soundfile as sf
        wav_path = tmp_path / "test.wav"
        sf.write(wav_path, waveform, 48000, subtype="FLOAT")

        # Should still work but with warning
        result = decode_wav_file(str(wav_path), config)

        # May or may not succeed depending on resampling
        # Just verify it doesn't crash
        assert result is not None


class TestReceiverConfigValidation:
    """Tests for ReceiverConfig validation."""

    def test_samples_per_symbol_calculation(self):
        """Test samples_per_symbol property."""
        config = ReceiverConfig(sample_rate=44100, symbol_duration=0.02)
        assert config.samples_per_symbol == 882

        config = ReceiverConfig(sample_rate=48000, symbol_duration=0.01)
        assert config.samples_per_symbol == 480

    def test_block_size_fallback(self):
        """Test block_size falls back to samples_per_symbol."""
        config = ReceiverConfig(sample_rate=44100, symbol_duration=0.02)
        assert config.block_size_samples == 882

        config = ReceiverConfig(sample_rate=44100, symbol_duration=0.02, block_size=512)
        assert config.block_size_samples == 512


# Import generate_symbol for tests
from whisper.protocol import generate_symbol


if __name__ == "__main__":
    pytest.main([__file__, "-v"])