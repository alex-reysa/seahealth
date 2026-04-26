import { Outlet } from 'react-router-dom';

export function Layout() {
  return (
    <div className="h-screen w-screen overflow-hidden bg-surface-canvas">
      <main className="relative h-full w-full overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
