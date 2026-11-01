"""CLI module for WhisperProtocol."""

from .audio_test import main as audio_test_main
from .calibrate import main as calibrate_main
from .encode import main as encode_main
from .receive import main as receive_main
from .transmit import main as transmit_main
from .validate import main as validate_main

__all__ = [
    "audio_test_main",
    "calibrate_main",
    "encode_main",
    "receive_main",
    "transmit_main",
    "validate_main",
]