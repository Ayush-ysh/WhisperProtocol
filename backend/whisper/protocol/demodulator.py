"""AFSK demodulator and receiver for WhisperProtocol Phase 3."""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np
import sounddevice as sd
from numpy.fft import rfft, rfftfreq

from .constants import (
    FREQ_ZERO,
    FREQ_ONE,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    PREAMBLE_BITS,
    SYNC_BITS,
    LENGTH_FIELD_BITS,
    CHECKSUM_BITS,
    FREQUENCY_BAND_18KHZ,
    FREQUENCY_BAND_19KHZ,
    TARGET_TOLERANCE_HZ,
    get_samples_per_symbol,
)
from .bitstream import bits_to_bytes, BitstreamError
from .checksum import strip_and_verify, ChecksumError
from .framing import decode_frame, Frame, FrameError
from .ecc import rs_decode, ECCError, ECCUncorrectableError
from whisper.events import (

    emit_receiver_listening,
    emit_receiver_signal_detected,
    emit_receiver_preamble_detected,
    emit_receiver_sync_locked,
    emit_receiver_receiving,
    emit_receiver_verifying,
    emit_receiver_completed,
    emit_receiver_error,
    emit_receiver_stopped,
)

logger = logging.getLogger(__name__)


class SymbolDecision(Enum):
    """Result of symbol classification."""
    ZERO = 0
    ONE = 1
    UNKNOWN = 2
    LOW_CONFIDENCE = 3


class ReceiverState(Enum):
    """Receiver state machine states."""
    WAITING = "WAITING"
    SEARCHING = "SEARCHING"
    PREAMBLE_DETECTED = "PREAMBLE_DETECTED"
    SYNCING = "SYNCING"
    RECEIVING = "RECEIVING"
    FRAME_VALIDATION = "FRAME_VALIDATION"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ReceiverConfig:
    """Configuration for the receiver."""
    sample_rate: int = DEFAULT_SAMPLE_RATE
    symbol_duration: float = DEFAULT_SYMBOL_DURATION
    freq_zero: float = FREQ_ZERO
    freq_one: float = FREQ_ONE
    band_zero: Optional[tuple[float, float]] = None
    band_one: Optional[tuple[float, float]] = None
    target_tolerance_hz: float = 350.0
    detection_threshold_db: float = 4.0
    min_snr_db: float = 4.0
    min_confidence: float = 0.25
    input_device: Optional[int] = None
    block_size: Optional[int] = None
    max_preamble_errors: int = 6
    max_sync_errors: int = 1
    enable_clock_recovery: bool = True
    ecc_symbols: int = 0
    canonical_framing: bool = False

    def __post_init__(self):
        if self.band_zero is None:
            object.__setattr__(self, "band_zero", (self.freq_zero - 500.0, self.freq_zero + 500.0))
        if self.band_one is None:
            object.__setattr__(self, "band_one", (self.freq_one - 500.0, self.freq_one + 500.0))


    @property
    def samples_per_symbol(self) -> int:
        return get_samples_per_symbol(self.sample_rate, self.symbol_duration)

    @property
    def block_size_samples(self) -> int:
        if self.block_size is not None:
            return self.block_size
        return self.samples_per_symbol


@dataclass(frozen=True)
class SymbolDetection:
    """Result of symbol detection from FFT analysis."""
    decision: SymbolDecision
    detected_frequency: float
    energy_zero: float
    energy_one: float
    noise_floor: float
    snr_zero_db: Optional[float]
    snr_one_db: Optional[float]
    confidence: float
    timestamp: float

    def __str__(self) -> str:
        return (
            f"SymbolDetection(decision={self.decision.name}, "
            f"freq={self.detected_frequency:.1f}Hz, "
            f"E0={self.energy_zero:.4f}, E1={self.energy_one:.4f}, "
            f"conf={self.confidence:.3f})"
        )


@dataclass(frozen=True)
class ReceiverStatus:
    """Current receiver status for monitoring."""
    state: ReceiverState
    detected_frequency: float = 0.0
    current_symbol: Optional[int] = None
    confidence: float = 0.0
    frame_progress: int = 0
    frame_total: int = 0
    signal_level: float = 0.0
    noise_floor: float = 0.0
    symbols_received: int = 0
    error_message: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"ReceiverStatus(state={self.state.value}, "
            f"freq={self.detected_frequency:.1f}Hz, "
            f"symbol={self.current_symbol}, "
            f"conf={self.confidence:.2f}, "
            f"progress={self.frame_progress}/{self.frame_total})"
        )


