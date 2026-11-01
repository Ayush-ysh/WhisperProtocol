"""Centralized protocol constants for WhisperProtocol."""

# Frequency mapping
FREQ_ZERO: int = 18000
FREQ_ONE: int = 19000

# Audio parameters
DEFAULT_SAMPLE_RATE: int = 44100
DEFAULT_SYMBOL_DURATION: float = 0.020  # 20 ms
DEFAULT_AMPLITUDE: float = 0.8
DEFAULT_FADE_MS: float = 2.0

# Frame structure
PREAMBLE_PATTERN: str = "10" * 16  # 32 bits: 101010...
SYNC_PATTERN: str = "1111000011110000"  # 16 bits distinct from preamble
LENGTH_FIELD_BITS: int = 16  # Max payload: 65535 bytes
CHECKSUM_BITS: int = 16  # CRC-16

# Derived values
SAMPLES_PER_SYMBOL: int = int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)
BITS_PER_BYTE: int = 8

# Precomputed bit patterns
PREAMBLE_BITS: list[int] = [int(c) for c in PREAMBLE_PATTERN]
SYNC_BITS: list[int] = [int(c) for c in SYNC_PATTERN]

PREAMBLE_LENGTH: int = len(PREAMBLE_BITS)
SYNC_LENGTH: int = len(SYNC_BITS)
HEADER_LENGTH: int = PREAMBLE_LENGTH + SYNC_LENGTH + LENGTH_FIELD_BITS

# Frequency bands for detection
FREQUENCY_BAND_18KHZ: tuple[float, float] = (17500.0, 18500.0)
FREQUENCY_BAND_19KHZ: tuple[float, float] = (18500.0, 19500.0)
TARGET_TOLERANCE_HZ: float = 200.0


def get_samples_per_symbol(sample_rate: int, symbol_duration: float) -> int:
    """Calculate samples per symbol for given parameters."""
    return int(sample_rate * symbol_duration)


def get_symbol_duration(samples_per_symbol: int, sample_rate: int) -> float:
    """Calculate symbol duration from samples and sample rate."""
    return samples_per_symbol / sample_rate