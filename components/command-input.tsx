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
    <div
      className={cn(
        "glass-control rounded-[var(--radius-xl)] p-2 transition-all",
        isExecuting && "ring-2 ring-[var(--color-accent-aura)]",
        className
      )}
    >
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <div className="relative flex-1">
          {/* Aura glow on focus/executing */}
          <div
            className={cn(
              "absolute inset-0 rounded-[var(--radius-lg)] bg-[var(--color-accent-aura)] opacity-0 transition-opacity blur-xl -z-10",
              (isExecuting || inputRef.current === document.activeElement) &&
                "opacity-100"
            )}
          />
          <div className="relative flex items-center">
            <Search className="absolute left-3 h-5 w-5 text-[var(--color-content-tertiary)]" />
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={isExecuting}
              className="w-full h-12 pl-11 pr-4 bg-transparent text-body text-[var(--color-content-primary)] placeholder:text-[var(--color-content-tertiary)] focus:outline-none disabled:opacity-50"
            />
          </div>
        </div>

        {/* Voice button (future) */}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          disabled
          className="text-[var(--color-content-tertiary)] opacity-50"
          aria-label="Voice input (coming soon)"
        >
          <Mic className="h-5 w-5" />
        </Button>

        {/* Submit button */}
        <Button
          type="submit"
          variant="primary"
          size="icon"
          disabled={!value.trim() || isExecuting}
          className="flex-shrink-0"
          aria-label="Execute command"
        >
          {isExecuting ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Send className="h-5 w-5" />
          )}
        </Button>
      </form>

      {/* Status indicator */}
      {status && (
        <div className="mt-2 px-3 flex items-center gap-2 text-caption text-[var(--color-content-secondary)]">
          {isExecuting && (
            <span className="inline-block h-2 w-2 rounded-full bg-[var(--color-accent-primary)] animate-pulse" />
          )}
          <span>{status}</span>
        </div>
      )}
    </div>
  );
}
