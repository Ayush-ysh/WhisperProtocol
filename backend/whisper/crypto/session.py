"""Session Lifecycle and Security State Management for WhisperProtocol."""

from enum import Enum
import time
import struct
from typing import Optional, Set, Dict, Any
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from .x25519 import generate_keypair, derive_shared_secret, export_public_key, load_public_key
from .hkdf import derive_session_keys, SessionKeys
from .aes_gcm import (
    encrypt_and_pack,
    unpack_and_decrypt,
    generate_nonce,
    GCM_NONCE_LEN,
    GCM_OVERHEAD,
)
from .errors import (
    SASNotVerifiedError,
    SASRejectedError,
    SessionExpiredError,
    SessionNotActiveError,
    ReplayAttackError,
    CryptoError,
)

DEFAULT_SESSION_TTL_SECONDS: float = 300.0  # 5 minutes


class SessionRole(str, Enum):
    """Role of the local device in this cryptographic session."""
    SENDER = "sender"
    RECEIVER = "receiver"


class SessionState(str, Enum):
    """Lifecycle states of a cryptographic session."""
    INITIALIZING = "initializing"
    SAS_PENDING = "sas_pending"
    SAS_VERIFIED = "sas_verified"
    SAS_REJECTED = "sas_rejected"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class CryptoSession:
    """
    Manages ephemeral X25519 keys, HKDF directional session keys,
    mandatory SAS verification, nonce tracking, and replay protection.
    """

    def __init__(
        self,
        session_id: int,
        role: SessionRole,
        ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
        private_key: Optional[X25519PrivateKey] = None,
        public_key_bytes: Optional[bytes] = None,
    ) -> None:
        self.session_id: int = session_id
        self.role: SessionRole = role
        self.ttl_seconds: float = ttl_seconds
        self.created_at: float = time.time()
        self.state: SessionState = SessionState.INITIALIZING

        # Ephemeral Keypair
        if private_key is not None and public_key_bytes is not None:
            self._private_key: X25519PrivateKey = private_key
            self.local_public_key: bytes = public_key_bytes
        else:
            self._private_key, self.local_public_key = generate_keypair()

        self.peer_public_key: Optional[bytes] = None
        self._shared_secret: Optional[bytes] = None
        self._session_keys: Optional[SessionKeys] = None

        # Anti-Replay Nonce Tracking
        self._seen_rx_nonces: Set[bytes] = set()
        self._seen_tx_nonces: Set[bytes] = set()

        # Sequence numbers
        self._tx_seq_num: int = 0
        self._last_rx_seq_num: int = -1

    @property
    def is_expired(self) -> bool:
        """Check if session duration has exceeded its TTL."""
        if self.state in (SessionState.TERMINATED, SessionState.EXPIRED):
            return True
        if (time.time() - self.created_at) > self.ttl_seconds:
            self.state = SessionState.EXPIRED
            return True
        return False

    @property
    def sas_code(self) -> str:
        """Get the 6-digit visual SAS code formatted as 'XXX-XXX'."""
        if self._session_keys is None:
            raise CryptoError("Cannot get SAS code: keys have not been derived yet")
        return self._session_keys.sas_code

    @property
    def sas_numeric(self) -> int:
        """Get the integer SAS value."""
        if self._session_keys is None:
            raise CryptoError("Cannot get SAS numeric: keys have not been derived yet")
        return self._session_keys.sas_numeric

    def establish_peer_key(self, peer_public_bytes: bytes) -> str:
        """
        Record peer public key, perform DH key exchange, and derive directional keys and SAS.
        Transitions session to SAS_PENDING.

        Returns:
            str: The derived 6-digit SAS code for visual verification.
        """
        self._check_not_expired()
        if self.state not in (SessionState.INITIALIZING, SessionState.SAS_PENDING):
            raise CryptoError(f"Cannot establish peer key in state {self.state.value}")

        self.peer_public_key = peer_public_bytes
        self._shared_secret = derive_shared_secret(self._private_key, peer_public_bytes)

        # Align transcript info order: sender first, receiver second
        if self.role == SessionRole.SENDER:
            sender_pub = self.local_public_key
            receiver_pub = peer_public_bytes
        else:
            sender_pub = peer_public_bytes
            receiver_pub = self.local_public_key

        self._session_keys = derive_session_keys(
            shared_secret=self._shared_secret,
            sender_pub=sender_pub,
            receiver_pub=receiver_pub,
        )
        self.state = SessionState.SAS_PENDING
        return self._session_keys.sas_code

    def confirm_sas(self, confirmed: bool) -> None:
        """
        Record the user's explicit visual confirmation of the 6-digit SAS code.

        Args:
            confirmed: True if user verified matching SAS on both devices, False if mismatched.
        """
        self._check_not_expired()
        if self.state != SessionState.SAS_PENDING:
            raise CryptoError(f"Cannot confirm SAS in state {self.state.value} (must be in 'sas_pending')")

        if confirmed:
            self.state = SessionState.ACTIVE
        else:
            self.state = SessionState.SAS_REJECTED

    def build_aad(self, frame_type: int, seq_num: int) -> bytes:
        """Construct standard Additional Authenticated Data binding session ID, frame type, and seq."""
        return struct.pack(">IBH", self.session_id, frame_type, seq_num)

    def encrypt_outgoing(self, plaintext: bytes, aad: Optional[bytes] = None) -> bytes:
        """
        Encrypt and pack an outgoing payload using the directional key.
        Guarded by mandatory SAS verification.

        Returns:
            bytes: Canonical packed binary [NONCE 12B][TAG 16B][CIPHERTEXT].
        """
        self._check_not_expired()
        self._check_active_for_transfer()

        assert self._session_keys is not None
        # Sender role uses sender_key; Receiver role uses receiver_key
        key = (
            self._session_keys.sender_key
            if self.role == SessionRole.SENDER
            else self._session_keys.receiver_key
        )

        # Generate unique nonce not previously used in this session
        nonce = generate_nonce()
        while nonce in self._seen_tx_nonces:
            nonce = generate_nonce()
        self._seen_tx_nonces.add(nonce)

        packed = encrypt_and_pack(plaintext, key, nonce=nonce, aad=aad)
        self._tx_seq_num += 1
        return packed

    def decrypt_incoming(self, packed_payload: bytes, aad: Optional[bytes] = None) -> bytes:
        """
        Authenticate, decrypt, and unpack an incoming payload using the opposite directional key.
        Guarded by mandatory SAS verification and anti-replay nonce tracking.

        Raises:
            SASNotVerifiedError: If SAS has not been verified.
            ReplayAttackError: If nonce was previously seen in this session.
            DecryptionError: If authentication tag fails or data is corrupt.
        """
        self._check_not_expired()
        self._check_active_for_transfer()

        if len(packed_payload) < GCM_OVERHEAD:
            raise CryptoError(f"Packed payload too short ({len(packed_payload)} bytes)")

        # Extract nonce to check for replay
        nonce = packed_payload[:GCM_NONCE_LEN]
        if nonce in self._seen_rx_nonces:
            raise ReplayAttackError(
                f"Replay attack detected: nonce {nonce.hex()} was already received in session {self.session_id:#010x}"
            )
        self._seen_rx_nonces.add(nonce)

        assert self._session_keys is not None
        # Incoming from peer: Sender uses receiver_key; Receiver uses sender_key
        key = (
            self._session_keys.receiver_key
            if self.role == SessionRole.SENDER
            else self._session_keys.sender_key
        )

        plaintext = unpack_and_decrypt(packed_payload, key, aad=aad)
        return plaintext

    def terminate(self) -> None:
        """Explicitly end the session and wipe keys from memory."""
        self.state = SessionState.TERMINATED
        self._shared_secret = None
        self._session_keys = None

    def get_status(self) -> Dict[str, Any]:
        """Return safe, non-sensitive session metadata for telemetry/UI."""
        return {
            "session_id": self.session_id,
            "role": self.role.value,
            "state": self.state.value,
            "is_expired": self.is_expired,
            "sas_code": self._session_keys.sas_code if self._session_keys else None,
            "has_peer_key": self.peer_public_key is not None,
            "tx_packets": len(self._seen_tx_nonces),
            "rx_packets": len(self._seen_rx_nonces),
            "age_seconds": round(time.time() - self.created_at, 2),
            "ttl_seconds": self.ttl_seconds,
        }

    def _check_not_expired(self) -> None:
        if self.is_expired:
            raise SessionExpiredError(f"Session {self.session_id:#010x} has expired (TTL={self.ttl_seconds}s)")

    def _check_active_for_transfer(self) -> None:
        if self.state == SessionState.SAS_REJECTED:
            raise SASRejectedError(f"Transfer blocked: SAS verification was rejected for session {self.session_id:#010x}")
        if self.state == SessionState.SAS_PENDING:
            raise SASNotVerifiedError(
                f"Cannot transfer payload: SAS code '{self.sas_code}' requires user confirmation first"
            )
        if self.state != SessionState.ACTIVE:
            raise SessionNotActiveError(f"Session is not active (current state: {self.state.value})")
