import { motion, AnimatePresence } from 'framer-motion';
import { useAppContext } from '../../store/AppContext';
import { useLocation } from 'react-router-dom';

export function FloatingNav() {
  const { menuOpen, toggleMenu } = useAppContext();
  const location = useLocation();

  // Hide nav during the cinematic transmission state (we'll detect this via a hash or state if needed, but for now we just show it).
  
  return (
    <motion.header
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 1, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
      className="fixed top-0 left-0 right-0 z-50 px-6 py-6 flex items-center justify-between mix-blend-difference text-[#E8E8E3]"
    >
      <div className="w-1/3 flex justify-start">
        <span className="text-[10px] font-mono tracking-widest uppercase">
          WP
        </span>
      </div>
      
      <div className="w-1/3 flex justify-center">
        <span className="text-[10px] font-mono tracking-[0.3em] uppercase hidden sm:block">
          WHISPERPROTOCOL
        </span>
      </div>
      
      <div className="w-1/3 flex justify-end">
        <button 
          onClick={toggleMenu}
          className="text-[10px] font-mono tracking-widest uppercase hover:opacity-50 transition-opacity"
        >
          {menuOpen ? 'CLOSE' : 'MENU'}
        </button>
      </div>
    </motion.header>
  );
}
