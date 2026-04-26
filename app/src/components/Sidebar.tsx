import React from 'react';
import { NavLink, useLocation, useSearchParams } from 'react-router-dom';
import { LayoutDashboard, Map as MapIcon, Search, Stethoscope, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { motion } from 'motion/react';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/' },
  { id: 'query', label: 'Planner Query', icon: Search, path: '/planner-query' },
  { id: 'map', label: 'Desert Map', icon: MapIcon, path: '/desert-map' },
];

export function Sidebar() {
  const [expanded, setExpanded] = React.useState(true);
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const getPathWithParams = (path: string) => {
    if (path === '/planner-query' && location.pathname !== '/planner-query') {
      const q = searchParams.get('q');
      if (q) return `${path}?q=${encodeURIComponent(q)}`;
    }
    return path;
  };

  return (
    <div
      className={cn(
        "flex flex-col h-full bg-white border-r border-border-subtle shadow-sm transition-all duration-300 z-50 relative",
        expanded ? "w-64" : "w-16"
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="absolute -right-3 top-6 bg-white border border-border-subtle rounded-full p-1 shadow-sm hover:bg-surface-sunken z-50"
      >
        {expanded ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>
      
      <div className="p-4 flex items-center justify-center border-b border-border-subtle shrink-0">
         <Stethoscope className="w-8 h-8 text-accent-primary" />
         {expanded && <span className="ml-3 text-heading-s text-content-primary">SeaHealth</span>}
      </div>
      
      <nav className="flex-1 px-2 py-4 space-y-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.id}
            to={getPathWithParams(item.path)}
            className={({ isActive }) =>
              cn(
                "relative flex items-center px-3 min-h-[44px] rounded-md transition-colors text-body group",
                isActive ? "text-accent-primary font-medium" : "text-content-secondary hover:bg-surface-sunken hover:text-content-primary"
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.div
                    layoutId="activeTab"
                    className="absolute inset-0 bg-accent-primary-subtle rounded-md -z-10"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.45 }}
                  />
                )}
                <item.icon className="w-5 h-5 shrink-0" />
                {expanded ? (
                  <span className="ml-3 whitespace-nowrap">{item.label}</span>
                ) : (
                  <div className="absolute left-full ml-2 px-2 py-1 bg-surface-sunken border border-border-subtle rounded text-caption whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
                    {item.label}
                  </div>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      {expanded && (
        <div className="m-3 rounded-lg border border-border-subtle bg-surface-sunken p-3">
          <div className="text-caption text-content-secondary uppercase tracking-wider">Demo Status</div>
          <div className="mt-1 text-heading-s text-content-primary">Synthetic gold audits</div>
          <div className="mt-1 text-caption text-content-secondary">Backend detached · traces faked</div>
        </div>
      )}
    </div>
  );
}
