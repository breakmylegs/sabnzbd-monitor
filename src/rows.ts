// Pure formatting for the SABnzbd panel. Tested with vitest.
import { formatBytes, formatDuration, formatSpeed, truncate } from "./shared/format";
import type { GameAction, HistoryJob, QueueJob, SabData, StatsSums } from "./types";

export const TIMED_PAUSES = [15, 30, 60];
export const SPEED_LIMITS = [25, 50, 75, 100];

export const PRIORITIES: { value: number; label: string }[] = [
  { value: 2, label: "Force" },
  { value: 1, label: "High" },
  { value: 0, label: "Normal" },
  { value: -1, label: "Low" },
];

export function jobTitle(job: { name: string }): string {
  return truncate(job.name || "Unnamed job", 60);
}

export function queueDetail(job: QueueJob): string {
  const parts = [job.label, `${job.percent}%`];
  if (!job.paused && job.timeleft !== null) parts.push(formatDuration(job.timeleft));
  if (job.sizeleft) parts.push(`${job.sizeleft} left`);
  if (job.priority_label && job.priority_label !== "Normal") parts.push(job.priority_label);
  return parts.join(" | ");
}

export function historyDetail(job: HistoryJob): string {
  if (job.status === "Failed") return job.fail_message ? `Failed. ${job.fail_message}` : "Failed";
  if (job.action_line && job.label !== "Completed") return `${job.label}. ${job.action_line}`;
  return job.size ? `${job.label} | ${job.size}` : job.label;
}

export function serverSummary(server: SabData["server"]): string {
  if (server.paused) {
    return server.pause_left ? `Paused, resumes in ${formatDuration(server.pause_left)}` : "Paused";
  }
  if (server.jobs === 0) return "Idle";
  const parts = [formatSpeed(server.speed)];
  if (server.timeleft !== null) parts.push(`${formatDuration(server.timeleft)} left`);
  if (server.sizeleft) parts.push(server.sizeleft);
  return parts.join(" | ");
}

export function speedLimitOption(limit: number): number {
  // Show the nearest preset so the dropdown always has a selection.
  return SPEED_LIMITS.reduce((best, p) => (Math.abs(p - limit) < Math.abs(best - limit) ? p : best), 100);
}

// SABnzbd reports free space in GB as text. Round down, so free space is never overstated.
export function formatGb(gb: number): string {
  return gb >= 1000 ? `${(Math.floor(gb / 10) / 100).toFixed(2)} TB` : `${Math.floor(gb)} GB`;
}

export function diskSummary(server: SabData["server"]): string | null {
  const parts: string[] = [];
  if (server.disk_incomplete !== null) parts.push(`${formatGb(server.disk_incomplete)} free for downloads`);
  if (server.disk_complete !== null && server.disk_complete !== server.disk_incomplete) {
    parts.push(`${formatGb(server.disk_complete)} for completed`);
  }
  if (server.quota_left) parts.push(`quota left ${server.quota_left.trim()}`);
  return parts.length ? parts.join(", ") : null;
}

// What failed, step by step, from the history stage log.
export function stageLines(job: HistoryJob): string[] {
  return job.stage_log.flatMap((stage) => stage.actions.map((a) => `${stage.name}: ${a}`));
}

export function categoryLabel(category: string): string {
  return category === "*" ? "Default" : category;
}

export function statsLine(label: string, sums: StatsSums): string {
  return `${label}: today ${formatBytes(sums.day)}, this week ${formatBytes(sums.week)}, this month ${formatBytes(sums.month)}, total ${formatBytes(sums.total)}`;
}

export const GAME_ACTION_OPTIONS: { data: GameAction; label: string }[] = [
  { data: "off", label: "Do nothing" },
  { data: "pause", label: "Pause downloads" },
  { data: "limit_25", label: "Limit speed to 25%" },
  { data: "limit_50", label: "Limit speed to 50%" },
];
