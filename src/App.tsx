import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { AppProvider } from './store/AppContext';
import { AppShell } from './components/layout/AppShell';
import { Introduction } from './pages/Introduction';
import { Transmit } from './pages/Transmit';
import { Receive } from './pages/Receive';
import { Broadcast } from './pages/Broadcast';
import { Security } from './pages/Security';
import { System } from './pages/System';

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<AppShell />}>
          <Route index element={<Introduction />} />
          <Route path="transmit" element={<Transmit />} />
          <Route path="receive" element={<Receive />} />
          <Route path="broadcast" element={<Broadcast />} />
          <Route path="security" element={<Security />} />
          <Route path="system" element={<System />} />
        </Route>
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <AnimatedRoutes />
      </AppProvider>
    </BrowserRouter>
  );
}
