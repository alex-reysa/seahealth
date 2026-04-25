import * as React from "react"
import { cn } from "@/src/lib/utils"

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { variant?: 'default' | 'glass' | 'glass-elevated' | 'glass-control' }>(
  ({ className, variant = 'default', ...props }, ref) => {
    
    const variants = {
      default: "bg-surface-raised border border-border-subtle rounded-md shadow-elevation-1",
      glass: "glass-standard rounded-md",
      "glass-elevated": "glass-elevated rounded-lg",
      "glass-control": "glass-control rounded-xl",
    }
    
    return (
      <div
        ref={ref}
        className={cn(variants[variant], className)}
        {...props}
      />
    )
  }
)
Card.displayName = "Card"
