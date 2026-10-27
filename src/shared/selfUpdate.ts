// Hand the latest release to Decky's own installer, the one Install Plugin from
// URL uses. Decky shows its update prompt, then replaces the plugin in place
// and keeps its settings folder. DeckyBackend and this route are loader
// internals (frontend/src/index.ts and backend utilities.py in v3.3.0), not
// the public plugin API, so callers fall back to showing the link.

// InstallType.UPDATE in Decky's frontend/src/plugin.ts.
export const INSTALL_TYPE_UPDATE = 2;
export const INSTALL_ROUTE = "utilities/install_plugin";

export interface LoaderBackend {
  call(route: string, ...args: unknown[]): Promise<unknown>;
}

export function loaderBackend(): LoaderBackend | null {
  const backend = (globalThis as { DeckyBackend?: Partial<LoaderBackend> }).DeckyBackend;
  return backend && typeof backend.call === "function" ? (backend as LoaderBackend) : null;
}

// name must be the plugin.json name exactly, or Decky cannot find the copy to
// replace. True when Decky accepted the request and is showing its prompt.
export async function requestUpdate(
  url: string,
  name: string,
  version: string,
  backend: LoaderBackend | null = loaderBackend(),
): Promise<boolean> {
  if (!backend || !url || !name) return false;
  try {
    await backend.call(INSTALL_ROUTE, url, name, version, "", INSTALL_TYPE_UPDATE);
    return true;
  } catch {
    return false;
  }
}
