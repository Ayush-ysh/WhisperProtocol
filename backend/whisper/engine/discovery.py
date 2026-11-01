"""Acoustic Discovery Engine for WhisperProtocol.

Enables nearby compatible devices to discover each other purely through sound waves:
- Opt-in 'Ready to Receive' mode
- PING / RESPONSE handshake
- Randomized collision avoidance response slots (800ms)
- Half-duplex muting and reverberation decay protection
"""

from dataclasses import dataclass, field
import logging
import random
import threading
import time
from typing import Callable, Dict, List, Optional

import numpy as np

from whisper.audio.coordinator import HalfDuplexAudioCoordinator
from whisper.protocol.constants import (
    MODULATION_PROFILES,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
)
from whisper.protocol.demodulator import ReceiverConfig, FrameDecodeResult
from whisper.protocol.frames import (
    FrameType,
    ProtocolFrame,
    create_discovery_ping,
    create_discovery_response,
    encode_protocol_frame,
)
from whisper.protocol.modulation import modulate_bits
from whisper.events import get_event_bus, Event, EventType

logger = logging.getLogger(__name__)

COLLISION_AVOIDANCE_SLOT_SECONDS: float = 0.8
DEVICE_EXPIRY_SECONDS: float = 60.0


@dataclass
class DiscoveredDevice:
    """Metadata for a peer device discovered acoustically."""
    alias: str
    session_id: int
    last_seen: float = field(default_factory=time.time)
    rssi_db: float = 0.0
    profile: str = "ultrasonic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "session_id": self.session_id,
            "last_seen": self.last_seen,
            "age_seconds": round(time.time() - self.last_seen, 1),
            "rssi_db": self.rssi_db,
            "profile": self.profile,
        }