@dataclass
class FrameDecodeResult:
    """Result of frame decoding."""
    success: bool
    payload: Optional[bytes] = None
    checksum_valid: bool = False
    error: Optional[str] = None
    frame: Optional[Frame] = None
    protocol_frame: Optional[Any] = None
    ecc_corrected_symbols: int = 0

    def __str__(self) -> str:
        if self.success:
            ecc_info = f", ecc_corrected={self.ecc_corrected_symbols}" if self.ecc_corrected_symbols > 0 else ""
            return f"FrameDecodeResult(success=True, payload={self.payload}, checksum_valid={self.checksum_valid}{ecc_info})"
        return f"FrameDecodeResult(success=False, error={self.error})"



class SymbolDetector:
    """FFT-based AFSK symbol detector."""

    def __init__(self, config: ReceiverConfig):
        self.config = config
        n_samples = config.samples_per_symbol
        self.window = (0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n_samples) / n_samples)).astype(np.float32)
        self.frequencies = rfftfreq(n_samples, 1.0 / config.sample_rate)

        self.zero_band_mask = (self.frequencies >= config.band_zero[0]) & (self.frequencies <= config.band_zero[1])
        self.one_band_mask = (self.frequencies >= config.band_one[0]) & (self.frequencies <= config.band_one[1])

        self.zero_target_idx = np.argmin(np.abs(self.frequencies - config.freq_zero))
        self.one_target_idx = np.argmin(np.abs(self.frequencies - config.freq_one))

        logger.debug(
            "SymbolDetector initialized: sr=%d, sym_dur=%.3f, spp=%d, "
            "zero_band=[%.0f-%.0f], one_band=[%.0f-%.0f]",
            config.sample_rate, config.symbol_duration, config.samples_per_symbol,
            config.band_zero[0], config.band_zero[1],
            config.band_one[0], config.band_one[1]
        )

    def detect(self, samples: np.ndarray, timestamp: float = 0.0) -> SymbolDetection:
        """
        Detect symbol from audio samples.

        Args:
            samples: Audio samples (mono, float32), length = samples_per_symbol
            timestamp: Timestamp for this detection

        Returns:
            SymbolDetection with classification result
        """
        if len(samples) != self.config.samples_per_symbol:
            logger.warning(
                "Sample count mismatch: got %d, expected %d",
                len(samples), self.config.samples_per_symbol
            )
            # Pad or truncate to expected size
            if len(samples) < self.config.samples_per_symbol:
                samples = np.pad(samples, (0, self.config.samples_per_symbol - len(samples)))
            else:
                samples = samples[:self.config.samples_per_symbol]

        windowed = samples * self.window
        magnitudes = np.abs(rfft(windowed))

        noise_floor = float(np.median(magnitudes))

        zero_band_mags = magnitudes[self.zero_band_mask]
        one_band_mags = magnitudes[self.one_band_mask]

        if len(zero_band_mags) > 0:
            zero_peak_idx = np.argmax(zero_band_mags)
            energy_zero = float(zero_band_mags[zero_peak_idx])
            zero_peak_freq = float(self.frequencies[self.zero_band_mask][zero_peak_idx])
        else:
            energy_zero = 0.0
            zero_peak_freq = self.config.freq_zero

        if len(one_band_mags) > 0:
            one_peak_idx = np.argmax(one_band_mags)
            energy_one = float(one_band_mags[one_peak_idx])
            one_peak_freq = float(self.frequencies[self.one_band_mask][one_peak_idx])
        else:
            energy_one = 0.0
            one_peak_freq = self.config.freq_one

        snr_zero_db = None
        snr_one_db = None
        if noise_floor > 0:
            if energy_zero > 0:
                snr_zero_db = 20 * np.log10(energy_zero / noise_floor)
            if energy_one > 0:
                snr_one_db = 20 * np.log10(energy_one / noise_floor)

        threshold_linear = 10 ** (self.config.detection_threshold_db / 20.0)
        min_snr_linear = 10 ** (self.config.min_snr_db / 20.0)

        zero_detected = (
            snr_zero_db is not None
            and snr_zero_db >= self.config.min_snr_db
            and energy_zero > noise_floor * threshold_linear
            and abs(zero_peak_freq - self.config.freq_zero) <= self.config.target_tolerance_hz
        )

        one_detected = (
            snr_one_db is not None
            and snr_one_db >= self.config.min_snr_db
            and energy_one > noise_floor * threshold_linear
            and abs(one_peak_freq - self.config.freq_one) <= self.config.target_tolerance_hz
        )

        if zero_detected and not one_detected:
            decision = SymbolDecision.ZERO
            detected_freq = zero_peak_freq
            confidence = min(1.0, snr_zero_db / 30.0) if snr_zero_db else 0.0
        elif one_detected and not zero_detected:
            decision = SymbolDecision.ONE
            detected_freq = one_peak_freq
            confidence = min(1.0, snr_one_db / 30.0) if snr_one_db else 0.0
        elif zero_detected and one_detected:
            if energy_zero > energy_one:
                decision = SymbolDecision.ZERO
                detected_freq = zero_peak_freq
                confidence = min(1.0, (snr_zero_db or 0) / 30.0)
            else:
                decision = SymbolDecision.ONE
                detected_freq = one_peak_freq
                confidence = min(1.0, (snr_one_db or 0) / 30.0)
        else:
            max_snr = max(snr_zero_db or -np.inf, snr_one_db or -np.inf)
            if max_snr >= self.config.min_snr_db / 2:
                decision = SymbolDecision.LOW_CONFIDENCE
                confidence = min(1.0, max_snr / 30.0) if max_snr != -np.inf else 0.0
            else:
                decision = SymbolDecision.UNKNOWN
                confidence = 0.0
            detected_freq = zero_peak_freq if energy_zero >= energy_one else one_peak_freq

        if confidence < self.config.min_confidence and decision in (SymbolDecision.ZERO, SymbolDecision.ONE):
            decision = SymbolDecision.LOW_CONFIDENCE

        return SymbolDetection(
            decision=decision,
            detected_frequency=detected_freq,
            energy_zero=energy_zero,
            energy_one=energy_one,
            noise_floor=noise_floor,
            snr_zero_db=snr_zero_db,
            snr_one_db=snr_one_db,
            confidence=confidence,
            timestamp=timestamp,
        )


