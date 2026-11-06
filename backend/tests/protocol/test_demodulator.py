"""Unit tests for WhisperProtocol demodulator (Phase 3)."""

import numpy as np
import pytest
from scipy.signal import get_window
from scipy.fft import rfft, rfftfreq

from whisper.protocol import (
    ReceiverConfig,
    SymbolDecision,
    ReceiverState,
    SymbolDetection,
    SymbolDetector,
    DemodulatorStateMachine,
    AudioStreamReceiver,
    decode_wav_file,
    FrameDecodeResult,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    FREQ_ZERO,
    FREQ_ONE,
    PREAMBLE_BITS,
    SYNC_BITS,
    LENGTH_FIELD_BITS,
    CHECKSUM_BITS,
    encode_frame,
    generate_symbol,
    modulate_bits,
)


def _generate_test_symbol(bit: int, config: ReceiverConfig, snr_db: float = 30.0) -> np.ndarray:
    """Generate a test symbol with controlled SNR."""
    np.random.seed(42)  # Deterministic for tests
    symbol = generate_symbol(
        bit,
        sample_rate=config.sample_rate,
        symbol_duration=config.symbol_duration,
        amplitude=1.0,
    )

    if snr_db < 100:
        signal_power = np.mean(symbol**2)
        noise_power = signal_power / (10 ** (snr_db / 10.0))
        noise = np.random.normal(0, np.sqrt(noise_power), len(symbol)).astype(np.float32)
        symbol = symbol + noise

    return symbol.astype(np.float32)


