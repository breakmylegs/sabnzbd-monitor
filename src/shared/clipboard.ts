// Copy text in Game Mode. There is no clipboard API in @decky/ui or SteamClient
// (VERIFICATION.md item 10), so try navigator.clipboard, then the textarea and
// execCommand fallback other plugins use. Report what happened honestly.

export interface ClipboardEnv {
  writeText?: (text: string) => Promise<void>;
  execCopy?: (text: string) => boolean;
}

function domExecCopy(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(area);
  return ok;
}

export function defaultEnv(): ClipboardEnv {
  const env: ClipboardEnv = {};
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    env.writeText = (text) => navigator.clipboard.writeText(text);
  }
  if (typeof document !== "undefined") env.execCopy = domExecCopy;
  return env;
}

export async function copyText(text: string, env: ClipboardEnv = defaultEnv()): Promise<boolean> {
  if (env.writeText) {
    try {
      await env.writeText(text);
      return true;
    } catch {
      // Fall through to the textarea method.
    }
  }
  return env.execCopy ? env.execCopy(text) : false;
}