class DemodulatorStateMachine:
    """State machine for preamble detection, sync, and frame reception."""

    def __init__(self, config: ReceiverConfig):
        self.config = config
        self.state = ReceiverState.WAITING
        self.preamble_buffer: list[int] = []
        self.sync_buffer: list[int] = []
        self.received_bits: list[int] = []
        self.expected_frame_bits: int = 0
        self.payload_length: int = 0
        self._sync_bits_seen: int = 0
        self.symbol_detector = SymbolDetector(config)

    def reset(self) -> None:
        """Reset state machine to initial state."""
        self.state = ReceiverState.WAITING
        self.preamble_buffer.clear()
        self.sync_buffer.clear()
        self.received_bits.clear()
        self.expected_frame_bits = 0
        self.payload_length = 0
        self._sync_bits_seen = 0

    def process_symbol(self, detection: SymbolDetection) -> tuple[ReceiverState, Optional[FrameDecodeResult]]:
        """
        Process a single symbol detection.

        Returns:
            Tuple of (new_state, frame_result_if_complete)
        """
        if detection.decision == SymbolDecision.UNKNOWN:
            if self.state in (ReceiverState.WAITING, ReceiverState.SEARCHING):
                self.preamble_buffer.clear()
            return self.state, None

        if detection.decision == SymbolDecision.LOW_CONFIDENCE:
            carrier_present = (
                detection.noise_floor > 0
                and (detection.energy_zero > detection.noise_floor * 1.5 or detection.energy_one > detection.noise_floor * 1.5)
            )
            if carrier_present or self.state in (ReceiverState.PREAMBLE_DETECTED, ReceiverState.SYNCING, ReceiverState.RECEIVING):
                bit = 0 if detection.energy_zero >= detection.energy_one else 1
            elif self.state in (ReceiverState.SEARCHING, ReceiverState.WAITING):
                bit = 0 if detection.energy_zero >= detection.energy_one else 1
            else:
                return self.state, None
        else:
            bit = 0 if detection.decision == SymbolDecision.ZERO else 1

        if self.state == ReceiverState.WAITING:
            self.state = ReceiverState.SEARCHING
            self.preamble_buffer.append(bit)

        elif self.state == ReceiverState.SEARCHING:
            self.preamble_buffer.append(bit)
            if len(self.preamble_buffer) > len(PREAMBLE_BITS):
                self.preamble_buffer.pop(0)
            if self._match_preamble():
                logger.info("Preamble detected")
                self.state = ReceiverState.PREAMBLE_DETECTED
                self.sync_buffer.clear()
                self._sync_bits_seen = 0
                self._preamble_errors = sum(a != b for a, b in zip(self.preamble_buffer, PREAMBLE_BITS))
                try:
                    emit_receiver_preamble_detected()
                except Exception as e:
                    logger.debug("Failed to emit preamble_detected: %s", e)

        elif self.state == ReceiverState.PREAMBLE_DETECTED:
            self.sync_buffer.append(bit)
            self._sync_bits_seen += 1
            if len(self.sync_buffer) > len(SYNC_BITS):
                self.sync_buffer.pop(0)

            if len(self.sync_buffer) == len(SYNC_BITS) and self._match_sync():
                logger.info("Sync detected")
                self.state = ReceiverState.SYNCING
                self.received_bits.clear()
                self._sync_bits_seen = 0
                try:
                    emit_receiver_sync_locked()
                except Exception as e:
                    logger.debug("Failed to emit sync_locked: %s", e)
            elif self._sync_bits_seen >= (len(SYNC_BITS) + 24 if self.config.canonical_framing else len(SYNC_BITS) + getattr(self, '_preamble_errors', 0)):
                logger.debug("Sync timeout, returning to SEARCHING")
                self.state = ReceiverState.SEARCHING
                self.preamble_buffer.clear()
                self.sync_buffer.clear()
                self._sync_bits_seen = 0

        elif self.state == ReceiverState.SYNCING:
            self.received_bits.append(bit)
            header_bits_needed = 80 if self.config.canonical_framing else LENGTH_FIELD_BITS
            if len(self.received_bits) == header_bits_needed:
                if self.config.canonical_framing:
                    self.payload_length = self._decode_length(self.received_bits[64:80])
                    self.expected_frame_bits = 80 + self.payload_length * 8 + CHECKSUM_BITS
                else:
                    self.payload_length = self._decode_length(self.received_bits)
                    self.expected_frame_bits = (
                        LENGTH_FIELD_BITS + self.payload_length * 8 + CHECKSUM_BITS
                    )
                logger.info(
                    "Length decoded: %d bytes, expecting %d total bits (canonical=%s)",
                    self.payload_length, self.expected_frame_bits, self.config.canonical_framing
                )
                self.state = ReceiverState.RECEIVING
                try:
                    emit_receiver_receiving(len(self.received_bits), self.expected_frame_bits)
                except Exception as e:
                    logger.debug("Failed to emit receiving: %s", e)

        elif self.state == ReceiverState.RECEIVING:
            self.received_bits.append(bit)
            try:
                emit_receiver_receiving(len(self.received_bits), self.expected_frame_bits)
            except Exception as e:
                logger.debug("Failed to emit receiving: %s", e)

            if len(self.received_bits) >= self.expected_frame_bits:
                logger.info("Frame complete, validating")
                self.state = ReceiverState.FRAME_VALIDATION
                try:
                    emit_receiver_verifying()
                except Exception as e:
                    logger.debug("Failed to emit verifying: %s", e)

                result = self._validate_frame()
                self.state = ReceiverState.COMPLETE

                try:
                    if result.success:
                        msg_str = result.payload.decode("utf-8", errors="replace") if result.payload else ""
                        emit_receiver_completed(
                            message=msg_str,
                            checksum_valid=result.checksum_valid,
                            confidence=detection.confidence,
                        )
                    else:
                        emit_receiver_error(
                            error=result.error or "Frame validation failed",
                            state=self.state.value,
                        )
                except Exception as e:
                    logger.debug("Failed to emit completion event: %s", e)

                return self.state, result

        return self.state, None

    def _match_preamble(self) -> bool:
        if len(self.preamble_buffer) != len(PREAMBLE_BITS):
            return False
        errors = sum(a != b for a, b in zip(self.preamble_buffer, PREAMBLE_BITS))
        return errors <= self.config.max_preamble_errors

    def _match_sync(self) -> bool:
        if len(self.sync_buffer) != len(SYNC_BITS):
            return False
        errors = sum(a != b for a, b in zip(self.sync_buffer, SYNC_BITS))
        return errors <= self.config.max_sync_errors

    def _decode_length(self, length_bits: list[int]) -> int:
        length = 0
        for bit in length_bits:
            length = (length << 1) | bit
        return length

    def _validate_frame(self) -> FrameDecodeResult:
        if self.config.canonical_framing:
            from .frames import decode_protocol_frame, ProtocolFrameError
            all_bits = PREAMBLE_BITS + SYNC_BITS + self.received_bits
            try:
                proto_frame = decode_protocol_frame(
                    all_bits,
                    max_preamble_errors=self.config.max_preamble_errors,
                    max_sync_errors=self.config.max_sync_errors,
                )
                payload = proto_frame.payload
                corrected_count = 0
                if self.config.ecc_symbols > 0 and payload:
                    payload, corrected_count = rs_decode(payload, n_ecc_symbols=self.config.ecc_symbols)

                return FrameDecodeResult(
                    success=True,
                    payload=payload,
                    checksum_valid=proto_frame.valid,
                    protocol_frame=proto_frame,
                    ecc_corrected_symbols=corrected_count,
                )
            except (ProtocolFrameError, ECCError, BitstreamError) as e:
                # 1-bit CRC syndrome recovery across received bits (header + payload + CRC)
                rec_bits = list(self.received_bits)
                if len(rec_bits) >= 80 + 16:
                    for bit_idx in range(len(rec_bits)):
                        rec_bits[bit_idx] ^= 1
                        try:
                            recovered_frame = decode_protocol_frame(
                                PREAMBLE_BITS + SYNC_BITS + rec_bits,
                                max_preamble_errors=self.config.max_preamble_errors,
                                max_sync_errors=self.config.max_sync_errors,
                            )
                            logger.info(
                                "Recovered canonical frame via 1-bit CRC syndrome correction at bit %d/%d",
                                bit_idx, len(rec_bits)
                            )
                            payload = recovered_frame.payload
                            corrected_count = 0
                            if self.config.ecc_symbols > 0 and payload:
                                payload, corrected_count = rs_decode(payload, n_ecc_symbols=self.config.ecc_symbols)
                            return FrameDecodeResult(
                                success=True,
                                payload=payload,
                                checksum_valid=True,
                                protocol_frame=recovered_frame,
                                ecc_corrected_symbols=corrected_count + 1,
                            )
                        except (ProtocolFrameError, ECCError, BitstreamError):
                            rec_bits[bit_idx] ^= 1  # revert bit flip

                logger.warning("Canonical frame validation failed: %s", e)
                return FrameDecodeResult(
                    success=False,
                    error=str(e),
                )

        try:
            frame = decode_frame(PREAMBLE_BITS + SYNC_BITS + self.received_bits)
            if not frame.valid:
                # Attempt 1-bit CRC error recovery
                rec_bits = list(self.received_bits)
                if len(rec_bits) >= 16 + 16:
                    for bit_idx in range(len(rec_bits)):
                        rec_bits[bit_idx] ^= 1
                        try:
                            recovered_frame = decode_frame(PREAMBLE_BITS + SYNC_BITS + rec_bits)
                            if recovered_frame.valid:
                                logger.info(
                                    "Recovered legacy frame via 1-bit CRC correction at bit %d/%d",
                                    bit_idx, len(rec_bits)
                                )
                                frame = recovered_frame
                                break
                        except (FrameError, BitstreamError, ChecksumError):
                            pass
                        rec_bits[bit_idx] ^= 1

            payload = frame.payload
            corrected_count = 0
            if self.config.ecc_symbols > 0 and payload:
                payload, corrected_count = rs_decode(payload, n_ecc_symbols=self.config.ecc_symbols)

            return FrameDecodeResult(
                success=True,
                payload=payload,
                checksum_valid=frame.valid,
                frame=frame,
                ecc_corrected_symbols=corrected_count,
            )
        except (FrameError, BitstreamError, ChecksumError, ECCError) as e:
            logger.warning("Frame validation failed: %s", e)
            return FrameDecodeResult(
                success=False,
                error=str(e),
            )


    def get_status(self, last_detection: Optional[SymbolDetection] = None) -> ReceiverStatus:
        """Get current receiver status."""
        frame_progress = len(self.received_bits)
        frame_total = self.expected_frame_bits

        return ReceiverStatus(
            state=self.state,
            detected_frequency=last_detection.detected_frequency if last_detection else 0.0,
            current_symbol=(
                0 if last_detection and last_detection.decision == SymbolDecision.ZERO else
                1 if last_detection and last_detection.decision == SymbolDecision.ONE else
                None
            ),
            confidence=last_detection.confidence if last_detection else 0.0,
            frame_progress=frame_progress,
            frame_total=frame_total,
            signal_level=max(last_detection.energy_zero, last_detection.energy_one) if last_detection else 0.0,
            noise_floor=last_detection.noise_floor if last_detection else 0.0,
            symbols_received=frame_progress,
            error_message=None,
        )


