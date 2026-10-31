import { ButtonItem, ConfirmModal, DropdownItem, PanelSectionRow, showModal } from "@decky/ui";
import { callable } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import type { ActionResult } from "./shared/backend";
import { FullPage } from "./shared/FullPage";
import { HistoryRow, failed, getHistory, note, retryAll } from "./jobs";
import type { HistoryPage as Page } from "./types";

export const HISTORY_ROUTE = "/sabnzbd-monitor/history";

const deleteHistory = callable<[nzoId: string, deleteFiles: boolean], ActionResult>("delete_history");

const SHOW = [
  { data: false, label: "All jobs" },
  { data: true, label: "Failed only" },
];

// The last 50 finished jobs. Loaded when the page opens and after each action,
// not on every poll.
export function HistoryPage() {
  const [failedOnly, setFailedOnly] = useState(false);
  const [page, setPage] = useState<Page | null>(null);

  // Switching Show quickly starts two requests. Keep only the newest reply.
  const latest = useRef(0);
  const load = () => {
    const id = ++latest.current;
    return getHistory(failedOnly).then((res) => {
      if (id === latest.current) setPage(res);
    });
  };
  useEffect(() => {
    setPage(null);
    load();
  }, [failedOnly]);

  const jobs = page?.jobs ?? [];
  const anyFailed = jobs.some((j) => j.status === "Failed");
  const menu = { bShiftToFitWindow: true, bFitToWindow: true };

  return (
    <FullPage title="SABnzbd history">
      <PanelSectionRow>
        <DropdownItem
          label="Show"
          rgOptions={SHOW}
          selectedOption={failedOnly}
          contextMenuPositionOptions={menu}
          onChange={(o) => setFailedOnly(o.data as boolean)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => load()}>
          Refresh
        </ButtonItem>
      </PanelSectionRow>
      {anyFailed && (
        <>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={async () => {
                if (failed(await retryAll(), "Retry all")) load();
              }}
            >
              Retry all failed jobs
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() =>
                showModal(
                  <ConfirmModal
                    strTitle="Remove all failed jobs?"
                    strDescription="Every failed job leaves the history. Their files stay on disk."
                    strOKButtonText="Remove failed jobs"
                    onOK={async () => {
                      if (failed(await deleteHistory("failed", false), "Remove failed jobs")) load();
                    }}
                  />,
                )
              }
            >
              Remove all failed jobs...
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {page === null && <div style={note}>Loading...</div>}
      {page && !page.ok && <div style={note}>{page.error?.message ?? "Could not load the history."}</div>}
      {page?.ok && (
        <div style={{ ...note, margin: "8px 0" }}>
          {jobs.length === 0
            ? "No jobs."
            : (page.total ?? 0) > jobs.length
              ? `The latest ${jobs.length} of ${page.total} jobs.`
              : `${jobs.length} jobs.`}
        </div>
      )}
      {jobs.map((job) => (
        <HistoryRow key={job.id} job={job} onDone={load} />
      ))}
    </FullPage>
  );
}
