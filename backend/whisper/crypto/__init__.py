"""WhisperProtocol Cryptography Module.

Provides offline-first authenticated encryption for acoustic air-gap communication:
- Ephemeral X25519 Diffie-Hellman key agreement
- HKDF-SHA256 directional session key derivation
- 6-digit Short Authentication String (SAS) visual pairing verification
- AES-256-GCM authenticated encryption with anti-replay nonce tracking
- Session lifecycle and TTL management
"""

from .errors import (
    CryptoError,
    KeyExchangeError,
    SASNotVerifiedError,
    SASRejectedError,
    SessionExpiredError,
    SessionNotActiveError,
    ReplayAttackError,
    DecryptionError,
    InvalidNonceError,
)

from .x25519 import (
    generate_keypair,
    export_public_key,
    load_public_key,
    derive_shared_secret,
    X25519_KEY_LEN,
)

from .hkdf import (
    derive_session_keys,
    compute_sas_only,
    SessionKeys,
    DEFAULT_HKDF_SALT,
)

from .aes_gcm import (
    encrypt_gcm,
    decrypt_gcm,
    pack_encrypted_payload,
    unpack_encrypted_payload,
    encrypt_and_pack,
    unpack_and_decrypt,
    generate_nonce,
    GCM_NONCE_LEN,
    GCM_TAG_LEN,
    GCM_OVERHEAD,
)

from .session import (
    CryptoSession,
    SessionRole,
    SessionState,
    DEFAULT_SESSION_TTL_SECONDS,
)

__all__ = [
    # Errors
    "CryptoError",
    "KeyExchangeError",
    "SASNotVerifiedError",
    "SASRejectedError",
    "SessionExpiredError",
    "SessionNotActiveError",
    "ReplayAttackError",
    "DecryptionError",
    "InvalidNonceError",
    # X25519
    "generate_keypair",
    "export_public_key",
    "load_public_key",
    "derive_shared_secret",
    "X25519_KEY_LEN",
    # HKDF
    "derive_session_keys",
    "compute_sas_only",
    "SessionKeys",
    "DEFAULT_HKDF_SALT",
    # AES-GCM
    "encrypt_gcm",
    "decrypt_gcm",
    "pack_encrypted_payload",
    "unpack_encrypted_payload",
    "encrypt_and_pack",
    "unpack_and_decrypt",
    "generate_nonce",
    "GCM_NONCE_LEN",
    "GCM_TAG_LEN",
    "GCM_OVERHEAD",
    # Session
    "CryptoSession",
    "SessionRole",
    "SessionState",
    "DEFAULT_SESSION_TTL_SECONDS",
]
