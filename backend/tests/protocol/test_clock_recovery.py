"""Tests for symbol clock recovery and phase offset resilience in WhisperProtocol."""

import tempfile
import numpy as np
import pytest
import soundfile as sf

from whisper.protocol.constants import DEFAULT_SAMPLE_RATE, PREAMBLE_BITS, SYNC_BITS
from whisper.protocol.encoder import encode_message
from whisper.protocol.demodulator import (
    decode_wav_file,
    ReceiverConfig,
    DemodulatorStateMachine,
    SymbolDecision,
    SymbolDetection,
    ReceiverState,
)


class TestPhaseOffsetResilience:
    """Tests decoding waveforms with arbitrary sub-symbol time offsets."""

    @pytest.mark.parametrize("offset", [0, 75, 180, 350, 441, 600, 750])
    def test_roundtrip_with_subsymbol_offsets(self, offset):
        """Test that decode_wav_file successfully decodes at arbitrary offsets."""
        msg = "WHISPER_SYNC"
        encoded = encode_message(msg)

        # Prepend silence of arbitrary length
        silence = np.zeros(offset, dtype=np.float32)
        trailing = np.zeros(882, dtype=np.float32)
        waveform = np.concatenate([silence, encoded.waveform, trailing])

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            sf.write(f.name, waveform, DEFAULT_SAMPLE_RATE)
            result = decode_wav_file(f.name)

            assert result.success is True, f"Failed at offset {offset}: {result.error}"
            assert result.payload == msg.encode("utf-8")
            assert result.checksum_valid is True

    def test_roundtrip_with_offset_and_noise(self):
        """Test roundtrip with offset combined with additive Gaussian noise."""
        msg = "SECRET_OFFSET"
        encoded = encode_message(msg)
        offset = 317

        silence = np.zeros(offset, dtype=np.float32)
        clean = np.concatenate([silence, encoded.waveform, np.zeros(882, dtype=np.float32)])
        noise = np.random.normal(0, 0.03, len(clean)).astype(np.float32)
        noisy = clean + noise

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            sf.write(f.name, noisy, DEFAULT_SAMPLE_RATE)
            result = decode_wav_file(f.name)

            assert result.success is True
            assert result.payload == msg.encode("utf-8")
            assert result.checksum_valid is True


class TestPreambleSyncErrorTolerance:
    """Tests Hamming distance tolerance for preamble and sync matching."""

    @staticmethod
    def _create_detection(bit: int) -> SymbolDetection:
        return SymbolDetection(
            decision=SymbolDecision.ONE if bit == 1 else SymbolDecision.ZERO,
            detected_frequency=19000.0 if bit == 1 else 18000.0,
            energy_zero=0.0 if bit == 1 else 1.0,
            energy_one=1.0 if bit == 1 else 0.0,
            noise_floor=0.01,
            snr_zero_db=0.0 if bit == 1 else 25.0,
            snr_one_db=25.0 if bit == 1 else 0.0,
            confidence=0.95,
            timestamp=0.0,
        )

    def test_preamble_tolerates_bit_errors(self):
        """Test that preamble locks even if up to max_preamble_errors bits are flipped."""
        config = ReceiverConfig(max_preamble_errors=2)
        sm = DemodulatorStateMachine(config)

        corrupted_preamble = list(PREAMBLE_BITS)
        corrupted_preamble[5] = 1 - corrupted_preamble[5]   # Flip 1st bit
        corrupted_preamble[17] = 1 - corrupted_preamble[17] # Flip 2nd bit

        for b in corrupted_preamble:
            sm.process_symbol(self._create_detection(b))

        assert sm.state == ReceiverState.PREAMBLE_DETECTED

    def test_preamble_rejects_excessive_bit_errors(self):
        """Test that preamble rejects when bit errors exceed tolerance."""
        config = ReceiverConfig(max_preamble_errors=2)
        sm = DemodulatorStateMachine(config)

        corrupted_preamble = list(PREAMBLE_BITS)
        corrupted_preamble[2] = 1 - corrupted_preamble[2]
        corrupted_preamble[8] = 1 - corrupted_preamble[8]
        corrupted_preamble[14] = 1 - corrupted_preamble[14] # 3 errors > 2

        for b in corrupted_preamble:
            sm.process_symbol(self._create_detection(b))

        assert sm.state != ReceiverState.PREAMBLE_DETECTED

    def test_sync_tolerates_single_bit_error(self):
        """Test that sync locks even if 1 bit is flipped."""
        config = ReceiverConfig(max_sync_errors=1)
        sm = DemodulatorStateMachine(config)

        # Feed preamble
        for b in PREAMBLE_BITS:
            sm.process_symbol(self._create_detection(b))

        assert sm.state == ReceiverState.PREAMBLE_DETECTED

        # Feed sync with 1 error
        corrupted_sync = list(SYNC_BITS)
        corrupted_sync[3] = 1 - corrupted_sync[3]

        for b in corrupted_sync:
            sm.process_symbol(self._create_detection(b))

        assert sm.state == ReceiverState.SYNCING