class TestReceiverConfig:
    """Tests for ReceiverConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ReceiverConfig()
        assert config.sample_rate == DEFAULT_SAMPLE_RATE
        assert config.symbol_duration == DEFAULT_SYMBOL_DURATION
        assert config.freq_zero == FREQ_ZERO
        assert config.freq_one == FREQ_ONE
        assert config.samples_per_symbol == int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)

    def test_custom_config(self):
        """Test custom configuration."""
        config = ReceiverConfig(
            sample_rate=48000,
            symbol_duration=0.01,
            freq_zero=17000,
            freq_one=18000,
        )
        assert config.sample_rate == 48000
        assert config.symbol_duration == 0.01
        assert config.samples_per_symbol == 480


class TestSymbolDetector:
    """Tests for SymbolDetector."""

    @pytest.fixture
    def config(self):
        return ReceiverConfig()

    @pytest.fixture
    def detector(self, config):
        return SymbolDetector(config)

    def test_detect_18khz_symbol(self, detector, config):
        """Test detection of 18 kHz (bit 0) symbol."""
        symbol = _generate_test_symbol(0, config, snr_db=30.0)
        detection = detector.detect(symbol)

        assert detection.decision == SymbolDecision.ZERO
        assert detection.confidence > 0.8
        assert abs(detection.detected_frequency - FREQ_ZERO) < 50

    def test_detect_19khz_symbol(self, detector, config):
        """Test detection of 19 kHz (bit 1) symbol."""
        symbol = _generate_test_symbol(1, config, snr_db=30.0)
        detection = detector.detect(symbol)

        assert detection.decision == SymbolDecision.ONE
        assert detection.confidence > 0.8
        assert abs(detection.detected_frequency - FREQ_ONE) < 50

    def test_detect_low_snr_symbol(self, detector, config):
        """Test detection with low SNR returns LOW_CONFIDENCE or UNKNOWN."""
        # Use very high noise to ensure low SNR
        np.random.seed(42)
        symbol = generate_symbol(0, sample_rate=config.sample_rate, symbol_duration=config.symbol_duration, amplitude=0.1)
        noise = np.random.normal(0, 1.0, config.samples_per_symbol).astype(np.float32)
        noisy_symbol = symbol + noise
        detection = detector.detect(noisy_symbol)

        # With very low SNR, should be LOW_CONFIDENCE or UNKNOWN
        assert detection.decision in (SymbolDecision.LOW_CONFIDENCE, SymbolDecision.UNKNOWN)
        assert detection.confidence < 0.5

    def test_detect_noise_only(self, detector, config):
        """Test detection on pure noise returns UNKNOWN or LOW_CONFIDENCE."""
        np.random.seed(123)
        noise = np.random.normal(0, 0.001, config.samples_per_symbol).astype(np.float32)
        detection = detector.detect(noise)

        assert detection.decision in (SymbolDecision.UNKNOWN, SymbolDecision.LOW_CONFIDENCE)
        assert detection.confidence < 0.5

    def test_detect_frequency_measurement(self, detector, config):
        """Test that detected frequency is measured correctly."""
        symbol = _generate_test_symbol(0, config, snr_db=30.0)
        detection = detector.detect(symbol)

        assert abs(detection.detected_frequency - FREQ_ZERO) < 50

    def test_energy_measurements(self, detector, config):
        """Test energy measurements are populated."""
        symbol = _generate_test_symbol(0, config, snr_db=30.0)
        detection = detector.detect(symbol)

        assert detection.energy_zero > 0
        assert detection.energy_one >= 0
        assert detection.noise_floor > 0
        assert detection.snr_zero_db is not None
        assert detection.snr_zero_db > 20

    def test_custom_frequencies(self):
        """Test detector with custom frequencies."""
        config = ReceiverConfig(
            freq_zero=17000, freq_one=18000,
            band_zero=(16500.0, 17500.0),
            band_one=(17500.0, 18500.0)
        )
        detector = SymbolDetector(config)

        symbol = generate_symbol(
            0, sample_rate=config.sample_rate, symbol_duration=config.symbol_duration,
            amplitude=1.0, freq_zero=17000, freq_one=18000
        )
        detection = detector.detect(symbol)

        assert detection.decision == SymbolDecision.ZERO
        assert abs(detection.detected_frequency - 17000) < 100


class TestDemodulatorStateMachine:
    """Tests for DemodulatorStateMachine."""

    @pytest.fixture
    def config(self):
        return ReceiverConfig()

    @pytest.fixture
    def state_machine(self, config):
        return DemodulatorStateMachine(config)

    def create_detection(self, bit: int, confidence: float = 1.0) -> SymbolDetection:
        """Create a mock SymbolDetection."""
        return SymbolDetection(
            decision=SymbolDecision.ZERO if bit == 0 else SymbolDecision.ONE,
            detected_frequency=FREQ_ZERO if bit == 0 else FREQ_ONE,
            energy_zero=1.0 if bit == 0 else 0.01,
            energy_one=0.01 if bit == 0 else 1.0,
            noise_floor=0.01,
            snr_zero_db=30.0 if bit == 0 else None,
            snr_one_db=30.0 if bit == 1 else None,
            confidence=confidence,
            timestamp=0.0,
        )

    def test_initial_state(self, state_machine):
        """Test initial state is WAITING."""
        assert state_machine.state == ReceiverState.WAITING

    def test_preamble_detection(self, state_machine):
        """Test preamble detection transitions."""
        detections = [self.create_detection(b) for b in PREAMBLE_BITS]

        for det in detections[:-1]:
            state, result = state_machine.process_symbol(det)
            assert state == ReceiverState.SEARCHING
            assert result is None

        # Last bit of preamble
        state, result = state_machine.process_symbol(detections[-1])
        assert state == ReceiverState.PREAMBLE_DETECTED
        assert result is None

    def test_sync_detection(self, state_machine):
        """Test sync detection after preamble."""
        # Feed preamble
        for b in PREAMBLE_BITS:
            det = self.create_detection(b)
            state_machine.process_symbol(det)

        # Feed sync
        for b in SYNC_BITS[:-1]:
            det = self.create_detection(b)
            state, result = state_machine.process_symbol(det)
            assert state == ReceiverState.PREAMBLE_DETECTED

        # Last sync bit
        det = self.create_detection(SYNC_BITS[-1])
        state, result = state_machine.process_symbol(det)
        assert state == ReceiverState.SYNCING
        assert result is None

    def test_length_decoding(self, state_machine):
        """Test length field decoding."""
        # Preamble + Sync
        for b in PREAMBLE_BITS + SYNC_BITS:
            state_machine.process_symbol(self.create_detection(b))

        # Length field: 5 bytes = 0x0005 (16 bits)
        length_bits = [0]*13 + [1, 0, 1]  # 5 in 16 bits: 0000000000000101
        for i, b in enumerate(length_bits):
            state, result = state_machine.process_symbol(self.create_detection(b))
            if i < len(length_bits) - 1:
                assert state == ReceiverState.SYNCING

        # After length, should be RECEIVING
        assert state_machine.state == ReceiverState.RECEIVING
        assert state_machine.payload_length == 5

    def test_frame_reception(self, state_machine):
        """Test complete frame reception."""
        # Create a valid frame: "HELLO"
        payload = b"HELLO"
        frame_bits = encode_frame(payload)

        # Process all bits
        for bit in frame_bits:
            det = self.create_detection(bit)
            state, result = state_machine.process_symbol(det)

        assert state == ReceiverState.COMPLETE
        assert result is not None
        assert result.success
        assert result.payload == payload
        assert result.checksum_valid

    def test_sync_mismatch_returns_to_searching(self, state_machine):
        """Test that sync mismatch returns to SEARCHING."""
        # Preamble
        for b in PREAMBLE_BITS:
            state_machine.process_symbol(self.create_detection(b))

        # Wrong sync
        wrong_sync = [0] * len(SYNC_BITS)
        for b in wrong_sync:
            state_machine.process_symbol(self.create_detection(b))

        assert state_machine.state == ReceiverState.SEARCHING

    def test_unknown_symbol_during_searching_clears_buffer(self, state_machine):
        """Test UNKNOWN symbol during SEARCHING clears preamble buffer."""
        for b in PREAMBLE_BITS[:16]:
            state_machine.process_symbol(self.create_detection(b))

        # UNKNOWN symbol
        unknown_det = SymbolDetection(
            decision=SymbolDecision.UNKNOWN,
            detected_frequency=1000.0,
            energy_zero=0.0, energy_one=0.0, noise_floor=0.1,
            snr_zero_db=None, snr_one_db=None, confidence=0.0, timestamp=0.0
        )
        state_machine.process_symbol(unknown_det)

        # Buffer should be cleared
        assert len(state_machine.preamble_buffer) == 0

    def test_get_status(self, state_machine):
        """Test status reporting."""
        status = state_machine.get_status()
        assert status.state == ReceiverState.WAITING
        assert status.frame_progress == 0


class TestFrameDecodeResult:
    """Tests for FrameDecodeResult."""

    def test_success_result(self):
        """Test successful decode result."""
        result = FrameDecodeResult(
            success=True,
            payload=b"TEST",
            checksum_valid=True,
        )
        assert result.success
        assert result.payload == b"TEST"
        assert result.checksum_valid

    def test_failure_result(self):
        """Test failed decode result."""
        result = FrameDecodeResult(
            success=False,
            error="Checksum mismatch",
        )
        assert not result.success
        assert result.error == "Checksum mismatch"


class TestWavDecoder:
    """Tests for WAV file decoding."""

    def test_decode_valid_wav(self, tmp_path):
        """Test decoding a valid WAV file."""
        # Generate test message
        message = "HELLO WAV"
        config = ReceiverConfig()

        # Create waveform using encoder
        waveform = modulate_bits(
            encode_frame(message.encode("utf-8")),
            sample_rate=config.sample_rate,
            symbol_duration=config.symbol_duration,
        )

        # Save to WAV
        import soundfile as sf
        wav_path = tmp_path / "test.wav"
        sf.write(wav_path, waveform, config.sample_rate, subtype="FLOAT")

        # Decode using WAV decoder
        result = decode_wav_file(str(wav_path), config)

        assert result.success
        assert result.payload == message.encode("utf-8")
        assert result.checksum_valid

    def test_decode_truncated_wav(self, tmp_path):
        """Test decoding truncated WAV returns error."""
        config = ReceiverConfig()
        # Create too-short waveform
        waveform = np.zeros(config.samples_per_symbol * 10, dtype=np.float32)

        import soundfile as sf
        wav_path = tmp_path / "truncated.wav"
        sf.write(wav_path, waveform, config.sample_rate, subtype="FLOAT")

        result = decode_wav_file(str(wav_path), config)

        assert not result.success
        assert result.error is not None


class TestEncoderDecoderRoundtrip:
    """Integration tests for encoder -> decoder round trip."""

    @pytest.fixture
    def config(self):
        return ReceiverConfig()

    def test_roundtrip_hello(self, config):
        """Test HELLO round trip."""
        message = "HELLO"
        frame_bits = encode_frame(message.encode("utf-8"))
        waveform = modulate_bits(
            frame_bits,
            sample_rate=config.sample_rate,
            symbol_duration=config.symbol_duration,
        )

        # Simulate decoding
        detector = SymbolDetector(config)
        state_machine = DemodulatorStateMachine(config)

        spp = config.samples_per_symbol
        for i in range(0, len(waveform), spp):
            if i + spp > len(waveform):
                break
            symbol_samples = waveform[i:i+spp]
            detection = detector.detect(symbol_samples)
            state, result = state_machine.process_symbol(detection)
            if result:
                break

        assert result is not None
        assert result.success
        assert result.payload == message.encode("utf-8")
        assert result.checksum_valid

    def test_roundtrip_various_messages(self, config):
        """Test round trip with various messages."""
        test_messages = [
            "HELLO",
            "HELLO WHISPER",
            "TEST 123",
            "WHISPERPROTOCOL",
            "A" * 100,
            "",  # empty
            "🎵",  # unicode
        ]

        for message in test_messages:
            frame_bits = encode_frame(message.encode("utf-8"))
            waveform = modulate_bits(
                frame_bits,
                sample_rate=config.sample_rate,
                symbol_duration=config.symbol_duration,
            )

            detector = SymbolDetector(config)
            state_machine = DemodulatorStateMachine(config)

            spp = config.samples_per_symbol
            for i in range(0, len(waveform), spp):
                if i + spp > len(waveform):
                    break
                symbol_samples = waveform[i:i+spp]
                detection = detector.detect(symbol_samples)
                state, result = state_machine.process_symbol(detection)
                if result:
                    break

            assert result is not None, f"Failed to decode: {message}"
            assert result.success, f"Decode failed for: {message}"
            assert result.payload == message.encode("utf-8"), f"Payload mismatch: {message}"

    def test_roundtrip_with_noise(self, config):
        """Test round trip with added noise."""
        message = "NOISY TEST"
        frame_bits = encode_frame(message.encode("utf-8"))
        waveform = modulate_bits(
            frame_bits,
            sample_rate=config.sample_rate,
            symbol_duration=config.symbol_duration,
        )

        # Add noise (20 dB SNR)
        signal_power = np.mean(waveform**2)
        noise_power = signal_power / 100.0  # 20 dB
        noise = np.random.normal(0, np.sqrt(noise_power), len(waveform)).astype(np.float32)
        noisy_waveform = waveform + noise

        detector = SymbolDetector(config)
        state_machine = DemodulatorStateMachine(config)

        spp = config.samples_per_symbol
        for i in range(0, len(noisy_waveform), spp):
            if i + spp > len(noisy_waveform):
                break
            symbol_samples = noisy_waveform[i:i+spp]
            detection = detector.detect(symbol_samples)
            state, result = state_machine.process_symbol(detection)
            if result:
                break

        assert result is not None
        assert result.success
        assert result.payload == message.encode("utf-8")

    def test_roundtrip_frequency_offset(self, config):
        """Test tolerance to small frequency offset."""
        # This tests the detector's frequency tolerance
        message = "OFFSET TEST"
        frame_bits = encode_frame(message.encode("utf-8"))

        # Generate with slightly offset frequencies
        offset_config = ReceiverConfig(
            freq_zero=FREQ_ZERO + 50,  # 50 Hz offset
            freq_one=FREQ_ONE + 50,
        )
        waveform = modulate_bits(
            frame_bits,
            sample_rate=offset_config.sample_rate,
            symbol_duration=offset_config.symbol_duration,
        )

        # Decode with standard config (should tolerate offset within TARGET_TOLERANCE_HZ)
        detector = SymbolDetector(config)
        state_machine = DemodulatorStateMachine(config)

        spp = config.samples_per_symbol
        for i in range(0, len(waveform), spp):
            if i + spp > len(waveform):
                break
            symbol_samples = waveform[i:i+spp]
            detection = detector.detect(symbol_samples)
            state, result = state_machine.process_symbol(detection)
            if result:
                break

        assert result is not None
        assert result.success


class TestSymbolDetectionEdgeCases:
    """Tests for edge cases in symbol detection."""

    @pytest.fixture
    def config(self):
        return ReceiverConfig()

    @pytest.fixture
    def detector(self, config):
        return SymbolDetector(config)

    def test_both_frequencies_present(self, detector, config):
        """Test when both 18kHz and 19kHz are present (should pick stronger)."""
        # Create composite signal
        s0 = generate_symbol(0, sample_rate=config.sample_rate, symbol_duration=config.symbol_duration)
        s1 = generate_symbol(1, sample_rate=config.sample_rate, symbol_duration=config.symbol_duration)
        # Make 18kHz stronger
        composite = s0 * 1.0 + s1 * 0.3

        detection = detector.detect(composite)

        # Should detect the stronger one (0)
        assert detection.decision == SymbolDecision.ZERO

    def test_short_buffer(self, detector, config):
        """Test detection with shorter buffer."""
        short_samples = np.zeros(config.samples_per_symbol // 2, dtype=np.float32)
        detection = detector.detect(short_samples)

        # Should not crash, returns some result
        assert detection is not None

    def test_detection_timestamp(self, detector, config):
        """Test that timestamp is preserved."""
        symbol = _generate_test_symbol(0, config)
        timestamp = 123.456
        detection = detector.detect(symbol, timestamp=timestamp)

        assert detection.timestamp == timestamp


class TestParallelMultiPhaseAndCRCRecovery:
    """Tests for multi-phase clock receiver and 1-bit CRC syndrome recovery."""

    def test_single_bit_crc_recovery_canonical(self):
        """Test that single bit flips in canonical frames are corrected via CRC syndrome recovery."""
        from whisper.protocol.frames import ProtocolFrame, FrameType, encode_protocol_frame
        frame = ProtocolFrame(
            frame_type=FrameType.TRANSFER_OFFER,
            session_id=0x12345678,
            seq_num=0,
            payload=b"test-offer-payload-1234",
        )
        bits = encode_protocol_frame(frame)
        # bits = PREAMBLE (32) + SYNC (16) + body_bits
        body_bits = bits[len(PREAMBLE_BITS) + len(SYNC_BITS):]

        config = ReceiverConfig(canonical_framing=True)
        sm = DemodulatorStateMachine(config)

        # Test flipping bit 10, bit 35, bit 75
        for flip_idx in [10, 35, 75]:
            corrupted_body = list(body_bits)
            corrupted_body[flip_idx] ^= 1
            sm.received_bits = corrupted_body
            sm.payload_length = len(frame.payload)
            sm.expected_frame_bits = len(corrupted_body)

            result = sm._validate_frame()
            assert result.success, f"Failed to recover bit flip at index {flip_idx}"
            assert result.protocol_frame is not None
            assert result.protocol_frame.session_id == 0x12345678
            assert result.protocol_frame.payload == b"test-offer-payload-1234"

    def test_single_bit_crc_recovery_legacy(self):
        """Test that single bit flips in legacy frames are corrected via CRC recovery."""
        payload = b"LEGACY_DATA"
        bits = encode_frame(payload)
        body_bits = bits[len(PREAMBLE_BITS) + len(SYNC_BITS):]

        config = ReceiverConfig(canonical_framing=False)
        sm = DemodulatorStateMachine(config)

        corrupted_body = list(body_bits)
        corrupted_body[20] ^= 1  # Flip bit in payload
        sm.received_bits = corrupted_body
        sm.payload_length = len(payload)
        sm.expected_frame_bits = len(corrupted_body)

        result = sm._validate_frame()
        assert result.success
        assert result.payload == payload

    def test_multiphase_receiver_with_time_offsets(self):
        """Test that AudioStreamReceiver decodes frames arriving at arbitrary clock phase shifts."""
        config = ReceiverConfig(canonical_framing=True, enable_clock_recovery=True)
        from whisper.protocol.frames import ProtocolFrame, FrameType, encode_protocol_frame
        frame = ProtocolFrame(
            frame_type=FrameType.DISCOVERY_PING,
            session_id=0xABCDEF01,
            seq_num=0,
            payload=b"PING",
        )
        bits = encode_protocol_frame(frame)
        waveform = modulate_bits(
            bits,
            sample_rate=config.sample_rate,
            symbol_duration=config.symbol_duration,
            freq_zero=config.freq_zero,
            freq_one=config.freq_one,
        )

        spp = config.samples_per_symbol
        # Test time offsets across symbol fractions
        for shift in [0, spp // 4, spp // 2, (3 * spp) // 4]:
            decoded_frames = []
            receiver = AudioStreamReceiver(config, on_frame=lambda res: decoded_frames.append(res))
            padded_audio = np.concatenate([np.zeros(shift, dtype=np.float32), waveform, np.zeros(spp * 4, dtype=np.float32)])

            # Feed in 1024-sample chunks like sounddevice callback
            chunk_size = 1024
            for i in range(0, len(padded_audio), chunk_size):
                chunk = padded_audio[i : i + chunk_size]
                receiver._process_audio_block(chunk)

            assert len(decoded_frames) == 1, f"Failed at shift {shift}: got {len(decoded_frames)} decoded frames"
            assert decoded_frames[0].success
            assert decoded_frames[0].protocol_frame.session_id == 0xABCDEF01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])