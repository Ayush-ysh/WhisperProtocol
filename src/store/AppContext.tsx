import React, { createContext, useContext, useState, useCallback } from 'react';

interface AppState {
  menuOpen: boolean;
}

interface AppContextValue extends AppState {
  toggleMenu: () => void;
  closeMenu: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);

  const toggleMenu = useCallback(() => setMenuOpen((v) => !v), []);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  return (
    <AppContext.Provider value={{ menuOpen, toggleMenu, closeMenu }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
