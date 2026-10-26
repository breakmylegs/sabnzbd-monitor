import { Router } from "@decky/ui";

// Report whether a game is running. Uses the Steam client's app lifetime
// notifications, with Router.MainRunningApp as the starting value.
// Returns an unsubscribe function.
export function watchGameRunning(onChange: (running: boolean) => void): () => void {
  const running = new Set<number>();
  try {
    const appId = Router.MainRunningApp?.appid;
    if (appId) running.add(Number(appId));
  } catch {
    // Router may not be ready on very early loads. Notifications fill in later.
  }
  onChange(running.size > 0);
  let unregister: (() => void) | undefined;
  try {
    const handle = window.SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications((n) => {
      if (n.bRunning) running.add(n.unAppID);
      else running.delete(n.unAppID);
      onChange(running.size > 0);
    });
    unregister = () => handle?.unregister();
  } catch {
    unregister = undefined;
  }
  return () => unregister?.();
}
