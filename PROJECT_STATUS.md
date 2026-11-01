# WHISPERPROTOCOL — PROJECT STATUS & SYSTEM AUDIT

**Date:** 2026-11-01  
**Repository Branch:** `main`  
**Current Git Commit:** `cff7bb9`  
**Lead Architecture:** Principal Software Architect & Lead Engineer  

---

## 1. Executive Summary

WhisperProtocol is an offline-first, cross-platform acoustic communication desktop application designed to exchange short, explicitly approved text messages between devices via near-ultrasonic sound waves (Mark = 18 kHz, Space = 19 kHz) traversing physical air (`SPEAKER → AIR → MICROPHONE`). No Wi-Fi, Bluetooth, cellular, TCP/UDP, cloud services, or external networks are utilized for payload transport.

Following the completion of **Phase 3.5 (Critical Bug Fixes & Stabilization)**, all physical layer baseline regressions have been resolved, and the test suite passes at 100% (156/156 automated tests passing). The project is now prepared for full desktop product engineering across **Milestones A, B, and C**.

---

## 2. Current Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   WhisperProtocol Desktop Host                   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │             Presentation Layer (React 18 + Vite)           │  │
│  │   - Brutalist / Editorial Dark UI (Tailwind CSS)           │  │
│  │   - Framer Motion Transitions & Animations                 │  │
│  │   - Self-hosted Inter & JetBrains Mono Typography          │  │
│  │   - Views: Intro, Transmit, Receive, Broadcast, System,    │  │
│  │            Security, (Pending: Discovery, Sessions, Config)│  │
│  └──────────────────────────────┬─────────────────────────────┘  │
│                                 │ Tauri IPC / Events             │
│  ┌──────────────────────────────▼─────────────────────────────┐  │
│  │                Desktop Shell (Tauri 2 + Rust)              │  │
│  │   - Window management & Native Menu                        │  │
│  │   - Controlled JSON Lines Stdin/Stdout Process Bridge      │  │
│  │   - Local SQLite Storage (Metadata, Settings, History)     │  │
│  │   - Microphone Permissions & OS Audio Management           │  │
│  └──────────────────────────────┬─────────────────────────────┘  │
│                                 │ JSON Lines IPC (No TCP/HTTP)   │
│  ┌──────────────────────────────▼─────────────────────────────┐  │
│  │                 Python 3.11+ Core Engine                   │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │ Security & Crypto Layer (Phase 4)                    │  │  │
│  │  │ - X25519 Ephemeral Key Agreement                    │  │  │
│  │  │ - HKDF-SHA256 Key Derivation                         │  │  │
│  │  │ - AES-256-GCM Authenticated Encryption               │  │  │
│  │  └──────────────────────────┬───────────────────────────┘  │  │
│  │                             │                              │  │
│  │  ┌──────────────────────────▼───────────────────────────┐  │  │
│  │  │ Error Correction Layer (Phase 5)                     │  │  │
│  │  │ - Reed-Solomon (RS) Codec at Frame Level             │  │  │
│  │  └──────────────────────────┬───────────────────────────┘  │  │
│  │                             │                              │  │
│  │  ┌──────────────────────────▼───────────────────────────┐  │  │
│  │  │ Protocol Framing & Framing Handshake (Phase 6)       │  │  │
│  │  │ - Canonical Protocol Frames: DISCOVERY_PING/RESP,    │  │  │
│  │  │   PAIRING_REQ/RESP, TRANSFER_OFFER/ACCEPT, DATA_FRAME│  │  │
│  │  │ - CRC-16 Checksum & Session ID Management            │  │  │
│  │  └──────────────────────────┬───────────────────────────┘  │  │
│  │                             │                              │  │
│  │  ┌──────────────────────────▼───────────────────────────┐  │  │
│  │  │ 2-FSK Modulation & Demodulation Engine               │  │  │
│  │  │ - 18,000 Hz (Bit 0) & 19,000 Hz (Bit 1)              │  │  │
│  │  │ - 20 ms Symbol Duration (50 Baud)                    │  │  │
│  │  │ - Raised-Cosine Windowing (2 ms fade)                │  │  │
│  │  │ - Symbol Clock Recovery & Phase-Offset Scanning      │  │  │
│  │  │ - Hamming Distance Tolerant Preamble/Sync Lock       │  │  │
│  │  └──────────────────────────┬───────────────────────────┘  │  │
│  │                             │                              │  │
│  │  ┌──────────────────────────▼───────────────────────────┐  │  │
│  │  │ Audio Hardware I/O (PortAudio / SoundDevice)         │  │  │
│  │  │ - Device Probing, Spectrum Diagnostics, Noise Est.   │  │  │
│  │  │ - Default Sample Rate: 44,100 Hz (48,000 Hz verified)│  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Completed Features (Phase 1 through Phase 3.5)

