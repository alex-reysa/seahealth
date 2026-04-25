"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { Search, Mic, Send, Loader2 } from "lucide-react";

interface CommandInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  isExecuting?: boolean;
  status?: string;
  className?: string;
}

export function CommandInput({
  value,
  onChange,
  onSubmit,
  placeholder = "Focus Patna, appendectomy, 50 km",
  isExecuting = false,
  status,
  className,
}: CommandInputProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [isFocused, setIsFocused] = React.useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim() && !isExecuting) {
      onSubmit(value.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      handleSubmit(e);
    }
  };

  return (
    <div className={cn("relative", className)}>
      {/* Aura glow on focus/executing */}
      <div
        className={cn(
          "pointer-events-none absolute inset-0 rounded-[var(--radius-lg)] bg-[var(--color-accent-aura)] opacity-0 transition-opacity blur-2xl -z-10",
          (isExecuting || isFocused) && "opacity-100"
        )}
      />
      <form onSubmit={handleSubmit} className="flex items-center gap-1.5">
        <div className="relative flex-1 min-w-0 flex items-center">
          <Search className="absolute left-3 h-4 w-4 text-[var(--color-content-tertiary)] pointer-events-none" />
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={placeholder}
            disabled={isExecuting}
            className="w-full h-11 pl-10 pr-4 bg-[var(--color-surface-sunken)] border border-[var(--color-border-subtle)] rounded-[var(--radius-md)] text-body text-[var(--color-content-primary)] placeholder:text-[var(--color-content-tertiary)] focus:outline-none focus:border-[var(--color-accent-primary)] focus:ring-2 focus:ring-[var(--color-accent-primary-subtle)] disabled:opacity-50 transition-all"
          />
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          disabled
          className="text-[var(--color-content-tertiary)] opacity-40 flex-shrink-0"
          aria-label="Voice input (coming soon)"
        >
          <Mic className="h-4 w-4" />
        </Button>

        <Button
          type="submit"
          variant="primary"
          size="icon"
          disabled={!value.trim() || isExecuting}
          className="flex-shrink-0"
          aria-label="Execute command"
        >
          {isExecuting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </form>

      {status && (
        <div className="mt-1.5 px-1 flex items-center gap-2 text-mono-s text-[var(--color-content-secondary)]">
          {isExecuting && (
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-accent-primary)] animate-pulse" />
          )}
          <span>{status}</span>
        </div>
      )}
    </div>
  );
}
