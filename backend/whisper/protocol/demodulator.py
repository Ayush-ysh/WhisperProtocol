"""AFSK demodulator and receiver for WhisperProtocol Phase 3."""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from scipy.signal import get_window
from scipy.fft import rfft, rfftfreq

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
    band_zero: tuple[float, float] = FREQUENCY_BAND_18KHZ
    band_one: tuple[float, float] = FREQUENCY_BAND_19KHZ
    target_tolerance_hz: float = TARGET_TOLERANCE_HZ
    detection_threshold_db: float = 20.0
    min_snr_db: float = 12.0
    min_confidence: float = 0.6
    input_device: Optional[int] = None
    block_size: Optional[int] = None
    max_preamble_errors: int = 2
    max_sync_errors: int = 1
    enable_clock_recovery: bool = True

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

    def __str__(self) -> str:
        if self.success:
            return f"FrameDecodeResult(success=True, payload={self.payload}, checksum_valid={self.checksum_valid})"
        return f"FrameDecodeResult(success=False, error={self.error})"


class SymbolDetector:
    """FFT-based AFSK symbol detector."""

    def __init__(self, config: ReceiverConfig):
        self.config = config
        self.window = get_window("hann", config.samples_per_symbol, fftbins=True)
        self.frequencies = rfftfreq(config.samples_per_symbol, 1.0 / config.sample_rate)

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
        self.symbol_detector = SymbolDetector(config)

    def reset(self) -> None:
        """Reset state machine to initial state."""
        self.state = ReceiverState.WAITING
        self.preamble_buffer.clear()
        self.sync_buffer.clear()
        self.received_bits.clear()
        self.expected_frame_bits = 0
        self.payload_length = 0

    def process_symbol(self, detection: SymbolDetection) -> tuple[ReceiverState, Optional[FrameDecodeResult]]:
        """
        Process a single symbol detection.

        Returns:
            Tuple of (new_state, frame_result_if_complete)
        """
        if detection.decision in (SymbolDecision.UNKNOWN, SymbolDecision.LOW_CONFIDENCE):
            if self.state == ReceiverState.SEARCHING:
                self.preamble_buffer.clear()
            return self.state, None

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
                try:
                    emit_receiver_preamble_detected()
                except Exception as e:
                    logger.debug("Failed to emit preamble_detected: %s", e)

        elif self.state == ReceiverState.PREAMBLE_DETECTED:
            self.sync_buffer.append(bit)
            if len(self.sync_buffer) == len(SYNC_BITS):
                if self._match_sync():
                    logger.info("Sync detected")
                    self.state = ReceiverState.SYNCING
                    self.received_bits.clear()
                    try:
                        emit_receiver_sync_locked()
                    except Exception as e:
                        logger.debug("Failed to emit sync_locked: %s", e)
                else:
                    logger.debug("Sync mismatch, returning to SEARCHING")
                    self.state = ReceiverState.SEARCHING
                    self.preamble_buffer.clear()
                    self.sync_buffer.clear()

        elif self.state == ReceiverState.SYNCING:
            self.received_bits.append(bit)
            if len(self.received_bits) == LENGTH_FIELD_BITS:
                self.payload_length = self._decode_length(self.received_bits)
                self.expected_frame_bits = (
                    LENGTH_FIELD_BITS + self.payload_length * 8 + CHECKSUM_BITS
                )
                logger.info(
                    "Length decoded: %d bytes, expecting %d total bits",
                    self.payload_length, self.expected_frame_bits
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
        try:
            frame = decode_frame(PREAMBLE_BITS + SYNC_BITS + self.received_bits)
            return FrameDecodeResult(
                success=True,
                payload=frame.payload,
                checksum_valid=frame.valid,
                frame=frame,
            )
        except (FrameError, BitstreamError, ChecksumError) as e:
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
    """Real-time microphone streaming receiver."""

    def __init__(
        self,
        config: Optional[ReceiverConfig] = None,
        on_symbol: Optional[Callable[[SymbolDetection], None]] = None,
        on_state_change: Optional[Callable[[ReceiverState], None]] = None,
        on_frame: Optional[Callable[[FrameDecodeResult], None]] = None,
    ):
        self.config = config or ReceiverConfig()
        self.state_machine = DemodulatorStateMachine(self.config)
        self.on_symbol = on_symbol
        self.on_state_change = on_state_change
        self.on_frame = on_frame

        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._buffer = np.zeros(self.config.samples_per_symbol, dtype=np.float32)
        self._buffer_pos = 0
        self._last_state = ReceiverState.WAITING
        self._symbol_count = 0
        self._start_time = 0.0

    def start(self) -> None:
        """Start the receiver."""
        if self._running:
            logger.warning("Receiver already running")
            return

        self._running = True
        self.state_machine.reset()
        self._buffer_pos = 0
        self._symbol_count = 0
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

        try:
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
        except sd.PortAudioError as e:
            self._running = False
            logger.error("Failed to start receiver: %s", e)
            raise

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
        """Process incoming audio block."""
        for sample in block:
            self._buffer[self._buffer_pos] = sample
            self._buffer_pos += 1

            if self._buffer_pos >= self.config.samples_per_symbol:
                timestamp = time.time() - self._start_time
                detection = self.state_machine.symbol_detector.detect(self._buffer.copy(), timestamp)

                self._symbol_count += 1

                if self.on_symbol:
                    self.on_symbol(detection)

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

                new_state, frame_result = self.state_machine.process_symbol(detection)

                if new_state != self._last_state:
                    if self.on_state_change:
                        self.on_state_change(new_state)
                    self._last_state = new_state

                if frame_result and self.on_frame:
                    self.on_frame(frame_result)

                self._buffer_pos = 0

    def get_status(self) -> ReceiverStatus:
        """Get current receiver status."""
        return self.state_machine.get_status()

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