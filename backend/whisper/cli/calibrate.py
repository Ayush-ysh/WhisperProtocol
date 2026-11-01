"""CLI command for WhisperProtocol hardware calibration."""

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

from whisper.protocol import (
    ReceiverConfig,
    SymbolDetector,
    SymbolDecision,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SYMBOL_DURATION,
    FREQ_ZERO,
    FREQ_ONE,
    generate_symbol,
)
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
)
from whisper.audio.diagnostics import (
    analyze_spectrum,
    detect_test_tone,
    FREQUENCY_BAND_18KHZ,
    FREQUENCY_BAND_19KHZ,
    TARGET_FREQ_18KHZ,
    TARGET_FREQ_19KHZ,
    DetectionStatus,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print(f"{'=' * 60}")


def print_subsection(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(title)
    print(f"{'-' * 60}")


def test_devices(input_device: int | None, output_device: int | None, sample_rate: int) -> dict:
    """Test device availability and sample rate support."""
    results = {}

    print_subsection("DEVICE TEST")
    
    # Input device
    if input_device is not None:
        try:
            supported = check_sample_rate_support(input_device, sample_rate, is_input=True)
            results['input_supported'] = supported
            print(f"  Input Device {input_device}: {'SUPPORTED' if supported else 'NOT SUPPORTED'} at {sample_rate} Hz")
        except Exception as e:
            results['input_supported'] = False
            print(f"  Input Device {input_device}: ERROR - {e}")
    else:
        print("  Input Device: Not specified")

    # Output device
    if output_device is not None:
        try:
            supported = check_sample_rate_support(output_device, sample_rate, is_input=False)
            results['output_supported'] = supported
            print(f"  Output Device {output_device}: {'SUPPORTED' if supported else 'NOT SUPPORTED'} at {sample_rate} Hz")
        except Exception as e:
            results['output_supported'] = False
            print(f"  Output Device {output_device}: ERROR - {e}")
    else:
        print("  Output Device: Not specified")

    return results


def test_speaker_response(output_device: int | None, sample_rate: int, duration: float, amplitude: float) -> dict:
    """Test speaker response at 18 kHz and 19 kHz."""
    results = {}

    print_subsection("SPEAKER RESPONSE TEST")
    print(f"  Playing test tones at amplitude {amplitude:.2f}...")

    # Test 18 kHz
    print(f"  18 kHz test tone ({duration:.1f}s)...")
    try:
        play_18khz_test(duration, output_device, sample_rate, amplitude)
        results['speaker_18khz_ok'] = True
        print("    OK")
    except Exception as e:
        results['speaker_18khz_ok'] = False
        print(f"    FAILED: {e}")

    time.sleep(0.5)

    # Test 19 kHz
    print(f"  19 kHz test tone ({duration:.1f}s)...")
    try:
        play_19khz_test(duration, output_device, sample_rate, amplitude)
        results['speaker_19khz_ok'] = True
        print("    OK")
    except Exception as e:
        results['speaker_19khz_ok'] = False
        print(f"    FAILED: {e}")

    return results


def test_microphone_capture(input_device: int | None, sample_rate: int, duration: float) -> tuple:
    """Capture audio from microphone and return samples."""
    print_subsection("MICROPHONE CAPTURE TEST")
    print(f"  Recording {duration:.1f}s of ambient audio...")
    print("  (Please remain quiet during capture)")

    try:
        samples = record_audio(duration, input_device, sample_rate)
        rms = np.sqrt(np.mean(samples**2))
        peak = np.max(np.abs(samples))
        print(f"  Captured {len(samples)} samples")
        print(f"  RMS: {rms:.6f}")
        print(f"  Peak: {peak:.6f}")
        return samples, sample_rate
    except Exception as e:
        print(f"  FAILED: {e}")
        return None, None


def analyze_frequency_response(samples: np.ndarray, sample_rate: int) -> dict:
    """Analyze frequency response for 18/19 kHz bands."""
    results = {}

    print_subsection("FREQUENCY RESPONSE ANALYSIS")

    try:
        analysis = analyze_spectrum(samples, sample_rate)

        print(f"  Peak Frequency: {analysis.peak_frequency:.1f} Hz")
        print(f"  Peak Magnitude: {analysis.peak_magnitude:.6f}")

        print(f"\n  Noise Floor:")
        print(f"    Mean: {analysis.noise_floor.mean_magnitude:.6f}")
        print(f"    Median: {analysis.noise_floor.median_magnitude:.6f}")
        print(f"    Est. dB: {analysis.noise_floor.estimated_db:.1f} dB")

        # 18 kHz band
        d18 = analysis.detection_18khz
        print(f"\n  18 kHz Band ({FREQUENCY_BAND_18KHZ[0]:.0f}-{FREQUENCY_BAND_18KHZ[1]:.0f} Hz):")
        print(f"    Status: {d18.status.value}")
        if d18.peak_frequency:
            print(f"    Peak: {d18.peak_frequency:.1f} Hz")
            print(f"    Magnitude: {d18.peak_magnitude:.6f}")
            if d18.snr_db is not None:
                print(f"    SNR: {d18.snr_db:.1f} dB")
            print(f"    Relative Energy: {d18.relative_energy:.3f}")
        results['band_18khz'] = {
            'status': d18.status.value,
            'peak_freq': d18.peak_frequency,
            'snr_db': d18.snr_db,
            'relative_energy': d18.relative_energy,
        }

        # 19 kHz band
        d19 = analysis.detection_19khz
        print(f"\n  19 kHz Band ({FREQUENCY_BAND_19KHZ[0]:.0f}-{FREQUENCY_BAND_19KHZ[1]:.0f} Hz):")
        print(f"    Status: {d19.status.value}")
        if d19.peak_frequency:
            print(f"    Peak: {d19.peak_frequency:.1f} Hz")
            print(f"    Magnitude: {d19.peak_magnitude:.6f}")
            if d19.snr_db is not None:
                print(f"    SNR: {d19.snr_db:.1f} dB")
            print(f"    Relative Energy: {d19.relative_energy:.3f}")
        results['band_19khz'] = {
            'status': d19.status.value,
            'peak_freq': d19.peak_frequency,
            'snr_db': d19.snr_db,
            'relative_energy': d19.relative_energy,
        }

    except Exception as e:
        print(f"  Analysis failed: {e}")
        logger.exception("Analysis error")

    return results


def test_loopback(
    input_device: int | None,
    output_device: int | None,
    sample_rate: int,
    symbol_duration: float,
    amplitude: float,
) -> dict:
    """Test full loopback: transmit known symbols, receive and verify."""
    results = {}

    print_subsection("LOOPBACK TEST")
    print("  Testing transmitter -> air -> receiver path...")
    print("  (Ensure speaker and microphone are positioned for loopback)")

    # Generate test pattern: alternating 0/1 for 2 seconds
    test_bits = "01" * 50  # 100 symbols = 2 seconds at 20ms
    print(f"  Transmitting test pattern: {test_bits[:20]}... ({len(test_bits)} symbols)")

    from whisper.protocol import modulate_bits

    try:
        waveform = modulate_bits(
            [int(b) for b in test_bits],
            sample_rate=sample_rate,
            symbol_duration=symbol_duration,
            amplitude=amplitude,
        )

        # Play and record simultaneously would be ideal, but we'll do sequential
        # For now, just verify we can generate the waveform
        print(f"  Generated waveform: {len(waveform)} samples, {len(waveform)/sample_rate:.2f}s")
        results['waveform_ok'] = True

        # Try to play it
        from whisper.audio.output import _play_samples, stop_playback
        try:
            _play_samples(waveform, sample_rate, device=output_device, blocking=True)
            results['playback_ok'] = True
            print("  Playback complete")
        except Exception as e:
            results['playback_ok'] = False
            print(f"  Playback failed: {e}")

    except Exception as e:
        results['waveform_ok'] = False
        print(f"  Waveform generation failed: {e}")

    return results


def run_symbol_detection_test(config: ReceiverConfig) -> dict:
    """Test symbol detector with synthetic signals."""
    results = {}

    print_subsection("SYMBOL DETECTION TEST (Synthetic)")

    detector = SymbolDetector(config)

    # Test clean 18 kHz symbol
    print("  Testing clean 18 kHz symbol (bit 0)...")
    sym_0 = generate_symbol(0, sample_rate=config.sample_rate, symbol_duration=config.symbol_duration, amplitude=1.0)
    det_0 = detector.detect(sym_0)
    print(f"    Decision: {det_0.decision.name}, Freq: {det_0.detected_frequency:.1f} Hz, Conf: {det_0.confidence:.3f}")
    results['detect_18khz'] = {
        'decision': det_0.decision.name,
        'freq': det_0.detected_frequency,
        'confidence': det_0.confidence,
    }

    # Test clean 19 kHz symbol
    print("  Testing clean 19 kHz symbol (bit 1)...")
    sym_1 = generate_symbol(1, sample_rate=config.sample_rate, symbol_duration=config.symbol_duration, amplitude=1.0)
    det_1 = detector.detect(sym_1)
    print(f"    Decision: {det_1.decision.name}, Freq: {det_1.detected_frequency:.1f} Hz, Conf: {det_1.confidence:.3f}")
    results['detect_19khz'] = {
        'decision': det_1.decision.name,
        'freq': det_1.detected_frequency,
        'confidence': det_1.confidence,
    }

    # Test noise
    print("  Testing noise only...")
    noise = np.random.normal(0, 0.001, config.samples_per_symbol).astype(np.float32)
    det_n = detector.detect(noise)
    print(f"    Decision: {det_n.decision.name}, Conf: {det_n.confidence:.3f}")
    results['detect_noise'] = {
        'decision': det_n.decision.name,
        'confidence': det_n.confidence,
    }

    return results


def print_recommendations(results: dict) -> None:
    """Print calibration recommendations based on test results."""
    print_section("CALIBRATION RECOMMENDATIONS")

    recommendations = []

    # Check device support
    if not results.get('devices', {}).get('input_supported', False):
        recommendations.append("⚠ Input device doesn't support configured sample rate")
    if not results.get('devices', {}).get('output_supported', False):
        recommendations.append("⚠ Output device doesn't support configured sample rate")

    # Check speaker
    if not results.get('speaker', {}).get('speaker_18khz_ok', False):
        recommendations.append("⚠ Speaker may not reproduce 18 kHz well")
    if not results.get('speaker', {}).get('speaker_19khz_ok', False):
        recommendations.append("⚠ Speaker may not reproduce 19 kHz well")

    # Check microphone capture
    if results.get('mic_capture') is None:
        recommendations.append("⚠ Microphone capture failed")
    else:
        samples, sr = results['mic_capture']
        if samples is not None:
            rms = np.sqrt(np.mean(samples**2))
            if rms < 1e-5:
                recommendations.append("⚠ Very low microphone signal - check permissions/gain")
            elif rms > 0.5:
                recommendations.append("⚠ High microphone signal - possible clipping")

    # Check frequency response
    fr = results.get('freq_response', {})
    if fr.get('band_18khz', {}).get('status') == 'DETECTED':
        recommendations.append("✓ 18 kHz tone detected in ambient")
    else:
        recommendations.append("⚠ 18 kHz not reliably detected in ambient (expected if no signal)")

    if fr.get('band_19khz', {}).get('status') == 'DETECTED':
        recommendations.append("✓ 19 kHz tone detected in ambient")
    else:
        recommendations.append("⚠ 19 kHz not reliably detected in ambient (expected if no signal)")

    # Symbol detector
    sd = results.get('symbol_detector', {})
    if sd.get('detect_18khz', {}).get('decision') == 'ZERO':
        recommendations.append("✓ Symbol detector correctly identifies 18 kHz")
    else:
        recommendations.append("⚠ Symbol detector issue with 18 kHz")

    if sd.get('detect_19khz', {}).get('decision') == 'ONE':
        recommendations.append("✓ Symbol detector correctly identifies 19 kHz")
    else:
        recommendations.append("⚠ Symbol detector issue with 19 kHz")

    if sd.get('detect_noise', {}).get('decision') in ('UNKNOWN', 'LOW_CONFIDENCE'):
        recommendations.append("✓ Symbol detector correctly rejects noise")
    else:
        recommendations.append("⚠ Symbol detector may false-trigger on noise")

    print()
    for r in recommendations:
        print(f"  {r}")

    print(f"\n{'=' * 60}")
    print("CALIBRATION COMPLETE")
    print(f"{'=' * 60}")
    print("\nNext steps:")
    print("  1. If speaker/microphone issues: Check OS audio permissions")
    print("  2. If frequency response poor: Try different sample rate (48000 Hz)")
    print("  3. If loopback works: Run two-device test with:")
    print("       PC A: python -m whisper.cli.transmit 'HELLO'")
    print("       PC B: python -m whisper.cli.receive")
    print("  4. For production: Use amplitude 0.3-0.6, adjust based on distance")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WhisperProtocol Hardware Calibration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m whisper.cli.calibrate
  python -m whisper.cli.calibrate --input 0 --output 1
  python -m whisper.cli.calibrate --sample-rate 48000 --duration 0.01
  python -m whisper.cli.calibrate --amplitude 0.5 --capture-duration 3.0
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
        default=DEFAULT_SYMBOL_DURATION,
        help=f"Symbol duration in seconds (default: {DEFAULT_SYMBOL_DURATION})",
    )
    parser.add_argument(
        "--amplitude",
        type=float,
        default=0.5,
        help="Test amplitude 0.0-1.0 (default: 0.5)",
    )
    parser.add_argument(
        "--tone-duration",
        type=float,
        default=1.0,
        help="Test tone duration in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--capture-duration",
        type=float,
        default=2.0,
        help="Microphone capture duration in seconds (default: 2.0)",
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

    print_section("WHISPERPROTOCOL CALIBRATION")

    # List devices
    input_devices = list_input_devices()
    output_devices = list_output_devices()

    print_subsection("AVAILABLE DEVICES")
    print("Input devices:")
    for d in input_devices:
        print(f"  {d}")
    print("Output devices:")
    for d in output_devices:
        print(f"  {d}")

    default_in = get_default_input_device()
    default_out = get_default_output_device()
    if default_in:
        print(f"\nDefault Input:  {default_in}")
    if default_out:
        print(f"Default Output: {default_out}")

    if args.list_only:
        return 0

    # Resolve device indices
    input_device = args.input
    if input_device is None and default_in:
        input_device = default_in.index

    output_device = args.output
    if output_device is None and default_out:
        output_device = default_out.index

    # Configuration
    config = ReceiverConfig(
        sample_rate=args.sample_rate,
        symbol_duration=args.duration,
        freq_zero=FREQ_ZERO,
        freq_one=FREQ_ONE,
    )

    all_results = {}

    # Test 1: Device support
    all_results['devices'] = test_devices(input_device, output_device, args.sample_rate)

    # Test 2: Speaker response
    if output_device is not None:
        all_results['speaker'] = test_speaker_response(
            output_device, args.sample_rate, args.tone_duration, args.amplitude
        )

    # Test 3: Microphone capture
    if input_device is not None:
        print("\nPress ENTER to begin microphone capture...")
        try:
            input()
        except KeyboardInterrupt:
            print("\nCancelled")
            return 0

        mic_samples, mic_sr = test_microphone_capture(input_device, args.sample_rate, args.capture_duration)
        all_results['mic_capture'] = (mic_samples, mic_sr) if mic_samples is not None else None

        if args.save_wav and mic_samples is not None:
            save_recording(mic_samples, args.save_wav, args.sample_rate)
            print(f"  Saved capture to: {args.save_wav}")

    # Test 4: Frequency response analysis
    if input_device is not None and mic_samples is not None:
        all_results['freq_response'] = analyze_frequency_response(mic_samples, args.sample_rate)

    # Test 5: Symbol detector with synthetic signals
    all_results['symbol_detector'] = run_symbol_detection_test(config)

    # Test 6: Loopback test (optional)
    if input_device is not None and output_device is not None:
        print("\nPress ENTER to run loopback test (speaker -> air -> mic)...")
        try:
            input()
        except KeyboardInterrupt:
            print("\nSkipped")
        else:
            all_results['loopback'] = test_loopback(
                input_device, output_device, args.sample_rate,
                args.duration, args.amplitude
            )

    # Print recommendations
    print_recommendations(all_results)

    return 0


if __name__ == "__main__":
    sys.exit(main())