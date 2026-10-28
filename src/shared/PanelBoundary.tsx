import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { Component, type ReactNode } from "react";

// Catches a render error inside the panel, so the plugin shows the error and a
// Retry button instead of Steam's "Shared SteamUI" error screen. The text is
// what a bug report needs.
export class PanelBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("[panel]", error);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const where = (error.stack ?? "").split("\n").slice(1, 3).map((l) => l.trim()).join(" ");
    return (
      <PanelSection title="Something went wrong">
        <PanelSectionRow>
          <div style={{ fontSize: 12, lineHeight: 1.35 }}>
            <div>The panel hit an error. Retry, or report this text:</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, wordBreak: "break-all", marginTop: 4 }}>
              {String(error.message || error)}
              {where ? ` ${where}` : ""}
            </div>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => this.setState({ error: null })}>
            Retry
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }
}
