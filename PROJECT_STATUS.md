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

### E. Desktop Foundation & JSON Lines IPC Bridge (Milestone A)
- **Rust Toolchain:** Installed and verified Rust 1.99.1 and Cargo 1.99.1.
- **Tauri 2 Desktop Host (`src-tauri/`):** Initialized Tauri 2 application shell with Tokio async runtime, child process management, and native macOS permissions. Compiles cleanly with zero errors/warnings.
- **Python JSON Lines Bridge (`whisper/engine/bridge.py`):** Pure stdin/stdout IPC process server. Stdout is reserved exclusively for JSON responses and events; stderr is dedicated to logs. Includes request ID correlation, command timeout handling, and graceful process termination.
- **Frontend IPC Adapter (`src/services/tauriBridge.ts`):** Type-safe client wrapping Tauri commands (`get_app_status`, `list_audio_devices`, `run_calibration`, `start_engine`, `stop_engine`, `shutdown_engine`) with transparent web fallback.
- **Real Hardware Telemetry:** `System.tsx` and `diagnosticsService.ts` wired to live device enumeration and calibration, replacing the previous `setTimeout` simulation.
- **Automated Verification:** Added `backend/tests/test_bridge.py` (7 tests covering JSON parsing, error dispatch, request ID matching, and event forwarding).

### F. Physical Acoustic Transmission & Error Correction (Milestone B)
- **Primary 48 kHz Standard:** Migrated default system sample rate to 48,000 Hz with transparent 44,100 Hz fallback negotiation.
- **Configurable Modulation Profiles:** Defined `ModulationProfile` architecture with primary near-ultrasonic standard (`18.0 / 19.0 kHz`) and secondary audible fallback (`14.0 / 15.0 kHz`) for hardware with limited ultrasonic frequency response.
- **Phase-Continuous FSK (CPFSK):** Implemented continuous-phase frequency generation with raised-cosine outer windowing, eliminating high-frequency spectral phase splatter.
- **Reed-Solomon ECC:** Implemented `whisper/protocol/ecc.py` supporting configurable parity (8, 16, 32 symbols) with uncorrectable frame rejection.
- **Half-Duplex Coordinator:** Implemented `HalfDuplexAudioCoordinator` (`whisper/audio/coordinator.py`) providing mutual exclusion between speaker playback and microphone listening, paired with a 350 ms acoustic reverberation decay guard interval.
- **CLI Upgrades:** Updated `whisper.cli.transmit` and `whisper.cli.receive` with `--profile {ultrasonic,audible}`, `--ecc {0,8,16,32}`, and `--phase-continuous` options.

---

## 4. Pending Milestones

| Milestone | Scope & Deliverables | Status |
|---|---|:---:|
| **Milestone C: Canonical Protocol Framing** | Canonical 8-type frame architecture (`DISCOVERY_PING`, `TRANSFER_OFFER`, `DATA_FRAME`, etc.), protocol version, session ID, sequence numbers. | **NEXT** |
| **Milestone D: Cryptography & Secure Pairing** | Ephemeral X25519 key exchange, HKDF-SHA256 directional session keys, AES-256-GCM authenticated encryption, 6-digit SAS visual confirmation, unique nonce tracking. | Pending |
| **Milestone E: Discovery & Transfer State Machine** | Opt-in discovery with randomized collision avoidance slots (800 ms), explicit offer/accept handshake, SAS verification gating payload transfer. | Pending |
| **Milestone F: Multi-Device Broadcast** | Pairwise group key distribution, individual acknowledgement slots, partial delivery matrix. | Pending |
| **Milestone G: Local Storage** | SQLite local store in OS application data directory for transfer history, aliases, and settings. | Pending |
| **Milestone H: Full UI Integration** | Connect all 8 React pages (Overview, Receive, Transmit, Broadcast, Security, Sessions, Settings) to real backend events. | Pending |
| **Milestone I: Production Packaging** | PyInstaller sidecar binary compilation, Tauri bundler for macOS (.dmg/.app), Windows (.msi/.exe), Linux (.deb/.AppImage). | Pending |

---

## 5. Known Bugs & Code Smells

1. **Frontend Services Disconnect:** Transmission, receiver, and security services still use mock simulations pending Milestones C–E.
2. **Vestigial Frontend Dependencies:** `lucide-react` is installed but unreferenced; `recharts` is installed but unused.

---

## 6. Current Test Results

### Backend Automated Test Suite
- **Command:** `source backend/venv/bin/activate && pytest backend/tests/ -v`
- **Result:** **178 passed in 1.24s** (100% pass rate)
  - `test_audio_b.py`: 6 passed (NEW - coordinator, CPFSK, audible profile)
  - `test_ecc.py`: 9 passed (NEW - Reed-Solomon FEC)
  - `test_bridge.py`: 7 passed
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


### Desktop Shell Compilation (Tauri 2 + Rust)
- **Command:** `cargo check` in `src-tauri`
- **Result:** **100% clean compilation** (0 warnings, 0 errors, dev profile finished in 0.65s).

### Frontend Typecheck & Build
- **Command:** `npx tsc --noEmit && npm run build`
- **Result:** **100% clean compilation**
  - Bundle size: 307.55 kB JS, 60.56 kB CSS, zero network CDN references.

---

## 7. Next Implementation Tasks (Roadmap)

### Milestone A: Desktop Foundation & IPC Bridge
- [x] Task A.1: Initialize Tauri 2 desktop shell in `src-tauri/` with Rust configuration and native permissions.
- [x] Task A.2: Implement Python JSON Lines IPC server (`whisper/engine/bridge.py`) for stdin/stdout communication.
- [x] Task A.3: Implement Rust sidecar process manager and Tauri command handlers for `get_app_status`, `list_audio_devices`, and `run_calibration`.
- [x] Task A.4: Create frontend Tauri IPC client adapter replacing mock services.


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
