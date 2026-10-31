import { DialogButton, Navigation, staticClasses } from "@decky/ui";
import { useEffect, type ReactNode } from "react";

// A full-screen page opened from the panel, for lists too long for the Quick
// Access Menu. Decky hides the menu while the page is open, so the page tells
// the backend it is showing, which keeps the fast poll on.

export function openPage(path: string) {
  Navigation.Navigate(path);
  Navigation.CloseSideMenus();
}

export function FullPage({
  title,
  onVisible,
  children,
}: {
  title: string;
  onVisible?: (visible: boolean) => void;
  children: ReactNode;
}) {
  useEffect(() => {
    onVisible?.(true);
    return () => onVisible?.(false);
  }, []);
  return (
    <div style={{ marginTop: 40, height: "calc(100% - 40px)", overflowY: "auto", padding: "16px 24px 48px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div className={staticClasses.Title}>{title}</div>
        <DialogButton style={{ width: "auto", minWidth: 120 }} onClick={() => Navigation.NavigateBack()}>
          Back
        </DialogButton>
      </div>
      {children}
    </div>
  );
}
