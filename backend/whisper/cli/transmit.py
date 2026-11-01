"""CLI command for real-time AFSK message transmission."""

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

from whisper.protocol import (
    encode_message,
    EncodeResult,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    DEFAULT_AMPLITUDE,
    DEFAULT_FADE_MS,
    FREQ_ZERO,
    FREQ_ONE,
    get_frame_info,
)
from whisper.audio.output import _play_samples, stop_playback, PlaybackError
from whisper.audio.devices import list_output_devices, get_default_output_device, check_sample_rate_support
from whisper.events import (
    emit_transmission_started,
    emit_transmission_progress,
    emit_transmission_completed,
    emit_transmission_cancelled,
    emit_transmission_error,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


class TransmitterState:
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    TRANSMITTING = "TRANSMITTING"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class TransmitterUI:
    """Terminal UI for the transmitter."""

    def __init__(self, config: dict):
        self.config = config
        self.state = TransmitterState.IDLE
        self.start_time = 0.0
        self.duration = 0.0

    def print_header(self) -> None:
        print("=" * 60)
        print("WHISPERPROTOCOL TRANSMITTER")
        print("=" * 60)

        print(f"\nOutput device: {self.config['output_device_name']}")
        print(f"Message:       {self.config['message']}")
        print(f"\nProtocol:      AFSK")
        print(f"  0:           {self.config['freq_zero']:.3f} kHz")
        print(f"  1:           {self.config['freq_one']:.3f} kHz")
        print(f"\nSample rate:   {self.config['sample_rate']} Hz")
        print(f"Symbol dur:    {self.config['symbol_duration'] * 1000:.1f} ms")
        print(f"Amplitude:     {self.config['amplitude']:.2f}")

    def print_preparing(self) -> None:
        self.state = TransmitterState.PREPARING
        print(f"\nPreparing...")

    def print_transmitting(self, result: EncodeResult) -> None:
        self.state = TransmitterState.TRANSMITTING
        self.start_time = time.time()
        self.duration = result.duration_seconds

        print(f"\nTransmitting...")
        print(f"Duration: {result.duration_seconds:.3f} s ({result.symbol_count} symbols)")

    def print_progress(self, elapsed: float) -> None:
        if self.duration <= 0:
            return
        progress = min(1.0, elapsed / self.duration)
        bar_width = 40
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)
        percent = progress * 100
        print(f"\rProgress: [{bar}] {percent:.0f}%", end="", flush=True)

    def print_complete(self) -> None:
        self.state = TransmitterState.COMPLETE
        elapsed = time.time() - self.start_time
        print(f"\n\nTransmission complete. ({elapsed:.3f} s)")

    def print_cancelled(self) -> None:
        self.state = TransmitterState.CANCELLED
        print("\n\nTransmission cancelled.")

    def print_error(self, error: str) -> None:
        self.state = TransmitterState.ERROR
        print(f"\n\nERROR: {error}")


