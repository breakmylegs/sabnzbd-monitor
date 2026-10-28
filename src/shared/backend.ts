import { callable } from "@decky/api";
import type { ConnectionState, TestStep } from "./format";

// Callables every monitor plugin backend implements. Secret values never come back.

export interface SecretView {
  set: boolean;
  masked: string;
}

export interface BackendError {
  kind: string;
  message: string;
  // TLS failures only: OpenSSL's reason and where certificates came from.
  detail?: string;
  status?: number | null;
}

export interface Status {
  state: ConnectionState;
  error: BackendError | null;
  last_success: number | null;
}

export interface UpdateInfo {
  current: string;
  latest: string | null;
  available: boolean;
  install_url: string | null;
}

export interface Snapshot<S, D> {
  version: string;
  settings: S;
  secrets: Record<string, SecretView>;
  status: Status;
  data: D | null;
  update: UpdateInfo | null;
  import_path: string;
}

export interface TestReport {
  ok: boolean;
  steps: TestStep[];
  warnings: string[];
  failed_step: string | null;
  auth_path: string | null;
  server_version: string | null;
  error?: BackendError;
}

export interface ActionResult {
  ok: boolean;
  error?: BackendError;
  message?: string;
}

export interface SnapshotResult<S, D> {
  ok: boolean;
  message?: string;
  snapshot?: Snapshot<S, D>;
}

export interface ImportResult<S, D> {
  ok: boolean;
  message?: string;
  imported?: string[];
  path: string;
  snapshot?: Snapshot<S, D>;
}

export function monitorBackend<S, D>() {
  return {
    getSnapshot: callable<[], Snapshot<S, D>>("get_snapshot"),
    saveSettings: callable<[values: Partial<S>], SnapshotResult<S, D>>("save_settings"),
    setSecret: callable<[name: string, value: string], SnapshotResult<S, D>>("set_secret"),
    clearSecret: callable<[name: string], SnapshotResult<S, D>>("clear_secret"),
    importFromFile: callable<[], ImportResult<S, D>>("import_from_file"),
    deleteImportFile: callable<[], ActionResult>("delete_import_file"),
    testConnection: callable<[], TestReport>("test_connection"),
    setVisible: callable<[visible: boolean], void>("set_visible"),
    setGameRunning: callable<[running: boolean], void>("set_game_running"),
    refresh: callable<[], void>("refresh"),
    checkUpdate: callable<[force: boolean], UpdateInfo | null>("check_update"),
  };
}

export type MonitorBackend<S, D> = ReturnType<typeof monitorBackend<S, D>>;
