"""CLI command for encoding messages to AFSK waveform."""

import argparse
import sys
from pathlib import Path

from whisper.protocol import (
    encode_message,
    encode_and_save,
    get_frame_info,
    EncodeResult,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    DEFAULT_AMPLITUDE,
    FREQ_ZERO,
    FREQ_ONE,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WhisperProtocol Message Encoder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m whisper.cli.encode "HELLO WHISPER"
  python -m whisper.cli.encode "HELLO" --wav output.wav
  python -m whisper.cli.encode "TEST" --bits --wav test.wav
  python -m whisper.cli.encode "LONG MESSAGE" --duration 0.01 --sample-rate 48000
        """,
    )

    parser.add_argument("message", help="Message to encode")
    parser.add_argument(
        "--wav",
        type=Path,
        help="Output WAV file path",
    )
    parser.add_argument(
        "--bits",
        action="store_true",
        help="Print generated bitstream",
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
        "--subtype",
        type=str,
        default="PCM_16",
        choices=["PCM_16", "FLOAT", "PCM_24", "PCM_32"],
        help="WAV subtype (default: PCM_16)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("WHISPERPROTOCOL ENCODER")
    print("=" * 60)

    print(f"\nPayload:")
    print(f"  {args.message}")

    payload_bytes = args.message.encode("utf-8")
    print(f"\nPayload bytes:")
    print(f"  {len(payload_bytes)} bytes")
    if args.verbose:
        print(f"  Hex: {payload_bytes.hex()}")
        print(f"  Bytes: {' '.join(f'{b:02x}' for b in payload_bytes)}")

    frame_info = get_frame_info(payload_bytes)
    print(f"\nFrame structure:")
    print(f"  Preamble:  {frame_info['preamble_bits']} bits")
    print(f"  Sync:      {frame_info['sync_bits']} bits")
    print(f"  Length:    {frame_info['length_bits']} bits")
    print(f"  Payload:   {frame_info['payload_bits']} bits ({frame_info['payload_bytes']} bytes)")
    print(f"  Checksum:  {frame_info['checksum_bits']} bits")
    print(f"  Total:     {frame_info['total_bits']} bits ({frame_info['total_symbols']} symbols)")

    print(f"\nFrequency mapping:")
    print(f"  0 -> {FREQ_ZERO} Hz")
    print(f"  1 -> {FREQ_ONE} Hz")

    print(f"\nSymbol duration:")
    print(f"  {args.duration * 1000:.1f} ms")

    print(f"\nEstimated duration:")
    print(f"  {frame_info['estimated_duration_ms']:.1f} ms")

    if args.bits:
        from whisper.protocol import encode_frame
        frame_bits = encode_frame(payload_bytes)
        from whisper.protocol import bits_to_string
        print(f"\nGenerated bitstream ({len(frame_bits)} bits):")
        print(f"  {bits_to_string(frame_bits)}")

    if args.wav:
        print(f"\nGenerating waveform...")
        try:
            result = encode_and_save(
                args.message,
                args.wav,
                sample_rate=args.sample_rate,
                symbol_duration=args.duration,
                amplitude=args.amplitude,
                subtype=args.subtype,
            )
            print(f"Saved: {args.wav}")
            print(f"Waveform:")
            print(f"  Samples: {len(result.waveform)}")
            print(f"  Duration: {result.duration_seconds:.3f} s")
            print(f"  Sample rate: {result.sample_rate} Hz")
            print(f"  Bit count: {result.bit_count}")
            print(f"  Symbol count: {result.symbol_count}")
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            return 1
    else:
        print(f"\nNo output file specified. Use --wav to save.")
        result = encode_message(
            args.message,
            sample_rate=args.sample_rate,
            symbol_duration=args.duration,
            amplitude=args.amplitude,
        )
        print(f"Waveform info (not saved):")
        print(f"  Samples: {len(result.waveform)}")
        print(f"  Duration: {result.duration_seconds:.3f} s")

    return 0


if __name__ == "__main__":
    sys.exit(main())