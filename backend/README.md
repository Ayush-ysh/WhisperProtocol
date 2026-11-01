# WhisperProtocol - Audio Backend

Python audio foundation for WhisperProtocol acoustic communication.

## Overview

This package provides the core audio engine for WhisperProtocol, a controlled acoustic communication demonstration using 18 kHz and 19 kHz tones for binary data transmission.

**BIT 0 → 18,000 Hz**  
**BIT 1 → 19,000 Hz**

The physical transport is acoustic: Speaker → Air → Microphone.

## Installation

```bash
cd backend
pip install -e .[dev]
```

### Dependencies

- **numpy** ≥ 1.24 - Numerical computations
- **scipy** ≥ 1.10 - Signal processing (FFT, windows)
- **sounddevice** ≥ 0.4.6 - Cross-platform audio I/O (PortAudio backend)
- **soundfile** ≥ 0.12 - WAV file read/write

Optional: `pytest`, `pytest-cov`, `ruff` for development.

### System Requirements

- **Python** 3.11+
- **PortAudio** library (installed via sounddevice wheels on most platforms)
  - macOS: Included in wheels
  - Linux: `sudo apt install portaudio19-dev` (or equivalent)
  - Windows: Included in wheels

### Microphone Permissions

On macOS, Terminal (or your IDE) needs **Microphone** permission in:
**System Settings → Privacy & Security → Microphone**

On Linux, user may need to be in `audio` group:
```bash
sudo usermod -a -G audio $USER
```

## Quick Start

```bash
# Run full diagnostic (lists devices, plays tones, captures, analyzes)
python -m whisper.cli.audio_test

# Analyze existing WAV file
python -m whisper.cli.audio_test --wav recording.wav

# Custom devices and durations
python -m whisper.cli.audio_test --input 1 --output 2 --duration 2.0 --capture 3.0
```

## Architecture

```
whisper/
├── audio/
│   ├── devices.py      # Device discovery & sample rate checking
│   ├── signal.py       # Tone generation (sine waves, sequences)
│   ├── output.py       # Audio playback
│   ├── input.py        # Microphone capture & WAV I/O
│   └── diagnostics.py  # FFT analysis, detection, noise floor
└── cli/
    └── audio_test.py   # Diagnostic command-line interface
```

## API Reference

### Device Discovery

```python
from whisper.audio import (
    list_input_devices,
    list_output_devices,
    get_default_input_device,
    get_default_output_device,
    check_sample_rate_support,
    AudioDevice,
)

# List all devices
inputs = list_input_devices()
outputs = list_output_devices()

# Get defaults
mic = get_default_input_device()
speaker = get_default_output_device()

# Check sample rate support
supported = check_sample_rate_support(device_index, 44100, is_input=True)
```

### Tone Generation

```python
from whisper.audio import (
    generate_tone,
    generate_18khz_tone,
    generate_19khz_tone,
    generate_tone_sequence,
    TONE_FREQUENCY_BIT_0,  # 18000.0
    TONE_FREQUENCY_BIT_1,  # 19000.0
)

# Single tone
samples = generate_tone(18000.0, duration=1.0, sample_rate=44100)

# Protocol tones
bit0 = generate_18khz_tone(0.1)   # 100ms BIT 0
bit1 = generate_19khz_tone(0.1)   # 100ms BIT 1

# Bit sequence
sequence = generate_tone_sequence("01011001", bit_duration=0.1)
```

### Playback

```python
from whisper.audio import (
    play_tone,
    play_18khz_test,
    play_19khz_test,
    play_tone_sequence,
    stop_playback,
)

# Play test tones
play_18khz_test(duration=1.0, output_device=0)
play_19khz_test(duration=1.0, output_device=0)

# Play bit sequence
play_tone_sequence("01011001", bit_duration=0.1, output_device=0)

# Stop immediately
stop_playback()
```

### Recording

```python
from whisper.audio import record_audio, save_recording, load_recording

# Record from microphone
samples = record_audio(duration=2.0, input_device=0, sample_rate=44100)

# Save to WAV
save_recording(samples, "recording.wav", 44100)

# Load from WAV
samples, sr = load_recording("recording.wav")
```

### Analysis & Detection

```python
from whisper.audio import (
    analyze_spectrum,
    detect_test_tone,
    SpectrumAnalysis,
    DetectionResult,
    ToneDetection,
    DetectionStatus,
    FREQUENCY_BAND_18KHZ,  # (17500, 18500)
    FREQUENCY_BAND_19KHZ,  # (18500, 19500)
)

# Full spectrum analysis
analysis = analyze_spectrum(samples, sample_rate)
print(f"Peak: {analysis.peak_frequency:.1f} Hz")
print(f"18 kHz: {analysis.detection_18khz}")
print(f"19 kHz: {analysis.detection_19khz}")

# Detection with threshold
result = detect_test_tone(samples, sample_rate)
print(f"Channel Ready: {result.channel_ready}")
print(result.summary)
```

