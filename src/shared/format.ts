// Pure formatting helpers. No Decky imports, so vitest can load this file.

const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "-";
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < UNITS.length - 1) {
    value /= 1000;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${UNITS[unit]}`;
}

export function formatSpeed(bytesPerSecond: number | null | undefined): string {
  if (!bytesPerSecond || bytesPerSecond <= 0) return "0 B/s";
  return `${formatBytes(bytesPerSecond)}/s`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return "No ETA";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  if (d > 99) return "No ETA";
  return `${d}d ${h % 24}h`;
}

export function formatPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return "0%";
  const pct = Math.max(0, Math.min(1, fraction)) * 100;
  if (pct > 0 && pct < 1) return "<1%";
  if (pct < 100 && pct > 99) return "99%";
  return `${Math.floor(pct)}%`;
}

export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 3))}...`;
}

export type ConnectionState = "unconfigured" | "connecting" | "online" | "offline" | "error";

export const STATE_LABELS: Record<ConnectionState, string> = {
  unconfigured: "Not set up",
  connecting: "Connecting",
  online: "Connected",
  offline: "Offline",
  error: "Error",
};

export interface TestStep {
  step: string;
  ok: boolean;
  detail: string;
  kind?: string;
}

export const STEP_LABELS: Record<string, string> = {
  url: "Address",
  port: "Port",
  version: "Server",
  auth: "Sign-in",
};

export function describeStep(step: TestStep): string {
  const label = STEP_LABELS[step.step] ?? step.step;
  const mark = step.ok ? "OK" : "Failed";
  return step.detail ? `${label}: ${mark}. ${step.detail}` : `${label}: ${mark}`;
}
