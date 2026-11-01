"""CLI command for receiving/decoding AFSK messages."""

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

from whisper.protocol import (
    ReceiverConfig,
    AudioStreamReceiver,
    decode_wav_file,
    ReceiverState,
    SymbolDecision,
    FrameDecodeResult,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    FREQ_ZERO,
    FREQ_ONE,
)
from whisper.audio.devices import list_input_devices, get_default_input_device

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


class ReceiverUI:
    """Terminal UI for the receiver with enhanced state display."""

    def __init__(self, config: ReceiverConfig, continuous: bool = False):
        self.config = config
        self.continuous = continuous
        self.receiver: AudioStreamReceiver | None = None
        self.last_detection = None
        self.last_status = None
        self.frame_received = False
        self.last_state_printed = None

    def on_symbol(self, detection) -> None:
        self.last_detection = detection
        self._update_display()

    def on_state_change(self, state: ReceiverState) -> None:
        self.last_status = self.receiver.get_status() if self.receiver else None
        if state != self.last_state_printed:
            self._print_state_transition(state)
            self.last_state_printed = state
        if state == ReceiverState.COMPLETE:
            self.frame_received = True

    def _print_state_transition(self, state: ReceiverState) -> None:
        """Print clean state transition messages."""
        state_messages = {
            ReceiverState.WAITING: "Status: WAITING FOR SIGNAL",
            ReceiverState.SEARCHING: "Searching for preamble...",
            ReceiverState.PREAMBLE_DETECTED: "Preamble detected.",
            ReceiverState.SYNCING: "Synchronizing...",
            ReceiverState.RECEIVING: "Receiving frame...",
            ReceiverState.FRAME_VALIDATION: "Verifying checksum...",
            ReceiverState.COMPLETE: "Frame complete.",
            ReceiverState.ERROR: "Error occurred.",
        }
        msg = state_messages.get(state, f"State: {state.value}")
        print(f"\n{msg}")

    def on_frame(self, result: FrameDecodeResult) -> None:
        print("\n" + "=" * 60)
        if result.success:
            print("FRAME VALIDATED")
            print("=" * 60)
            print(f"\nCHECKSUM: {'PASS' if result.checksum_valid else 'FAIL'}")
            if result.payload:
                try:
                    message = result.payload.decode("utf-8")
                    print(f"MESSAGE:  {message}")
                except UnicodeDecodeError:
                    print(f"MESSAGE:  {result.payload.hex()}")
        else:
            print("DECODE FAILED")
            print("=" * 60)
            print(f"\nERROR: {result.error}")

        if not self.continuous:
            print("\nPress ENTER to stop...")
        else:
            print("\nContinuing to listen...")
            self.frame_received = False
            self.last_state_printed = None
            if self.receiver:
                self.receiver.state_machine.reset()

    def _update_display(self) -> None:
        if not self.last_detection:
            return

        det = self.last_detection
        status = self.receiver.get_status() if self.receiver else None

        # Only show detailed display during active reception
        if status and status.state in (ReceiverState.SEARCHING, ReceiverState.PREAMBLE_DETECTED,
                                        ReceiverState.SYNCING, ReceiverState.RECEIVING):
            freq_khz = det.detected_frequency / 1000.0
            if det.decision == SymbolDecision.ZERO:
                sym_str = "0"
            elif det.decision == SymbolDecision.ONE:
                sym_str = "1"
            elif det.decision == SymbolDecision.LOW_CONFIDENCE:
                sym_str = "?"
            else:
                sym_str = "?"

            e0 = det.energy_zero
            e1 = det.energy_one
            nf = det.noise_floor

            # Calculate dB values
            e0_db = 20 * np.log10(e0 / nf) if e0 > 0 and nf > 0 else -float('inf')
            e1_db = 20 * np.log10(e1 / nf) if e1 > 0 and nf > 0 else -float('inf')

            print(
                f"\r  Frequency: {freq_khz:>6.2f} kHz | Symbol: {sym_str} | "
                f"Conf: {det.confidence:.2f} | E0: {e0_db:>6.1f} dB | E1: {e1_db:>6.1f} dB | NF: {nf:.4f}  ",
                end="", flush=True
            )

            if status and status.state == ReceiverState.RECEIVING:
                pct = (status.frame_progress / status.frame_total * 100) if status.frame_total > 0 else 0
                print(f" | Frame: {status.frame_progress}/{status.frame_total} ({pct:.0f}%)", end="", flush=True)

    def run_live(self) -> int:
        """Run live receiver."""
        print("=" * 60)
        print("WHISPERPROTOCOL RECEIVER")
        print("=" * 60)

        input_device_name = "default"
        if self.config.input_device is not None:
            from whisper.audio.devices import get_device_by_index
            dev = get_device_by_index(self.config.input_device)
            if dev:
                input_device_name = dev.name

        print(f"\nInput device: {input_device_name}")
        print(f"Sample rate:  {self.config.sample_rate} Hz")
        print(f"Frequency 0:  {self.config.freq_zero / 1000:.3f} kHz")
        print(f"Frequency 1:  {self.config.freq_one / 1000:.3f} kHz")
        print(f"Symbol dur:   {self.config.symbol_duration * 1000:.1f} ms")

        print(f"\nStatus: WAITING FOR SIGNAL")
        print("\nPress ENTER to start listening.")
        try:
            input()
        except KeyboardInterrupt:
            print("\nCancelled")
            return 0

        print("\nLISTENING...")

        self.receiver = AudioStreamReceiver(
            config=self.config,
            on_symbol=self.on_symbol,
            on_state_change=self.on_state_change,
            on_frame=self.on_frame,
        )

        try:
            self.receiver.start()
        except Exception as e:
            print(f"\nFAILED TO START: {e}")
            return 1

        try:
            while self.receiver.is_running():
                if self.frame_received and not self.continuous:
                    try:
                        input()
                    except KeyboardInterrupt:
                        pass
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\nInterrupted")
        finally:
            self.receiver.stop()
            print("\nReceiver stopped.")

        return 0

    def run_wav(self, wav_path: Path) -> int:
        """Decode WAV file."""
        print("=" * 60)
        print("WHISPERPROTOCOL WAV DECODER")
        print("=" * 60)

        print(f"\nInput file:  {wav_path}")
        print(f"Sample rate: {self.config.sample_rate} Hz")
        print(f"Freq 0:      {self.config.freq_zero / 1000:.3f} kHz")
        print(f"Freq 1:      {self.config.freq_one / 1000:.3f} kHz")
        print(f"Symbol dur:  {self.config.symbol_duration * 1000:.1f} ms")

        print("\nDecoding...")
        result = decode_wav_file(str(wav_path), self.config)

        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)

        if result.success:
            print(f"\nCHECKSUM: {'PASS' if result.checksum_valid else 'FAIL'}")
            if result.payload:
                try:
                    message = result.payload.decode("utf-8")
                    print(f"MESSAGE:  {message}")
                except UnicodeDecodeError:
                    print(f"MESSAGE:  {result.payload.hex()}")
            return 0
        else:
            print(f"\nDECODE FAILED: {result.error}")
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WhisperProtocol Receiver - Real-time AFSK Demodulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m whisper.cli.receive
  python -m whisper.cli.receive --input 1
  python -m whisper.cli.receive --wav captured.wav
  python -m whisper.cli.receive --continuous
  python -m whisper.cli.receive --sample-rate 48000 --duration 0.01
        """,
    )

    parser.add_argument(
        "--input",
        type=int,
        help="Input device index (default: system default)",
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
        "--freq-zero",
        type=float,
        default=FREQ_ZERO,
        help=f"Frequency for bit 0 in Hz (default: {FREQ_ZERO})",
    )
    parser.add_argument(
        "--freq-one",
        type=float,
        default=FREQ_ONE,
        help=f"Frequency for bit 1 in Hz (default: {FREQ_ONE})",
    )
    parser.add_argument(
        "--threshold-db",
        type=float,
        default=20.0,
        help="Detection threshold in dB (default: 20.0)",
    )
    parser.add_argument(
        "--min-snr-db",
        type=float,
        default=12.0,
        help="Minimum SNR in dB (default: 12.0)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="Minimum confidence for classification (default: 0.6)",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        help="Audio block size (default: samples_per_symbol)",
    )
    parser.add_argument(
        "--wav",
        type=Path,
        help="Decode WAV file instead of live capture",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Continue listening after frame received",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List input devices and exit",
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
        devices = list_input_devices()
        print("INPUT DEVICES")
        print("-" * 60)
        for d in devices:
            print(f"  {d}")
        return 0

    config = ReceiverConfig(
        sample_rate=args.sample_rate,
        symbol_duration=args.duration,
        freq_zero=args.freq_zero,
        freq_one=args.freq_one,
        detection_threshold_db=args.threshold_db,
        min_snr_db=args.min_snr_db,
        min_confidence=args.min_confidence,
        input_device=args.input,
        block_size=args.block_size,
    )

    ui = ReceiverUI(config, continuous=args.continuous)

    if args.wav:
        return ui.run_wav(args.wav)
    else:
        return ui.run_live()


if __name__ == "__main__":
    sys.exit(main())