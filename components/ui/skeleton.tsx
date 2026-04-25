"use client";

import { cn } from "@/lib/utils";

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "skeleton rounded-[var(--radius-md)] bg-[var(--color-surface-sunken)]",
        className
      )}
      {...props}
    />
  );
}

export { Skeleton };
