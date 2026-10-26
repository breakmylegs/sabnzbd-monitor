import { Field, PanelSectionRow } from "@decky/ui";
import type { UpdateInfo } from "./backend";

// Shows when the mirror has a newer release. Install stays manual: Decky
// Developer Mode, Install Plugin from URL.
export function UpdateBadge({ update }: { update: UpdateInfo | null }) {
  if (!update?.available || !update.install_url) return null;
  return (
    <PanelSectionRow>
      <Field
        label={`Update available: ${update.latest}`}
        description={
          <>
            <div>You have {update.current}. Install from Decky Settings, Developer, Install Plugin from URL:</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, wordBreak: "break-all" }}>{update.install_url}</div>
          </>
        }
        focusable
        bottomSeparator="none"
      />
    </PanelSectionRow>
  );
}
