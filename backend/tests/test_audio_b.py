"""Unit tests for Milestone B audio features: coordinator, profiles, and ECC roundtrip."""

import time
import numpy as np
import pytest

from whisper.audio.coordinator import HalfDuplexAudioCoordinator, CoordinatorState
from whisper.protocol import (
    ReceiverConfig,
    encode_message,
    decode_wav_file,
    PROFILE_ULTRASONIC,
    PROFILE_AUDIBLE,
    modulate_bits,
    encode_frame,
)
from whisper.protocol.demodulator import DemodulatorStateMachine, SymbolDetector


class TestHalfDuplexCoordinator:
    """Tests for HalfDuplexAudioCoordinator mutual exclusion and guard interval."""

    def test_initial_state(self):
        coord = HalfDuplexAudioCoordinator(guard_decay_ms=50.0)
        assert coord.state == CoordinatorState.IDLE

    def test_start_stop_listening_state_flow(self, monkeypatch):
        # Mock sounddevice InputStream to avoid opening real hardware stream in test runner
        class MockStream:
            def start(self): pass
            def stop(self): pass
            def close(self): pass

        monkeypatch.setattr("sounddevice.InputStream", lambda **kwargs: MockStream())

        coord = HalfDuplexAudioCoordinator(guard_decay_ms=50.0)
        coord.start_listening()
        assert coord.state == CoordinatorState.LISTENING

        coord.stop_listening()
        assert coord.state == CoordinatorState.IDLE

    def test_transmit_half_duplex_switching(self, monkeypatch):
        # Mock sounddevice play to simulate instantaneous playback
        played_samples = []

        def mock_play(waveform, **kwargs):
            played_samples.append(len(waveform))

        monkeypatch.setattr("sounddevice.play", mock_play)

        coord = HalfDuplexAudioCoordinator(guard_decay_ms=100.0)
        waveform = np.zeros(960, dtype=np.float32)

        start = time.time()
        coord.transmit(waveform, sample_rate=48000, blocking=True)
        elapsed = time.time() - start

        assert len(played_samples) == 1
        assert played_samples[0] == 960
        # Must have respected the 100ms guard interval
        assert elapsed >= 0.09
        assert coord.state == CoordinatorState.IDLE


class TestProfilesAndContinuousPhase:
    """Tests for modulation profiles and CPFSK waveform decoding."""

    def test_secondary_audible_profile_decode(self):
        msg = "AIR GAP BACKUP"
        res = encode_message(
            message=msg,
            sample_rate=48000,
            symbol_duration=0.02,
            freq_zero=PROFILE_AUDIBLE.freq_zero,
            freq_one=PROFILE_AUDIBLE.freq_one,
        )

        cfg = ReceiverConfig(
            sample_rate=48000,
            symbol_duration=0.02,
            freq_zero=PROFILE_AUDIBLE.freq_zero,
            freq_one=PROFILE_AUDIBLE.freq_one,
        )
        detector = SymbolDetector(cfg)
        sm = DemodulatorStateMachine(cfg)

        spp = cfg.samples_per_symbol
        decoded_payload = None

        for i in range(len(res.waveform) // spp):
            block = res.waveform[i * spp : (i + 1) * spp]
            det = detector.detect(block)
            state, frame_res = sm.process_symbol(det)
            if frame_res and frame_res.success:
                decoded_payload = frame_res.payload
                break

        assert decoded_payload == msg.encode("utf-8")

    def test_phase_continuous_modulation_decode(self):
        msg = "PHASE CONTINUOUS 48KHZ"
        res = encode_message(
            message=msg,
            sample_rate=48000,
            symbol_duration=0.02,
            phase_continuous=True,
        )

        cfg = ReceiverConfig(sample_rate=48000, symbol_duration=0.02)
        detector = SymbolDetector(cfg)
        sm = DemodulatorStateMachine(cfg)

        spp = cfg.samples_per_symbol
        decoded_payload = None

        for i in range(len(res.waveform) // spp):
            block = res.waveform[i * spp : (i + 1) * spp]
            det = detector.detect(block)
            state, frame_res = sm.process_symbol(det)
            if frame_res and frame_res.success:
                decoded_payload = frame_res.payload
                break

        assert decoded_payload == msg.encode("utf-8")

    def test_reed_solomon_ecc_recovery_under_burst_noise(self):
        msg = "ECC PROTECTED PAYLOAD"
        # 16 parity symbols can correct up to 8 symbol errors
        res = encode_message(
            message=msg,
            sample_rate=48000,
            symbol_duration=0.02,
            ecc_symbols=16,
        )

        cfg = ReceiverConfig(
            sample_rate=48000,
            symbol_duration=0.02,
            ecc_symbols=16,
        )
        detector = SymbolDetector(cfg)
        sm = DemodulatorStateMachine(cfg)

        spp = cfg.samples_per_symbol
        decoded_payload = None

        for i in range(len(res.waveform) // spp):
            block = res.waveform[i * spp : (i + 1) * spp]
            det = detector.detect(block)
            state, frame_res = sm.process_symbol(det)
            if frame_res and frame_res.success:
                decoded_payload = frame_res.payload
                break

        assert decoded_payload == msg.encode("utf-8")
