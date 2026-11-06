"""Secure Acoustic Transfer Engine for WhisperProtocol.

Coordinates the end-to-end secure transmission lifecycle:
1. Sender: TRANSFER_OFFER (metadata + X25519 public key)
2. Receiver: explicit user prompt -> TRANSFER_ACCEPT (X25519 public key) or TRANSFER_DECLINE
3. Both: compute and display 6-digit SAS code
4. Both: user visual verification gate
5. Sender: AES-256-GCM encrypted DATA_FRAME + Reed-Solomon ECC
6. Receiver: ECC correction, AEAD authentication, decryption, and acoustic TRANSFER_ACK
7. Sender: verified completion confirmation
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import secrets
import struct
import threading
import time
from typing import Callable, Dict, Optional, Any

import numpy as np

from whisper.audio.coordinator import HalfDuplexAudioCoordinator
from whisper.crypto import (
    CryptoSession,
    SessionRole,
    SessionState,
    CryptoError,
    SASNotVerifiedError,
)
from whisper.protocol.constants import (
    MODULATION_PROFILES,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
)
from whisper.protocol.demodulator import ReceiverConfig, FrameDecodeResult
from whisper.protocol.ecc import rs_encode, rs_decode
from whisper.protocol.frames import (
    FrameType,
    ProtocolFrame,
    create_transfer_offer,
    create_transfer_accept,
    create_transfer_decline,
    create_data_frame,
    create_transfer_ack,
    create_transfer_error,
    encode_protocol_frame,
)
from whisper.protocol.modulation import modulate_bits

logger = logging.getLogger(__name__)


class TransferState(str, Enum):
    IDLE = "idle"
    OFFER_SENT = "offer_sent"
    OFFER_RECEIVED = "offer_received"
    SAS_PENDING = "sas_pending"
    SAS_VERIFIED = "sas_verified"
    TRANSMITTING = "transmitting"
    RECEIVING = "receiving"
    COMPLETED = "completed"
    DECLINED = "declined"
    FAILED = "failed"


@dataclass
class TransferSessionContext:
    session_id: int
    role: SessionRole
    state: TransferState
    file_name: str = ""
    file_size: int = 0
    payload_bytes: bytes = b""
    decrypted_bytes: bytes = b""
    peer_alias: str = ""
    peer_public_key: bytes = b""
    crypto_session: Optional[CryptoSession] = None
    sas_code: Optional[str] = None
    error_message: Optional[str] = None
    ecc_symbols: int = 8
    profile_name: str = "ultrasonic"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "role": self.role.value,
            "state": self.state.value,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "peer_alias": self.peer_alias,
            "sas_code": self.sas_code,
            "error_message": self.error_message,
            "ecc_symbols": self.ecc_symbols,
            "profile_name": self.profile_name,
            "created_at": self.created_at,
            "payload_received": len(self.decrypted_bytes) > 0,
        }


class TransferEngine:
    """End-to-end acoustic transfer engine executing the full authenticated handshake."""

    def __init__(
        self,
        local_alias: str = "WhisperNode",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        coordinator: Optional[HalfDuplexAudioCoordinator] = None,
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.local_alias: str = local_alias
        self.sample_rate: int = sample_rate
        self.on_event = on_event

        self._lock = threading.RLock()
        self._sessions: Dict[int, TransferSessionContext] = {}

        receiver_config = ReceiverConfig(
            sample_rate=self.sample_rate,
            symbol_duration=DEFAULT_SYMBOL_DURATION,
            canonical_framing=True,
        )

        self.coordinator = coordinator or HalfDuplexAudioCoordinator(
            receiver_config=receiver_config,
            on_frame_received=self._on_frame_received,
        )

    def _emit(self, event_name: str, data: Dict[str, Any]) -> None:
        """Emit high-level transfer event to bridge / UI."""
        if self.on_event:
            try:
                self.on_event(event_name, data)
            except Exception as e:
                logger.error("Failed to invoke transfer on_event for %s: %s", event_name, e)

    def initiate_transfer(
        self,
        file_name: str,
        payload: bytes,
        target_alias: str = "",
        profile_name: str = "ultrasonic",
        ecc_symbols: int = 8,
    ) -> int:
        """
        Sender action: Start transfer offer with ephemeral key agreement.
        
        Returns:
            int: 32-bit session_id.
        """
        session_id = secrets.randbits(31)
        crypto_session = CryptoSession(session_id=session_id, role=SessionRole.SENDER)

        ctx = TransferSessionContext(
            session_id=session_id,
            role=SessionRole.SENDER,
            state=TransferState.OFFER_SENT,
            file_name=file_name,
            file_size=len(payload),
            payload_bytes=payload,
            peer_alias=target_alias,
            crypto_session=crypto_session,
            ecc_symbols=ecc_symbols,
            profile_name=profile_name,
        )

        with self._lock:
            self._sessions[session_id] = ctx
            self.coordinator.start_listening()

        logger.info(
            "Initiating transfer '%s' (%d bytes) in session %#x...",
            file_name, len(payload), session_id
        )

        # Build TRANSFER_OFFER carrying sender's raw X25519 public key (32 bytes)
        offer_frame = create_transfer_offer(
            file_name=file_name,
            file_size=len(payload),
            session_id=session_id,
            public_key=crypto_session.local_public_key,
        )
        self._transmit_frame(offer_frame, profile_name)

        self._emit("transfer_offer_sent", ctx.to_dict())

        # Auto-retransmit offer up to 4 times (every 3.5s) until accepted or cancelled
        def offer_retransmit_worker():
            for attempt in range(1, 4):
                time.sleep(3.5)
                with self._lock:
                    curr_ctx = self._sessions.get(session_id)
                    if not curr_ctx or curr_ctx.state != TransferState.OFFER_SENT:
                        break
                logger.info("Auto re-transmitting TRANSFER_OFFER (attempt %d/4) for session %#x...", attempt + 1, session_id)
                try:
                    self._transmit_frame(offer_frame, profile_name)
                except Exception as e:
                    logger.debug("Offer re-transmit error: %s", e)

        threading.Thread(target=offer_retransmit_worker, daemon=True).start()
        return session_id

    def accept_transfer(self, session_id: int) -> bool:
        """
        Receiver action: Explicit user acceptance of an incoming transfer offer.
        Sends TRANSFER_ACCEPT with receiver's ephemeral public key.
        """
        with self._lock:
            ctx = self._sessions.get(session_id)
            if not ctx or ctx.state != TransferState.OFFER_RECEIVED:
                logger.error("Cannot accept transfer: session %#x not in OFFER_RECEIVED state", session_id)
                return False

            assert ctx.crypto_session is not None
            # Derive session keys and 6-digit SAS code
            sas_code = ctx.crypto_session.establish_peer_key(ctx.peer_public_key)
            ctx.sas_code = sas_code
            ctx.state = TransferState.SAS_PENDING

            # Build TRANSFER_ACCEPT frame carrying receiver's raw X25519 public key
            accept_frame = create_transfer_accept(
                session_id=session_id,
                public_key=ctx.crypto_session.local_public_key,
            )

        logger.info("Accepting transfer %#x. Transmitting TRANSFER_ACCEPT...", session_id)
        self._transmit_frame(accept_frame, ctx.profile_name)

        # Auto-retransmit accept up to 3 times (every 3.0s) until data frame arrives
        def accept_retransmit_worker():
            for attempt in range(1, 3):
                time.sleep(3.0)
                with self._lock:
                    curr_ctx = self._sessions.get(session_id)
                    if not curr_ctx or curr_ctx.state != TransferState.SAS_PENDING:
                        break
                logger.info("Auto re-transmitting TRANSFER_ACCEPT (attempt %d/3) for session %#x...", attempt + 1, session_id)
                try:
                    self._transmit_frame(accept_frame, ctx.profile_name)
                except Exception as e:
                    logger.debug("Accept re-transmit error: %s", e)

        threading.Thread(target=accept_retransmit_worker, daemon=True).start()

        self._emit("sas_pending", ctx.to_dict())
        return True

    def decline_transfer(self, session_id: int, reason: str = "DECLINED") -> bool:
        """
        Receiver action: User explicitly declines incoming transfer offer.
        """
        with self._lock:
            ctx = self._sessions.get(session_id)
            if not ctx:
                return False
            ctx.state = TransferState.DECLINED
            ctx.error_message = reason

        decline_frame = create_transfer_decline(session_id=session_id, reason=reason)
        try:
            self._transmit_frame(decline_frame, ctx.profile_name)
        except Exception as e:
            logger.warning("Error transmitting decline: %s", e)

        self._emit("transfer_declined", ctx.to_dict())
        return True

    def confirm_sas(self, session_id: int, confirmed: bool) -> bool:
        """
        User action on either Sender or Receiver: Confirms matching 6-digit visual SAS code.
        """
        with self._lock:
            ctx = self._sessions.get(session_id)
            if not ctx or ctx.state != TransferState.SAS_PENDING:
                logger.error("Cannot confirm SAS: session %#x not in SAS_PENDING state", session_id)
                return False

            assert ctx.crypto_session is not None
            ctx.crypto_session.confirm_sas(confirmed)

            if not confirmed:
                ctx.state = TransferState.FAILED
                ctx.error_message = "SAS mismatch rejected by user"
                err_frame = create_transfer_error(session_id, error_code=0x01, message="SAS_MISMATCH")
                self._transmit_frame(err_frame, ctx.profile_name)
                self._emit("transfer_failed", ctx.to_dict())
                return False

            ctx.state = TransferState.SAS_VERIFIED

        if ctx.role == SessionRole.SENDER:
            # Sender proceeds to encrypt and transmit payload
            self._send_encrypted_data(ctx)
        else:
            # Receiver enters receiving state waiting for DATA_FRAME
            with self._lock:
                ctx.state = TransferState.RECEIVING
            self._emit("transfer_progress", {"session_id": session_id, "state": "awaiting_data"})

        return True

    def _send_encrypted_data(self, ctx: TransferSessionContext) -> None:
        """Sender helper: Encrypt payload with AES-256-GCM, apply RS ECC, and transmit DATA_FRAME."""
        with self._lock:
            ctx.state = TransferState.TRANSMITTING
            assert ctx.crypto_session is not None

            # 1. AAD binds session_id, frame_type, and sequence number
            seq_num = 1
            aad = ctx.crypto_session.build_aad(FrameType.DATA_FRAME, seq_num)

            # 2. Encrypt payload
            try:
                encrypted_blob = ctx.crypto_session.encrypt_outgoing(ctx.payload_bytes, aad=aad)
            except Exception as e:
                ctx.state = TransferState.FAILED
                ctx.error_message = f"Encryption failed: {e}"
                self._emit("transfer_failed", ctx.to_dict())
                return

            # 3. Apply Reed-Solomon ECC to the encrypted blob if configured
            if ctx.ecc_symbols > 0:
                frame_data = rs_encode(encrypted_blob, n_ecc_symbols=ctx.ecc_symbols)
            else:
                frame_data = encrypted_blob

        logger.info(
            "Transmitting encrypted DATA_FRAME (%d bytes raw, %d bytes with ECC) for session %#x...",
            len(ctx.payload_bytes), len(frame_data), ctx.session_id
        )

        data_frame = create_data_frame(
            session_id=ctx.session_id,
            seq_num=seq_num,
            data=frame_data,
        )
        self._transmit_frame(data_frame, ctx.profile_name)
        self._emit("transfer_progress", {"session_id": ctx.session_id, "state": "data_transmitted"})

    def get_session_status(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Return status dictionary of a transfer session."""
        with self._lock:
            ctx = self._sessions.get(session_id)
            return ctx.to_dict() if ctx else None

    def _transmit_frame(self, frame: ProtocolFrame, profile_name: str) -> None:
        """Modulate and transmit a canonical protocol frame."""
        profile = MODULATION_PROFILES.get(profile_name, MODULATION_PROFILES["ultrasonic"])
        bits = encode_protocol_frame(frame)
        waveform = modulate_bits(
            bits,
            sample_rate=self.sample_rate,
            symbol_duration=DEFAULT_SYMBOL_DURATION,
            amplitude=0.85,
            freq_zero=profile.freq_zero,
            freq_one=profile.freq_one,
            phase_continuous=True,
        )
        self.coordinator.transmit(waveform, sample_rate=self.sample_rate)

    def _on_frame_received(self, result: FrameDecodeResult) -> None:
        """Dispatcher for all incoming canonical protocol frames."""
        if not result.success or not result.protocol_frame:
            return

        frame: ProtocolFrame = result.protocol_frame
        ftype = frame.frame_type

        if ftype == FrameType.TRANSFER_OFFER:
            self._handle_transfer_offer(frame)
        elif ftype == FrameType.TRANSFER_ACCEPT:
            self._handle_transfer_accept(frame)
        elif ftype == FrameType.TRANSFER_DECLINE:
            self._handle_transfer_decline(frame)
        elif ftype == FrameType.DATA_FRAME:
            self._handle_data_frame(frame)
        elif ftype == FrameType.TRANSFER_ACK:
            self._handle_transfer_ack(frame)
        elif ftype == FrameType.TRANSFER_ERROR:
            self._handle_transfer_error(frame)

    def _handle_transfer_offer(self, frame: ProtocolFrame) -> None:
        """Receiver: Parse incoming offer, initialize CryptoSession, and alert user."""
        payload = frame.payload
        if len(payload) < 37:  # 1B len + 0B name + 4B size + 32B pubkey
            logger.warning("Malformed TRANSFER_OFFER payload: len=%d", len(payload))
            return

        name_len = payload[0]
        if len(payload) < 1 + name_len + 4 + 32:
            logger.warning("Truncated TRANSFER_OFFER payload")
            return

        file_name = payload[1 : 1 + name_len].decode("utf-8", errors="replace")
        file_size = struct.unpack(">I", payload[1 + name_len : 5 + name_len])[0]
        sender_pubkey = payload[5 + name_len : 37 + name_len]

        crypto_session = CryptoSession(session_id=frame.session_id, role=SessionRole.RECEIVER)

        receiver_cfg = getattr(self.coordinator, "receiver_config", None)
        profile_name = "audible" if (receiver_cfg and receiver_cfg.freq_zero < 16000) else "ultrasonic"

        ctx = TransferSessionContext(
            session_id=frame.session_id,
            role=SessionRole.RECEIVER,
            state=TransferState.OFFER_RECEIVED,
            file_name=file_name,
            file_size=file_size,
            peer_public_key=sender_pubkey,
            crypto_session=crypto_session,
            profile_name=profile_name,
        )

        with self._lock:
            self._sessions[frame.session_id] = ctx

        logger.info(
            "Received TRANSFER_OFFER for '%s' (%d bytes) in session %#x. Prompting user.",
            file_name, file_size, frame.session_id
        )
        self._emit("transfer_offer_received", ctx.to_dict())

    def _handle_transfer_accept(self, frame: ProtocolFrame) -> None:
        """Sender: Peer accepted! Extract receiver public key, compute SAS, and prompt user."""
        with self._lock:
            ctx = self._sessions.get(frame.session_id)
            if not ctx or ctx.role != SessionRole.SENDER or ctx.state != TransferState.OFFER_SENT:
                return

            if len(frame.payload) < 32:
                logger.warning("TRANSFER_ACCEPT payload missing 32-byte public key")
                return

            receiver_pubkey = frame.payload[:32]
            ctx.peer_public_key = receiver_pubkey
            assert ctx.crypto_session is not None

            # Derive session keys and 6-digit SAS code
            sas_code = ctx.crypto_session.establish_peer_key(receiver_pubkey)
            ctx.sas_code = sas_code
            ctx.state = TransferState.SAS_PENDING

        logger.info("Receiver accepted transfer %#x. SAS is %s. Prompting user for match.", frame.session_id, sas_code)
        self._emit("sas_pending", ctx.to_dict())

    def _handle_transfer_decline(self, frame: ProtocolFrame) -> None:
        """Sender: Peer declined transfer offer."""
        with self._lock:
            ctx = self._sessions.get(frame.session_id)
            if not ctx:
                return
            ctx.state = TransferState.DECLINED
            ctx.error_message = frame.payload.decode("utf-8", errors="replace")

        logger.info("Transfer %#x was declined: %s", frame.session_id, ctx.error_message)
        self._emit("transfer_declined", ctx.to_dict())

    def _handle_data_frame(self, frame: ProtocolFrame) -> None:
        """Receiver: Correct ECC, decrypt payload, send TRANSFER_ACK, and mark complete."""
        with self._lock:
            ctx = self._sessions.get(frame.session_id)
            if not ctx or ctx.role != SessionRole.RECEIVER:
                return

            raw_data = frame.payload
            # 1. Reed-Solomon Error Correction
            if ctx.ecc_symbols > 0:
                try:
                    decrypted_data, _ = rs_decode(raw_data, n_ecc_symbols=ctx.ecc_symbols)
                except Exception as e:
                    logger.error("RS ECC decode failed: %s", e)
                    ctx.state = TransferState.FAILED
                    ctx.error_message = f"ECC uncorrectable error: {e}"
                    self._emit("transfer_failed", ctx.to_dict())
                    return
            else:
                decrypted_data = raw_data

            # 2. AEAD Decryption and Authentication
            assert ctx.crypto_session is not None
            aad = ctx.crypto_session.build_aad(frame.frame_type, frame.seq_num)
            try:
                plaintext = ctx.crypto_session.decrypt_incoming(decrypted_data, aad=aad)
            except Exception as e:
                logger.error("AEAD decryption failed: %s", e)
                ctx.state = TransferState.FAILED
                ctx.error_message = f"Decryption/authentication error: {e}"
                self._emit("transfer_failed", ctx.to_dict())
                return

            ctx.decrypted_bytes = plaintext
            ctx.state = TransferState.COMPLETED

        logger.info("Decrypted %d-byte payload in session %#x. Sending TRANSFER_ACK...", len(plaintext), frame.session_id)

        # 3. Transmit acoustic TRANSFER_ACK confirming authenticated delivery
        ack_frame = create_transfer_ack(session_id=frame.session_id, seq_num=frame.seq_num)
        self._transmit_frame(ack_frame, ctx.profile_name)

        self._emit("transfer_completed", {
            "session_id": ctx.session_id,
            "file_name": ctx.file_name,
            "bytes_received": len(plaintext),
            "payload_text": plaintext.decode("utf-8", errors="replace"),
        })

    def _handle_transfer_ack(self, frame: ProtocolFrame) -> None:
        """Sender: Authenticated receipt confirmed by receiver."""
        with self._lock:
            ctx = self._sessions.get(frame.session_id)
            if not ctx or ctx.role != SessionRole.SENDER:
                return

            ctx.state = TransferState.COMPLETED

        logger.info("Acoustic TRANSFER_ACK confirmed for session %#x!", frame.session_id)
        self._emit("transfer_completed", {
            "session_id": ctx.session_id,
            "file_name": ctx.file_name,
            "status": "verified_by_receiver",
        })

    def _handle_transfer_error(self, frame: ProtocolFrame) -> None:
        """Handle error frame."""
        with self._lock:
            ctx = self._sessions.get(frame.session_id)
            if ctx:
                ctx.state = TransferState.FAILED
                ctx.error_message = frame.payload.decode("utf-8", errors="replace")

        logger.error("Received TRANSFER_ERROR in session %#x: %s", frame.session_id, frame.payload)
        if ctx:
            self._emit("transfer_failed", ctx.to_dict())
