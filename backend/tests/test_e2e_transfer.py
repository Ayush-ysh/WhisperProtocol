"""End-to-End Tests for WhisperProtocol Acoustic Transfer Engine (Milestone E)."""

import pytest
import time
from whisper.engine.transfer import TransferEngine, TransferState
from whisper.protocol.frames import (
    encode_protocol_frame,
    decode_protocol_frame,
    FrameType,
)
from whisper.protocol.demodulator import FrameDecodeResult
from whisper.crypto import SessionRole


class DirectLoopbackCoordinator:
    """Coordinator that directly pipes encoded frames to a connected peer engine."""

    def __init__(self):
        self.peer_engine = None
        self.is_listening = True

    def start_listening(self):
        self.is_listening = True

    def stop_listening(self):
        self.is_listening = False

    def transmit(self, waveform, sample_rate, output_device=None, blocking=True):
        pass


class TestEndToEndTransferEngine:
    """Full lifecycle acoustic transfer tests with authenticated encryption and SAS."""

    def setup_method(self):
        # Alice (Sender)
        self.alice_coord = DirectLoopbackCoordinator()
        self.alice_events = []
        self.alice = TransferEngine(
            local_alias="Alice",
            coordinator=self.alice_coord,
            on_event=lambda ev, data: self.alice_events.append((ev, data)),
        )

        # Bob (Receiver)
        self.bob_coord = DirectLoopbackCoordinator()
        self.bob_events = []
        self.bob = TransferEngine(
            local_alias="Bob",
            coordinator=self.bob_coord,
            on_event=lambda ev, data: self.bob_events.append((ev, data)),
        )

        # Connect Alice's transmit to Bob's receive
        def alice_transmit_hook(frame, profile_name):
            bits = encode_protocol_frame(frame)
            decoded = decode_protocol_frame(bits)
            res = FrameDecodeResult(success=True, payload=decoded.payload, checksum_valid=True, protocol_frame=decoded)
            self.bob._on_frame_received(res)

        # Connect Bob's transmit to Alice's receive
        def bob_transmit_hook(frame, profile_name):
            bits = encode_protocol_frame(frame)
            decoded = decode_protocol_frame(bits)
            res = FrameDecodeResult(success=True, payload=decoded.payload, checksum_valid=True, protocol_frame=decoded)
            self.alice._on_frame_received(res)

        self.alice._transmit_frame = alice_transmit_hook
        self.bob._transmit_frame = bob_transmit_hook

    def test_complete_authenticated_transfer_lifecycle(self):
        secret_message = b"Top secret acoustic payload 2026"
        file_name = "secret.txt"

        # 1. Alice initiates transfer offer
        session_id = self.alice.initiate_transfer(
            file_name=file_name,
            payload=secret_message,
            target_alias="Bob",
            ecc_symbols=8,
        )

        alice_ctx = self.alice._sessions[session_id]
        assert alice_ctx.state == TransferState.OFFER_SENT

        # 2. Bob received the offer
        bob_ctx = self.bob._sessions.get(session_id)
        assert bob_ctx is not None
        assert bob_ctx.state == TransferState.OFFER_RECEIVED
        assert bob_ctx.file_name == file_name
        assert bob_ctx.file_size == len(secret_message)

        # 3. Bob accepts the offer
        accepted = self.bob.accept_transfer(session_id)
        assert accepted is True
        assert bob_ctx.state == TransferState.SAS_PENDING
        assert bob_ctx.sas_code is not None

        # Alice should have processed TRANSFER_ACCEPT and also derived the SAS
        assert alice_ctx.state == TransferState.SAS_PENDING
        assert alice_ctx.sas_code is not None

        # 4. SAS visual comparison: MUST MATCH!
        assert alice_ctx.sas_code == bob_ctx.sas_code
        assert len(alice_ctx.sas_code) == 7
        assert alice_ctx.sas_code[3] == "-"

        # 5. User confirms SAS match on both sides
        # Bob confirms first
        assert self.bob.confirm_sas(session_id, True) is True
        assert bob_ctx.state == TransferState.RECEIVING

        # Alice confirms second (which triggers encryption and data transmission)
        assert self.alice.confirm_sas(session_id, True) is True

        # 6. Data transmitted, decrypted by Bob, and acoustic ACK returned to Alice!
        assert bob_ctx.state == TransferState.COMPLETED
        assert bob_ctx.decrypted_bytes == secret_message

        assert alice_ctx.state == TransferState.COMPLETED

    def test_decline_transfer_offer(self):
        session_id = self.alice.initiate_transfer(
            file_name="notes.txt",
            payload=b"Hello Bob",
            target_alias="Bob",
        )

        bob_ctx = self.bob._sessions[session_id]
        assert bob_ctx.state == TransferState.OFFER_RECEIVED

        # Bob declines
        declined = self.bob.decline_transfer(session_id, reason="Busy right now")
        assert declined is True
        assert bob_ctx.state == TransferState.DECLINED

        # Alice receives decline
        alice_ctx = self.alice._sessions[session_id]
        assert alice_ctx.state == TransferState.DECLINED
        assert alice_ctx.error_message == "Busy right now"

    def test_sas_rejection_blocks_transfer(self):
        session_id = self.alice.initiate_transfer(
            file_name="plan.pdf",
            payload=b"Important design document",
            target_alias="Bob",
        )

        self.bob.accept_transfer(session_id)
        alice_ctx = self.alice._sessions[session_id]
        bob_ctx = self.bob._sessions[session_id]

        assert alice_ctx.state == TransferState.SAS_PENDING
        assert bob_ctx.state == TransferState.SAS_PENDING

        # Alice's user sees SAS mismatch and rejects
        confirmed = self.alice.confirm_sas(session_id, False)
        assert confirmed is False
        assert alice_ctx.state == TransferState.FAILED

        # Bob receives TRANSFER_ERROR and also fails
        assert bob_ctx.state == TransferState.FAILED
        assert bob_ctx.decrypted_bytes == b""