### A. Audio Foundation (Phase 1)
- **Audio Hardware Enumeration & Probing:** Accurate input/output device querying via `sounddevice` with hardware-level sample rate verification via `check_input_settings` / `check_output_settings` and heuristic fallback.
- **Diagnostics & Spectral Analysis:** FFT spectrum computation, peak frequency detection, noise floor estimation, and SNR calculation for 18 kHz and 19 kHz bands.
- **Audio Input & Output:** Non-blocking playback and recording pipelines using `sounddevice` and `soundfile`.
- **Signal Synthesis:** Sine wave generation with raised-cosine fade-in/fade-out windows to minimize high-frequency splatter.

### B. Protocol Framing & AFSK Modulation (Phase 2)
- **Bitstream Manipulation:** Endian-safe byte-to-bit and bit-to-byte conversions, UTF-8 bitstream serialization.
- **Integrity Validation:** CCITT-FALSE CRC-16 checksum computation and verification.
- **Physical Layer Framing:** 32-bit alternating preamble (`101010...`), 16-bit sync pattern (`1111000011110000`), 16-bit payload length field, payload data, and 16-bit CRC.
- **AFSK Modulation:** 18 kHz (Bit 0) / 19 kHz (Bit 1) continuous tone generation with raised-cosine symbol shaping.

### C. Demodulation, Clock Recovery & Stabilization (Phase 3 & Phase 3.5)
- **FFT Symbol Detector:** Hann-windowed FFT energy estimation comparing 18 kHz vs 19 kHz power with noise-floor rejection.
- **Demodulator State Machine:** Robust state machine (`WAITING → SEARCHING → PREAMBLE_DETECTED → SYNCING → RECEIVING → FRAME_VALIDATION → COMPLETE`).
- **Symbol Clock Recovery:** Candidate phase offset search (`k * spp / 8`) enabling reception of signals regardless of leading silence or arbitrary sample offset.
- **Hamming-Distance Error Tolerance:** Configurable tolerance for preamble (up to 2 flipped bits) and sync word (up to 1 flipped bit), preventing packet drops from ambient acoustic noise.
- **Event Bus System:** Thread-safe publish-subscribe event system with 17 structured event emitters covering transmitter, receiver, and diagnostic lifecycles.

### D. Frontend Presentation & Air-Gap Compliance
- **Offline Font Hardening:** Installed local `@fontsource/inter` and `@fontsource/jetbrains-mono` dependencies; purged all Google Fonts CDN links from `index.html`.
- **Consistent Editorial Design:** Monochromatic dark terminal aesthetic with synchronized route numbering, high-contrast layouts, and brutalist buttons.
- **Clean Builds:** Zero TypeScript errors (`tsc --noEmit`), clean production bundle (`vite build`).

---

## 4. Incomplete Features (To Be Implemented)

| Feature Area | Description | Target Milestone |
|---|---|---|
| **Desktop Shell (Tauri 2)** | Rust-based desktop shell (`src-tauri`), native windowing, permissions, and app lifecycle. | Milestone A |
| **JSON Lines IPC Bridge** | Standard input/output process controller connecting Tauri Rust host to the Python engine without open network ports. | Milestone A |
| **Cryptography Layer** | X25519 ephemeral key exchange, HKDF-SHA256 derivation, AES-256-GCM authenticated payload encryption. | Milestone B |
| **Reed-Solomon ECC** | Frame-level forward error correction (FEC) to correct corrupted symbols before authentication. | Milestone B |
| **Acoustic Device Discovery** | Framed request/response protocol (`DISCOVERY_PING`, `DISCOVERY_RESPONSE`, collision avoidance backoff) for opt-in receivers. | Milestone B |
| **Acoustic Pairing & Transfer** | Explicit `TRANSFER_OFFER`, user accept/decline dialog, short authentication string (SAS) comparison, and acoustic `TRANSFER_ACK`. | Milestone B |
| **Multi-Device Broadcast** | Group session key distribution with individual acoustic acknowledgments. | Milestone B |
| **Offline Storage (SQLite)** | Local SQLite database for settings, device aliases, and transfer history. | Milestone B / C |
| **Frontend Service Wiring** | Connecting React pages to real Tauri IPC commands/events (replacing `setTimeout` mocks). | Milestone C |
| **Cross-Platform Packaging** | PyInstaller standalone binary compilation and Tauri bundler configurations (.dmg/.app, .msi/.exe, .deb/.AppImage). | Milestone C |

