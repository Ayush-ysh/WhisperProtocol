"""WhisperProtocol Cryptography Errors and Exceptions."""


class CryptoError(Exception):
    """Base exception for all cryptographic operations."""
    pass


class KeyExchangeError(CryptoError):
    """Raised when key generation, loading, or exchange fails."""
    pass


class SASNotVerifiedError(CryptoError):
    """Raised when encryption/decryption is attempted before SAS confirmation."""
    pass


class SASRejectedError(CryptoError):
    """Raised when SAS verification is explicitly rejected by the user."""
    pass


class SessionExpiredError(CryptoError):
    """Raised when operating on an expired cryptographic session."""
    pass


class SessionNotActiveError(CryptoError):
    """Raised when operating on a session that is not in the ACTIVE state."""
    pass


class ReplayAttackError(CryptoError):
    """Raised when a replayed or duplicate nonce is detected."""
    pass


class DecryptionError(CryptoError):
    """Raised when AEAD decryption or authentication tag verification fails."""
    pass


class InvalidNonceError(CryptoError):
    """Raised when a nonce does not conform to expected size or format."""
    pass