class DiscoveryEngine:
    """Acoustic discovery coordinator managing ping/response and collision avoidance."""

    def __init__(
        self,
        local_alias: str = "WhisperNode",
        profile_name: str = "ultrasonic",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        coordinator: Optional[HalfDuplexAudioCoordinator] = None,
        on_device_discovered: Optional[Callable[[DiscoveredDevice], None]] = None,
    ):
        self.local_alias: str = local_alias
        self.profile_name: str = profile_name
        self.profile = MODULATION_PROFILES.get(profile_name, MODULATION_PROFILES["ultrasonic"])
        self.sample_rate: int = sample_rate
        self.on_device_discovered = on_device_discovered

        self._lock = threading.RLock()
        self._devices: Dict[str, DiscoveredDevice] = {}
        self._receiver_mode_active = False
        self._discovery_active = False

        # Audio coordinator with canonical protocol framing enabled
        receiver_config = ReceiverConfig(
            sample_rate=self.sample_rate,
            symbol_duration=DEFAULT_SYMBOL_DURATION,
            freq_zero=self.profile.freq_zero,
            freq_one=self.profile.freq_one,
            canonical_framing=True,
        )

        self.coordinator = coordinator or HalfDuplexAudioCoordinator(
            receiver_config=receiver_config,
            on_frame_received=self._on_frame_received,
        )

    @property
    def is_receiver_mode(self) -> bool:
        with self._lock:
            return self._receiver_mode_active

    @property
    def is_discovering(self) -> bool:
        with self._lock:
            return self._discovery_active

    def set_receiver_mode(self, enabled: bool, alias: Optional[str] = None) -> bool:
        """
        Toggle opt-in 'Ready to Receive' mode.
        When enabled, the device listens for DISCOVERY_PING and responds in random slots.
        """
        with self._lock:
            if alias:
                self.local_alias = alias
            self._receiver_mode_active = enabled

            if enabled:
                logger.info("Discovery Receiver Mode ENABLED as '%s'", self.local_alias)
                self.coordinator.start_listening()
            else:
                logger.info("Discovery Receiver Mode DISABLED")
                if not self._discovery_active:
                    self.coordinator.stop_listening()

            return self._receiver_mode_active

    def start_discovery(self, alias: Optional[str] = None) -> None:
        """Broadcast a DISCOVERY_PING and listen for DISCOVERY_RESPONSE frames."""
        with self._lock:
            if alias:
                self.local_alias = alias
            self._discovery_active = True
            self.coordinator.start_listening()

        logger.info("Transmitting DISCOVERY_PING for alias '%s'...", self.local_alias)
        ping_frame = create_discovery_ping(alias=self.local_alias)
        self._transmit_frame(ping_frame)

    def stop_discovery(self) -> None:
        """Stop active discovery listening."""
        with self._lock:
            self._discovery_active = False
            if not self._receiver_mode_active:
                self.coordinator.stop_listening()
        logger.info("Discovery stopped")

    def get_discovered_devices(self) -> List[Dict[str, Any]]:
        """Return list of active devices discovered within last 60 seconds."""
        now = time.time()
        with self._lock:
            # Purge expired
            self._devices = {
                k: v for k, v in self._devices.items()
                if (now - v.last_seen) <= DEVICE_EXPIRY_SECONDS
            }
            return [dev.to_dict() for dev in self._devices.values()]

    def _transmit_frame(self, frame: ProtocolFrame) -> None:
        """Encode, modulate (CPFSK), and acoustically transmit a protocol frame."""
        bits = encode_protocol_frame(frame)
        waveform = modulate_bits(
            bits,
            sample_rate=self.sample_rate,
            symbol_duration=DEFAULT_SYMBOL_DURATION,
            amplitude=0.5,
            freq_zero=self.profile.freq_zero,
            freq_one=self.profile.freq_one,
            phase_continuous=True,
        )
        self.coordinator.transmit(waveform, sample_rate=self.sample_rate)

    def _on_frame_received(self, result: FrameDecodeResult) -> None:
        """Process incoming decoded acoustic frames."""
        if not result.success or not result.protocol_frame:
            return

        frame: ProtocolFrame = result.protocol_frame

        if frame.frame_type == FrameType.DISCOVERY_PING:
            self._handle_discovery_ping(frame)
        elif frame.frame_type == FrameType.DISCOVERY_RESPONSE:
            self._handle_discovery_response(frame)

    def _handle_discovery_ping(self, frame: ProtocolFrame) -> None:
        """Handle incoming DISCOVERY_PING from a remote sender."""
        with self._lock:
            if not self._receiver_mode_active:
                return

        peer_alias = frame.payload.decode("utf-8", errors="replace").strip()
        if peer_alias == self.local_alias:
            # Ignore self-reflection
            return

        logger.info("Received DISCOVERY_PING from '%s'. Scheduling collision-avoidant reply.", peer_alias)

        # Collision avoidance: Pick random slot 0..3 (spaced by 800ms)
        slot = random.choice([0, 1, 2, 3])
        delay = slot * COLLISION_AVOIDANCE_SLOT_SECONDS

        def reply_worker():
            if delay > 0:
                time.sleep(delay)
            with self._lock:
                if not self._receiver_mode_active:
                    return
            resp_frame = create_discovery_response(alias=self.local_alias, session_id=frame.session_id)
            try:
                self._transmit_frame(resp_frame)
                logger.info("Transmitted DISCOVERY_RESPONSE to '%s' in slot %d (delay=%.2fs)", peer_alias, slot, delay)
            except Exception as e:
                logger.error("Failed to transmit DISCOVERY_RESPONSE: %s", e)

        reply_thread = threading.Thread(target=reply_worker, daemon=True)
        reply_thread.start()

    def _handle_discovery_response(self, frame: ProtocolFrame) -> None:
        """Handle incoming DISCOVERY_RESPONSE from a nearby receiver."""
        peer_alias = frame.payload.decode("utf-8", errors="replace").strip()
        if not peer_alias or peer_alias == self.local_alias:
            return

        device = DiscoveredDevice(
            alias=peer_alias,
            session_id=frame.session_id,
            last_seen=time.time(),
            profile=self.profile_name,
        )

        with self._lock:
            self._devices[peer_alias] = device

        logger.info("Discovered acoustic device: '%s' (session=%#x)", peer_alias, frame.session_id)

        if self.on_device_discovered:
            try:
                self.on_device_discovered(device)
            except Exception as e:
                logger.error("Error in on_device_discovered callback: %s", e)
