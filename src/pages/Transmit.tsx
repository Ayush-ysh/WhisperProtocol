import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../components/ui/Button';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function Transmit() {
  const [payload, setPayload] = useState('');
  const [isTransmitting, setIsTransmitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('IDLE');

  const byteCount = new TextEncoder().encode(payload).length;

  const handleTransmit = () => {
    if (!payload.trim()) return;
    setIsTransmitting(true);
    setProgress(0);
    setStage('ENCRYPTING');

    // Mock transmission sequence
    const sequence = [
      { p: 15, s: 'ENCRYPTING' },
      { p: 35, s: 'ECC ENCODING' },
      { p: 50, s: 'AFSK MODULATION' },
      { p: 100, s: 'TRANSMITTING' },
    ];

    let t = 0;
    sequence.forEach((step, i) => {
      t += 800 + Math.random() * 800;
      setTimeout(() => {
        setProgress(step.p);
        setStage(step.s);
      }, t);
    });

    setTimeout(() => {
      setStage('COMPLETE');
    }, t + 2000);
  };

  const handleReset = () => {
    setIsTransmitting(false);
    setProgress(0);
    setStage('IDLE');
    setPayload('');
  };

  if (isTransmitting) {
    const isComplete = stage === 'COMPLETE';

    return (
      <div className="fixed inset-0 z-50 bg-[#101114] flex flex-col items-center justify-center overflow-hidden">
        {/* Animated wave background */}
        {!isComplete && (
          <motion.div 
            animate={{ x: ['-100%', '0%'] }} 
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            className="absolute inset-0 flex items-center opacity-10 pointer-events-none"
          >
            {Array.from({ length: 100 }).map((_, i) => (
              <div 
                key={i} 
                className="w-1 bg-[#E8E8E3] mx-1" 
                style={{ height: `${Math.random() * 40 + 10}vh` }} 
              />
            ))}
          </motion.div>
        )}

        <div className="relative z-10 flex flex-col items-center text-center">
          <motion.h1 
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-6xl md:text-8xl lg:text-9xl font-bold tracking-tighter mb-8 text-[#E8E8E3]"
          >
            {isComplete ? 'TRANSMISSION\nCOMPLETE.' : 'TRANSMITTING'}
          </motion.h1>

          {!isComplete ? (
            <>
              <div className="text-[120px] font-mono font-bold tracking-tighter text-[#E8E8E3] leading-none mb-12">
                {progress}%
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-16 text-left">
                {[
                  ['FREQ', '19002 HZ'],
                  ['SNR', '31.6 DB'],
                  ['ECC', 'OK'],
                  ['AES', 'OK'],
                ].map(([label, val]) => (
                  <div key={label}>
                    <p className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-1">{label}</p>
                    <p className="text-[10px] font-mono tracking-widest text-[#E8E8E3]">{val}</p>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center gap-12"
            >
              <div className="flex flex-col items-center gap-2">
                <p className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">PAYLOAD INTEGRITY VERIFIED</p>
                <p className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">CHANNEL CLOSED</p>
              </div>
              <Button onClick={handleReset}>NEW TRANSMISSION</Button>
            </motion.div>
          )}
        </div>
      </div>
    );
  }

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col">
      <div className="mb-16">
        <h1 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-4">
          TRANSMIT
        </h1>
        <p className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">
          CREATE A SECURE ACOUSTIC PAYLOAD
        </p>
      </div>

      <div className="flex-1 bg-[#101114] border border-[#E8E8E3]/10 flex flex-col lg:flex-row">
        {/* Editor */}
        <div className="flex-1 flex flex-col border-b lg:border-b-0 lg:border-r border-[#E8E8E3]/10">
          <div className="px-8 py-6 border-b border-[#E8E8E3]/10 flex justify-between items-center">
            <h2 className="text-[10px] font-mono tracking-widest uppercase">PAYLOAD</h2>
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F]">{byteCount} BYTES</span>
          </div>
          <textarea
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            placeholder="TYPE YOUR MESSAGE..."
            className="flex-1 w-full bg-transparent resize-none outline-none p-8 text-sm md:text-base font-mono text-[#E8E8E3] placeholder:text-[#888A8F]/40 leading-relaxed"
            spellCheck={false}
          />
        </div>

        {/* Channel config */}
        <div className="lg:w-80 flex flex-col">
          <div className="px-8 py-6 border-b border-[#E8E8E3]/10">
            <h2 className="text-[10px] font-mono tracking-widest uppercase">CHANNEL</h2>
          </div>
          <div className="flex-1 flex flex-col justify-between p-8">
            <div className="flex flex-col gap-6">
              {[
                '19.000 KHZ',
                'AFSK',
                '20 MS SYMBOL',
                'AES-256',
                'REED-SOLOMON',
              ].map((item) => (
                <div key={item} className="flex items-center gap-4">
                  <div className="w-1 h-1 bg-[#E8E8E3]/20" />
                  <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">{item}</span>
                </div>
              ))}
            </div>

            <button
              onClick={handleTransmit}
              disabled={!payload.trim()}
              className="mt-12 w-full border border-[#E8E8E3]/20 px-6 py-6 text-xl font-bold tracking-tighter uppercase text-[#E8E8E3] hover:bg-[#E8E8E3] hover:text-[#101114] transition-all duration-300 disabled:opacity-30 disabled:cursor-not-allowed text-left flex justify-between items-center"
            >
              <span>TRANSMIT</span>
              <span>→</span>
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
