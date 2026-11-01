import { motion } from 'framer-motion';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function Security() {
  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col justify-center">
      <div className="absolute top-12 left-12">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">05 / SECURITY</span>
      </div>

      <div className="flex flex-col gap-0 border-l border-[#E8E8E3]/10 pl-8 md:pl-16">
        <h1 className="text-6xl md:text-8xl lg:text-9xl font-bold tracking-tighter leading-[0.85] text-[#E8E8E3] mb-16">
          ENCRYPTED<br />
          <span className="text-[#888A8F]">BEFORE</span><br />
          TRANSMISSION.
        </h1>

        <div className="flex flex-col gap-12 max-w-2xl">
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            className="flex flex-col"
          >
            <div className="h-px w-full bg-[#E8E8E3]/10 mb-8" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-2 uppercase">SYMMETRIC ENCRYPTION</span>
            <span className="text-4xl md:text-6xl font-bold tracking-tighter text-[#E8E8E3]">AES-256</span>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
            className="flex flex-col"
          >
            <div className="h-px w-full bg-[#E8E8E3]/10 mb-8" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-2 uppercase">FORWARD ERROR CORRECTION</span>
            <span className="text-4xl md:text-6xl font-bold tracking-tighter text-[#E8E8E3]">REED-SOLOMON ECC</span>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.2 }}
            className="flex flex-col"
          >
            <div className="h-px w-full bg-[#E8E8E3]/10 mb-8" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-2 uppercase">NETWORK EXPOSURE</span>
            <span className="text-4xl md:text-6xl font-bold tracking-tighter text-[#E8E8E3]">AIR-GAPPED</span>
            <div className="flex flex-col gap-1 mt-4">
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">NO IP</span>
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">NO WI-FI</span>
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">NO BLUETOOTH</span>
            </div>
          </motion.div>
        </div>
      </div>

      <div className="absolute bottom-12 right-12 text-right">
        <span className="block text-[10px] font-mono tracking-widest text-[#888A8F] uppercase mb-1">SECURITY STATUS</span>
        <span className="block text-[10px] font-mono tracking-widest text-[#E8E8E3] uppercase">VERIFIED</span>
      </div>
    </motion.div>
  );
}