---

## 5. Known Bugs & Code Smells

1. **Frontend Services Disconnect:** All 5 services in `src/services/` are currently mock `setTimeout` loops and do not invoke any backend functionality.
2. **Vestigial Frontend Dependencies:** `lucide-react` is installed but unreferenced; `recharts` is installed but unused.
3. **Hardware Sample Rate Standard:** Protocol constants default to 44,100 Hz, whereas the master engineering specification specifies 48,000 Hz as the primary target with 44,100 Hz as fallback. Dynamic sample rate negotiation must be introduced.
4. **Half-Duplex Audio Transition:** Sound cards cannot simultaneously record and play ultrasonic audio cleanly without self-interference. The state machine must enforce explicit half-duplex transmit/receive switching with acoustic guard intervals.

---

## 6. Current Test Results

### Backend Automated Test Suite
- **Command:** `source backend/venv/bin/activate && python -m pytest backend/tests/ -v`
- **Result:** **156 passed in 0.99s** (100% pass rate)
  - `test_bitstream.py`: 8 passed
  - `test_checksum.py`: 12 passed
  - `test_clock_recovery.py`: 5 passed
  - `test_demodulator.py`: 30 passed
  - `test_encoder.py`: 14 passed
  - `test_framing.py`: 15 passed
  - `test_modulation.py`: 17 passed
  - `test_receive_cli.py`: 13 passed
  - `test_diagnostics.py`: 17 passed
  - `test_events.py`: 5 passed
  - `test_signal.py`: 20 passed

### Frontend Typecheck & Build
- **Command:** `npx tsc --noEmit && npm run build`
- **Result:** **100% clean compilation**
  - Bundle size: 301.87 kB JS, 59.90 kB CSS, zero network CDN references.

---

## 7. Next Implementation Tasks (Roadmap)

### Milestone A: Desktop Foundation & IPC Bridge
- [ ] Task A.1: Initialize Tauri 2 desktop shell in `src-tauri/` with Rust configuration and native permissions.
- [ ] Task A.2: Implement Python JSON Lines IPC server (`whisper/engine/bridge.py`) for stdin/stdout communication.
- [ ] Task A.3: Implement Rust sidecar process manager and Tauri command handlers for `get_app_status`, `list_audio_devices`, and `run_calibration`.
- [ ] Task A.4: Create frontend Tauri IPC client adapter replacing mock services.

### Milestone B: Complete Acoustic Protocol & Security
- [ ] Task B.1: Implement Cryptography Layer (`whisper/crypto/`: X25519, HKDF-SHA256, AES-256-GCM, SAS computation).
- [ ] Task B.2: Implement Reed-Solomon Forward Error Correction (`whisper/protocol/ecc.py`).
- [ ] Task B.3: Implement Extended Frame Architecture (`whisper/protocol/frames.py`: Ping, Response, Offer, Accept, Data, Ack).
- [ ] Task B.4: Implement Acoustic Discovery Engine with collision avoidance and randomized backoff.
- [ ] Task B.5: Implement Secure Transfer & Pairing State Machine (Offer → Accept → SAS Verify → Transfer → ACK).
- [ ] Task B.6: Implement Multi-Device Group Key Broadcast Engine.
- [ ] Task B.7: Implement Local SQLite Database for settings, paired aliases, and transfer history.

### Milestone C: Full Frontend Integration, Testing & Packaging
- [ ] Task C.1: Wire React pages (Overview, Discovery, Transmit, Receive, Broadcast, Diagnostics, History, Settings) to real Tauri IPC events.
- [ ] Task C.2: PyInstaller packaging script for Python core sidecar executable.
- [ ] Task C.3: Tauri bundler configuration for cross-platform installers (macOS, Windows, Linux).
- [ ] Task C.4: End-to-end integration and acoustic verification test suite.
