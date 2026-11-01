"""Half-duplex audio coordinator for WhisperProtocol.

Ensures that:
1. Microphone capture is suspended during acoustic transmission to prevent self-reception.
2. A configurable acoustic decay guard interval (default 350ms) elapses before listening resumes.
3. Audio buffer residue from local speaker playback is discarded before re-engaging the receiver.
"""

import logging
import threading
import time
from enum import Enum
from typing import Optional, Callable

import numpy as np
import sounddevice as sd

from whisper.protocol.demodulator import AudioStreamReceiver, ReceiverConfig, FrameDecodeResult

logger = logging.getLogger(__name__)


class CoordinatorState(Enum):
    """Audio coordinator operational states."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSMITTING = "TRANSMITTING"
    GUARD_INTERVAL = "GUARD_INTERVAL"


class HalfDuplexAudioCoordinator:
    """Coordinates half-duplex acoustic transmission and reception."""

    def __init__(
        self,
        receiver_config: Optional[ReceiverConfig] = None,
        guard_decay_ms: float = 350.0,
        on_frame_received: Optional[Callable[[FrameDecodeResult], None]] = None,
    ):
        self.receiver_config = receiver_config or ReceiverConfig()
        self.guard_decay_seconds = guard_decay_ms / 1000.0
        self.on_frame_received = on_frame_received

        self._state = CoordinatorState.IDLE
        self._lock = threading.RLock()
        self._receiver: Optional[AudioStreamReceiver] = None
        self._wants_listening = False

    @property
    def state(self) -> CoordinatorState:
        with self._lock:
            return self._state

    def start_listening(self) -> None:
        """Activate microphone receiver in half-duplex mode."""
        with self._lock:
            self._wants_listening = True
            if self._state == CoordinatorState.TRANSMITTING or self._state == CoordinatorState.GUARD_INTERVAL:
                logger.info("Listening requested, but transmitter is active. Will engage after guard interval.")
                return

            self._engage_receiver()

    def stop_listening(self) -> None:
        """Deactivate microphone receiver."""
        with self._lock:
            self._wants_listening = False
            self._disengage_receiver()
            self._state = CoordinatorState.IDLE

    def _engage_receiver(self) -> None:
        """Internal helper to start PortAudio stream."""
        if self._receiver is None or not self._receiver.is_running():
            logger.info("Engaging half-duplex microphone stream...")
            self._receiver = AudioStreamReceiver(
                config=self.receiver_config,
                on_frame=self.on_frame_received,
            )
            try:
                self._receiver.start()
                self._state = CoordinatorState.LISTENING
            except Exception as e:
                logger.error("Failed to start AudioStreamReceiver: %s", e)
                self._state = CoordinatorState.IDLE
                raise

    def _disengage_receiver(self) -> None:
        """Internal helper to stop PortAudio stream and clear buffers."""
        if self._receiver is not None and self._receiver.is_running():
            logger.info("Disengaging half-duplex microphone stream...")
            try:
                self._receiver.stop()
            except Exception as e:
                logger.warning("Error stopping receiver: %s", e)
            finally:
                self._receiver = None

    def transmit(
        self,
        waveform: np.ndarray,
        sample_rate: int,
        output_device: Optional[int] = None,
        blocking: bool = True,
    ) -> None:
        """
        Transmit acoustic waveform with half-duplex guard switching.

        Args:
            waveform: Float32 audio samples
            sample_rate: Playback sample rate
            output_device: Optional sounddevice output device index
            blocking: If True, waits until playback and guard interval finish
        """
        with self._lock:
            was_listening = self._wants_listening

            # 1. Suspend microphone capture to prevent acoustic self-interference
            if self._state == CoordinatorState.LISTENING:
                self._disengage_receiver()

            self._state = CoordinatorState.TRANSMITTING

        logger.info(
            "Transmitting %d samples (%.2fs) through device %s...",
            len(waveform),
            len(waveform) / sample_rate,
            output_device,
        )

        try:
            # 2. Play acoustic signal through physical speaker
            sd.play(waveform, samplerate=sample_rate, device=output_device, blocking=True)
        except Exception as e:
            logger.error("Acoustic playback failed: %s", e)
            with self._lock:
                self._state = CoordinatorState.IDLE
            raise
        finally:
            # 3. Acoustic room reverberation decay guard interval
            with self._lock:
                self._state = CoordinatorState.GUARD_INTERVAL
            logger.debug("Entering acoustic decay guard interval (%.0f ms)...", self.guard_decay_seconds * 1000)
            time.sleep(self.guard_decay_seconds)

            # 4. Resume listening if previously enabled
            with self._lock:
                if was_listening and self._wants_listening:
                    self._engage_receiver()
                else:
                    self._state = CoordinatorState.IDLE
