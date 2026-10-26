import { PanelSectionRow } from "@decky/ui";
import type { Status } from "./backend";

const box: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: 4,
  fontSize: 12,
  lineHeight: 1.3,
};

// One line for offline or error states. Nothing when connected.
export function OfflineBanner({ status }: { status: Status | null }) {
  if (!status || status.state === "online" || status.state === "connecting") return null;
  let text: string;
  let tone: string;
  if (status.state === "unconfigured") {
    text = "Not set up. Enter the server address in Settings below.";
    tone = "#2a3a4f";
  } else if (status.state === "offline") {
    text = `Offline. ${status.error?.message ?? "Cannot reach the server."} Retrying in the background.`;
    tone = "#4f3a1f";
  } else {
    text = status.error?.message ?? "The server returned an error.";
    tone = "#5a2424";
  }
  return (
    <PanelSectionRow>
      <div style={{ ...box, background: tone }}>{text}</div>
    </PanelSectionRow>
  );
}
