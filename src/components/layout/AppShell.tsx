import { Outlet } from 'react-router-dom';
import { FloatingNav } from './FloatingNav';
import { FullScreenMenu } from './FullScreenMenu';

export function AppShell() {
  return (
    <>
      {/* Global Overlays */}
      <div className="tech-grid fixed inset-0 opacity-40 pointer-events-none z-0" />
      <div className="film-grain" />

      <FloatingNav />
      <FullScreenMenu />

      {/* Main Content */}
      <main className="relative z-10 w-full min-h-screen">
        <Outlet />
      </main>
    </>
  );
}
