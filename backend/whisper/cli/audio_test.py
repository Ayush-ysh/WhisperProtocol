"""CLI module for WhisperProtocol audio diagnostics."""

import argparse
import logging
import sys
from pathlib import Path

from whisper.audio import (
    list_input_devices,
    list_output_devices,
    get_default_input_device,
    get_default_output_device,
    check_sample_rate_support,
    play_18khz_test,
    play_19khz_test,
    record_audio,
    save_recording,
    load_recording,
    detect_test_tone,
    analyze_spectrum,
    TONE_FREQUENCY_BIT_0,
    TONE_FREQUENCY_BIT_1,
    DEFAULT_SAMPLE_RATE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def print_devices(devices: list, label: str) -> None:
    """Print device list."""
    print(f"\n{label}")
    print("-" * 60)
    if not devices:
        print("  (none found)")
    for d in devices:
        print(f"  {d}")


def print_default_devices() -> None:
    """Print default input/output devices."""
    print("\nDEFAULT DEVICES")
    print("-" * 60)

    in_dev = get_default_input_device()
    out_dev = get_default_output_device()

    if in_dev:
        print(f"  Input:  {in_dev}")
    else:
        print("  Input:  (none)")

    if out_dev:
        print(f"  Output: {out_dev}")
    else:
        print("  Output: (none)")


def check_sample_rates(input_device: int | None, output_device: int | None) -> None:
    """Check sample rate support for devices."""
    print("\nSAMPLE RATE SUPPORT (44100 Hz)")
    print("-" * 60)

    if input_device is not None:
        supported = check_sample_rate_support(input_device, DEFAULT_SAMPLE_RATE, is_input=True)
        print(f"  Input Device {input_device}: {'SUPPORTED' if supported else 'NOT SUPPORTED'}")

    if output_device is not None:
        supported = check_sample_rate_support(output_device, DEFAULT_SAMPLE_RATE, is_input=False)
        print(f"  Output Device {output_device}: {'SUPPORTED' if supported else 'NOT SUPPORTED'}")


def run_playback_tests(
    output_device: int | None,
    sample_rate: int,
    tone_duration: float,
) -> None:
    """Play test tones."""
    print("\n" + "=" * 60)
    print("PLAYBACK TESTS")
    print("=" * 60)

    print(f"\n18 kHz Test (BIT 0):")
    print(f"  PLAYING {tone_duration:.1f}s tone...")
    try:
        play_18khz_test(tone_duration, output_device, sample_rate)
        print("  DONE")
    except Exception as e:
        print(f"  FAILED: {e}")

    print(f"\n19 kHz Test (BIT 1):")
    print(f"  PLAYING {tone_duration:.1f}s tone...")
    try:
        play_19khz_test(tone_duration, output_device, sample_rate)
        print("  DONE")
    except Exception as e:
        print(f"  FAILED: {e}")


def run_capture_and_analysis(
    input_device: int | None,
    sample_rate: int,
    capture_duration: float,
    output_wav: Path | None,
) -> tuple:
    """Capture audio and run analysis."""
    print("\n" + "=" * 60)
    print("MICROPHONE CAPTURE")
    print("=" * 60)

    print(f"\nPress ENTER to begin microphone capture ({capture_duration:.1f}s)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelled")
        return None, None

    print("Recording...")
    try:
        samples = record_audio(capture_duration, input_device, sample_rate)
        print("DONE")
    except Exception as e:
        print(f"FAILED: {e}")
        return None, None

    if output_wav:
        try:
            save_recording(samples, output_wav, sample_rate)
            print(f"Saved to: {output_wav}")
        except Exception as e:
            print(f"Failed to save WAV: {e}")

    return samples, sample_rate


def analyze_and_report(samples: np.ndarray, sample_rate: int) -> None:
    """Run FFT analysis and report results."""
    print("\n" + "=" * 60)
    print("FFT ANALYSIS")
    print("=" * 60)

    try:
        result = detect_test_tone(samples, sample_rate)
        analysis = result.analysis

        print(f"\nPeak Frequency: {analysis.peak_frequency:.1f} Hz")
        print(f"Peak Magnitude: {analysis.peak_magnitude:.6f}")
        print(f"\nNoise Floor:")
        print(f"  Mean: {analysis.noise_floor.mean_magnitude:.6f}")
        print(f"  Median: {analysis.noise_floor.median_magnitude:.6f}")
        print(f"  Est. dB: {analysis.noise_floor.estimated_db:.1f} dB")

        print(f"\n18 kHz BAND ({TONE_FREQUENCY_BIT_0:.0f} Hz ± 500 Hz):")
        d18 = analysis.detection_18khz
        print(f"  Status: {d18.status.value}")
        if d18.peak_frequency:
            print(f"  Peak: {d18.peak_frequency:.1f} Hz")
            print(f"  Magnitude: {d18.peak_magnitude:.6f}")
            if d18.snr_db is not None:
                print(f"  SNR: {d18.snr_db:.1f} dB")
            print(f"  Relative Energy: {d18.relative_energy:.3f}")

        print(f"\n19 kHz BAND ({TONE_FREQUENCY_BIT_1:.0f} Hz ± 500 Hz):")
        d19 = analysis.detection_19khz
        print(f"  Status: {d19.status.value}")
        if d19.peak_frequency:
            print(f"  Peak: {d19.peak_frequency:.1f} Hz")
            print(f"  Magnitude: {d19.peak_magnitude:.6f}")
            if d19.snr_db is not None:
                print(f"  SNR: {d19.snr_db:.1f} dB")
            print(f"  Relative Energy: {d19.relative_energy:.3f}")

        print("\n" + "=" * 60)
        print("DIAGNOSTIC RESULT")
        print("=" * 60)
        print(f"\n{result.summary}")

    except Exception as e:
        print(f"Analysis failed: {e}")
        logger.exception("Analysis error")


def analyze_wav_file(wav_path: Path) -> None:
    """Analyze existing WAV file."""
    print("\n" + "=" * 60)
    print(f"WAV ANALYSIS: {wav_path}")
    print("=" * 60)

    try:
        samples, sample_rate = load_recording(wav_path)
        print(f"Loaded: {len(samples)} samples at {sample_rate} Hz")
        analyze_and_report(samples, sample_rate)
    except Exception as e:
        print(f"Failed to load/analyze WAV: {e}")
        logger.exception("WAV analysis error")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WhisperProtocol Audio Diagnostics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m whisper.cli.audio_test
  python -m whisper.cli.audio_test --input 1 --output 2
  python -m whisper.cli.audio_test --wav test.wav
  python -m whisper.cli.audio_test --duration 2.0 --capture 3.0
        """,
    )

    parser.add_argument(
        "--input",
        type=int,
        help="Input device index (default: system default)",
    )
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
        default=1.0,
        help="Test tone duration in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--capture",
        type=float,
        default=2.0,
        help="Capture duration in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--wav",
        type=Path,
        help="Analyze existing WAV file instead of live capture",
    )
    parser.add_argument(
        "--save-wav",
        type=Path,
        help="Save capture to WAV file",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list devices and exit",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 60)
    print("WHISPERPROTOCOL AUDIO DIAGNOSTICS")
    print("=" * 60)

    input_devices = list_input_devices()
    output_devices = list_output_devices()

    print_devices(input_devices, "INPUT DEVICES")
    print_devices(output_devices, "OUTPUT DEVICES")
    print_default_devices()

    input_device = args.input
    output_device = args.output

    if input_device is None:
        default_in = get_default_input_device()
        if default_in:
            input_device = default_in.index

    if output_device is None:
        default_out = get_default_output_device()
        if default_out:
            output_device = default_out.index

    check_sample_rates(input_device, output_device)

    if args.list_only:
        return 0

    if args.wav:
        analyze_wav_file(args.wav)
        return 0

    if output_device is not None:
        run_playback_tests(output_device, args.sample_rate, args.duration)
    else:
        print("\nNo output device available, skipping playback tests")

    if input_device is not None:
        samples, sr = run_capture_and_analysis(
            input_device, args.sample_rate, args.capture, args.save_wav
        )
        if samples is not None:
            analyze_and_report(samples, sr)
    else:
        print("\nNo input device available, skipping capture")

    return 0


if __name__ == "__main__":
    sys.exit(main())