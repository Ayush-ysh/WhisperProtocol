"""AES-256-GCM Authenticated Encryption for WhisperProtocol."""

import os
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from .errors import DecryptionError, InvalidNonceError, CryptoError

GCM_NONCE_LEN: int = 12  # 96 bits standard recommended by NIST SP 800-38D
GCM_TAG_LEN: int = 16    # 128 bits authentication tag
GCM_OVERHEAD: int = GCM_NONCE_LEN + GCM_TAG_LEN  # 28 bytes


def generate_nonce() -> bytes:
    """Generate a cryptographically secure 12-byte random nonce."""
    return os.urandom(GCM_NONCE_LEN)


def encrypt_gcm(
    plaintext: bytes,
    key: bytes,
    nonce: Optional[bytes] = None,
    aad: Optional[bytes] = None,
) -> Tuple[bytes, bytes, bytes]:
    """
    Encrypt plaintext using AES-256-GCM with associated authenticated data (AAD).

    Args:
        plaintext: Raw data to encrypt.
        key: 32-byte AES key.
        nonce: 12-byte unique nonce. If None, a secure random nonce is generated.
        aad: Optional additional authenticated data.

    Returns:
        tuple[bytes, bytes, bytes]: (ciphertext, nonce, tag)

    Raises:
        CryptoError: If key size is invalid or encryption fails.
    """
    if len(key) != 32:
        raise CryptoError(f"AES-256 requires a 32-byte key, got {len(key)} bytes")

    if nonce is None:
        nonce = generate_nonce()
    elif len(nonce) != GCM_NONCE_LEN:
        raise InvalidNonceError(
            f"AES-GCM nonce must be {GCM_NONCE_LEN} bytes, got {len(nonce)}"
        )

    try:
        aesgcm = AESGCM(key)
        # aesgcm.encrypt returns ciphertext + 16-byte tag
        ct_with_tag = aesgcm.encrypt(nonce, plaintext, aad)
        ciphertext = ct_with_tag[:-GCM_TAG_LEN]
        tag = ct_with_tag[-GCM_TAG_LEN:]
        return ciphertext, nonce, tag
    except Exception as e:
        raise CryptoError(f"AES-GCM encryption failed: {e}") from e


def decrypt_gcm(
    ciphertext: bytes,
    key: bytes,
    nonce: bytes,
    tag: bytes,
    aad: Optional[bytes] = None,
) -> bytes:
    """
    Authenticate and decrypt AES-256-GCM ciphertext.

    Args:
        ciphertext: Encrypted payload bytes.
        key: 32-byte AES key.
        nonce: 12-byte nonce used during encryption.
        tag: 16-byte authentication tag.
        aad: Additional authenticated data (must match encryption AAD).

    Returns:
        bytes: Decrypted plaintext.

    Raises:
        DecryptionError: If authentication tag check fails or data is corrupted.
    """
    if len(key) != 32:
        raise CryptoError(f"AES-256 requires a 32-byte key, got {len(key)} bytes")
    if len(nonce) != GCM_NONCE_LEN:
        raise InvalidNonceError(f"Nonce must be {GCM_NONCE_LEN} bytes, got {len(nonce)}")
    if len(tag) != GCM_TAG_LEN:
        raise DecryptionError(f"Tag must be {GCM_TAG_LEN} bytes, got {len(tag)}")

    try:
        aesgcm = AESGCM(key)
        ct_with_tag = ciphertext + tag
        return aesgcm.decrypt(nonce, ct_with_tag, aad)
    except InvalidTag as e:
        raise DecryptionError("AEAD authentication tag verification failed: payload corrupted or tampered") from e
    except Exception as e:
        raise DecryptionError(f"AES-GCM decryption failed: {e}") from e


def pack_encrypted_payload(ciphertext: bytes, nonce: bytes, tag: bytes) -> bytes:
    """
    Pack nonce, tag, and ciphertext into a single canonical binary payload:
    [NONCE 12B] [TAG 16B] [CIPHERTEXT N B]
    """
    if len(nonce) != GCM_NONCE_LEN:
        raise InvalidNonceError(f"Nonce must be {GCM_NONCE_LEN} bytes, got {len(nonce)}")
    if len(tag) != GCM_TAG_LEN:
        raise DecryptionError(f"Tag must be {GCM_TAG_LEN} bytes, got {len(tag)}")
    return nonce + tag + ciphertext


def unpack_encrypted_payload(packed: bytes) -> Tuple[bytes, bytes, bytes]:
    """
    Unpack canonical binary payload into (ciphertext, nonce, tag).
    
    Raises:
        DecryptionError: If packed payload is shorter than 28 bytes (nonce + tag).
    """
    if len(packed) < GCM_OVERHEAD:
        raise DecryptionError(
            f"Packed payload too short: expected at least {GCM_OVERHEAD} bytes, got {len(packed)}"
        )
    nonce = packed[:GCM_NONCE_LEN]
    tag = packed[GCM_NONCE_LEN:GCM_OVERHEAD]
    ciphertext = packed[GCM_OVERHEAD:]
    return ciphertext, nonce, tag


def encrypt_and_pack(
    plaintext: bytes,
    key: bytes,
    nonce: Optional[bytes] = None,
    aad: Optional[bytes] = None,
) -> bytes:
    """Convenience method: encrypts and packs into [NONCE 12B][TAG 16B][CIPHERTEXT]."""
    ciphertext, n, tag = encrypt_gcm(plaintext, key, nonce=nonce, aad=aad)
    return pack_encrypted_payload(ciphertext, n, tag)


def unpack_and_decrypt(packed: bytes, key: bytes, aad: Optional[bytes] = None) -> bytes:
    """Convenience method: unpacks and decrypts [NONCE 12B][TAG 16B][CIPHERTEXT]."""
    ciphertext, nonce, tag = unpack_encrypted_payload(packed)
    return decrypt_gcm(ciphertext, key, nonce=nonce, tag=tag, aad=aad)