class AudioStreamReceiver:
    """Real-time microphone streaming receiver with polyphase symbol clock recovery."""

    def __init__(
        self,
        config: Optional[ReceiverConfig] = None,
        on_symbol: Optional[Callable[[SymbolDetection], None]] = None,
        on_state_change: Optional[Callable[[ReceiverState], None]] = None,
        on_frame: Optional[Callable[[FrameDecodeResult], None]] = None,
    ):
        self.config = config or ReceiverConfig()
        self.on_symbol = on_symbol
        self.on_state_change = on_state_change
        self.on_frame = on_frame

        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        spp = self.config.samples_per_symbol
        self.num_phases = 4 if self.config.enable_clock_recovery else 1
        self.hop = spp // self.num_phases

        self.phase_sms = [DemodulatorStateMachine(self.config) for _ in range(self.num_phases)]
        self._primary_sm = self.phase_sms[0]
        self.detector = SymbolDetector(self.config)
        self.locked_phase: Optional[int] = None

        self._ring_size = max(spp * 64, 48000 * 4)
        self._ring_buffer = np.zeros(self._ring_size, dtype=np.float32)
        self._ring_write_pos = 0
        self._total_samples = 0
        self._next_eval_sample = spp

        self._last_state = ReceiverState.WAITING
        self._symbol_count = 0
        self._start_time = 0.0
        self._last_detection: Optional[SymbolDetection] = None
        self._seen_frame_keys: dict[Any, float] = {}

    @property
    def state_machine(self) -> DemodulatorStateMachine:
        if self.locked_phase is not None and self.locked_phase < len(self.phase_sms):
            return self.phase_sms[self.locked_phase]
        state_order = {
            ReceiverState.RECEIVING: 4,
            ReceiverState.FRAME_VALIDATION: 4,
            ReceiverState.SYNCING: 3,
            ReceiverState.PREAMBLE_DETECTED: 2,
            ReceiverState.SEARCHING: 1,
            ReceiverState.WAITING: 0,
            ReceiverState.COMPLETE: 0,
            ReceiverState.ERROR: 0,
        }
        return max(self.phase_sms, key=lambda s: state_order.get(s.state, 0))

    @state_machine.setter
    def state_machine(self, sm: DemodulatorStateMachine) -> None:
        self._primary_sm = sm
        if self.locked_phase is not None and self.locked_phase < len(self.phase_sms):
            self.phase_sms[self.locked_phase] = sm
        else:
            self.phase_sms = [sm]

    def reset_state_machines(self) -> None:
        """Reset state machines back to WAITING without clearing audio ring buffer."""
        self.locked_phase = None
        for sm in self.phase_sms:
            sm.reset()
        self._last_state = ReceiverState.WAITING

    def reset(self) -> None:
        """Full reset of receiver state and audio ring buffer."""
        self.reset_state_machines()
        self._ring_write_pos = 0
        self._total_samples = 0
        self._next_eval_sample = self.config.samples_per_symbol
        self._symbol_count = 0


    def start(self) -> None:
        """Start the receiver."""
        if self._running:
            logger.warning("Receiver already running")
            return

        self._running = True
        self.reset()
        self._start_time = time.time()

        try:
            emit_receiver_listening({
                "sample_rate": self.config.sample_rate,
                "symbol_duration": self.config.symbol_duration,
                "freq_zero": self.config.freq_zero,
                "freq_one": self.config.freq_one,
            })
        except Exception as e:
            logger.debug("Failed to emit receiver_listening: %s", e)

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug("Audio callback status: %s", status)
            self._process_audio_block(indata[:, 0] if indata.ndim > 1 else indata)

        fallback_rates = [self.config.sample_rate]
        if self.config.sample_rate == 48000:
            fallback_rates.append(44100)
        elif self.config.sample_rate == 44100:
            fallback_rates.append(48000)

        started = False
        last_err = None
        for sr in fallback_rates:
            try:
                if sr != self.config.sample_rate:
                    import dataclasses
                    self.config = dataclasses.replace(self.config, sample_rate=sr)
                    spp = self.config.samples_per_symbol
                    self.hop = spp // self.num_phases
                    self.phase_sms = [DemodulatorStateMachine(self.config) for _ in range(self.num_phases)]
                    self._primary_sm = self.phase_sms[0]
                    self.detector = SymbolDetector(self.config)
                    self._ring_size = spp * 8
                    self._ring_buffer = np.zeros(self._ring_size, dtype=np.float32)
                    self._ring_write_pos = 0
                    self._total_samples = 0
                    self._next_eval_sample = spp
                    logger.info("Retrying receiver initialization with fallback sample rate %d Hz...", sr)

                self._stream = sd.InputStream(
                    device=self.config.input_device,
                    samplerate=self.config.sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=self.config.block_size_samples,
                    callback=audio_callback,
                )
                self._stream.start()
                logger.info("Receiver started on device %s at %d Hz", self.config.input_device, self.config.sample_rate)
                started = True
                break
            except sd.PortAudioError as e:
                last_err = e
                logger.warning("PortAudio error starting receiver at %d Hz: %s", sr, e)

        if not started:
            self._running = False
            logger.error("Failed to start receiver on any supported sample rate: %s", last_err)
            raise last_err or sd.PortAudioError("Failed to initialize audio input")

    def stop(self) -> None:
        """Stop the receiver."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        try:
            emit_receiver_stopped()
        except Exception as e:
            logger.debug("Failed to emit receiver_stopped: %s", e)
        logger.info("Receiver stopped")

    def _process_audio_block(self, block: np.ndarray) -> None:
        """Process incoming audio block with ring-buffered polyphase tracking."""
        if block.ndim > 1:
            block = block[:, 0]
        n_samples = len(block)
        if n_samples == 0:
            return

        spp = self.config.samples_per_symbol
        hop = self.hop

        # Write samples into circular ring buffer
        end = self._ring_write_pos + n_samples
        if end <= self._ring_size:
            self._ring_buffer[self._ring_write_pos:end] = block
        else:
            p1 = self._ring_size - self._ring_write_pos
            self._ring_buffer[self._ring_write_pos:] = block[:p1]
            self._ring_buffer[:end - self._ring_size] = block[p1:]
        self._ring_write_pos = end % self._ring_size
        self._total_samples += n_samples

        while self._total_samples >= self._next_eval_sample:
            eval_sample = self._next_eval_sample
            phase_idx = ((eval_sample - spp) // hop) % self.num_phases

            # Extract window of spp samples ending at eval_sample
            samples_ago = self._total_samples - eval_sample
            w_end = (self._ring_write_pos - samples_ago) % self._ring_size
            if w_end >= spp:
                window = self._ring_buffer[w_end - spp : w_end]
            else:
                window = np.concatenate([self._ring_buffer[w_end - spp :], self._ring_buffer[:w_end]])

            timestamp = (eval_sample / self.config.sample_rate) if self.config.sample_rate else 0.0
            detection = self.detector.detect(window, timestamp)
            self._last_detection = detection

            sm = self.phase_sms[phase_idx]
            new_state, frame_result = sm.process_symbol(detection)

            if detection.decision in (SymbolDecision.ZERO, SymbolDecision.ONE):
                try:
                    emit_receiver_signal_detected(
                        frequency=detection.detected_frequency,
                        confidence=detection.confidence,
                        energy_zero=detection.energy_zero,
                        energy_one=detection.energy_one,
                    )
                except Exception as e:
                    logger.debug("Failed to emit signal_detected: %s", e)

            if self.on_symbol and phase_idx == 0:
                self._symbol_count += 1
                self.on_symbol(detection)

            state_order = {
                ReceiverState.RECEIVING: 4,
                ReceiverState.FRAME_VALIDATION: 4,
                ReceiverState.SYNCING: 3,
                ReceiverState.PREAMBLE_DETECTED: 2,
                ReceiverState.SEARCHING: 1,
                ReceiverState.WAITING: 0,
                ReceiverState.COMPLETE: 0,
                ReceiverState.ERROR: 0,
            }
            highest_sm = max(self.phase_sms, key=lambda s: state_order.get(s.state, 0))
            if highest_sm.state in (ReceiverState.SYNCING, ReceiverState.RECEIVING):
                self.locked_phase = self.phase_sms.index(highest_sm)

            if highest_sm.state != self._last_state:
                if self.on_state_change:
                    self.on_state_change(highest_sm.state)
                self._last_state = highest_sm.state

            if frame_result and frame_result.success:
                now = time.time()
                frame_key = None
                if frame_result.protocol_frame:
                    pf = frame_result.protocol_frame
                    frame_key = (pf.session_id, pf.seq_num, pf.frame_type.value)
                elif frame_result.frame:
                    f = frame_result.frame
                    frame_key = (getattr(f, "session_id", 0), getattr(f, "seq_num", 0), getattr(f, "frame_type", 0))
                elif frame_result.payload:
                    frame_key = (hash(frame_result.payload),)

                is_duplicate = False
                if frame_key is not None:
                    self._seen_frame_keys = {k: ts for k, ts in self._seen_frame_keys.items() if now - ts < 5.0}
                    if frame_key in self._seen_frame_keys and (now - self._seen_frame_keys[frame_key]) < 3.0:
                        is_duplicate = True
                    else:
                        self._seen_frame_keys[frame_key] = now

                if not is_duplicate:
                    logger.info("Decoded valid frame on clock phase %d/%d (key=%s)", phase_idx, self.num_phases, frame_key)
                    if self.on_frame:
                        self.on_frame(frame_result)
                    self.reset_state_machines()
                    self._next_eval_sample += hop
                    break
                else:
                    logger.debug("Ignored duplicate frame on clock phase %d/%d (key=%s)", phase_idx, self.num_phases, frame_key)

            self._next_eval_sample += hop

    def get_status(self) -> ReceiverStatus:
        """Get current receiver status."""
        state_order = {
            ReceiverState.RECEIVING: 4,
            ReceiverState.FRAME_VALIDATION: 4,
            ReceiverState.SYNCING: 3,
            ReceiverState.PREAMBLE_DETECTED: 2,
            ReceiverState.SEARCHING: 1,
            ReceiverState.WAITING: 0,
            ReceiverState.COMPLETE: 0,
            ReceiverState.ERROR: 0,
        }
        active_sm = max(self.phase_sms, key=lambda s: state_order.get(s.state, 0))
        return active_sm.get_status(self._last_detection)

    def is_running(self) -> bool:
        return self._running


def decode_wav_file(
    wav_path: str,
    config: Optional[ReceiverConfig] = None,
) -> FrameDecodeResult:
    """
    Decode a WAV file using the demodulator pipeline with clock recovery.

    Args:
        wav_path: Path to WAV file
        config: Optional receiver configuration

    Returns:
        FrameDecodeResult with decoded payload
    """
    import soundfile as sf

    cfg = config or ReceiverConfig()

    try:
        samples, sample_rate = sf.read(wav_path, dtype="float32", always_2d=True)
    except (sf.LibsndfileError, FileNotFoundError, OSError) as e:
        logger.error("Failed to read WAV file %s: %s", wav_path, e)
        return FrameDecodeResult(
            success=False,
            error=f"Failed to read WAV file: {e}",
        )

    if samples.ndim > 1:
        samples = samples[:, 0]

    if sample_rate != cfg.sample_rate:
        logger.warning("Sample rate mismatch: file=%d, config=%d", sample_rate, cfg.sample_rate)

    spp = cfg.samples_per_symbol

    # Candidate symbol offsets for clock recovery.
    # We evaluate offset 0 first (fast path). If that fails and clock recovery is enabled,
    # we test candidate phase offsets across the symbol duration.
    candidate_offsets = [0]
    if cfg.enable_clock_recovery and len(samples) >= spp * 4:
        candidate_offsets.extend([int(k * spp / 8) for k in range(1, 8)])

    last_result: Optional[FrameDecodeResult] = None
    last_state = ReceiverState.WAITING

    for offset in candidate_offsets:
        detector = SymbolDetector(cfg)
        state_machine = DemodulatorStateMachine(cfg)

        offset_samples = samples[offset:]
        num_symbols = len(offset_samples) // spp

        for i in range(num_symbols):
            start = i * spp
            end = start + spp
            symbol_samples = offset_samples[start:end]

            detection = detector.detect(symbol_samples, timestamp=(offset + start) / cfg.sample_rate)
            state, result = state_machine.process_symbol(detection)

            if result and result.success:
                return result
            if result:
                last_result = result

        last_state = state_machine.state

    return last_result or FrameDecodeResult(
        success=False,
        error=f"End of file reached without complete frame (state={last_state.value})",
    )