# WhisperProtocol - Protocol Specification

Version: 1.0 (Phase 2)
Date: 2024

---

## 1. Overview

WhisperProtocol is an acoustic communication protocol using Audio Frequency Shift Keying (AFSK) at ultrasonic frequencies (18-19 kHz) for controlled demonstration purposes.

This document specifies the binary frame format, modulation scheme, and encoding pipeline.

---

## 2. Bit Mapping

| Bit | Frequency |
|-----|-----------|
| 0   | 18,000 Hz |
| 1   | 19,000 Hz |

---

## 3. Audio Parameters

| Parameter | Value |
|-----------|-------|
| Sample Rate | 44,100 Hz |
| Symbol Duration | 20 ms |
| Samples per Symbol | 882 |
| Amplitude | 0.8 (configurable) |
| Fade Duration | 2 ms (in/out) |

---

## 4. Frame Structure

```
┌─────────────┬────────┬─────────┬─────────────┬──────────┐
│  PREAMBLE   │  SYNC  │ LENGTH  │   PAYLOAD   │ CHECKSUM │
│   (32 bits) │(16 bits)│(16 bits)│ (N × 8 bits)│(16 bits) │
└─────────────┴────────┴─────────┴─────────────┴──────────┘
```

### 4.1 Preamble (32 bits)
Pattern: `10101010101010101010101010101010` (alternating 1/0)

Purpose: Allows receiver to detect signal presence and estimate timing.

### 4.2 Sync (16 bits)
Pattern: `1111000011110000`

Purpose: Distinct from preamble; marks frame start after preamble detection.

### 4.3 Length (16 bits)
Big-endian unsigned integer encoding payload length in bytes.
Maximum payload: 65,535 bytes.

### 4.4 Payload (variable)
UTF-8 encoded message bytes. Each byte expands to 8 bits (MSB first).

### 4.5 Checksum (16 bits)
CRC-16-CCITT (polynomial 0x1021, initial value 0xFFFF) computed over:
`LENGTH || PAYLOAD` (i.e., everything after preamble and sync)

---

## 5. Encoding Pipeline

```
STRING (UTF-8 text)
    │
    ▼
BYTES (UTF-8 encoding)
    │
    ▼
FRAME (preamble + sync + length + payload + checksum)
    │
    ▼
BITS (MSB first per byte)
    │
    ▼
AFSK MODULATION (18 kHz / 19 kHz per symbol)
    │
    ▼
WAVEFORM (44.1 kHz, float32)
```

---

## 6. Symbol Generation

Each bit becomes one symbol of 20 ms duration:

- **Bit 0**: 18,000 Hz sine wave, 20 ms
- **Bit 1**: 19,000 Hz sine wave, 20 ms

### Fade Windows
- 2 ms raised-cosine fade-in at symbol start
- 2 ms raised-cosine fade-out at symbol end
- Reduces spectral artifacts at symbol boundaries

### Amplitude
Normalized to 0.8 peak to avoid clipping.

---

## 7. Checksum Algorithm

**CRC-16-CCITT**
- Polynomial: 0x1021 (x^16 + x^12 + x^5 + 1)
- Initial value: 0xFFFF
- No final XOR
- Input: bytes (not bit-reflected)
- Output: 16-bit value, transmitted MSB first

Implementation uses Python's `binascii.crc_hqx()`.

---

## 8. Example Frame

Message: `"A"` (single byte 0x41)

### Step 1: UTF-8 Bytes
```
41
```

### Step 2: Payload Bits (8 bits, MSB first)
```
01000001
```

### Step 3: Length Field (16 bits, big-endian)
```
0000000000000001  (length = 1)
```

### Step 4: Frame without Checksum
```
PREAMBLE:  10101010101010101010101010101010
SYNC:      1111000011110000
LENGTH:    0000000000000001
PAYLOAD:   01000001
```

### Step 5: CRC-16 over LENGTH + PAYLOAD
Data: `00 01 41` (3 bytes)
CRC-16: `0x8A79` (example value)

### Step 6: Complete Frame (72 bits)
```
10101010101010101010101010101010 1111000011110000 0000000000000001 01000001 1000101001111001
```

### Step 7: Modulated Waveform
- 72 symbols × 20 ms = 1.44 seconds
- 72 × 882 = 63,504 samples at 44.1 kHz

---

## 9. Decoding (Future Phase 3)

Receiver pipeline (conceptual):

```
WAVEFORM (44.1 kHz)
    │
    ▼
SYNCHRONIZATION (preamble detection)
    │
    ▼
SYMBOL TIMING RECOVERY
    │
    ▼
FFT / GOERTZEL PER SYMBOL
    │
    ▼
BIT CLASSIFICATION (18 vs 19 kHz)
    │
    ▼
BITSTREAM
    │
    ▼
FRAME PARSING (preamble → sync → length → payload → checksum)
    │
    ▼
CRC VERIFICATION
    │
    ▼
PAYLOAD BYTES → UTF-8 STRING
```

---

## 10. Known Limitations

1. **No Forward Error Correction**: Single bit error corrupts frame. Reed-Solomon planned for Phase 4.

2. **No Encryption**: Payload is plaintext. AES-GCM planned for Phase 3.

3. **Fixed Symbol Rate**: 50 symbols/sec (20 ms). No adaptive rate.

4. **No Doppler Compensation**: Assumes stationary devices.

5. **No Multi-path Mitigation**: Single-tone symbols susceptible to fading.

6. **Preamble Length**: 32 bits may be insufficient in high noise. May need extension.

7. **Sample Rate Dependency**: Requires 44.1 kHz or integer multiple.

---

## 11. Configuration Parameters

The following can be adjusted without breaking protocol compatibility (if both ends agree):

| Parameter | Default | Range | Notes |
|-----------|---------|-------|-------|
| FREQ_ZERO | 18000 | 10000-22000 | Must be < Nyquist |
| FREQ_ONE | 19000 | 10000-22000 | Must be > FREQ_ZERO |
| SAMPLE_RATE | 44100 | 44100, 48000, 96000 | Affects symbol timing |
| SYMBOL_DURATION | 0.020 | 0.010-0.100 | Longer = more robust, slower |
| AMPLITUDE | 0.8 | 0.1-1.0 | Higher = more range, more distortion |
| PREAMBLE_LENGTH | 32 | 16-128 | Even number |
| SYNC_PATTERN | 16-bit | 8-32 bits | Must differ from preamble |

---

## 12. Implementation Notes

- All bit operations use MSB-first (big-endian) ordering
- CRC computed on byte level, not bit level
- Waveform generation is deterministic for given parameters
- No randomization or spreading applied in Phase 2
- Symbol boundaries use fade windows to minimize spectral splatter