"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  MessageSquareText,
  Map,
  Activity,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  {
    label: "Dashboard",
    href: "/",
    icon: <LayoutDashboard className="h-5 w-5" />,
  },
  {
    label: "Planner Query",
    href: "/planner-query",
    icon: <MessageSquareText className="h-5 w-5" />,
  },
  {
    label: "Desert Map",
    href: "/desert-map",
    icon: <Map className="h-5 w-5" />,
  },
];

export function NavRail() {
  const pathname = usePathname();
  const [isCollapsed, setIsCollapsed] = React.useState(false);

  // Check if a path is active (exact match or starts with for nested routes)
  const isActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname.startsWith(href);
  };

  return (
    <nav
      className={cn(
        "fixed left-0 top-0 h-full bg-white border-r border-[var(--color-border-default)] shadow-sm z-50 flex flex-col transition-all duration-300",
        isCollapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo / Brand */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-[var(--color-border-subtle)]">
        <AnimatePresence mode="wait">
          {!isCollapsed && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.2 }}
              className="flex items-center gap-2"
            >
              <Activity className="h-6 w-6 text-[var(--color-accent-primary)]" />
              <span className="text-heading-m text-[var(--color-content-primary)]">
                SeaHealth
              </span>
            </motion.div>
          )}
        </AnimatePresence>
        {isCollapsed && (
          <Activity className="h-6 w-6 text-[var(--color-accent-primary)] mx-auto" />
        )}
      </div>

      {/* Navigation Items */}
      <div className="flex-1 py-4 px-2 space-y-1 relative">
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative flex items-center gap-3 h-11 px-3 rounded-[var(--radius-md)] transition-colors",
                active
                  ? "text-[var(--color-accent-primary)]"
                  : "text-[var(--color-content-secondary)] hover:text-[var(--color-content-primary)] hover:bg-zinc-100/80"
              )}
            >
              {active && (
                <motion.div
                  layoutId="activeTab"
                  className="absolute inset-0 bg-[var(--color-accent-primary-subtle)] rounded-[var(--radius-md)] -z-10"
                  transition={{ type: "spring", bounce: 0.2, duration: 0.45 }}
                />
              )}
              {item.icon}
              <AnimatePresence mode="wait">
                {!isCollapsed && (
                  <motion.span
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: "auto" }}
                    exit={{ opacity: 0, width: 0 }}
                    transition={{ duration: 0.2 }}
                    className="text-body whitespace-nowrap overflow-hidden"
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </Link>
          );
        })}
      </div>

      {/* Collapse Toggle */}
      <div className="p-2 border-t border-[var(--color-border-subtle)]">
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="flex items-center justify-center w-full h-10 rounded-[var(--radius-md)] text-[var(--color-content-tertiary)] hover:text-[var(--color-content-primary)] hover:bg-zinc-100/80 transition-colors"
          aria-label={isCollapsed ? "Expand navigation" : "Collapse navigation"}
        >
          {isCollapsed ? (
            <ChevronRight className="h-5 w-5" />
          ) : (
            <>
              <ChevronLeft className="h-5 w-5" />
              <span className="text-caption ml-2">Collapse</span>
            </>
          )}
        </button>
      </div>
    </nav>
  );
}
