import { callable, toaster } from "@decky/api";
import {
  ButtonItem,
  ConfirmModal,
  DialogButton,
  Field,
  Focusable,
  ModalRoot,
  PanelSectionRow,
  ProgressBar,
  ToggleField,
  showModal,
  staticClasses,
} from "@decky/ui";
import { useEffect, useState, type ReactElement } from "react";
import type { ActionResult, BackendError } from "./shared/backend";
import { PRIORITIES, categoryLabel, historyDetail, jobTitle, queueDetail, stageLines, statsLine } from "./rows";
import type { HistoryJob, HistoryPage, QueueJob, ServerStats, Warning } from "./types";

// Queue and history rows and their modals, shared by the panel and the history page.

const jobAction = callable<[action: "pause" | "resume", nzoId: string], ActionResult>("job_action");
const setPriority = callable<[nzoId: string, priority: number], ActionResult>("set_priority");
const deleteJob = callable<[nzoId: string, deleteFiles: boolean], ActionResult>("delete_job");
const moveJob = callable<[nzoId: string, where: "top" | "bottom"], ActionResult>("move_job");
const getCategories = callable<[], { ok: boolean; categories?: string[]; error?: BackendError }>("get_categories");
const changeCategory = callable<[nzoId: string, category: string], ActionResult>("change_category");
const getWarnings = callable<[], { ok: boolean; warnings?: Warning[]; error?: BackendError }>("get_warnings");
const clearWarnings = callable<[], ActionResult>("clear_warnings");
const retryJob = callable<[nzoId: string], ActionResult>("retry_job");
const deleteHistory = callable<[nzoId: string, deleteFiles: boolean], ActionResult>("delete_history");
const getServerStats = callable<[], ServerStats>("get_server_stats");
export const getHistory = callable<[failedOnly: boolean], HistoryPage>("get_history");
export const retryAll = callable<[], ActionResult>("retry_all");

export const note: React.CSSProperties = { fontSize: 12, lineHeight: 1.35 };
const column: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 8 };

export function failed(res: ActionResult, what: string): boolean {
  if (!res.ok) toaster.toast({ title: `${what} failed`, body: res.error?.message ?? res.message ?? "Try again." });
  return res.ok;
}

function DeleteModal({ job, closeModal }: { job: QueueJob; closeModal?: () => void }) {
  const [withFiles, setWithFiles] = useState(false);
  return (
    <ConfirmModal
      closeModal={closeModal}
      strTitle="Delete job?"
      strDescription={
        <>
          <div style={{ marginBottom: 12 }}>{job.name}</div>
          <ToggleField
            label="Also delete downloaded files"
            description={withFiles ? "Partial files are removed from disk." : "Partial files stay on disk."}
            checked={withFiles}
            onChange={setWithFiles}
          />
        </>
      }
      strOKButtonText={withFiles ? "Delete job and files" : "Delete job"}
      bDestructiveWarning={withFiles}
      onOK={async () => failed(await deleteJob(job.id, withFiles), "Delete")}
    />
  );
}

function CategoryModal({ job, closeModal }: { job: QueueJob; closeModal?: () => void }) {
  const [categories, setCategories] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getCategories().then((res) => {
      if (res.ok) setCategories(res.categories ?? []);
      else setError(res.error?.message ?? "Could not load categories.");
    });
  }, []);
  const current = job.category || "*";
  const pick = async (category: string) => {
    closeModal?.();
    failed(await changeCategory(job.id, category), "Category change");
  };
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: 8 }}>
        Category
      </div>
      <div style={{ ...note, marginBottom: 16 }}>{job.name}</div>
      <Focusable style={{ ...column, maxHeight: 360, overflowY: "auto" }}>
        {error && <div style={note}>{error}</div>}
        {categories === null && !error && <div style={note}>Loading...</div>}
        {categories
          ?.filter((c) => c !== current)
          .map((c) => (
            <DialogButton key={c} onClick={() => pick(c)}>
              {categoryLabel(c)}
            </DialogButton>
          ))}
        <DialogButton onClick={() => closeModal?.()}>Cancel</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

function JobModal({ job, jobs, closeModal }: { job: QueueJob; jobs: number; closeModal?: () => void }) {
  const run = async (fn: () => Promise<ActionResult>, what: string) => {
    closeModal?.();
    failed(await fn(), what);
  };
  const then = (modal: ReactElement) => {
    closeModal?.();
    showModal(modal);
  };
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: 8 }}>
        {job.name}
      </div>
      <div style={{ ...note, marginBottom: 16 }}>
        {queueDetail(job)}
        {job.category ? ` | ${job.category}` : ""}
      </div>
      <Focusable style={column}>
        {job.paused ? (
          <DialogButton onClick={() => run(() => jobAction("resume", job.id), "Resume")}>Resume</DialogButton>
        ) : (
          <DialogButton onClick={() => run(() => jobAction("pause", job.id), "Pause")}>Pause</DialogButton>
        )}
        {jobs > 1 && job.index !== 0 && (
          <DialogButton onClick={() => run(() => moveJob(job.id, "top"), "Move")}>Move to top</DialogButton>
        )}
        {jobs > 1 && job.index !== jobs - 1 && (
          <DialogButton onClick={() => run(() => moveJob(job.id, "bottom"), "Move")}>Move to bottom</DialogButton>
        )}
        {PRIORITIES.filter((p) => p.value !== job.priority).map((p) => (
          <DialogButton key={p.value} onClick={() => run(() => setPriority(job.id, p.value), "Priority change")}>
            Priority: {p.label}
          </DialogButton>
        ))}
        <DialogButton onClick={() => then(<CategoryModal job={job} />)}>Category...</DialogButton>
        <DialogButton onClick={() => then(<DeleteModal job={job} />)}>Delete...</DialogButton>
        <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

