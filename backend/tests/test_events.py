"""Tests for WhisperProtocol event system."""

import pytest
from whisper.events import (
    Event,
    EventType,
    EventBus,
    get_event_bus,
    emit_event,
)
from whisper.protocol.encoder import encode_message
from whisper.protocol.demodulator import (
    DemodulatorStateMachine,
    ReceiverConfig,
    SymbolDecision,
    SymbolDetection,
    ReceiverState,
)
from whisper.protocol.constants import PREAMBLE_BITS, SYNC_BITS, DEFAULT_SAMPLE_RATE


class TestEventBus:
    """Tests for EventBus pub/sub messaging."""

    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []

        unsubscribe = bus.subscribe(
            EventType.TRANSMISSION_STARTED,
            lambda event: received.append(event),
        )

        bus.emit(EventType.TRANSMISSION_STARTED, {"test": "data"})
        assert len(received) == 1
        assert received[0].type == EventType.TRANSMISSION_STARTED
        assert received[0].data["test"] == "data"

        # Test unsubscribe
        unsubscribe()
        bus.emit(EventType.TRANSMISSION_STARTED, {"test": "data2"})
        assert len(received) == 1

    def test_subscribe_all(self):
        bus = EventBus()
        received = []

        unsubscribe_all = bus.subscribe_all(lambda event: received.append(event))

        bus.emit(EventType.TRANSMISSION_STARTED, {})
        bus.emit(EventType.TRANSMISSION_COMPLETED, {})
        assert len(received) == 2

        unsubscribe_all()
        bus.emit(EventType.RECEIVER_LISTENING, {})
        assert len(received) == 2

    def test_event_history(self):
        bus = EventBus()
        bus.clear_history()

        bus.emit(EventType.TRANSMISSION_STARTED, {"idx": 1})
        bus.emit(EventType.TRANSMISSION_PROGRESS, {"idx": 2})
        bus.emit(EventType.TRANSMISSION_COMPLETED, {"idx": 3})

        history = bus.get_history()
        assert len(history) == 3
        assert history[0].data["idx"] == 1

        # Filter history by type
        started = bus.get_history(event_type=EventType.TRANSMISSION_STARTED)
        assert len(started) == 1
        assert started[0].data["idx"] == 1


class TestEncoderEventIntegration:
    """Tests that encode_message emits events."""

    def test_encode_message_emits_events(self):
        bus = get_event_bus()
        events = []

        unsub1 = bus.subscribe(
            EventType.TRANSMISSION_STARTED,
            lambda e: events.append(e),
        )
        unsub2 = bus.subscribe(
            EventType.TRANSMISSION_COMPLETED,
            lambda e: events.append(e),
        )

        try:
            encode_message("TEST_EVENTS")
            assert any(e.type == EventType.TRANSMISSION_STARTED for e in events)
            assert any(e.type == EventType.TRANSMISSION_COMPLETED for e in events)
            completed = next(e for e in events if e.type == EventType.TRANSMISSION_COMPLETED)
            assert completed.data["message"] == "TEST_EVENTS"
        finally:
            unsub1()
            unsub2()


class TestDemodulatorEventIntegration:
    """Tests that DemodulatorStateMachine emits events."""

    def test_state_machine_emits_events(self):
        bus = get_event_bus()
        events = []

        unsub_all = bus.subscribe_all(lambda e: events.append(e))

        try:
            config = ReceiverConfig()
            sm = DemodulatorStateMachine(config)

            # Helper for symbol detection
            def make_det(bit: int) -> SymbolDetection:
                return SymbolDetection(
                    decision=SymbolDecision.ONE if bit == 1 else SymbolDecision.ZERO,
                    detected_frequency=19000.0 if bit == 1 else 18000.0,
                    energy_zero=0.0 if bit == 1 else 1.0,
                    energy_one=1.0 if bit == 1 else 0.0,
                    noise_floor=0.01,
                    snr_zero_db=0.0 if bit == 1 else 20.0,
                    snr_one_db=20.0 if bit == 1 else 0.0,
                    confidence=0.9,
                    timestamp=0.0,
                )

            # Feed preamble
            for b in PREAMBLE_BITS:
                sm.process_symbol(make_det(b))

            assert any(e.type == EventType.RECEIVER_PREAMBLE_DETECTED for e in events)

            # Feed sync
            for b in SYNC_BITS:
                sm.process_symbol(make_det(b))

            assert any(e.type == EventType.RECEIVER_SYNC_LOCKED for e in events)
        finally:
            unsub_all()
