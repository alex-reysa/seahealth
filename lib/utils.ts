import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat("en-IN").format(num);
}

export function formatDistance(km: number): string {
  return `${km.toFixed(1)} km`;
}

export function formatTimestamp(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function formatDate(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function getTrustScoreBand(score: number): "verified" | "flagged" | "critical" {
  if (score >= 80) return "verified";
  if (score >= 50) return "flagged";
  return "critical";
}

export function validatePinCode(pin: string): boolean {
  return /^\d{6}$/.test(pin);
}
