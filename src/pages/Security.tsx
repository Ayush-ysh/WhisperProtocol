import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { getSecurityStatus, getSecurityEvents } from '../services/securityService';
import type { SecurityStatus, SecurityEvent } from '../types';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function Security() {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [events, setEvents] = useState<SecurityEvent[]>([]);

  useEffect(() => {
    getSecurityStatus().then(setStatus).catch(console.error);
    getSecurityEvents().then(setEvents).catch(console.error);
  }, []);

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

        <div className="flex flex-col gap-10 max-w-3xl">
          {/* Key Agreement & Authenticated Encryption */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            className="flex flex-col"
          >
            <div className="h-px w-full bg-[#E8E8E3]/10 mb-6" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-2 uppercase">AUTHENTICATED ENCRYPTION & KEY AGREEMENT</span>
            <span className="text-3xl md:text-5xl font-bold tracking-tighter text-[#E8E8E3] mb-2">AES-256-GCM + X25519</span>
            <p className="text-xs font-mono text-[#888A8F] leading-relaxed">
              Ephemeral Diffie-Hellman key exchange via X25519. Directional session keys (Sender → Receiver and Receiver → Sender) derived with HKDF-SHA256. 96-bit unique nonces with anti-replay state enforcement.
            </p>
          </motion.div>

          {/* Visual SAS Pairing */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
            className="flex flex-col"
          >
            <div className="h-px w-full bg-[#E8E8E3]/10 mb-6" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-2 uppercase">VISUAL OUT-OF-BAND AUTHENTICATION</span>
            <span className="text-3xl md:text-5xl font-bold tracking-tighter text-[#E8E8E3] mb-2">6-DIGIT SAS (SHORT AUTH STRING)</span>
            <p className="text-xs font-mono text-[#888A8F] leading-relaxed">
              Cryptographically bound to transcript public keys. Mandatory explicit visual confirmation on both devices gates sensitive payload transmission, preventing MITM and acoustic injection attacks.
            </p>
          </motion.div>

          {/* Forward Error Correction */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.2 }}
            className="flex flex-col"
          >
            <div className="h-px w-full bg-[#E8E8E3]/10 mb-6" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-2 uppercase">FORWARD ERROR CORRECTION</span>
            <span className="text-3xl md:text-5xl font-bold tracking-tighter text-[#E8E8E3] mb-2">REED-SOLOMON ECC</span>
            <p className="text-xs font-mono text-[#888A8F] leading-relaxed">
              Configurable 8, 16, or 32 parity symbol protection over GF(2^8). Compensates for physical acoustic reflections, room echoes, and ambient noise spikes.
            </p>
          </motion.div>

          {/* Air Gap Guarantee */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3 }}
            className="flex flex-col"
          >
            <div className="h-px w-full bg-[#E8E8E3]/10 mb-6" />
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] mb-2 uppercase">NETWORK & HARDWARE EXPOSURE</span>
            <span className="text-3xl md:text-5xl font-bold tracking-tighter text-[#E8E8E3] mb-2">AIR-GAPPED (0 NETWORKING SOCKETS)</span>
            <div className="flex flex-wrap gap-4 mt-3">
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase bg-[#16181D] px-3 py-1.5 border border-[#E8E8E3]/10">NO TCP/UDP</span>
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase bg-[#16181D] px-3 py-1.5 border border-[#E8E8E3]/10">NO WI-FI</span>
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase bg-[#16181D] px-3 py-1.5 border border-[#E8E8E3]/10">NO BLUETOOTH</span>
              <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase bg-[#16181D] px-3 py-1.5 border border-[#E8E8E3]/10">NO CLOUD TELEMETRY</span>
            </div>
          </motion.div>
        </div>
      </div>

      <div className="mt-16 text-left border border-[#E8E8E3]/10 bg-[#101114] p-6 max-w-3xl ml-8 md:ml-16">
        <span className="block text-[10px] font-mono tracking-widest text-[#888A8F] uppercase mb-4">LIVE SECURITY EVENT AUDIT LOG</span>
        <div className="flex flex-col gap-2 font-mono text-[10px]">
          {events.slice(0, 5).map((ev) => (
            <div key={ev.id} className="flex justify-between border-b border-[#E8E8E3]/5 pb-1.5">
              <span className="text-[#888A8F]">{ev.event}</span>
              <span className="text-[#4ADE80]">VERIFIED</span>
            </div>
          ))}
        </div>
      </div>

      <div className="absolute bottom-12 right-12 text-right">
        <span className="block text-[10px] font-mono tracking-widest text-[#888A8F] uppercase mb-1">SECURITY STATUS</span>
        <span className="block text-[10px] font-mono tracking-widest text-[#4ADE80] uppercase">100% AIR-GAPPED & AUTHENTICATED</span>
      </div>
    </motion.div>
  );
}
