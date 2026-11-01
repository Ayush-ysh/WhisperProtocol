"""HKDF-SHA256 Key Derivation and Short Authentication String (SAS) for WhisperProtocol."""

from dataclasses import dataclass
import struct
from typing import Optional, Tuple
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from .errors import CryptoError

DEFAULT_HKDF_SALT: bytes = b"whisper-v1-acoustic"
SENDER_KEY_INFO_PREFIX: bytes = b"whisper-s2r-key-v1"
RECEIVER_KEY_INFO_PREFIX: bytes = b"whisper-r2s-key-v1"
SAS_INFO_PREFIX: bytes = b"whisper-sas-v1"
KEY_LEN_AES256: int = 32


@dataclass(frozen=True)
class SessionKeys:
    """Directional keys and visual authentication string derived for a session."""
    sender_key: bytes        # 32 bytes for Sender -> Receiver transmission
    receiver_key: bytes      # 32 bytes for Receiver -> Sender transmission
    sas_code: str            # 6-digit visual code formatted as "XXX-XXX" (e.g., "842-195")
    sas_numeric: int         # Numeric value between 0 and 999999
    raw_sas: str             # Unformatted 6-digit string (e.g., "842195")


def derive_session_keys(
    shared_secret: bytes,
    salt: Optional[bytes] = None,
    sender_pub: bytes = b"",
    receiver_pub: bytes = b"",
) -> SessionKeys:
    """
    Derive directional AES-256 session keys and a 6-digit Short Authentication String (SAS)
    using HKDF-SHA256 bound to the participant public keys.

    Args:
        shared_secret: 32-byte shared secret from X25519 DH exchange.
        salt: Optional salt; defaults to DEFAULT_HKDF_SALT (domain separated).
        sender_pub: 32-byte public key of the sender device.
        receiver_pub: 32-byte public key of the receiver device.

    Returns:
        SessionKeys: Container with directional keys and SAS representations.

    Raises:
        CryptoError: If shared_secret is invalid or derivation fails.
    """
    if not isinstance(shared_secret, (bytes, bytearray)) or len(shared_secret) != 32:
        raise CryptoError(f"Shared secret must be exactly 32 bytes, got {len(shared_secret) if hasattr(shared_secret, '__len__') else 'unknown'}")

    hkdf_salt = salt if salt is not None else DEFAULT_HKDF_SALT
    transcript_info = bytes(sender_pub) + bytes(receiver_pub)

    try:
        # 1. Derive Sender -> Receiver AES key (32 bytes)
        kdf_sender = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_LEN_AES256,
            salt=hkdf_salt,
            info=SENDER_KEY_INFO_PREFIX + transcript_info,
        )
        sender_key = kdf_sender.derive(shared_secret)

        # 2. Derive Receiver -> Sender AES key (32 bytes)
        kdf_receiver = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_LEN_AES256,
            salt=hkdf_salt,
            info=RECEIVER_KEY_INFO_PREFIX + transcript_info,
        )
        receiver_key = kdf_receiver.derive(shared_secret)

        # 3. Derive Short Authentication String (SAS)
        kdf_sas = HKDF(
            algorithm=hashes.SHA256(),
            length=4,
            salt=hkdf_salt,
            info=SAS_INFO_PREFIX + transcript_info,
        )
        sas_bytes = kdf_sas.derive(shared_secret)
        sas_numeric = struct.unpack(">I", sas_bytes)[0] % 1_000_000
        raw_sas = f"{sas_numeric:06d}"
        sas_code = f"{raw_sas[:3]}-{raw_sas[3:]}"

        return SessionKeys(
            sender_key=sender_key,
            receiver_key=receiver_key,
            sas_code=sas_code,
            sas_numeric=sas_numeric,
            raw_sas=raw_sas,
        )
    except Exception as e:
        raise CryptoError(f"Failed to derive session keys via HKDF: {e}") from e


def compute_sas_only(
    shared_secret: bytes,
    salt: Optional[bytes] = None,
    sender_pub: bytes = b"",
    receiver_pub: bytes = b"",
) -> Tuple[str, int]:
    """
    Derive only the SAS code and numeric value.
    
    Returns:
        tuple[str, int]: (sas_code 'XXX-XXX', numeric_value)
    """
    keys = derive_session_keys(shared_secret, salt, sender_pub, receiver_pub)
    return keys.sas_code, keys.sas_numeric
