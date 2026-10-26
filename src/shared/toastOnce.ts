// Toast at most once per key per session. The backend already suppresses the
// first poll and repeated transitions. This guards against duplicate events, for
// example when the frontend reloads and replays a cached snapshot.

const seen = new Map<string, number>();
const WINDOW_MS = 10 * 60 * 1000;

export function shouldToast(key: string, now: number = Date.now()): boolean {
  const last = seen.get(key);
  if (last !== undefined && now - last < WINDOW_MS) return false;
  seen.set(key, now);
  if (seen.size > 500) {
    for (const [k, t] of seen) {
      if (now - t >= WINDOW_MS) seen.delete(k);
    }
  }
  return true;
}

export function resetToasts(): void {
  seen.clear();
}
