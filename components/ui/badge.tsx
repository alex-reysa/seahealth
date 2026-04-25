"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, AlertCircle, HelpCircle } from "lucide-react";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-0.5 text-caption font-medium transition-colors",
  {
    variants: {
      variant: {
        verified:
          "bg-[var(--color-semantic-verified-subtle)] text-[var(--color-semantic-verified)]",
        flagged:
          "bg-[var(--color-semantic-flagged-subtle)] text-[var(--color-semantic-flagged)]",
        critical:
          "bg-[var(--color-semantic-critical-subtle)] text-[var(--color-semantic-critical)]",
        insufficient:
          "bg-[var(--color-semantic-insufficient-subtle)] text-[var(--color-semantic-insufficient)]",
        subtle:
          "bg-[var(--color-surface-sunken)] text-[var(--color-content-secondary)]",
      },
    },
    defaultVariants: {
      variant: "subtle",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  showIcon?: boolean;
}

function Badge({ className, variant, showIcon = true, children, ...props }: BadgeProps) {
  const icons = {
    verified: <CheckCircle2 className="h-3 w-3" />,
    flagged: <AlertTriangle className="h-3 w-3" />,
    critical: <AlertCircle className="h-3 w-3" />,
    insufficient: <HelpCircle className="h-3 w-3" />,
    subtle: null,
  };

  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props}>
      {showIcon && variant && icons[variant]}
      {children}
    </div>
  );
}

export { Badge, badgeVariants };
