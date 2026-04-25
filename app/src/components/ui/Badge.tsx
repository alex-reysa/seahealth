import * as React from "react"
import { cn } from "@/src/lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'verified' | 'flagged' | 'critical' | 'insufficient' | 'subtle';
}

export const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant = 'subtle', ...props }, ref) => {
    
    // Using inline styles or specific classes
    const variants = {
      verified: "bg-semantic-verified-subtle text-semantic-verified",
      flagged: "bg-semantic-flagged-subtle text-semantic-flagged",
      critical: "bg-semantic-critical-subtle text-semantic-critical",
      insufficient: "bg-semantic-insufficient-subtle text-semantic-insufficient",
      subtle: "bg-surface-sunken text-content-secondary",
    };

    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-sm px-2 py-0.5 text-caption font-medium",
          variants[variant],
          className
        )}
        {...props}
      />
    )
  }
)
Badge.displayName = "Badge"
