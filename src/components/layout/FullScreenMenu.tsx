import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppContext } from '../../store/AppContext';

const NAV_ITEMS = [
  { id: '01', label: 'INTRODUCTION', path: '/' },
  { id: '02', label: 'TRANSMIT',     path: '/transmit' },
  { id: '03', label: 'RECEIVE',      path: '/receive' },
  { id: '04', label: 'BROADCAST',    path: '/broadcast' },
  { id: '05', label: 'SECURITY',     path: '/security' },
  { id: '06', label: 'SYSTEM',       path: '/system' },
];

export function FullScreenMenu() {
  const { menuOpen, closeMenu } = useAppContext();
  const navigate = useNavigate();
  const location = useLocation();

  const handleNav = (path: string) => {
    closeMenu();
    setTimeout(() => {
      if (location.pathname !== path) navigate(path);
    }, 400); // Wait for menu out animation
  };

  return (
    <AnimatePresence>
      {menuOpen && (
        <motion.div
          initial={{ opacity: 0, clipPath: 'inset(0 0 100% 0)' }}
          animate={{ opacity: 1, clipPath: 'inset(0 0 0% 0)' }}
          exit={{ opacity: 0, clipPath: 'inset(100% 0 0 0)' }}
          transition={{ duration: 0.8, ease: [0.76, 0, 0.24, 1] }}
          className="fixed inset-0 z-40 bg-[#101114] flex flex-col justify-center px-12 lg:px-24"
        >
          {/* Faint tech grid in menu */}
          <div className="absolute inset-0 tech-grid opacity-30 pointer-events-none" />

          <nav className="relative z-10 flex flex-col gap-4 lg:gap-6">
            {NAV_ITEMS.map((item, i) => {
              const isActive = location.pathname === item.path;
              return (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, y: 40 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -40 }}
                  transition={{ delay: 0.1 + i * 0.05, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                  className="group flex items-baseline gap-6 cursor-pointer"
                  onClick={() => handleNav(item.path)}
                >
                  <span className="text-xs font-mono text-white/30 tracking-widest uppercase mb-1">
                    {item.id}
                  </span>
                  <span className={[
                    'text-4xl lg:text-7xl font-bold tracking-tighter uppercase transition-colors duration-500',
                    isActive ? 'text-[#E8E8E3]' : 'text-[#888A8F] group-hover:text-[#E8E8E3]'
                  ].join(' ')}>
                    {item.label}
                  </span>
                </motion.div>
              );
            })}
          </nav>

          <div className="absolute bottom-12 left-12 lg:left-24 flex gap-12 text-[10px] font-mono text-white/30 tracking-widest uppercase">
            <span>WP—OS V.1.0</span>
            <span>AIR-GAPPED ENVIRONMENT</span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
