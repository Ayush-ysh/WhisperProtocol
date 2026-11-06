import { useEffect, useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { FloatingNav } from './FloatingNav';
import { FullScreenMenu } from './FullScreenMenu';
import { setReceiverMode, listenToEngineEvent } from '../../services/tauriBridge';

export function AppShell() {
  const [incomingOffer, setIncomingOffer] = useState<{ sender: string; file: string; size: number } | null>(null);
  const [discoveredAlert, setDiscoveredAlert] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // Automatically engage acoustic discovery receiver mode once on startup
    setReceiverMode(true).catch((e) => console.debug('Auto-engage receiver mode:', e));
  }, []);

  useEffect(() => {
    let unsubOffer: (() => void) | undefined;
    let unsubDiscovered: (() => void) | undefined;

    listenToEngineEvent<{ session_id: number; file_name: string; peer_alias: string; file_size: number }>(
      'transfer_offer_received',
      (data) => {
        if (location.pathname !== '/receive') {
          setIncomingOffer({ sender: data.peer_alias, file: data.file_name, size: data.file_size });
        }
      }
    ).then((unsub) => {
      unsubOffer = unsub;
    });

    listenToEngineEvent<{ alias: string }>(
      'device_discovered',
      (peer) => {
        if (location.pathname !== '/receive') {
          setDiscoveredAlert(peer.alias);
          setTimeout(() => setDiscoveredAlert((curr) => (curr === peer.alias ? null : curr)), 6000);
        }
      }
    ).then((unsub) => {
      unsubDiscovered = unsub;
    });

    return () => {
      unsubOffer?.();
      unsubDiscovered?.();
    };
  }, [location.pathname]);

  return (
    <>
      {/* Global Overlays */}
      <div className="tech-grid fixed inset-0 opacity-40 pointer-events-none z-0" />
      <div className="film-grain" />

      {/* Global Incoming Acoustic Notification Banners */}
      <AnimatePresence>
        {incomingOffer && location.pathname !== '/receive' && (
          <motion.div
            initial={{ opacity: 0, y: -40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -40 }}
            className="fixed top-16 left-0 right-0 z-50 flex justify-center px-6"
          >
            <div className="bg-[#101114] border border-emerald-400/50 p-4 shadow-2xl flex items-center justify-between gap-6 max-w-xl w-full">
              <div className="flex items-center gap-3">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <div>
                  <p className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">
                    INCOMING ACOUSTIC TRANSFER
                  </p>
                  <p className="text-xs font-mono font-bold text-[#E8E8E3]">
                    {incomingOffer.sender} is offering &ldquo;{incomingOffer.file}&rdquo; ({incomingOffer.size} B)
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setIncomingOffer(null);
                  navigate('/receive');
                }}
                className="brutalist-button text-[10px] px-3 py-1.5 bg-emerald-500/20 border-emerald-400 text-emerald-300"
              >
                VIEW & ACCEPT
              </button>
            </div>
          </motion.div>
        )}

        {discoveredAlert && !incomingOffer && location.pathname !== '/receive' && (
          <motion.div
            initial={{ opacity: 0, y: -30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -30 }}
            className="fixed top-16 left-0 right-0 z-40 flex justify-center px-6 pointer-events-none"
          >
            <div className="bg-[#101114]/90 backdrop-blur border border-[#E8E8E3]/20 px-4 py-2 flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
              <span className="text-[10px] font-mono tracking-widest text-[#E8E8E3] uppercase">
                ACOUSTIC PEER IN RANGE: {discoveredAlert}
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <FloatingNav />
      <FullScreenMenu />

      {/* Main Content */}
      <main className="relative z-10 w-full min-h-screen">
        <Outlet />
      </main>
    </>
  );
}
