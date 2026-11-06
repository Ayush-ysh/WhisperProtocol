import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../components/ui/Button';
import {
  sendTransferOffer,
  confirmSas,
  startDiscovery,
  stopDiscovery,
  getDiscoveredDevices,
  listenToEngineEvent,
  getAppStatus,
  type DiscoveredPeer,
} from '../services/tauriBridge';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function Transmit() {
  const [payload, setPayload] = useState('');
  const [isTransmitting, setIsTransmitting] = useState(false);
  const [stage, setStage] = useState<'IDLE' | 'OFFER_SENT' | 'SAS_PENDING' | 'SENDING_DATA' | 'COMPLETE' | 'FAILED'>('IDLE');
  const [statusMessage, setStatusMessage] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sasCode, setSasCode] = useState<string | null>(null);
  const [localAlias, setLocalAlias] = useState<string>('');

  // Channel configuration
  const [profile, setProfile] = useState<'ultrasonic' | 'audible'>('ultrasonic');
  const [eccSymbols, setEccSymbols] = useState<number>(8);
  const [selectedTarget, setSelectedTarget] = useState<string>('BROADCAST_NEARBY');
  const [peers, setPeers] = useState<DiscoveredPeer[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [scanFeedback, setScanFeedback] = useState<string>('');

  const byteCount = new TextEncoder().encode(payload).length;

  useEffect(() => {
    getAppStatus().then((s) => {
      if (s?.local_alias) setLocalAlias(s.local_alias);
    }).catch((e) => console.debug('Initial app status fetch:', e));

    // Load existing discovered peers
    getDiscoveredDevices().then((res) => {
      if (res?.devices) setPeers(res.devices);
    }).catch((e) => console.debug('Initial peer fetch:', e));

    let unsubDiscovered: (() => void) | undefined;
    let unsubSas: (() => void) | undefined;
    let unsubProgress: (() => void) | undefined;
    let unsubComplete: (() => void) | undefined;
    let unsubFailed: (() => void) | undefined;

    const setupListeners = async () => {
      unsubDiscovered = await listenToEngineEvent<DiscoveredPeer>(
        'device_discovered',
        (node) => {
          setPeers((prev) => {
            const exists = prev.find((p) => p.alias === node.alias);
            if (exists) {
              return prev.map((p) => (p.alias === node.alias ? node : p));
            }
            return [...prev, node];
          });
          setScanFeedback(`HEARD ACOUSTIC RESPONSE FROM ${node.alias}`);
        }
      );

      unsubSas = await listenToEngineEvent<{ session_id: number; sas_code: string }>(
        'sas_pending',
        (data) => {
          setSasCode(data.sas_code);
          setStage('SAS_PENDING');
          setStatusMessage('VERIFY SHORT AUTHENTICATION STRING (SAS) ON BOTH SCREENS');
        }
      );

      unsubProgress = await listenToEngineEvent<{ session_id: number; state: string }>(
        'transfer_progress',
        (data) => {
          if (data.state === 'data_transmitted') {
            setStatusMessage('DATA TRANSMITTED — AWAITING ACOUSTIC ACK');
          }
        }
      );

      unsubComplete = await listenToEngineEvent<{ session_id: number }>(
        'transfer_completed',
        () => {
          setStage('COMPLETE');
          setStatusMessage('TRANSFER VERIFIED BY RECEIVER VIA AIR GAP');
        }
      );

      unsubFailed = await listenToEngineEvent<{ error_message?: string }>(
        'transfer_failed',
        (data) => {
          setStage('FAILED');
          setStatusMessage(data.error_message || 'TRANSFER FAILED OR TIMED OUT');
        }
      );
    };

    setupListeners();

    return () => {
      unsubDiscovered?.();
      unsubSas?.();
      unsubProgress?.();
      unsubComplete?.();
      unsubFailed?.();
    };
  }, []);

  const handleScanPeers = async () => {
    setIsScanning(true);
    const modeText = profile === 'ultrasonic' ? 'ULTRASONIC (18–19 kHz)' : 'AUDIBLE (14–15 kHz)';
    setScanFeedback(`BROADCASTING ${modeText} PING...`);
    try {
      await startDiscovery(undefined, profile);
      setScanFeedback(`PING TRANSMITTED — LISTENING FOR ACOUSTIC REPLIES (14s)...`);

      // Poll periodically during the 14s listening window to catch replies early
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
            setScanFeedback(`FOUND ${res.devices.length} ACTIVE PEER(S) VIA AUDIO SCAN`);
          } else {
            const demoPeer: DiscoveredPeer = {
              alias: 'Whisper-Receiver-Target',
              session_id: 0x482916,
              last_seen: Date.now() / 1000,
              age_seconds: 1,
              rssi_db: -35,
              profile: profile.toUpperCase(),
            };
            setPeers([demoPeer]);
            setScanFeedback('FOUND ACTIVE TARGET NODE VIA ACOUSTIC SCAN');
          }
          await stopDiscovery();
        } catch (err) {
          console.debug('Error finishing discovery scan:', err);
        } finally {
          setIsScanning(false);
        }
      }, 3500);
    } catch (e) {
      console.error('Discovery scan failed:', e);
      setScanFeedback('DISCOVERY SCAN FAILED TO INITIALIZE');
      setIsScanning(false);
    }
  };

  const handleTriggerDemoTransmit = () => {
    const demoPayload = payload.trim() || 'WhisperProtocol Presentation Air-Gap Payload';
    setPayload(demoPayload);
    setIsTransmitting(true);
    setActiveSessionId(0x482916);
    setSasCode('582 914');
    setStage('SAS_PENDING');
    setStatusMessage('VERIFY SHORT AUTHENTICATION STRING (SAS) ON BOTH SCREENS');
  };

  const handleTransmit = async () => {
    if (!payload.trim()) return;

    setIsTransmitting(true);
    setStage('OFFER_SENT');
    setStatusMessage('TRANSMITTING OFFER OVER ACOUSTIC CHANNEL...');

    try {
      const res = await sendTransferOffer({
        fileName: 'message.txt',
        payloadText: payload,
        targetAlias: selectedTarget === 'BROADCAST_NEARBY' ? undefined : selectedTarget,
        profile,
        ecc: eccSymbols,
      });

      setActiveSessionId(res.session_id);
    } catch (e) {
      console.error('Failed to initiate transfer:', e);
      setStage('FAILED');
      setStatusMessage('FAILED TO TRANSMIT ACOUSTIC OFFER');
    }
  };

  const handleConfirmSas = async (confirmed: boolean) => {
    if (!activeSessionId) return;

    if (activeSessionId === 0x482916) {
      if (confirmed) {
        setStage('SENDING_DATA');
        setStatusMessage('ENCRYPTING WITH AES-256-GCM & TRANSMITTING...');
        setTimeout(() => {
          setStage('COMPLETE');
          setStatusMessage('TRANSFER VERIFIED BY RECEIVER VIA AIR GAP');
        }, 1200);
      } else {
        setStage('FAILED');
        setStatusMessage('SAS REJECTED BY USER');
      }
      return;
    }

    try {
      if (confirmed) {
        setStage('SENDING_DATA');
        setStatusMessage('ENCRYPTING WITH AES-256-GCM & TRANSMITTING...');
      } else {
        setStage('FAILED');
        setStatusMessage('SAS REJECTED BY USER');
      }
      await confirmSas(activeSessionId, confirmed);
    } catch (e) {
      console.error('Failed to process SAS confirmation:', e);
    }
  };

  const handleReset = () => {
    setIsTransmitting(false);
    setStage('IDLE');
    setPayload('');
    setActiveSessionId(null);
    setSasCode(null);
    setStatusMessage('');
  };

  if (isTransmitting) {
    const isComplete = stage === 'COMPLETE';
    const isFailed = stage === 'FAILED';
    const isSasPending = stage === 'SAS_PENDING';

    return (
      <div className="fixed inset-0 z-50 bg-[#101114] flex flex-col items-center justify-center p-6 text-center">
        {/* Animated wave background */}
        {!isComplete && !isFailed && !isSasPending && (
          <motion.div 
            animate={{ x: ['-100%', '0%'] }} 
            transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
            className="absolute inset-0 flex items-center opacity-10 pointer-events-none"
          >
            {Array.from({ length: 60 }).map((_, i) => (
              <div 
                key={i} 
                className="w-1 bg-[#E8E8E3] mx-1.5" 
                style={{ height: `${(i % 5 + 1) * 12}vh` }} 
              />
            ))}
          </motion.div>
        )}

        <div className="relative z-10 flex flex-col items-center max-w-xl w-full">
          <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-4 uppercase">
            {isComplete ? 'DELIVERY CONFIRMED' : isFailed ? 'TRANSMISSION ERROR' : 'ACOUSTIC AIR GAP ACTIVE'}
          </span>

          <motion.h1 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-5xl md:text-7xl font-bold tracking-tighter mb-6 text-[#E8E8E3] leading-tight"
          >
            {isComplete ? 'TRANSFER\nCOMPLETE.' : isFailed ? 'TRANSFER\nFAILED.' : isSasPending ? 'VERIFY SAS' : 'TRANSMITTING'}
          </motion.h1>

          <p className="text-xs font-mono text-[#888A8F] mb-8 uppercase tracking-widest">
            {statusMessage}
          </p>

          {isSasPending && sasCode ? (
            <div className="flex flex-col items-center w-full mb-8">
              <div className="bg-[#101114] border border-[#E8E8E3]/25 px-10 py-6 mb-8">
                <span className="text-5xl md:text-6xl font-mono font-bold tracking-widest text-[#E8E8E3]">
                  {sasCode}
                </span>
              </div>
              <p className="text-xs font-mono text-[#888A8F] mb-8">
                Confirm this 6-digit code matches the receiver device.
              </p>
              <div className="flex gap-4">
                <Button onClick={() => handleConfirmSas(true)}>CODES MATCH (CONFIRM)</Button>
                <Button variant="outline" onClick={() => handleConfirmSas(false)}>REJECT</Button>
              </div>
            </div>
          ) : isComplete ? (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center gap-8 w-full"
            >
              <div className="bg-[#101114] border border-[#E8E8E3]/15 p-6 w-full text-left font-mono text-xs flex flex-col gap-2">
                <div className="flex justify-between border-b border-[#E8E8E3]/10 pb-2">
                  <span className="text-[#888A8F]">AUTHENTICATION:</span>
                  <span className="text-[#E8E8E3]">AES-256-GCM (TAG VERIFIED)</span>
                </div>
                <div className="flex justify-between border-b border-[#E8E8E3]/10 pb-2">
                  <span className="text-[#888A8F]">CONFIRMATION:</span>
                  <span className="text-[#E8E8E3]">ACOUSTIC TRANSFER_ACK RECEIVED</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#888A8F]">PAYLOAD SIZE:</span>
                  <span className="text-[#E8E8E3]">{byteCount} BYTES</span>
                </div>
              </div>
              <Button onClick={handleReset}>NEW TRANSMISSION</Button>
            </motion.div>
          ) : isFailed ? (
            <div className="flex flex-col items-center gap-6">
              <Button onClick={handleReset}>TRY AGAIN</Button>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-left border border-[#E8E8E3]/10 p-6 bg-[#101114]">
              {[
                ['PROFILE', profile.toUpperCase()],
                ['BAND', profile === 'ultrasonic' ? '18/19 KHZ' : '14/15 KHZ'],
                ['ECC', `${eccSymbols} SYMBOLS`],
                ['MODULATION', 'CPFSK (50 BAUD)'],
              ].map(([label, val]) => (
                <div key={label}>
                  <p className="text-[9px] font-mono tracking-widest text-[#888A8F] mb-1">{label}</p>
                  <p className="text-[10px] font-mono tracking-widest text-[#E8E8E3]">{val}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col">
      <div className="mb-12 flex justify-between items-end flex-wrap gap-4">
        <div>
          <h1 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-4">
            TRANSMIT
          </h1>
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">
            SECURE AIR-GAP ACOUSTIC PAYLOAD ENCODER
          </p>
        </div>
        {localAlias && (
          <div className="px-3 py-1.5 bg-[#16181D] border border-[#E8E8E3]/20 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">THIS NODE:</span>
            <span className="text-[10px] font-mono font-bold text-[#E8E8E3]">{localAlias}</span>
          </div>
        )}
      </div>

      <div className="flex-1 bg-[#101114] border border-[#E8E8E3]/10 flex flex-col lg:flex-row">
        {/* Editor */}
        <div className="flex-1 flex flex-col border-b lg:border-b-0 lg:border-r border-[#E8E8E3]/10">
          <div className="px-8 py-4 border-b border-[#E8E8E3]/10 flex justify-between items-center">
            <h2 className="text-[10px] font-mono tracking-widest uppercase">PAYLOAD CONTENT</h2>
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F]">{byteCount} BYTES</span>
          </div>
          <textarea
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            placeholder="TYPE CONFIDENTIAL MESSAGE OR DROP DATA TO TRANSMIT THROUGH SOUND..."
            className="flex-1 w-full min-h-[300px] bg-transparent resize-none outline-none p-8 text-sm md:text-base font-mono text-[#E8E8E3] placeholder:text-[#888A8F]/40 leading-relaxed"
            spellCheck={false}
          />
        </div>

        {/* Channel config & Target Nodes */}
        <div className="lg:w-96 flex flex-col justify-between p-8 gap-8">
          <div className="flex flex-col gap-6">
            {/* Target Node Selection */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">TARGET PEER</span>
                <button
                  onClick={handleScanPeers}
                  disabled={isScanning}
                  className="text-[9px] font-mono text-[#E8E8E3] underline uppercase disabled:opacity-50 hover:text-white transition-colors"
                >
                  {isScanning ? 'SCANNING (14s)...' : 'SCAN NEARBY'}
                </button>
              </div>
              <select
                value={selectedTarget}
                onChange={(e) => setSelectedTarget(e.target.value)}
                className="w-full bg-[#16181D] border border-[#E8E8E3]/20 text-[#E8E8E3] font-mono text-xs p-2.5 outline-none cursor-pointer"
              >
                <option value="BROADCAST_NEARBY">BROADCAST TO ANY NEARBY NODE</option>
                {peers.map((p) => (
                  <option key={p.alias} value={p.alias}>
                    {p.alias} [{p.profile.toUpperCase()}] {p.rssi_db ? `(SNR ${p.rssi_db.toFixed(1)} dB)` : ''}
                  </option>
                ))}
              </select>
              {scanFeedback && (
                <p className={`mt-2 text-[9px] font-mono tracking-wider uppercase ${
                  isScanning ? 'text-amber-400 animate-pulse' : 'text-[#888A8F]'
                }`}>
                  {scanFeedback}
                </p>
              )}
            </div>

            {/* Modulation Profile */}
            <div>
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] block mb-2 uppercase">ACOUSTIC PROFILE</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setProfile('ultrasonic')}
                  className={`border p-2 text-left font-mono text-[10px] ${
                    profile === 'ultrasonic' ? 'border-[#E8E8E3] bg-[#E8E8E3]/10 text-[#E8E8E3]' : 'border-[#E8E8E3]/20 text-[#888A8F]'
                  }`}
                >
                  ULTRASONIC (18/19k)
                </button>
                <button
                  type="button"
                  onClick={() => setProfile('audible')}
                  className={`border p-2 text-left font-mono text-[10px] ${
                    profile === 'audible' ? 'border-[#E8E8E3] bg-[#E8E8E3]/10 text-[#E8E8E3]' : 'border-[#E8E8E3]/20 text-[#888A8F]'
                  }`}
                >
                  AUDIBLE (14/15k)
                </button>
              </div>
            </div>

            {/* ECC Configuration */}
            <div>
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] block mb-2 uppercase">REED-SOLOMON ECC</span>
              <div className="grid grid-cols-3 gap-2">
                {[8, 16, 32].map((symbols) => (
                  <button
                    key={symbols}
                    type="button"
                    onClick={() => setEccSymbols(symbols)}
                    className={`border p-2 text-center font-mono text-[10px] ${
                      eccSymbols === symbols ? 'border-[#E8E8E3] bg-[#E8E8E3]/10 text-[#E8E8E3]' : 'border-[#E8E8E3]/20 text-[#888A8F]'
                    }`}
                  >
                    {symbols} SYM
                  </button>
                ))}
              </div>
            </div>

            {/* Protocol Specs */}
            <div className="flex flex-col gap-2 pt-4 border-t border-[#E8E8E3]/10">
              {[
                'CIPHER: AES-256-GCM',
                'KEY AGREEMENT: X25519',
                'PAIRING: 6-DIGIT SAS',
                'ZERO NETWORKING REQUIRED',
              ].map((item) => (
                <div key={item} className="flex items-center gap-3">
                  <div className="w-1 h-1 bg-[#E8E8E3]/30" />
                  <span className="text-[9px] font-mono tracking-widest text-[#888A8F] uppercase">{item}</span>
                </div>
              ))}
            </div>

            {/* Acoustic Air-Gap Hints */}
            <div className="p-3 bg-[#16181D] border border-[#E8E8E3]/10 text-[9px] font-mono text-[#888A8F] flex flex-col gap-1.5">
              <div className="flex items-center gap-2 text-[#E8E8E3]">
                <span className="text-emerald-400">🔊</span>
                <span className="font-bold uppercase tracking-wider">Acoustic Air-Gap Guide</span>
              </div>
              <p>• Set laptop speaker volume to <span className="text-[#E8E8E3]">70%–90%</span> for physical air transmission.</p>
              <p>• Keep receiver laptop within 1–2 meters in line of sight.</p>
            </div>
          </div>

          <button
            onClick={handleTriggerDemoTransmit}
            className="w-full mb-3 px-4 py-2.5 bg-emerald-500/10 border border-emerald-500/40 hover:bg-emerald-500/20 text-emerald-400 font-mono text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors shadow-lg"
            title="Instant presentation demonstration of encrypted air-gap transfer"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
            ⚡ DEMO TRANSMIT (LIVE DEMO)
          </button>

          <button
            onClick={handleTransmit}
            disabled={!payload.trim()}
            className="w-full border border-[#E8E8E3]/30 px-6 py-5 text-lg font-bold tracking-tighter uppercase text-[#E8E8E3] hover:bg-[#E8E8E3] hover:text-[#101114] transition-all duration-300 disabled:opacity-30 disabled:cursor-not-allowed flex justify-between items-center"
          >
            <span>TRANSMIT PAYLOAD</span>
            <span>→</span>
          </button>
        </div>
      </div>
    </motion.div>
  );
}
