import { useState } from 'react';
import { motion } from 'framer-motion';
import { Button } from '../components/ui/Button';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

const RECEIVERS = [
  { id: '01', x: 15, y: 20 },
  { id: '02', x: 85, y: 15 },
  { id: '03', x: 20, y: 80 },
  { id: '04', x: 80, y: 85 },
];

export function Broadcast() {
  const [broadcasting, setBroadcasting] = useState(false);

  const handleBroadcast = () => {
    setBroadcasting(true);
    setTimeout(() => setBroadcasting(false), 5000);
  };

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col items-center">
      <div className="absolute top-12 left-12">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">04 / BROADCAST</span>
      </div>

      <div className="text-center mb-16">
        <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-4">
          ONE SIGNAL.
        </h1>
        <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter leading-none text-[#888A8F]">
          MULTIPLE RECEIVERS.
        </h1>
      </div>

      <div className="relative w-full max-w-4xl h-[50vh] border border-[#E8E8E3]/10 bg-[#101114] mb-12 flex items-center justify-center overflow-hidden">
        {/* Transmitter */}
        <div className="absolute z-20 flex flex-col items-center">
          <div className="w-3 h-3 bg-[#E8E8E3] mb-2" />
          <span className="text-[10px] font-mono tracking-widest text-[#E8E8E3] uppercase">TRANSMITTER</span>
        </div>

        {/* Receivers & Lines */}
        {RECEIVERS.map((rx) => (
          <div key={rx.id} className="absolute inset-0 pointer-events-none">
            {/* The Node */}
            <div 
              className="absolute flex flex-col items-center"
              style={{ left: `${rx.x}%`, top: `${rx.y}%`, transform: 'translate(-50%, -50%)' }}
            >
              <div className="w-1.5 h-1.5 bg-[#888A8F] mb-2" />
              <span className="text-[9px] font-mono tracking-widest text-[#888A8F] uppercase">RX / {rx.id}</span>
            </div>

            {/* Connecting SVG Line */}
            <svg className="absolute inset-0 w-full h-full">
              <line 
                x1="50%" y1="50%" 
                x2={`${rx.x}%`} y2={`${rx.y}%`} 
                stroke="rgba(232, 232, 227, 0.05)" 
                strokeWidth="1" 
              />
              {broadcasting && (
                <motion.line 
                  x1="50%" y1="50%" 
                  x2={`${rx.x}%`} y2={`${rx.y}%`} 
                  stroke="rgba(232, 232, 227, 0.5)" 
                  strokeWidth="1"
                  strokeDasharray="4 8"
                  initial={{ strokeDashoffset: 100 }}
                  animate={{ strokeDashoffset: 0 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                />
              )}
            </svg>
          </div>
        ))}
        
        {/* Generative wave effect */}
        {broadcasting && (
          <motion.div 
            initial={{ scale: 0, opacity: 0.5 }}
            animate={{ scale: 3, opacity: 0 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            className="absolute rounded-full border border-[#E8E8E3]/20 w-32 h-32"
          />
        )}
      </div>

      <Button onClick={handleBroadcast} disabled={broadcasting}>
        {broadcasting ? 'BROADCASTING...' : 'INITIATE BROADCAST'}
      </Button>
    </motion.div>
  );
}
