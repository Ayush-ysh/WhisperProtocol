import { useState } from 'react';
import { motion } from 'framer-motion';
import { Button } from '../components/ui/Button';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function System() {
  const [testing, setTesting] = useState(false);
  const [results, setResults] = useState<Record<string, string>>({});

  const handleTest = () => {
    setTesting(true);
    setResults({});
    
    const items = [
      'AUDIO INPUT', 'AUDIO OUTPUT', 'SAMPLE RATE', 
      'CHANNEL', 'CENTER FREQUENCY', 'MODULATION', 
      'ERROR CORRECTION', 'SECURITY', 'NETWORK'
    ];
    
    let t = 0;
    items.forEach((item, i) => {
      t += 300 + Math.random() * 200;
      setTimeout(() => {
        setResults(prev => ({ ...prev, [item]: 'PASS' }));
      }, t);
    });

    setTimeout(() => {
      setTesting(false);
    }, t + 200);
  };

  const DIAGNOSTICS = [
    { label: 'AUDIO INPUT',      val: 'READY' },
    { label: 'AUDIO OUTPUT',     val: 'READY' },
    { label: 'SAMPLE RATE',      val: '44.1 KHZ' },
    { label: 'CHANNEL',          val: '18–20 KHZ' },
    { label: 'CENTER FREQUENCY', val: '19.0 KHZ' },
    { label: 'MODULATION',       val: 'AFSK' },
    { label: 'ERROR CORRECTION', val: 'REED-SOLOMON' },
    { label: 'SECURITY',         val: 'AES-256' },
    { label: 'NETWORK',          val: 'ISOLATED' },
  ];

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col items-center justify-center">
      <div className="absolute top-12 left-12">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">06 / SYSTEM</span>
      </div>

      <div className="w-full max-w-3xl flex flex-col items-center">
        <h1 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-12">
          THE CHANNEL.
        </h1>

        <div className="w-full bg-[#101114] border border-[#E8E8E3]/10 p-8 md:p-12 mb-12">
          <div className="flex flex-col gap-4">
            {DIAGNOSTICS.map((item) => (
              <div key={item.label} className="flex justify-between items-center border-b border-[#E8E8E3]/5 pb-4">
                <span className="text-xs md:text-sm font-mono tracking-widest text-[#888A8F]">{item.label}</span>
                <span className="text-xs md:text-sm font-mono tracking-widest text-[#E8E8E3]">
                  {results[item.label] || item.val}
                </span>
              </div>
            ))}
          </div>
        </div>

        <Button onClick={handleTest} disabled={testing}>
          {testing ? 'RUNNING DIAGNOSTICS...' : 'CHANNEL TEST'}
        </Button>
      </div>
    </motion.div>
  );
}
