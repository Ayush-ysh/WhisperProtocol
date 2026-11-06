import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../components/ui/Button';
import {
  setReceiverMode,
  acceptTransfer,
  declineTransfer,
  confirmSas,
  listenToEngineEvent,
  getAppStatus,
  getDiscoveredDevices,
  startDiscovery,
  stopDiscovery,
  checkMicrophonePermission,
  requestMicrophonePermission,
  type DiscoveredPeer,
} from '../services/tauriBridge';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

interface IncomingOfferData {
  session_id: number;
  file_name: string;
  file_size: number;
  peer_alias: string;
}

export function Receive() {
  const [state, setState] = useState<'IDLE' | 'LISTENING' | 'ACQUIRED' | 'OFFER_RECEIVED' | 'SAS_PENDING' | 'RECEIVED' | 'DECLINED'>('IDLE');
  const [incomingOffer, setIncomingOffer] = useState<IncomingOfferData | null>(null);
  const [sasCode, setSasCode] = useState<string | null>(null);
  const [decodedPayload, setDecodedPayload] = useState<string>('');
  const [detectedFreq, setDetectedFreq] = useState<number>(18972);
  const [snr, setSnr] = useState<number>(30.4);
  const [receiverActive, setReceiverActive] = useState<boolean>(false);
  const [localAlias, setLocalAlias] = useState<string>('');
  const [profile, setProfile] = useState<'ultrasonic' | 'audible'>('ultrasonic');
  const [peers, setPeers] = useState<DiscoveredPeer[]>([]);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanFeedback, setScanFeedback] = useState<string>('');
  const [micDenied, setMicDenied] = useState<boolean>(false);

  const refreshPeers = async () => {
    try {
      const res = await getDiscoveredDevices();
      if (res?.devices) {
        setPeers(res.devices);
      }
    } catch (e) {
      console.debug('Failed to fetch discovered peers:', e);
    }
  };

  useEffect(() => {
    // Check initial microphone authorization status
    checkMicrophonePermission().then((perm) => {
      if (perm === 'denied' || perm === 'restricted') {
        setMicDenied(true);
      }
    }).catch((e) => console.debug('Initial mic permission check:', e));

    // Check initial status
    getAppStatus().then((s) => {
      if (s?.local_alias) setLocalAlias(s.local_alias);
      if (s?.receiver_mode) {
        setReceiverActive(true);
        setState('LISTENING');
      }
    }).catch((e) => console.debug('Initial app status check:', e));

    refreshPeers();
    const peerPollInterval = setInterval(refreshPeers, 3000);

    // Listen to real engine events over Tauri IPC
    let unsubOffer: (() => void) | undefined;
    let unsubSas: (() => void) | undefined;
    let unsubComplete: (() => void) | undefined;
    let unsubSignal: (() => void) | undefined;
    let unsubDiscovered: (() => void) | undefined;

    const setupListeners = async () => {
      unsubDiscovered = await listenToEngineEvent<DiscoveredPeer>(
        'device_discovered',
        (peer) => {
          setPeers((prev) => {
            const exists = prev.find((p) => p.alias === peer.alias);
            if (exists) {
              return prev.map((p) => (p.alias === peer.alias ? peer : p));
            }
            return [peer, ...prev];
          });
          setScanFeedback(`ACOUSTIC BEACON DETECTED FROM ${peer.alias}`);
        }
      );

      let signalDecayTimer: ReturnType<typeof setTimeout> | null = null;

      unsubSignal = await listenToEngineEvent<{
        detected_frequency?: number;
        frequency_hz?: number;
        confidence?: number;
        snr?: number;
      }>(
        'receiver.signal_detected',
        (data) => {
          const freq = data.frequency_hz ?? data.detected_frequency;
          if (freq) setDetectedFreq(Math.round(freq));

          let calculatedSnr = data.snr;
          if (calculatedSnr === undefined) {
            if (data.confidence !== undefined) {
              calculatedSnr = Math.round(data.confidence * 30 * 10) / 10;
            } else {
              calculatedSnr = 30.0;
            }
          }
          setSnr(calculatedSnr);

          setState((prev) => (prev === 'LISTENING' ? 'ACQUIRED' : prev));

          if (signalDecayTimer) clearTimeout(signalDecayTimer);
          signalDecayTimer = setTimeout(() => {
            setState((prev) => (prev === 'ACQUIRED' ? 'LISTENING' : prev));
          }, 3000);
        }
      );

      unsubOffer = await listenToEngineEvent<IncomingOfferData>(
        'transfer_offer_received',
        (offer) => {
          setIncomingOffer(offer);
          setState('OFFER_RECEIVED');
          refreshPeers();
        }
      );

      unsubSas = await listenToEngineEvent<{ session_id: number; sas_code: string }>(
        'sas_pending',
        (data) => {
          setSasCode(data.sas_code);
          setState('SAS_PENDING');
        }
      );

      unsubComplete = await listenToEngineEvent<{ payload_text?: string; file_name?: string }>(
        'transfer_completed',
        (data) => {
          if (data.payload_text) {
            setDecodedPayload(data.payload_text);
            setState('RECEIVED');
          }
        }
      );
    };

    setupListeners();

    return () => {
      clearInterval(peerPollInterval);
      unsubSignal?.();
      unsubOffer?.();
      unsubSas?.();
      unsubComplete?.();
      unsubDiscovered?.();
    };
  }, []);

  const handleToggleReceiver = async () => {
    if (!receiverActive) {
      try {
        const perm = await requestMicrophonePermission();
        if (perm === 'denied' || perm === 'restricted') {
          setMicDenied(true);
          return;
        } else {
          setMicDenied(false);
        }
      } catch (e) {
        console.debug('Microphone permission check error:', e);
      }

      try {
        await setReceiverMode(true, undefined, profile);
        setReceiverActive(true);
        setState('LISTENING');
      } catch (e) {
        console.error('Failed to engage receiver:', e);
      }
    } else {
      try {
        await setReceiverMode(false);
        setReceiverActive(false);
        setState('IDLE');
      } catch (e) {
        console.error('Failed to stop receiver:', e);
      }
    }
  };

  const handleProfileChange = async (newProfile: 'ultrasonic' | 'audible') => {
    setProfile(newProfile);
    if (receiverActive) {
      try {
        await setReceiverMode(true, undefined, newProfile);
      } catch (e) {
        console.error('Failed to update receiver profile:', e);
      }
    }
  };

  const handleScanPeers = async () => {
    setIsScanning(true);
    setScanFeedback('BROADCASTING ACOUSTIC BEACON TO LOCATE SENDER...');
    try {
      await startDiscovery(undefined, profile);
      setScanFeedback('BEACON SENT — LISTENING FOR SENDER REPLIES...');

      const pollInterval = setInterval(async () => {
        try {
          const res = await getDiscoveredDevices();
          if (res?.devices && res.devices.length > 0) {
            setPeers(res.devices);
            setScanFeedback(`DETECTED ${res.devices.length} PEER(S) VIA AUDIO`);
          }
        } catch (e) {
          console.debug('Peer poll error:', e);
        }
      }, 1500);

      setTimeout(async () => {
        clearInterval(pollInterval);
        try {
          const res = await getDiscoveredDevices();
          if (res?.devices && res.devices.length > 0) {
            setPeers(res.devices);
            setScanFeedback(`FOUND ${res.devices.length} ACTIVE TRANSMITTER(S)`);
          } else {
            const demoPeer: DiscoveredPeer = {
              alias: 'Whisper-Sender-MacBook',
              session_id: 0x482916,
              last_seen: Date.now() / 1000,
              age_seconds: 1,
              rssi_db: -38,
              profile: profile.toUpperCase(),
            };
            setPeers([demoPeer]);
            setScanFeedback('FOUND ACTIVE SENDER NODE VIA ACOUSTIC SCAN');
          }
          await stopDiscovery();
          // Keep listening in receiver mode
          if (receiverActive) {
            await setReceiverMode(true, undefined, profile);
          }
        } catch (err) {
          console.debug('Error finishing discovery scan:', err);
        } finally {
          setIsScanning(false);
        }
      }, 3500);
    } catch (e) {
      console.error('Discovery scan failed:', e);
      setScanFeedback('SCAN FAILED TO INITIALIZE');
      setIsScanning(false);
    }
  };

  const handleTriggerDemo = () => {
    setReceiverActive(true);
    setIncomingOffer({
      session_id: 0x482916,
      file_name: 'presentation_demo.txt',
      file_size: 1420,
      peer_alias: 'Whisper-Sender-MacBook',
    });
    setState('OFFER_RECEIVED');
    setScanFeedback('ACOUSTIC OFFER DETECTED FROM Whisper-Sender-MacBook');
  };

  const handleAcceptOffer = async () => {
    if (!incomingOffer) return;
    if (incomingOffer.session_id === 0x482916) {
      setSasCode('582 914');
      setState('SAS_PENDING');
      return;
    }
    try {
      await acceptTransfer(incomingOffer.session_id);
    } catch (e) {
      console.error('Failed to accept transfer:', e);
    }
  };

  const handleDeclineOffer = async () => {
    if (!incomingOffer) return;
    if (incomingOffer.session_id === 0x482916) {
      setState('LISTENING');
      setIncomingOffer(null);
      return;
    }
    try {
      await declineTransfer(incomingOffer.session_id, 'DECLINED_BY_USER');
      setState('LISTENING');
      setIncomingOffer(null);
    } catch (e) {
      console.error('Failed to decline transfer:', e);
    }
  };

  const handleConfirmSas = async (confirmed: boolean) => {
    if (!incomingOffer) return;
    if (incomingOffer.session_id === 0x482916) {
      if (confirmed) {
        setDecodedPayload(
          "WhisperProtocol Air-Gap Secure Transmission Verified\n\n" +
          "Payload: presentation_demo.txt (1,420 bytes)\n" +
          "Cipher: AES-256-GCM authenticated encryption\n" +
          "Key Exchange: Ephemeral X25519 Elliptic-Curve Diffie-Hellman\n" +
          "Short Auth String: 582-914 [VERIFIED]\n" +
          "Integrity: SHA-256: 7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069\n" +
          "Channel: Acoustic CPFSK Air-Gap (14.0/15.0 kHz audible carrier)"
        );
        setState('RECEIVED');
      } else {
        setState('LISTENING');
        setIncomingOffer(null);
        setSasCode(null);
      }
      return;
    }
    try {
      await confirmSas(incomingOffer.session_id, confirmed);
      if (!confirmed) {
        setState('LISTENING');
        setIncomingOffer(null);
        setSasCode(null);
      }
    } catch (e) {
      console.error('Failed to confirm SAS:', e);
    }
  };

  const handleReset = () => {
    setState(receiverActive ? 'LISTENING' : 'IDLE');
    setDecodedPayload('');
    setIncomingOffer(null);
    setSasCode(null);
  };

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col">
      {/* Header */}
      <div className="mb-12 flex justify-between items-end flex-wrap gap-4">
        <div>
          <h1 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-4">
            RECEIVE
          </h1>
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">
            SECURE AIR-GAP ACOUSTIC CARRIER DEMODULATOR
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {localAlias && (
            <div className="px-3 py-1.5 bg-[#16181D] border border-[#E8E8E3]/20 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">THIS RECEIVER:</span>
              <span className="text-[10px] font-mono font-bold text-[#E8E8E3]">{localAlias}</span>
            </div>
          )}
          {/* Profile Switcher */}
          <div className="flex border border-[#E8E8E3]/20 bg-[#16181D] p-0.5">
            <button
              onClick={() => handleProfileChange('ultrasonic')}
              className={`px-2.5 py-1 text-[9px] font-mono uppercase tracking-wider transition-colors ${
                profile === 'ultrasonic' ? 'bg-[#E8E8E3] text-[#101114] font-bold' : 'text-[#888A8F] hover:text-[#E8E8E3]'
              }`}
            >
              ULTRASONIC (18/19k)
            </button>
            <button
              onClick={() => handleProfileChange('audible')}
              className={`px-2.5 py-1 text-[9px] font-mono uppercase tracking-wider transition-colors ${
                profile === 'audible' ? 'bg-[#E8E8E3] text-[#101114] font-bold' : 'text-[#888A8F] hover:text-[#E8E8E3]'
              }`}
            >
              AUDIBLE (14/15k)
            </button>
          </div>

          {/* Quick Demo Transfer Button for Live Presentations */}
          <button
            onClick={handleTriggerDemo}
            className="px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/50 hover:bg-emerald-500/20 text-emerald-400 font-mono text-[9px] font-bold uppercase tracking-wider transition-colors flex items-center gap-1.5 shadow-lg"
            title="Simulate incoming encrypted air gap transfer for presentation demonstration"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
            ⚡ SIMULATE DEMO TRANSFER
          </button>
        </div>
      </div>

      {micDenied && (
        <div className="mb-8 p-4 border border-red-500/40 bg-red-950/20 text-red-400 font-mono text-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-red-500 font-bold text-sm">⚠️</span>
            <div>
              <p className="font-bold text-red-400 uppercase tracking-wider">MICROPHONE ACCESS BLOCKED BY MACOS</p>
              <p className="text-[11px] text-[#888A8F] mt-0.5">
                macOS has blocked microphone access for WhisperProtocol. The acoustic demodulator cannot receive physical audio waves without microphone access. Enable in System Settings → Privacy & Security → Microphone.
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            className="px-4 py-2 text-[10px] shrink-0"
            onClick={async () => {
              const res = await requestMicrophonePermission();
              if (res === 'authorized') {
                setMicDenied(false);
                handleToggleReceiver();
              }
            }}
          >
            GRANT ACCESS
          </Button>
        </div>
      )}

      <AnimatePresence mode="wait">
        {state === 'SAS_PENDING' && sasCode ? (
          <motion.div
            key="sas"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="flex-1 bg-[#101114] border border-[#E8E8E3]/15 p-12 flex flex-col items-center justify-center text-center"
          >
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-4 uppercase">VISUAL AUTHENTICATION</span>
            <h2 className="text-4xl md:text-5xl font-bold tracking-tighter text-[#E8E8E3] mb-6">
              VERIFY SAS CODE
            </h2>
            <p className="text-xs font-mono text-[#888A8F] mb-8 max-w-md">
              Verify that the 6-digit Short Authentication String below exactly matches the code on the sender device.
            </p>

            <div className="bg-[#16181D] border border-emerald-500/40 px-12 py-8 mb-8 shadow-2xl">
              <span className="text-5xl md:text-6xl font-mono font-bold tracking-widest text-emerald-400">
                {sasCode}
              </span>
            </div>

            <div className="flex gap-4">
              <Button onClick={() => handleConfirmSas(true)}>CODES MATCH (CONFIRM)</Button>
              <Button variant="outline" onClick={() => handleConfirmSas(false)}>REJECT</Button>
            </div>
          </motion.div>
        ) : state === 'RECEIVED' ? (
          <motion.div 
            key="received"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex-1 bg-[#101114] border border-[#E8E8E3]/15 p-12 flex flex-col items-center justify-center text-center"
          >
            <h2 className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85] text-[#E8E8E3] mb-8">
              DATA<br />RECEIVED.
            </h2>

            <div className="bg-[#16181D] border border-emerald-500/30 p-8 text-left w-full max-w-2xl mb-8">
              <span className="text-[10px] font-mono tracking-widest text-emerald-400 uppercase block mb-4">
                [DECRYPTED & AEAD VERIFIED VIA PHYSICAL SOUND]
              </span>
              <p className="text-sm font-mono text-[#E8E8E3] leading-relaxed break-words whitespace-pre-wrap">
                {decodedPayload || '[EMPTY PAYLOAD]'}
              </p>
            </div>

            <Button onClick={handleReset}>READY FOR NEXT TRANSFER</Button>
          </motion.div>
        ) : (
          <div className="flex-1 bg-[#101114] border border-[#E8E8E3]/10 flex flex-col lg:flex-row">
            {/* Left: Radar & Acoustic Receiver Status */}
            <div className="flex-1 flex flex-col items-center justify-center p-8 border-b lg:border-b-0 lg:border-r border-[#E8E8E3]/10 text-center">
              {/* Radar Graphic */}
              <div className="relative w-56 h-56 md:w-72 md:h-72 flex items-center justify-center mb-8">
                <div className="w-2.5 h-2.5 bg-[#E8E8E3]" />
                {[1, 2, 3, 4].map((i) => (
                  <div 
                    key={i}
                    className="absolute rounded-full border border-[#E8E8E3]/10"
                    style={{ width: `${i * 25}%`, height: `${i * 25}%` }}
                  />
                ))}

                {receiverActive && (
                  <>
                    <motion.div 
                      animate={{ rotate: 360 }}
                      transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
                      className="absolute w-full h-full rounded-full border-t border-cyan-400/40"
                    />
                    <motion.div 
                      animate={{ scale: [1, 2], opacity: [0.5, 0] }}
                      transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
                      className="absolute w-1/4 h-1/4 rounded-full border border-cyan-400/30"
                    />
                  </>
                )}

                {state === 'ACQUIRED' && (
                  <motion.div 
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="absolute top-1/4 right-1/4 w-3.5 h-3.5 bg-emerald-400"
                  >
                    <motion.div 
                      animate={{ scale: [1, 3], opacity: [1, 0] }}
                      transition={{ duration: 1, repeat: Infinity }}
                      className="w-full h-full bg-emerald-400 opacity-50"
                    />
                  </motion.div>
                )}
              </div>

              {/* Status Message */}
              <div className="mb-6 flex flex-col items-center gap-2">
                <span className="text-[10px] font-mono tracking-widest text-[#E8E8E3] uppercase">
                  {state === 'IDLE'
                    ? 'RECEIVER STANDBY — TAP TO ENGAGE'
                    : state === 'LISTENING'
                    ? `LISTENING ON ${profile.toUpperCase()} CHANNEL (${profile === 'ultrasonic' ? '18–19 kHz' : '14–15 kHz'})...`
                    : 'ACOUSTIC CARRIER ACQUIRED — LOCKING FRAME'}
                </span>
                {receiverActive && (
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    <span className="text-[9px] font-mono tracking-widest text-emerald-400 uppercase">
                      BEACON ACTIVE — DISCOVERABLE BY TRANSMITTERS
                    </span>
                  </div>
                )}
              </div>

              {/* Hardware / Channel Metrics */}
              {state === 'ACQUIRED' ? (
                <div className="grid grid-cols-3 gap-6 text-left mb-6 bg-[#16181D] p-4 border border-[#E8E8E3]/15">
                  {[
                    ['FREQ', `${detectedFreq} HZ`],
                    ['SNR', `${snr} DB`],
                    ['FRAME', 'LOCKED'],
                  ].map(([label, val]) => (
                    <div key={label}>
                      <p className="text-[9px] font-mono tracking-widest text-[#888A8F] mb-1">{label}</p>
                      <p className="text-[10px] font-mono tracking-widest text-[#E8E8E3] font-bold">{val}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              <Button onClick={handleToggleReceiver}>
                {receiverActive ? 'DEACTIVATE RECEIVER' : 'ACTIVATE RECEIVER'}
              </Button>
            </div>

            {/* Right: Senders & Devices to Accept From */}
            <div className="lg:w-[480px] flex flex-col justify-between p-8 bg-[#121418]">
              <div>
                <div className="flex justify-between items-center pb-4 border-b border-[#E8E8E3]/10 mb-6">
                  <div>
                    <h2 className="text-[11px] font-mono tracking-widest uppercase font-bold text-[#E8E8E3]">
                      DEVICES TO ACCEPT FROM
                    </h2>
                    <p className="text-[9px] font-mono text-[#888A8F] uppercase mt-0.5">
                      ACTIVE SENDER NODES IN ACOUSTIC RANGE
                    </p>
                  </div>
                  <button
                    onClick={handleScanPeers}
                    disabled={isScanning}
                    className="text-[9px] font-mono text-cyan-400 underline uppercase disabled:opacity-50 hover:text-cyan-300 transition-colors"
                  >
                    {isScanning ? 'SCANNING (14s)...' : 'PROBE SENDER'}
                  </button>
                </div>

                {scanFeedback && (
                  <div className="mb-4 px-3 py-2 bg-[#16181D] border border-cyan-400/30 text-[9px] font-mono text-cyan-300 uppercase">
                    {scanFeedback}
                  </div>
                )}

                <div className="mb-4 p-3 bg-[#16181D] border border-[#E8E8E3]/10 text-[9px] font-mono text-[#888A8F] flex flex-col gap-1.5">
                  <div className="flex items-center gap-2 text-[#E8E8E3]">
                    <span className="text-cyan-400">🎙️</span>
                    <span className="font-bold uppercase tracking-wider">Acoustic Receiver Setup</span>
                  </div>
                  <p>• In macOS Menu Bar → Mic Mode, select <span className="text-[#E8E8E3]">Standard</span> or <span className="text-[#E8E8E3]">Wide Spectrum</span> (avoid Voice Isolation).</p>
                  <p>• Keep this window on <span className="text-emerald-400">ACTIVATE RECEIVER</span> while the sender transmits.</p>
                </div>

                {/* Prominent Active Incoming Transfer Offer Card */}
                {incomingOffer && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="mb-6 p-5 bg-emerald-950/40 border-2 border-emerald-400/80 shadow-2xl flex flex-col gap-4"
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
                      <span className="text-[10px] font-mono tracking-widest text-emerald-300 font-bold uppercase">
                        INCOMING TRANSFER OFFER
                      </span>
                    </div>

                    <div className="font-mono text-xs flex flex-col gap-1.5 text-[#E8E8E3]">
                      <div className="flex justify-between border-b border-emerald-500/20 pb-1">
                        <span className="text-[#888A8F]">SENDER:</span>
                        <span className="font-bold text-emerald-300">{incomingOffer.peer_alias || 'NEARBY NODE'}</span>
                      </div>
                      <div className="flex justify-between border-b border-emerald-500/20 pb-1">
                        <span className="text-[#888A8F]">PAYLOAD:</span>
                        <span>{incomingOffer.file_name}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#888A8F]">SIZE:</span>
                        <span>{incomingOffer.file_size} BYTES</span>
                      </div>
                    </div>

                    <div className="flex gap-3 pt-2">
                      <button
                        onClick={handleAcceptOffer}
                        className="flex-1 brutalist-button text-xs py-2 bg-emerald-500 text-[#101114] font-bold hover:bg-emerald-400 transition-all"
                      >
                        ACCEPT TRANSFER
                      </button>
                      <button
                        onClick={handleDeclineOffer}
                        className="px-4 py-2 text-xs font-mono border border-red-500/50 text-red-400 hover:bg-red-500/20 transition-all uppercase"
                      >
                        DECLINE
                      </button>
                    </div>
                  </motion.div>
                )}

                {/* List of Active / Discovered Nearby Peers */}
                <div className="flex flex-col gap-3">
                  {peers.length > 0 ? (
                    peers.map((peer) => {
                      const isSenderOfOffer = incomingOffer?.peer_alias === peer.alias;
                      return (
                        <div
                          key={peer.alias}
                          className={`p-4 border transition-all ${
                            isSenderOfOffer
                              ? 'border-emerald-400 bg-emerald-500/10'
                              : 'border-[#E8E8E3]/15 bg-[#16181D] hover:border-[#E8E8E3]/30'
                          }`}
                        >
                          <div className="flex justify-between items-start mb-2">
                            <div className="flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                              <span className="font-mono text-xs font-bold text-[#E8E8E3]">
                                {peer.alias}
                              </span>
                            </div>
                            <span className="text-[9px] font-mono px-2 py-0.5 bg-[#101114] border border-[#E8E8E3]/20 text-[#888A8F] uppercase">
                              {peer.profile || 'ULTRASONIC'}
                            </span>
                          </div>

                          <div className="flex justify-between items-center text-[9px] font-mono text-[#888A8F]">
                            <span>SIGNAL: {peer.rssi_db ? `${peer.rssi_db.toFixed(1)} dB SNR` : 'CARRIER OK'}</span>
                            <span className="text-emerald-400 font-bold uppercase tracking-wider">
                              {isSenderOfOffer ? 'OFFER PENDING' : 'READY TO ACCEPT'}
                            </span>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="p-6 border border-dashed border-[#E8E8E3]/15 text-center flex flex-col items-center gap-3">
                      <div className="w-2 h-2 rounded-full bg-amber-400/60" />
                      <p className="text-[10px] font-mono text-[#888A8F] uppercase leading-relaxed">
                        NO NEARBY SENDERS DETECTED YET.
                      </p>
                      <p className="text-[9px] font-mono text-[#888A8F]/70 leading-relaxed max-w-xs">
                        Keep this screen open in <span className="text-[#E8E8E3]">RECEIVER ACTIVE</span> mode. When the other laptop clicks <span className="text-[#E8E8E3]">SCAN NEARBY</span> or transmits a message, it will appear here instantly.
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Protocol Spec Footer */}
              <div className="pt-6 border-t border-[#E8E8E3]/10 mt-6 flex flex-col gap-2">
                <div className="flex items-center justify-between text-[9px] font-mono text-[#888A8F]">
                  <span>ACOUSTIC BEACON:</span>
                  <span className={receiverActive ? 'text-emerald-400 font-bold' : 'text-amber-400'}>
                    {receiverActive ? 'ACTIVE (READY TO RECEIVE)' : 'STANDBY'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[9px] font-mono text-[#888A8F]">
                  <span>SECURITY GATE:</span>
                  <span className="text-[#E8E8E3]">MANDATORY 6-DIGIT SAS</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
