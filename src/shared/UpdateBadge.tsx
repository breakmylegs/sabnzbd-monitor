import { ButtonItem, Field, PanelSectionRow } from "@decky/ui";
import { useState } from "react";
import type { UpdateInfo } from "./backend";
import { copyText } from "./clipboard";
import { loaderBackend, requestUpdate } from "./selfUpdate";

type State = "idle" | "asked" | "failed" | "copied" | "copy_failed";

const note = { fontSize: 12, lineHeight: 1.35 };
const link = { fontFamily: "monospace", fontSize: 11, wordBreak: "break-all" as const };

// Shows when the mirror has a newer release. Update now hands the release to
// Decky's own installer. If Decky does not offer that, show the link to use
// with Install Plugin from URL.
export function UpdateBadge({ update, name }: { update: UpdateInfo | null; name: string }) {
  const [state, setState] = useState<State>("idle");
  if (!update?.available || !update.install_url || !update.latest) return null;
  const url = update.install_url;
  const direct = loaderBackend() !== null && state !== "failed";

  return (
    <>
      <PanelSectionRow>
        <Field
          label={`Update available: ${update.latest}`}
          description={
            <div style={note}>
              <div>You have {update.current}. Your settings and keys are kept.</div>
              {state === "asked" && <div>Confirm the update in Decky's prompt.</div>}
              {!direct && (
                <>
                  <div>
                    {state === "failed" ? "Decky did not accept the update. " : ""}
                    Install from Decky Settings, Developer, Install Plugin from URL:
                  </div>
                  <div style={link}>{url}</div>
                  {state === "copied" && <div>Link copied.</div>}
                  {state === "copy_failed" && <div>Copying is not available here. Type the link instead.</div>}
                </>
              )}
            </div>
          }
          focusable
          bottomSeparator="none"
        />
      </PanelSectionRow>
      <PanelSectionRow>
        {direct ? (
          <ButtonItem
            layout="below"
            disabled={state === "asked"}
            onClick={async () => setState((await requestUpdate(url, name, update.latest ?? "")) ? "asked" : "failed")}
          >
            Update now
          </ButtonItem>
        ) : (
          <ButtonItem layout="below" onClick={async () => setState((await copyText(url)) ? "copied" : "copy_failed")}>
            Copy link
          </ButtonItem>
        )}
      </PanelSectionRow>
    </>
  );
}