## Diagnostic CLI

The `audio_test` command runs a complete diagnostic:

```
========================================
WHISPERPROTOCOL AUDIO DIAGNOSTICS
========================================

INPUT DEVICES
[0] Built-in Microphone (in:1 out:0 @ 44100Hz)
[1] USB Microphone (in:2 out:0 @ 48000Hz)

OUTPUT DEVICES
[0] Built-in Speakers (in:0 out:2 @ 44100Hz)
[1] USB Speaker (in:0 out:2 @ 48000Hz)

DEFAULT DEVICES
Input:  [0] Built-in Microphone
Output: [0] Built-in Speakers

SAMPLE RATE SUPPORT (44100 Hz)
Input Device 0: SUPPORTED
Output Device 0: SUPPORTED

PLAYBACK TESTS
18 kHz Test: PLAYING... DONE
19 kHz Test: PLAYING... DONE

Press ENTER to begin microphone capture.
Recording... DONE

FFT ANALYSIS
Peak Frequency: 19003 Hz
Noise Floor: ...

18 kHz BAND
Status: DETECTED
Peak: 17982 Hz
SNR: 24.5 dB

19 kHz BAND
Status: DETECTED
Peak: 19021 Hz
SNR: 22.1 dB

DIAGNOSTIC RESULT:
CHANNEL READY
```

### CLI Options

```bash
python -m whisper.cli.audio_test --help

Options:
  --input INT          Input device index
  --output INT         Output device index
  --sample-rate INT    Sample rate (default: 44100)
  --duration FLOAT     Tone duration (default: 1.0s)
  --capture FLOAT      Capture duration (default: 2.0s)
  --wav PATH           Analyze existing WAV file
  --save-wav PATH      Save capture to WAV
  --list-only          List devices and exit
  -v, --verbose        Verbose logging
```

## Frequency Bands

The detector uses configurable bands around target frequencies:

| Tone | Target | Band | Width |
|------|--------|------|-------|
| BIT 0 | 18,000 Hz | 17,500 – 18,500 Hz | ±500 Hz |
| BIT 1 | 19,000 Hz | 18,500 – 19,500 Hz | ±500 Hz |

Hardware frequency response varies. The bands accommodate:
- Speaker/microphone roll-off
- Clock drift
- Doppler shift (minimal at these frequencies)

## Detection Logic

A tone is **DETECTED** when:
1. Peak in band exceeds noise floor by `detection_threshold_db` (default 10 dB)
2. SNR exceeds `min_snr_db` (default 6 dB)

**LOW CONFIDENCE**: SNR ≥ 3 dB but below threshold  
**NOT DETECTED**: Peak present but insufficient SNR  
**NO RELIABLE DETECTION**: No clear peak or SNR undefined

Channel is **READY** only when both tones are DETECTED reliably.

## Noise Floor Estimation

Uses robust statistics on the full magnitude spectrum:
- **Median** magnitude (resistant to signal peaks)
- **10th/90th percentiles** for spread
- Reports estimated dB: `20 * log10(median)`

## Known Limitations

1. **Sample Rate**: Target is 44.1 kHz. Some devices only support 48 kHz. The CLI checks and reports support explicitly.

2. **Nyquist Limit**: At 44.1 kHz, max representable frequency is 22.05 kHz. Our 18/19 kHz tones are close to Nyquist - ensure device actually reproduces them.

3. **Hardware Variability**: Laptop speakers often roll off above 15 kHz. External speakers/headphones recommended for testing.

4. **Ambient Noise**: HVAC, fans, and ultrasonic noise (from switching power supplies) can raise noise floor at 18-19 kHz.

5. **No Background Capture**: Recording only happens on explicit request. No continuous monitoring.

6. **Single Channel**: Currently mono only. Stereo input averages channels.

## Testing

```bash
# Run unit tests (no hardware required)
pytest tests/ -v

# With coverage
pytest tests/ --cov=whisper --cov-report=term-missing
```

### Test Categories

- **Unit Tests** (`test_signal.py`, `test_diagnostics.py`): Pure Python, synthetic signals, no hardware
- **Hardware Tests**: Manual via `audio_test` CLI

## Safety & Scope

This is a **controlled demonstration** only:

- No covert recording
- No background audio capture
- No filesystem access beyond explicit WAV save/load
- No network communication
- No encryption, error correction, or protocol framing (future phases)

## Next Phase

Phase 2 will add:
- Local API/WebSocket server for frontend integration
- Framing protocol (preamble, sync, payload, checksum)
- Reed-Solomon error correction
- AES-GCM encryption
- File transfer demonstration

## License

Internal demonstration code.