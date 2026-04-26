import * as React from 'react';
import { cn } from '@/src/lib/utils';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', size = 'md', ...props }, ref) => {
    const baseClass = "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary-subtle disabled:pointer-events-none disabled:opacity-50";
    
    const variants = {
      primary: "bg-accent-primary text-white hover:bg-accent-primary-hover",
      secondary: "bg-surface-raised border border-border-default hover:shadow-elevation-2 text-content-primary",
      ghost: "bg-transparent text-accent-primary hover:bg-surface-sunken",
    };
    
    const sizes = {
      sm: "h-[32px] px-3 text-caption",
      md: "h-[40px] px-4 text-body",
      lg: "h-[48px] px-6 text-body-l",
    };

    return (
      <button
        ref={ref}
        className={cn(baseClass, variants[variant], sizes[size], className)}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
