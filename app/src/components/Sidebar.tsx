import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Map as MapIcon, Search, Stethoscope } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { motion } from 'motion/react';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/' },
  { id: 'query', label: 'Planner Query', icon: Search, path: '/planner-query' },
  { id: 'map', label: 'Desert Map', icon: MapIcon, path: '/desert-map' },
];

export function Sidebar() {
  const [expanded, setExpanded] = React.useState(true);

  return (
    <div
      className={cn(
        "flex flex-col h-full bg-white border-r border-zinc-200 shadow-sm rounded-r-lg transition-all duration-300 z-50",
        expanded ? "w-64" : "w-16"
      )}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      <div className="p-4 flex items-center justify-center border-b border-border-subtle shrink-0">
         <Stethoscope className="w-8 h-8 text-accent-primary" />
         {expanded && <span className="ml-3 text-heading-s text-content-primary">SeaHealth</span>}
      </div>
      
      <nav className="flex-1 px-2 py-4 space-y-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.id}
            to={item.path}
            className={({ isActive }) =>
              cn(
                "relative flex items-center px-3 min-h-[44px] rounded-md transition-colors text-body",
                isActive ? "text-accent-primary font-medium" : "text-content-secondary hover:bg-zinc-100/80 hover:text-content-primary"
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
                {expanded && <span className="ml-3 whitespace-nowrap">{item.label}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      {expanded && (
        <div className="m-3 rounded-lg border border-border-subtle bg-surface-sunken p-3">
          <div className="text-caption text-content-secondary uppercase tracking-wider">Demo Status</div>
          <div className="mt-1 text-heading-s text-content-primary">Mock gold data</div>
          <div className="mt-1 text-caption text-content-secondary">Backend detached · traces faked</div>
        </div>
      )}
    </div>
  );
}
