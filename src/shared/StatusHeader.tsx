import { Field, PanelSectionRow } from "@decky/ui";
import type { ReactNode } from "react";
import type { Status } from "./backend";
import { STATE_LABELS } from "./format";

const DOT: Record<string, string> = {
  online: "#59bf40",
  connecting: "#b8b8b8",
  offline: "#e0a030",
  error: "#e04848",
  unconfigured: "#808080",
};

// Connection state plus a summary line, for example speeds.
export function StatusHeader({ status, summary }: { status: Status | null; summary?: ReactNode }) {
  const state = status?.state ?? "connecting";
  return (
    <PanelSectionRow>
      <Field
        label={
          <span>
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: 4,
                marginRight: 6,
                background: DOT[state] ?? DOT.connecting,
              }}
            />
            {STATE_LABELS[state]}
          </span>
        }
        bottomSeparator="none"
        focusable={false}
      >
        {summary}
      </Field>
    </PanelSectionRow>
  );
}
