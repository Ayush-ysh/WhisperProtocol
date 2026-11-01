import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../components/ui/Button';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function Receive() {
  const [state, setState] = useState<'IDLE' | 'LISTENING' | 'ACQUIRED' | 'RECEIVED'>('IDLE');

  const handleListen = () => {
    setState('LISTENING');
    
    setTimeout(() => {
      setState('ACQUIRED');
      
      setTimeout(() => {
        setState('RECEIVED');
      }, 3000);
    }, 4000);
  };

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col items-center justify-center text-center">
      <div className="absolute top-12 left-12">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">03 / RECEIVE</span>
      </div>

      <AnimatePresence mode="wait">
        {state === 'RECEIVED' ? (
          <motion.div 
            key="received"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex flex-col items-center"
          >
            <h1 className="text-6xl md:text-8xl lg:text-9xl font-bold tracking-tighter leading-[0.85] text-[#E8E8E3] mb-12">
              DATA<br />RECEIVED.
            </h1>

            <div className="bg-[#101114] border border-[#E8E8E3]/10 p-8 text-left max-w-2xl w-full mb-12">
              <p className="text-sm font-mono text-[#E8E8E3] leading-relaxed break-words">
                [SECURE PAYLOAD CONTENT DECODED SUCCESSFULLY]
                <br /><br />
                OPERATION BLACKBIRD INITIATED.
                COORDINATES VERIFIED.
                AWAITING FURTHER INSTRUCTIONS.
              </p>
            </div>

            <Button onClick={() => setState('IDLE')}>RESET RECEIVER</Button>
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
              {/* Center point */}
              <div className="w-2 h-2 bg-[#E8E8E3]" />
              
              {/* Concentric circles */}
              {[1, 2, 3, 4].map(i => (
                <div 
                  key={i}
                  className="absolute rounded-full border border-[#E8E8E3]/5"
                  style={{ width: `${i * 25}%`, height: `${i * 25}%` }}
                />
              ))}

              {/* Scanning elements */}
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

              {/* Acquired state */}
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

            <div className="h-16 flex items-center justify-center mb-8">
              <span className="text-[10px] font-mono tracking-widest text-[#E8E8E3] uppercase">
                {state === 'IDLE' ? 'WAITING FOR SIGNAL' : 
                 state === 'LISTENING' ? 'LISTENING...' : 
                 'SIGNAL ACQUIRED'}
              </span>
            </div>

            {state === 'ACQUIRED' ? (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="grid grid-cols-3 gap-8 md:gap-16 text-left"
              >
                {[
                  ['FREQ', '18.972 KHZ'],
                  ['SNR', '30.4 DB'],
                  ['FRAME', 'LOCKED'],
                ].map(([label, val]) => (
                  <div key={label}>
                    <p className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-1">{label}</p>
                    <p className="text-[10px] font-mono tracking-widest text-[#E8E8E3]">{val}</p>
                  </div>
                ))}
              </motion.div>
            ) : (
              <Button onClick={handleListen} disabled={state !== 'IDLE'}>
                ACTIVATE RECEIVER
              </Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
