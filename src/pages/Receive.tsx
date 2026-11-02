import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../components/ui/Button';
import {
  setReceiverMode,
  acceptTransfer,
  declineTransfer,
  confirmSas,
  listenToEngineEvent,
  type AppStatus,
  getAppStatus,
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

  useEffect(() => {
    // Check initial status
    getAppStatus().then((s) => {
      if (s.receiver_mode) {
        setReceiverActive(true);
        setState('LISTENING');
      }
    }).catch((e) => console.debug('Initial app status check:', e));

    // Listen to real engine events over Tauri IPC
    let unsubOffer: (() => void) | undefined;
    let unsubSas: (() => void) | undefined;
    let unsubComplete: (() => void) | undefined;
    let unsubSignal: (() => void) | undefined;

    const setupListeners = async () => {
      unsubSignal = await listenToEngineEvent<{ detected_frequency?: number; snr?: number }>(
        'receiver.signal_detected',
        (data) => {
          if (data.detected_frequency) setDetectedFreq(Math.round(data.detected_frequency));
          if (data.snr) setSnr(Math.round(data.snr * 10) / 10);
          setState((prev) => (prev === 'LISTENING' ? 'ACQUIRED' : prev));
        }
      );

      unsubOffer = await listenToEngineEvent<IncomingOfferData>(
        'transfer_offer_received',
        (offer) => {
          setIncomingOffer(offer);
          setState('OFFER_RECEIVED');
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
      unsubSignal?.();
      unsubOffer?.();
      unsubSas?.();
      unsubComplete?.();
    };
  }, []);

  const handleToggleReceiver = async () => {
    if (!receiverActive) {
      try {
        await setReceiverMode(true);
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

  const handleAcceptOffer = async () => {
    if (!incomingOffer) return;
    try {
      await acceptTransfer(incomingOffer.session_id);
    } catch (e) {
      console.error('Failed to accept transfer:', e);
    }
  };

  const handleDeclineOffer = async () => {
    if (!incomingOffer) return;
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
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col items-center justify-center text-center">
      <div className="absolute top-12 left-12">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">03 / RECEIVE</span>
      </div>

      <AnimatePresence mode="wait">
        {state === 'OFFER_RECEIVED' && incomingOffer ? (
          <motion.div
            key="offer"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="flex flex-col items-center max-w-xl w-full"
          >
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-4 uppercase">INCOMING ACOUSTIC OFFER</span>
            <h1 className="text-4xl md:text-6xl font-bold tracking-tighter text-[#E8E8E3] mb-8">
              ACCEPT<br />TRANSFER?
            </h1>

            <div className="bg-[#101114] border border-[#E8E8E3]/15 p-6 w-full text-left mb-8 font-mono text-xs text-[#E8E8E3] flex flex-col gap-3">
              <div className="flex justify-between border-b border-[#E8E8E3]/10 pb-2">
                <span className="text-[#888A8F]">SENDER:</span>
                <span>{incomingOffer.peer_alias || 'NEARBY NODE'}</span>
              </div>
              <div className="flex justify-between border-b border-[#E8E8E3]/10 pb-2">
                <span className="text-[#888A8F]">PAYLOAD:</span>
                <span>{incomingOffer.file_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#888A8F]">SIZE:</span>
                <span>{incomingOffer.file_size} BYTES</span>
              </div>
            </div>

            <div className="flex gap-4">
              <Button onClick={handleAcceptOffer}>ACCEPT TRANSFER</Button>
              <Button variant="outline" onClick={handleDeclineOffer}>DECLINE</Button>
            </div>
          </motion.div>
        ) : state === 'SAS_PENDING' && sasCode ? (
          <motion.div
            key="sas"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="flex flex-col items-center max-w-xl w-full"
          >
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-4 uppercase">VISUAL AUTHENTICATION</span>
            <h1 className="text-4xl md:text-5xl font-bold tracking-tighter text-[#E8E8E3] mb-6">
              VERIFY SAS CODE
            </h1>
            <p className="text-xs font-mono text-[#888A8F] mb-8 max-w-md">
              Verify that the 6-digit Short Authentication String below exactly matches the code on the sender device.
            </p>

            <div className="bg-[#101114] border border-[#E8E8E3]/20 px-12 py-8 mb-8">
              <span className="text-5xl md:text-6xl font-mono font-bold tracking-widest text-[#E8E8E3]">
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
            className="flex flex-col items-center max-w-2xl w-full"
          >
            <h1 className="text-6xl md:text-8xl lg:text-9xl font-bold tracking-tighter leading-[0.85] text-[#E8E8E3] mb-8">
              DATA<br />RECEIVED.
            </h1>

            <div className="bg-[#101114] border border-[#E8E8E3]/15 p-8 text-left w-full mb-8">
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase block mb-4">
                [DECRYPTED & AEAD VERIFIED VIA AIR GAP]
              </span>
              <p className="text-sm font-mono text-[#E8E8E3] leading-relaxed break-words whitespace-pre-wrap">
                {decodedPayload || '[EMPTY PAYLOAD]'}
              </p>
            </div>

            <Button onClick={handleReset}>READY FOR NEXT TRANSFER</Button>
          </motion.div>
        ) : (
          <motion.div 
            key="listening"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center w-full max-w-4xl"
          >
            <h1 className="text-6xl md:text-8xl lg:text-9xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-16">
              LISTEN.
            </h1>

            {/* Abstract Radar / Spectrum */}
            <div className="relative w-64 h-64 md:w-96 md:h-96 flex items-center justify-center mb-16">
              <div className="w-2 h-2 bg-[#E8E8E3]" />
              {[1, 2, 3, 4].map((i) => (
                <div 
                  key={i}
                  className="absolute rounded-full border border-[#E8E8E3]/5"
                  style={{ width: `${i * 25}%`, height: `${i * 25}%` }}
                />
              ))}

              {state !== 'IDLE' && (
                <>
                  <motion.div 
                    animate={{ rotate: 360 }}
                    transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
                    className="absolute w-full h-full rounded-full border-t border-[#E8E8E3]/30"
                  />
                  <motion.div 
                    animate={{ scale: [1, 2], opacity: [0.5, 0] }}
                    transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
                    className="absolute w-1/4 h-1/4 rounded-full border border-[#E8E8E3]/20"
                  />
                </>
              )}

              {state === 'ACQUIRED' && (
                <motion.div 
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute top-1/4 right-1/4 w-3 h-3 bg-[#E8E8E3]"
                >
                  <motion.div 
                    animate={{ scale: [1, 3], opacity: [1, 0] }}
                    transition={{ duration: 1, repeat: Infinity }}
                    className="w-full h-full bg-[#E8E8E3] opacity-50"
                  />
                </motion.div>
              )}
            </div>

            <div className="flex flex-col items-center justify-center gap-2 mb-8 min-h-[4rem]">
              <span className="text-[10px] font-mono tracking-widest text-[#E8E8E3] uppercase">
                {state === 'IDLE'
                  ? 'RECEIVER STANDBY — TAP TO ENGAGE'
                  : state === 'LISTENING'
                  ? 'LISTENING ON ULTRASONIC CHANNEL (18–19 KHZ)...'
                  : 'ACOUSTIC CARRIER ACQUIRED — LOCKING FRAME'}
              </span>
              {receiverActive && (
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                  <span className="text-[9px] font-mono tracking-widest text-emerald-400 uppercase">
                    BEACON ACTIVE — DISCOVERABLE BY NEARBY PEERS
                  </span>
                </div>
              )}
            </div>

            {state === 'ACQUIRED' ? (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="grid grid-cols-3 gap-8 md:gap-16 text-left"
              >
                {[
                  ['FREQ', `${detectedFreq} HZ`],
                  ['SNR', `${snr} DB`],
                  ['FRAME', 'LOCKED'],
                ].map(([label, val]) => (
                  <div key={label}>
                    <p className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-1">{label}</p>
                    <p className="text-[10px] font-mono tracking-widest text-[#E8E8E3]">{val}</p>
                  </div>
                ))}
              </motion.div>
            ) : (
              <Button onClick={handleToggleReceiver}>
                {receiverActive ? 'DEACTIVATE RECEIVER' : 'ACTIVATE RECEIVER'}
              </Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
