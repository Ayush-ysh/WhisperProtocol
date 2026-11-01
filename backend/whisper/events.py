"""Event system for WhisperProtocol - enables frontend integration."""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events that can be emitted."""

    # Transmitter events
    TRANSMISSION_STARTED = "transmission.started"
    TRANSMISSION_PROGRESS = "transmission.progress"
    TRANSMISSION_COMPLETED = "transmission.completed"
    TRANSMISSION_CANCELLED = "transmission.cancelled"
    TRANSMISSION_ERROR = "transmission.error"

    # Receiver events
    RECEIVER_LISTENING = "receiver.listening"
    RECEIVER_SIGNAL_DETECTED = "receiver.signal_detected"
    RECEIVER_PREAMBLE_DETECTED = "receiver.preamble_detected"
    RECEIVER_SYNC_LOCKED = "receiver.sync_locked"
    RECEIVER_RECEIVING = "receiver.receiving"
    RECEIVER_VERIFYING = "receiver.verifying"
    RECEIVER_COMPLETED = "receiver.completed"
    RECEIVER_ERROR = "receiver.error"
    RECEIVER_STOPPED = "receiver.stopped"

    # Calibration events
    CALIBRATION_STARTED = "calibration.started"
    CALIBRATION_COMPLETED = "calibration.completed"


@dataclass(frozen=True)
class Event:
    """Event data structure."""
    type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


class EventBus:
    """Thread-safe event bus for pub/sub messaging."""

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()
        self._event_history: List[Event] = []
        self._max_history = 1000

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> Callable[[], None]:
        """
        Subscribe to an event type.

        Returns:
            Unsubscribe function
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

        def unsubscribe():
            with self._lock:
                if event_type in self._subscribers:
                    try:
                        self._subscribers[event_type].remove(callback)
                    except ValueError:
                        pass

        return unsubscribe

    def subscribe_all(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        """Subscribe to all events."""
        unsubscribes = []
        for event_type in EventType:
            unsubscribes.append(self.subscribe(event_type, callback))

        def unsubscribe_all():
            for u in unsubscribes:
                u()

        return unsubscribe_all

    def emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to all subscribers."""
        event = Event(type=event_type, data=data or {})

        with self._lock:
            # Add to history
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

            # Get subscribers
            subscribers = self._subscribers.get(event_type, []).copy()

        # Call subscribers outside lock
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error("Event callback error for %s: %s", event_type.value, e)

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """Get recent event history."""
        with self._lock:
            history = self._event_history.copy()

        if event_type:
            history = [e for e in history if e.type == event_type]

        return history[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._event_history.clear()


# Global event bus instance
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def emit_event(event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
    """Convenience function to emit an event on the global bus."""
    get_event_bus().emit(event_type, data)


# Pre-defined event emitters for common scenarios
def emit_transmission_started(message: str, sample_rate: int, symbol_duration: float, amplitude: float) -> None:
    """Emit transmission started event."""
    emit_event(EventType.TRANSMISSION_STARTED, {
        "message": message,
        "sample_rate": sample_rate,
        "symbol_duration": symbol_duration,
        "amplitude": amplitude,
    })


def emit_transmission_progress(progress: float, elapsed: float, total: float) -> None:
    """Emit transmission progress event."""
    emit_event(EventType.TRANSMISSION_PROGRESS, {
        "progress": progress,  # 0.0 to 1.0
        "elapsed_seconds": elapsed,
        "total_seconds": total,
    })


def emit_transmission_completed(message: str, duration: float) -> None:
    """Emit transmission completed event."""
    emit_event(EventType.TRANSMISSION_COMPLETED, {
        "message": message,
        "duration_seconds": duration,
    })


def emit_transmission_cancelled(message: str) -> None:
    """Emit transmission cancelled event."""
    emit_event(EventType.TRANSMISSION_CANCELLED, {
        "message": message,
    })


def emit_transmission_error(message: str, error: str) -> None:
    """Emit transmission error event."""
    emit_event(EventType.TRANSMISSION_ERROR, {
        "message": message,
        "error": error,
    })


def emit_receiver_listening(config: Dict[str, Any]) -> None:
    """Emit receiver listening event."""
    emit_event(EventType.RECEIVER_LISTENING, {
        "sample_rate": config.get("sample_rate"),
        "symbol_duration": config.get("symbol_duration"),
        "freq_zero": config.get("freq_zero"),
        "freq_one": config.get("freq_one"),
    })


def emit_receiver_signal_detected(frequency: float, confidence: float, energy_zero: float, energy_one: float) -> None:
    """Emit receiver signal detected event."""
    emit_event(EventType.RECEIVER_SIGNAL_DETECTED, {
        "frequency_hz": frequency,
        "confidence": confidence,
        "energy_zero": energy_zero,
        "energy_one": energy_one,
    })


def emit_receiver_preamble_detected() -> None:
    """Emit receiver preamble detected event."""
    emit_event(EventType.RECEIVER_PREAMBLE_DETECTED, {})


def emit_receiver_sync_locked() -> None:
    """Emit receiver sync locked event."""
    emit_event(EventType.RECEIVER_SYNC_LOCKED, {})


def emit_receiver_receiving(frame_progress: int, frame_total: int) -> None:
    """Emit receiver receiving event."""
    emit_event(EventType.RECEIVER_RECEIVING, {
        "frame_progress": frame_progress,
        "frame_total": frame_total,
        "progress_percent": (frame_progress / frame_total * 100) if frame_total > 0 else 0,
    })


def emit_receiver_verifying() -> None:
    """Emit receiver verifying event."""
    emit_event(EventType.RECEIVER_VERIFYING, {})


def emit_receiver_completed(message: str, checksum_valid: bool, confidence: float) -> None:
    """Emit receiver completed event."""
    emit_event(EventType.RECEIVER_COMPLETED, {
        "message": message,
        "checksum_valid": checksum_valid,
        "confidence": confidence,
    })


def emit_receiver_error(error: str, state: str) -> None:
    """Emit receiver error event."""
    emit_event(EventType.RECEIVER_ERROR, {
        "error": error,
        "state": state,
    })


def emit_receiver_stopped() -> None:
    """Emit receiver stopped event."""
    emit_event(EventType.RECEIVER_STOPPED, {})


def emit_calibration_started(config: Dict[str, Any]) -> None:
    """Emit calibration started event."""
    emit_event(EventType.CALIBRATION_STARTED, config)


def emit_calibration_completed(results: Dict[str, Any]) -> None:
    """Emit calibration completed event."""
    emit_event(EventType.CALIBRATION_COMPLETED, results)