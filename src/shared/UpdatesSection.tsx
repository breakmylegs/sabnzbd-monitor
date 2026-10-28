import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useState } from "react";
import type { UpdateInfo } from "./backend";
import { copyText } from "./clipboard";
import { checkedLine, loaderBackend, requestUpdate, updateStatus } from "./selfUpdate";

type Action = "idle" | "asked" | "refused" | "copied" | "copy_failed";

const note = { fontSize: 12, lineHeight: 1.35 };
const link = { fontFamily: "monospace", fontSize: 11, wordBreak: "break-all" as const, marginTop: 4 };

// Always shown. Check for updates, then Update now (or Reinstall latest) hands
// the release to Decky's own installer. Copy install link is always there for
// Install Plugin from URL, with the link shown in case copying is not
// available in Game Mode.
export function UpdatesSection({
  update,
  name,
  check,
}: {
  update: UpdateInfo | null;
  name: string;
  check: () => Promise<UpdateInfo | null>;
}) {
  const [info, setInfo] = useState<UpdateInfo | null>(update);
  const [checking, setChecking] = useState(false);
  const [action, setAction] = useState<Action>("idle");
  useEffect(() => setInfo(update), [update]);

  const url = info?.install_url ?? null;
  const direct = loaderBackend() !== null;
  const newer = Boolean(info?.available && info.latest);

  const runCheck = async () => {
    setChecking(true);
    try {
      const fresh = await check();
      if (fresh) setInfo(fresh);
    } catch {
      setInfo((old) => (old ? { ...old, check_failed: true } : old));
    } finally {
      setChecking(false);
    }
  };

  const install = async () => {
    if (!url) return;
    const ok = await requestUpdate(url, name, (newer ? info?.latest : info?.current) ?? "");
    setAction(ok ? "asked" : "refused");
  };

  return (
    <PanelSection title="Updates">
      <PanelSectionRow>
        <Field
          label={info ? `Version ${info.current}` : "Version"}
          description={
            <div style={note}>
              <div>{updateStatus(info, checking)}</div>
              {checkedLine(info?.checked_at) && <div>{checkedLine(info?.checked_at)}</div>}
              {action === "asked" && <div>Confirm in Decky's prompt. Your settings and keys are kept.</div>}
              {action === "refused" && <div>Decky did not accept the update. Use Copy install link instead.</div>}
              {!direct && <div>Install from Decky Settings, Developer, Install Plugin from URL.</div>}
            </div>
          }
          focusable
          bottomSeparator="none"
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={checking} onClick={runCheck}>
          {checking ? "Checking..." : "Check for updates"}
        </ButtonItem>
      </PanelSectionRow>
      {direct && url && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={action === "asked"} onClick={install}>
            {newer ? "Update now" : "Reinstall latest"}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {url && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => setAction((await copyText(url)) ? "copied" : "copy_failed")}>
            Copy install link
          </ButtonItem>
        </PanelSectionRow>
      )}
      {url && (
        <PanelSectionRow>
          <div style={note}>
            {action === "copied" && <div>Link copied.</div>}
            {action === "copy_failed" && <div>Copying is not available here. Type this link instead:</div>}
            <div style={link}>{url}</div>
          </div>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
