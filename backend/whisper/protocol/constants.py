"""Centralized protocol constants and modulation profiles for WhisperProtocol."""

from dataclasses import dataclass
from typing import Dict, Tuple

# Audio parameters
DEFAULT_SAMPLE_RATE: int = 48000
FALLBACK_SAMPLE_RATE: int = 44100
DEFAULT_SYMBOL_DURATION: float = 0.020  # 20 ms -> 50 baud
DEFAULT_AMPLITUDE: float = 0.8
DEFAULT_FADE_MS: float = 2.0

# Frame structure
PREAMBLE_PATTERN: str = "10" * 16  # 32 bits: 101010...
SYNC_PATTERN: str = "1111000011110000"  # 16 bits distinct from preamble
LENGTH_FIELD_BITS: int = 16  # Max payload: 65535 bytes
CHECKSUM_BITS: int = 16  # CRC-16

# Derived values
SAMPLES_PER_SYMBOL: int = int(DEFAULT_SAMPLE_RATE * DEFAULT_SYMBOL_DURATION)  # 960 at 48 kHz
BITS_PER_BYTE: int = 8

# Precomputed bit patterns
PREAMBLE_BITS: list[int] = [int(c) for c in PREAMBLE_PATTERN]
SYNC_BITS: list[int] = [int(c) for c in SYNC_PATTERN]

PREAMBLE_LENGTH: int = len(PREAMBLE_BITS)
SYNC_LENGTH: int = len(SYNC_BITS)
HEADER_LENGTH: int = PREAMBLE_LENGTH + SYNC_LENGTH + LENGTH_FIELD_BITS


@dataclass(frozen=True)
class ModulationProfile:
    """Configurable modulation profile for acoustic communication."""

    name: str
    freq_zero: float
    freq_one: float
    symbol_duration: float = DEFAULT_SYMBOL_DURATION
    fade_ms: float = DEFAULT_FADE_MS

    @property
    def baud_rate(self) -> float:
        return 1.0 / self.symbol_duration

    @property
    def band_zero(self) -> Tuple[float, float]:
        return (self.freq_zero - 500.0, self.freq_zero + 500.0)

    @property
    def band_one(self) -> Tuple[float, float]:
        return (self.freq_one - 500.0, self.freq_one + 500.0)


# Standard profiles
PROFILE_ULTRASONIC = ModulationProfile(
    name="ultrasonic_standard",
    freq_zero=18000.0,
    freq_one=19000.0,
    symbol_duration=DEFAULT_SYMBOL_DURATION,
    fade_ms=DEFAULT_FADE_MS,
)

PROFILE_AUDIBLE = ModulationProfile(
    name="acoustic_audible_fallback",
    freq_zero=14000.0,
    freq_one=15000.0,
    symbol_duration=DEFAULT_SYMBOL_DURATION,
    fade_ms=DEFAULT_FADE_MS,
)

MODULATION_PROFILES: Dict[str, ModulationProfile] = {
    "ultrasonic": PROFILE_ULTRASONIC,
    "audible": PROFILE_AUDIBLE,
}

# Backwards compatible frequency constants
FREQ_ZERO: int = int(PROFILE_ULTRASONIC.freq_zero)
FREQ_ONE: int = int(PROFILE_ULTRASONIC.freq_one)
FREQUENCY_BAND_18KHZ: Tuple[float, float] = PROFILE_ULTRASONIC.band_zero
FREQUENCY_BAND_19KHZ: Tuple[float, float] = PROFILE_ULTRASONIC.band_one
TARGET_TOLERANCE_HZ: float = 350.0


def get_samples_per_symbol(sample_rate: int, symbol_duration: float) -> int:
    """Calculate samples per symbol for given parameters."""
    return int(sample_rate * symbol_duration)


def get_symbol_duration(samples_per_symbol: int, sample_rate: int) -> float:
    """Calculate symbol duration from samples and sample rate."""
    return samples_per_symbol / sample_rate