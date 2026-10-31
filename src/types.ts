import type { CommonSettings } from "./shared/ConnectionForm";

export type GameAction = "off" | "pause" | "limit_25" | "limit_50";

export interface SabSettings extends CommonSettings {
  game_action: GameAction;
}

export interface QueueJob {
  id: string;
  name: string;
  status: string;
  label: string;
  percent: number;
  timeleft: number | null;
  sizeleft: string;
  priority: number | null;
  priority_label: string;
  category: string;
  paused: boolean;
  index: number;
}

export interface HistoryJob {
  id: string;
  name: string;
  status: string;
  label: string;
  fail_message: string;
  size: string;
  completed: number | null;
  action_line: string;
  category: string;
  stage_log: { name: string; actions: string[] }[];
}

export interface SabData {
  server: {
    status: string;
    paused: boolean;
    speed: number;
    timeleft: number | null;
    sizeleft: string;
    mbleft: number;
    jobs: number;
    speedlimit: number;
    warnings: number;
    pause_left: number | null;
    // Free space in GB. null when SABnzbd did not say.
    disk_incomplete: number | null;
    disk_complete: number | null;
    quota_left: string | null;
  };
  queue: QueueJob[];
  post_processing: HistoryJob[];
  recent: HistoryJob[];
  config_locked: boolean;
}

export interface Toast {
  kind: "completed" | "failed";
  key: string;
  title: string;
  body: string;
}

export interface Warning {
  type: string;
  text: string;
  time: number | null;
}

export interface HistoryPage {
  ok: boolean;
  jobs?: HistoryJob[];
  total?: number;
  limit?: number;
  error?: { kind: string; message: string };
}

export interface StatsSums {
  day: number;
  week: number;
  month: number;
  total: number;
}

export interface ServerStats {
  ok: boolean;
  totals?: StatsSums;
  servers?: (StatsSums & { name: string })[];
  error?: { kind: string; message: string };
}
