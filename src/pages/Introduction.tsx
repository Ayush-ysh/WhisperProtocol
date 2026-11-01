import { motion } from 'framer-motion';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function Introduction() {
  return (
    <motion.div {...PAGE_TRANSITION} className="w-full">
      {/* PAGE 01 — OPENING */}
      <section className="relative w-full h-screen flex flex-col items-center justify-center pt-20 pb-12 px-6">
        <div className="absolute top-1/4 flex flex-col items-center gap-4 opacity-50">
          <motion.div 
            animate={{ scaleY: [0.2, 1, 0.2] }} 
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            className="w-px h-16 bg-[#E8E8E3]" 
          />
          <span className="text-[9px] font-mono tracking-widest uppercase">ACOUSTIC COMMUNICATION SYSTEM</span>
        </div>

        <div className="text-center mt-12">
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 1, delay: 0.2 }}
            className="text-[12vw] sm:text-[9vw] lg:text-[140px] font-bold tracking-tighter leading-[0.85] text-[#E8E8E3]"
          >
            WHISPER
          </motion.h1>
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 1, delay: 0.3 }}
            className="text-[12vw] sm:text-[9vw] lg:text-[140px] font-bold tracking-tighter leading-[0.85] text-[#888A8F]"
          >
            PROTOCOL
          </motion.h1>
        </div>

        <motion.p 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          transition={{ duration: 1, delay: 0.6 }}
          className="mt-12 text-sm font-mono text-[#E8E8E3]/60 tracking-wider max-w-sm text-center uppercase"
        >
          SECURE DATA TRANSFER WITHOUT A NETWORK.
        </motion.p>

        <div className="absolute bottom-12 left-12 flex flex-col gap-2">
          <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">01 / INTRODUCTION</span>
          <span className="text-[10px] font-mono tracking-widest uppercase text-[#E8E8E3]">18.0 — 20.0 KHZ</span>
        </div>
      </section>

      {/* PAGE 02 — THE PROBLEM */}
      <section className="relative w-full min-h-screen flex flex-col justify-center px-12 lg:px-24 py-24 border-t border-[#E8E8E3]/10">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F] mb-12">01 / THE PROBLEM</span>
        
        <div className="mb-24">
          <h2 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3]">
            AIR-GAPPED<br />
            <span className="text-[#888A8F]">DOESN'T MEAN</span><br />
            RISK-FREE.
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-16 lg:gap-24 mb-32">
          {['USB', 'WI-FI', 'BLUETOOTH'].map((tech, i) => (
            <motion.div 
              key={tech}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ duration: 0.8, delay: i * 0.15 }}
              className="flex flex-col gap-6"
            >
              <div className="h-px w-full bg-[#E8E8E3]/20" />
              <div>
                <h3 className="text-xl font-bold tracking-tight mb-2">{tech}</h3>
                <p className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">
                  {i === 0 ? 'PHYSICAL MEDIA' : i === 1 ? 'RF EXPOSURE' : 'WIRELESS SURFACE'}
                </p>
              </div>
            </motion.div>
          ))}
        </div>

        <p className="text-xl md:text-3xl font-medium tracking-tight text-[#E8E8E3] max-w-4xl">
          Every bridge into an isolated system creates a potential attack surface.
        </p>
      </section>

      {/* PAGE 03 — THE SOLUTION */}
      <section className="relative w-full min-h-screen flex flex-col justify-center px-12 lg:px-24 py-24 border-t border-[#E8E8E3]/10 bg-[#101114]">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F] mb-12">02 / THE SOLUTION</span>
        
        <h2 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-32">
          SEND DATA<br />
          <span className="text-[#888A8F]">THROUGH SOUND.</span>
        </h2>

        {/* Abstract acoustic visualizer */}
        <div className="w-full h-64 border border-[#E8E8E3]/10 flex flex-col items-center justify-center relative overflow-hidden mb-16">
          <motion.div 
            animate={{ x: ['-100%', '100%'] }} 
            transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
            className="absolute inset-0 flex items-center justify-center opacity-20"
          >
            {Array.from({ length: 40 }).map((_, i) => (
              <div key={i} className="w-px h-full bg-[#E8E8E3] mx-4" style={{ opacity: Math.random() * 0.5 + 0.1 }} />
            ))}
          </motion.div>
          
          <div className="relative z-10 flex flex-col items-center gap-4 bg-[#101114] px-12 py-6 border border-[#E8E8E3]/10">
            <span className="text-[10px] font-mono tracking-widest text-[#E8E8E3]">19.000 KHZ</span>
            <span className="text-[9px] font-mono tracking-widest text-[#888A8F]">BINARY → ACOUSTIC → BINARY</span>
          </div>
        </div>

        <p className="text-xl md:text-2xl font-light tracking-tight text-[#E8E8E3]/80 max-w-3xl leading-relaxed">
          WhisperProtocol transforms encrypted data into acoustic symbols that can cross physical isolation without a network connection.
        </p>
      </section>

      {/* PAGE 04 — HOW IT WORKS */}
      <section className="relative w-full min-h-screen flex flex-col justify-center px-12 lg:px-24 py-24 border-t border-[#E8E8E3]/10">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F] mb-12">03 / PROTOCOL</span>
        
        <div className="flex flex-col lg:flex-row gap-24">
          <div className="lg:w-1/3">
            <h2 className="text-6xl md:text-8xl lg:text-9xl font-bold tracking-tighter leading-[0.85] text-[#E8E8E3]">
              FROM<br />
              DATA<br />
              <span className="text-[#888A8F]">TO<br />SOUND.</span>
            </h2>
          </div>

          <div className="lg:w-2/3 flex flex-col gap-0 border-t border-l border-r border-[#E8E8E3]/10">
            {[
              { num: '01', title: 'MESSAGE', desc: 'Raw binary input.' },
              { num: '02', title: 'AES', desc: 'Symmetric 256-bit encryption.' },
              { num: '03', title: 'ECC', desc: 'Reed-Solomon error correction.' },
              { num: '04', title: 'AFSK', desc: 'Audio frequency-shift keying.' },
              { num: '05', title: '18–20 KHZ', desc: 'Near-ultrasonic transmission.' },
              { num: '06', title: 'MICROPHONE', desc: 'Air-gapped receiver capture.' },
              { num: '07', title: 'RECONSTRUCTED DATA', desc: 'Integrity verified payload.' },
            ].map((stage, i) => (
              <motion.div 
                key={stage.num}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.6, delay: i * 0.1 }}
                className="flex flex-col sm:flex-row items-baseline gap-6 p-8 border-b border-[#E8E8E3]/10 hover:bg-[#E8E8E3]/5 transition-colors"
              >
                <span className="text-[10px] font-mono tracking-widest text-[#888A8F] w-8">{stage.num}</span>
                <h3 className="text-2xl lg:text-4xl font-bold tracking-tighter w-48">{stage.title}</h3>
                <p className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase mt-2 sm:mt-0">{stage.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>
    </motion.div>
  );
}
