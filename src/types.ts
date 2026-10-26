import type { CommonSettings } from "./shared/ConnectionForm";

export type SabSettings = CommonSettings;

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