function RemoveHistoryModal({
  job,
  onDone,
  closeModal,
}: {
  job: HistoryJob;
  onDone?: () => void;
  closeModal?: () => void;
}) {
  const [withFiles, setWithFiles] = useState(false);
  const isFailed = job.status === "Failed";
  return (
    <ConfirmModal
      closeModal={closeModal}
      strTitle="Remove from history?"
      strDescription={
        <>
          <div style={{ marginBottom: 12 }}>{job.name}</div>
          {isFailed && (
            <ToggleField
              label="Also delete the failed files"
              description={withFiles ? "The incomplete folder is removed." : "Files stay on disk."}
              checked={withFiles}
              onChange={setWithFiles}
            />
          )}
          {!isFailed && <div style={note}>The downloaded files stay on disk.</div>}
        </>
      }
      strOKButtonText="Remove"
      bDestructiveWarning={withFiles}
      onOK={async () => {
        if (failed(await deleteHistory(job.id, withFiles), "Remove")) onDone?.();
      }}
    />
  );
}

function HistoryModal({ job, onDone, closeModal }: { job: HistoryJob; onDone?: () => void; closeModal?: () => void }) {
  const lines = stageLines(job);
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: 8 }}>
        {job.name}
      </div>
      <div style={{ ...note, marginBottom: 8 }}>{historyDetail(job)}</div>
      {lines.length > 0 && (
        <Focusable style={{ ...note, maxHeight: 200, overflowY: "auto", marginBottom: 12 }}>
          {lines.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </Focusable>
      )}
      <Focusable style={column}>
        {job.status === "Failed" && (
          <DialogButton
            onClick={async () => {
              closeModal?.();
              if (failed(await retryJob(job.id), "Retry")) onDone?.();
            }}
          >
            Retry
          </DialogButton>
        )}
        <DialogButton
          onClick={() => {
            closeModal?.();
            showModal(<RemoveHistoryModal job={job} onDone={onDone} />);
          }}
        >
          Remove from history...
        </DialogButton>
        <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

export function WarningsModal({ closeModal }: { closeModal?: () => void }) {
  const [items, setItems] = useState<Warning[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getWarnings().then((res) => {
      if (res.ok) setItems(res.warnings ?? []);
      else setError(res.error?.message ?? "Could not load warnings.");
    });
  }, []);
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: 8 }}>
        SABnzbd warnings
      </div>
      <Focusable style={{ maxHeight: 320, overflowY: "auto", ...note }}>
        {error && <div>{error}</div>}
        {items === null && !error && <div>Loading...</div>}
        {items?.length === 0 && <div>No warnings.</div>}
        {items
          ?.slice()
          .reverse()
          .map((w, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <b>{w.type}</b> {w.text}
            </div>
          ))}
      </Focusable>
      <Focusable style={{ ...column, marginTop: 12 }}>
        {items && items.length > 0 && (
          <DialogButton
            onClick={async () => {
              closeModal?.();
              failed(await clearWarnings(), "Clear warnings");
            }}
          >
            Clear warnings
          </DialogButton>
        )}
        <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

export function StatsModal({ closeModal }: { closeModal?: () => void }) {
  const [stats, setStats] = useState<ServerStats | null>(null);
  useEffect(() => {
    getServerStats().then(setStats);
  }, []);
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: 8 }}>
        Download totals
      </div>
      <Focusable style={{ ...note, maxHeight: 320, overflowY: "auto" }}>
        {stats === null && <div>Loading...</div>}
        {stats && !stats.ok && <div>{stats.error?.message ?? "Could not load the totals."}</div>}
        {stats?.totals && <div style={{ marginBottom: 8 }}>{statsLine("All servers", stats.totals)}</div>}
        {stats?.servers?.map((s) => (
          <div key={s.name} style={{ marginBottom: 8 }}>
            {statsLine(s.name, s)}
          </div>
        ))}
      </Focusable>
      <DialogButton style={{ marginTop: 12 }} onClick={() => closeModal?.()}>
        Close
      </DialogButton>
    </ModalRoot>
  );
}

export function QueueRow({ job, jobs }: { job: QueueJob; jobs: number }) {
  return (
    <PanelSectionRow>
      <ButtonItem
        layout="below"
        bottomSeparator="none"
        description={
          <>
            <ProgressBar nProgress={job.percent} />
            <div style={{ ...note, marginTop: 4 }}>{queueDetail(job)}</div>
          </>
        }
        onClick={() => showModal(<JobModal job={job} jobs={jobs} />)}
      >
        <span style={{ fontSize: 13, wordBreak: "break-word" }}>{jobTitle(job)}</span>
      </ButtonItem>
    </PanelSectionRow>
  );
}

// Post-processing rows are for show. Finished rows open the retry and remove actions.
export function HistoryRow({ job, onDone, actions = true }: { job: HistoryJob; onDone?: () => void; actions?: boolean }) {
  const detail = (
    <span style={{ ...note, color: job.status === "Failed" ? "#e04848" : undefined }}>{historyDetail(job)}</span>
  );
  const title = <span style={{ fontSize: 13, wordBreak: "break-word" }}>{jobTitle(job)}</span>;
  if (!actions) {
    return (
      <PanelSectionRow>
        <Field label={title} focusable bottomSeparator="none">
          {detail}
        </Field>
      </PanelSectionRow>
    );
  }
  return (
    <PanelSectionRow>
      <ButtonItem
        layout="below"
        bottomSeparator="none"
        description={detail}
        onClick={() => showModal(<HistoryModal job={job} onDone={onDone} />)}
      >
        {title}
      </ButtonItem>
    </PanelSectionRow>
  );
}