def transmit_message(
    message: str,
    output_device: int | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    symbol_duration: float = DEFAULT_SYMBOL_DURATION,
    amplitude: float = DEFAULT_AMPLITUDE,
    fade_ms: float = DEFAULT_FADE_MS,
    output_device_name: str = "default",
    freq_zero: float = FREQ_ZERO,
    freq_one: float = FREQ_ONE,
    ecc_symbols: int = 0,
    phase_continuous: bool = False,
) -> int:
    """
    Transmit a message via AFSK over the selected output device.

    Returns:
        0 on success, 1 on error
    """
    ui = TransmitterUI({
        "message": message,
        "output_device_name": output_device_name,
        "sample_rate": sample_rate,
        "symbol_duration": symbol_duration,
        "amplitude": amplitude,
        "freq_zero": freq_zero / 1000.0,
        "freq_one": freq_one / 1000.0,
    })

    ui.print_header()

    # Check device sample rate support
    if output_device is not None:
        if not check_sample_rate_support(output_device, sample_rate, is_input=False):
            ui.print_error(f"Device {output_device} does not support {sample_rate} Hz")
            emit_transmission_error(message, f"Device {output_device} does not support {sample_rate} Hz")
            return 1

    # Encode message
    ui.print_preparing()
    try:
        result = encode_message(
            message,
            sample_rate=sample_rate,
            symbol_duration=symbol_duration,
            amplitude=amplitude,
            fade_ms=fade_ms,
            freq_zero=freq_zero,
            freq_one=freq_one,
            ecc_symbols=ecc_symbols,
            phase_continuous=phase_continuous,
        )
    except Exception as e:
        ui.print_error(f"Encoding failed: {e}")
        emit_transmission_error(message, f"Encoding failed: {e}")
        logger.exception("Encoding error")
        return 1

    # Frame info
    frame_info = get_frame_info(message.encode("utf-8"))
    ecc_msg = f" + {ecc_symbols} ECC" if ecc_symbols > 0 else ""
    print(f"Frame: {frame_info['total_bits']} bits "
          f"({frame_info['preamble_bits']} preamble + "
          f"{frame_info['sync_bits']} sync + "
          f"{frame_info['length_bits']} length + "
          f"{frame_info['payload_bits']} payload{ecc_msg} + "
          f"{frame_info['checksum_bits']} checksum)")


    # Emit transmission started event
    emit_transmission_started(message, sample_rate, symbol_duration, amplitude)

    # Transmit
    ui.print_transmitting(result)

    try:
        _play_samples(
            result.waveform,
            sample_rate=sample_rate,
            device=output_device,
            blocking=False,
        )

        # Progress display loop
        while True:
            elapsed = time.time() - ui.start_time
            if elapsed >= ui.duration:
                break
            progress = min(1.0, elapsed / ui.duration) if ui.duration > 0 else 1.0
            ui.print_progress(elapsed)
            emit_transmission_progress(progress, elapsed, ui.duration)
            time.sleep(0.05)

        # Wait for playback to actually complete
        time.sleep(0.1)

        ui.print_complete()
        emit_transmission_completed(message, ui.duration)
        return 0

    except PlaybackError as e:
        ui.print_error(f"Playback failed: {e}")
        emit_transmission_error(message, f"Playback failed: {e}")
        return 1
    except KeyboardInterrupt:
        stop_playback()
        ui.print_cancelled()
        emit_transmission_cancelled(message)
        return 130
    except Exception as e:
        stop_playback()
        ui.print_error(f"Unexpected error: {e}")
        emit_transmission_error(message, f"Unexpected error: {e}")
        logger.exception("Transmission error")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WhisperProtocol Transmitter - Real-time AFSK Modulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m whisper.cli.transmit "HELLO FROM PC A"
  python -m whisper.cli.transmit "HELLO" --output 1
  python -m whisper.cli.transmit "TEST" --amplitude 0.5 --duration 0.01
  python -m whisper.cli.transmit "LONG MESSAGE" --sample-rate 48000
        """,
    )

    parser.add_argument("message", help="Message to transmit")
    parser.add_argument(
        "--output",
        type=int,
        help="Output device index (default: system default)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help=f"Sample rate in Hz (default: {DEFAULT_SAMPLE_RATE})",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_SYMBOL_DURATION,
        help=f"Symbol duration in seconds (default: {DEFAULT_SYMBOL_DURATION})",
    )
    parser.add_argument(
        "--amplitude",
        type=float,
        default=DEFAULT_AMPLITUDE,
        help=f"Peak amplitude 0.0-1.0 (default: {DEFAULT_AMPLITUDE})",
    )
    parser.add_argument(
        "--fade-ms",
        type=float,
        default=DEFAULT_FADE_MS,
        help=f"Fade in/out duration in milliseconds (default: {DEFAULT_FADE_MS})",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List output devices and exit",
    )
    parser.add_argument(
        "--profile",
        choices=["ultrasonic", "audible"],
        default="ultrasonic",
        help="Modulation profile: 'ultrasonic' (18/19 kHz) or 'audible' (14/15 kHz) (default: ultrasonic)",
    )
    parser.add_argument(
        "--ecc",
        type=int,
        choices=[0, 8, 16, 32],
        default=0,
        help="Reed-Solomon parity symbols: 0, 8, 16, or 32 (default: 0)",
    )
    parser.add_argument(
        "--phase-continuous",
        action="store_true",
        help="Generate phase-continuous CPFSK waveform instead of symbol-windowed tones",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list_devices:
        devices = list_output_devices()
        print("OUTPUT DEVICES")
        print("-" * 60)
        for d in devices:
            print(f"  {d}")
        default = get_default_output_device()
        if default:
            print(f"\nDefault: {default}")
        return 0

    from whisper.protocol.constants import MODULATION_PROFILES
    profile = MODULATION_PROFILES.get(args.profile, MODULATION_PROFILES["ultrasonic"])

    # Get output device name
    output_device_name = "default"
    if args.output is not None:
        from whisper.audio.devices import get_device_by_index
        dev = get_device_by_index(args.output)
        if dev:
            output_device_name = dev.name

    return transmit_message(
        args.message,
        output_device=args.output,
        sample_rate=args.sample_rate,
        symbol_duration=args.duration,
        amplitude=args.amplitude,
        fade_ms=args.fade_ms,
        output_device_name=output_device_name,
        freq_zero=profile.freq_zero,
        freq_one=profile.freq_one,
        ecc_symbols=args.ecc,
        phase_continuous=args.phase_continuous,
    )



if __name__ == "__main__":
    sys.exit(main())