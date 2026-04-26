import { NavLink } from 'react-router-dom';
import { Map as MapIcon, Stethoscope } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { motion } from 'motion/react';

const NAV_ITEMS = [
  { id: 'map-workbench', label: 'Map Workbench', icon: MapIcon, path: '/' },
];

export function Sidebar() {
  return (
    <div className="flex h-full w-64 flex-col border-r border-border-subtle bg-white shadow-sm z-50 relative">
      <div className="p-4 flex items-center justify-center border-b border-border-subtle shrink-0">
         <Stethoscope className="w-8 h-8 text-accent-primary" />
         <span className="ml-3 text-heading-s text-content-primary">SeaHealth</span>
      </div>
      
      <nav className="flex-1 px-2 py-4 space-y-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.id}
            to={item.path}
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
                <span className="ml-3 whitespace-nowrap">{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="m-3 rounded-lg border border-border-subtle bg-surface-sunken p-3">
        <div className="text-caption text-content-secondary uppercase tracking-wider">Demo Status</div>
        <div className="mt-1 text-heading-s text-content-primary">Agentic map workbench</div>
        <div className="mt-1 text-caption text-content-secondary">Synthetic audits · visible tool calls</div>
      </div>
    </div>
  );
}
