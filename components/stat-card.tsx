"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "./ui/skeleton";

interface StatCardProps {
  label: string;
  value: string | number | null;
  subValue?: string;
  icon?: React.ReactNode;
  trend?: "up" | "down" | "neutral";
  isLoading?: boolean;
  className?: string;
}

export function StatCard({
  label,
  value,
  subValue,
  icon,
  trend,
  isLoading = false,
  className,
}: StatCardProps) {
  if (isLoading) {
    return (
      <div
        className={cn(
          "bg-[var(--color-surface-raised)] border border-[var(--color-border-subtle)] rounded-[var(--radius-md)] p-4",
          className
        )}
      >
        <Skeleton className="h-4 w-20 mb-2" />
        <Skeleton className="h-8 w-16 mb-1" />
        <Skeleton className="h-3 w-24" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "bg-[var(--color-surface-raised)] border border-[var(--color-border-subtle)] rounded-[var(--radius-md)] p-4",
        className
      )}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-caption text-[var(--color-content-secondary)]">
          {label}
        </span>
        {icon && (
          <span className="text-[var(--color-content-tertiary)]">{icon}</span>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-heading-l text-[var(--color-content-primary)]">
          {value ?? "—"}
        </span>
        {trend && (
          <span
            className={cn(
              "text-caption",
              trend === "up" && "text-[var(--color-semantic-verified)]",
              trend === "down" && "text-[var(--color-semantic-critical)]",
              trend === "neutral" && "text-[var(--color-content-tertiary)]"
            )}
          >
            {trend === "up" ? "↑" : trend === "down" ? "↓" : "→"}
          </span>
        )}
      </div>
      {subValue && (
        <span className="text-mono-s text-[var(--color-content-tertiary)] mt-1 block">
          {subValue}
        </span>
      )}
    </div>
  );
}

interface StatStripProps {
  stats: Array<{
    label: string;
    value: string | number | null;
    subValue?: string;
  }>;
  isLoading?: boolean;
  className?: string;
}

export function StatStrip({ stats, isLoading = false, className }: StatStripProps) {
  return (
    <div
      className={cn(
        "glass-control rounded-[var(--radius-lg)] p-3 flex items-center gap-6",
        className
      )}
    >
      {stats.map((stat, index) => (
        <React.Fragment key={stat.label}>
          {index > 0 && (
            <div className="h-8 w-px bg-[var(--color-border-subtle)]" />
          )}
          <div className="flex flex-col">
            <span className="text-caption text-[var(--color-content-secondary)]">
              {stat.label}
            </span>
            {isLoading ? (
              <Skeleton className="h-5 w-12 mt-1" />
            ) : (
              <div className="flex items-baseline gap-1">
                <span className="text-heading-m text-[var(--color-content-primary)]">
                  {stat.value ?? "—"}
                </span>
                {stat.subValue && (
                  <span className="text-mono-s text-[var(--color-content-tertiary)]">
                    {stat.subValue}
                  </span>
                )}
              </div>
            )}
          </div>
        </React.Fragment>
      ))}
    </div>
  );
}
