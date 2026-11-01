"""CLI command for validating encoded waveform."""

import argparse
import sys
from pathlib import Path

import numpy as np

from whisper.protocol import (
    DEFAULT_SAMPLE_RATE,
    FREQ_ZERO,
    FREQ_ONE,
)
from whisper.audio.input import load_recording
from whisper.audio.diagnostics import (
    analyze_spectrum,
    detect_test_tone,
    FREQUENCY_BAND_18KHZ,
    FREQUENCY_BAND_19KHZ,
    TARGET_FREQ_18KHZ,
    TARGET_FREQ_19KHZ,
    DEFAULT_DETECTION_THRESHOLD_DB,
    DEFAULT_MIN_SNR_DB,
    DetectionStatus,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WhisperProtocol Waveform Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m whisper.cli.validate output.wav
  python -m whisper.cli.validate output.wav --sample-rate 48000
        """,
    )

    parser.add_argument("wav", type=Path, help="Input WAV file to validate")
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help=f"Expected sample rate in Hz (default: {DEFAULT_SAMPLE_RATE})",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("WHISPERPROTOCOL WAVEFORM VALIDATOR")
    print("=" * 60)

    # Load WAV
    print(f"\nLoading: {args.wav}")
    try:
        samples, sample_rate = load_recording(args.wav)
        print(f"  Sample rate: {sample_rate} Hz")
        print(f"  Samples: {len(samples)}")
        print(f"  Duration: {len(samples) / sample_rate:.3f} s")
        print(f"  Channels: {samples.shape[1] if samples.ndim > 1 else 1}")
        print(f"  Dtype: {samples.dtype}")
    except Exception as e:
        print(f"  FAILED: {e}", file=sys.stderr)
        return 1

    # Check sample rate
    if sample_rate != args.sample_rate:
        print(f"\nWARNING: Sample rate mismatch!")
        print(f"  Expected: {args.sample_rate} Hz")
        print(f"  Actual:   {sample_rate} Hz")
    else:
        print(f"\nSample rate OK: {sample_rate} Hz")

    # Convert to mono if stereo
    if samples.ndim > 1:
        samples = samples[:, 0]  # Use first channel

    # Basic waveform statistics
    print(f"\nWaveform Statistics:")
    print(f"  Min: {np.min(samples):.6f}")
    print(f"  Max: {np.max(samples):.6f}")
    print(f"  Mean: {np.mean(samples):.6f}")
    print(f"  RMS: {np.sqrt(np.mean(samples**2)):.6f}")
    print(f"  Clipped: {np.any(np.abs(samples) >= 1.0)}")

    # Check for clipping
    if np.any(np.abs(samples) >= 1.0):
        print(f"  WARNING: Waveform contains clipped samples!")

    # FFT Analysis
    print(f"\n" + "=" * 60)
    print("FFT SPECTRUM ANALYSIS")
    print("=" * 60)

    try:
        analysis = analyze_spectrum(samples, sample_rate)

        print(f"\nPeak Frequency: {analysis.peak_frequency:.1f} Hz")
        print(f"Peak Magnitude: {analysis.peak_magnitude:.6f}")

        print(f"\nNoise Floor:")
        print(f"  Mean: {analysis.noise_floor.mean_magnitude:.6f}")
        print(f"  Median: {analysis.noise_floor.median_magnitude:.6f}")
        print(f"  Est. dB: {analysis.noise_floor.estimated_db:.1f} dB")

        print(f"\n18 kHz BAND ({FREQUENCY_BAND_18KHZ[0]:.0f}-{FREQUENCY_BAND_18KHZ[1]:.0f} Hz):")
        d18 = analysis.detection_18khz
        print(f"  Status: {d18.status.value}")
        if d18.peak_frequency:
            print(f"  Peak: {d18.peak_frequency:.1f} Hz")
            print(f"  Magnitude: {d18.peak_magnitude:.6f}")
            if d18.snr_db is not None:
                print(f"  SNR: {d18.snr_db:.1f} dB")
            print(f"  Relative Energy: {d18.relative_energy:.3f}")

        print(f"\n19 kHz BAND ({FREQUENCY_BAND_19KHZ[0]:.0f}-{FREQUENCY_BAND_19KHZ[1]:.0f} Hz):")
        d19 = analysis.detection_19khz
        print(f"  Status: {d19.status.value}")
        if d19.peak_frequency:
            print(f"  Peak: {d19.peak_frequency:.1f} Hz")
            print(f"  Magnitude: {d19.peak_magnitude:.6f}")
            if d19.snr_db is not None:
                print(f"  SNR: {d19.snr_db:.1f} dB")
            print(f"  Relative Energy: {d19.relative_energy:.3f}")

        # Overall validation
        print(f"\n" + "=" * 60)
        print("VALIDATION RESULT")
        print("=" * 60)

        has_18khz = d18.status == DetectionStatus.DETECTED
        has_19khz = d19.status == DetectionStatus.DETECTED

        if has_18khz and has_19khz:
            print(f"\nPASS: Both 18 kHz and 19 kHz tones detected")
            print(f"      Waveform appears to contain valid AFSK modulation")
        elif has_18khz or has_19khz:
            print(f"\nPARTIAL: Only one tone detected")
            print(f"         18 kHz: {'DETECTED' if has_18khz else 'NOT DETECTED'}")
            print(f"         19 kHz: {'DETECTED' if has_19khz else 'NOT DETECTED'}")
        else:
            print(f"\nFAIL: Neither 18 kHz nor 19 kHz tones reliably detected")
            print(f"      Waveform may not contain valid AFSK modulation")

        # Additional checks
        print(f"\nAdditional Checks:")
        symbol_duration_guess = 0.020  # 20ms
        expected_symbols = len(samples) / (sample_rate * symbol_duration_guess)
        print(f"  Estimated symbol count: ~{expected_symbols:.0f} (at {symbol_duration_guess*1000:.0f}ms/symbol)")

    except Exception as e:
        print(f"Analysis failed: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())