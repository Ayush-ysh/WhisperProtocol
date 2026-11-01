"""Ephemeral X25519 Key Agreement for WhisperProtocol."""

from typing import Tuple
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from .errors import KeyExchangeError

X25519_KEY_LEN: int = 32


def generate_keypair() -> Tuple[X25519PrivateKey, bytes]:
    """
    Generate an ephemeral X25519 private key and export its raw 32-byte public key.
    
    Returns:
        tuple[X25519PrivateKey, bytes]: (private_key_object, 32_byte_raw_public_key)
    """
    try:
        private_key = X25519PrivateKey.generate()
        public_bytes = export_public_key(private_key.public_key())
        return private_key, public_bytes
    except Exception as e:
        raise KeyExchangeError(f"Failed to generate ephemeral X25519 keypair: {e}") from e


def export_public_key(public_key: X25519PublicKey) -> bytes:
    """Export an X25519 public key as raw 32 bytes."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def load_public_key(public_bytes: bytes) -> X25519PublicKey:
    """
    Deserialize raw 32-byte public key into an X25519PublicKey object.
    
    Args:
        public_bytes: 32 bytes representing peer's public key.
        
    Raises:
        KeyExchangeError: If input is not exactly 32 bytes or invalid.
    """
    if not isinstance(public_bytes, (bytes, bytearray)):
        raise KeyExchangeError(f"Public key must be bytes, got {type(public_bytes).__name__}")
    if len(public_bytes) != X25519_KEY_LEN:
        raise KeyExchangeError(
            f"Invalid X25519 public key length: expected {X25519_KEY_LEN} bytes, got {len(public_bytes)}"
        )
    try:
        return X25519PublicKey.from_public_bytes(bytes(public_bytes))
    except Exception as e:
        raise KeyExchangeError(f"Failed to load X25519 public key: {e}") from e


def derive_shared_secret(private_key: X25519PrivateKey, peer_public_bytes: bytes) -> bytes:
    """
    Perform Diffie-Hellman key exchange using local private key and peer's raw public key.
    
    Args:
        private_key: Local ephemeral X25519 private key.
        peer_public_bytes: 32-byte peer public key.
        
    Returns:
        bytes: 32-byte raw shared secret.
        
    Raises:
        KeyExchangeError: If key loading or exchange fails.
    """
    if not isinstance(private_key, X25519PrivateKey):
        raise KeyExchangeError(
            f"Expected X25519PrivateKey instance, got {type(private_key).__name__}"
        )
    peer_pub = load_public_key(peer_public_bytes)
    try:
        return private_key.exchange(peer_pub)
    except Exception as e:
        raise KeyExchangeError(f"Diffie-Hellman shared secret exchange failed: {e}") from e
