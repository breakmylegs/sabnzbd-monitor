import { addEventListener, callable, definePlugin, removeEventListener, toaster, useQuickAccessVisible } from "@decky/api";
import {
  ButtonItem,
  ConfirmModal,
  DialogButton,
  DropdownItem,
  Field,
  Focusable,
  ModalRoot,
  PanelSection,
  PanelSectionRow,
  ProgressBar,
  ToggleField,
  showModal,
  staticClasses,
} from "@decky/ui";
import { useEffect, useState } from "react";
import { FaDownload } from "react-icons/fa";
import { monitorBackend, type ActionResult, type BackendError, type Snapshot, type Status, type UpdateInfo } from "./shared/backend";
import { ConnectionForm } from "./shared/ConnectionForm";
import { watchGameRunning } from "./shared/gameState";
import { OfflineBanner } from "./shared/OfflineBanner";
import { StatusHeader } from "./shared/StatusHeader";
import { shouldToast } from "./shared/toastOnce";
import { UpdateBadge } from "./shared/UpdateBadge";
import { useBackendEvent } from "./shared/useBackendEvent";
import {
  PRIORITIES,
  SPEED_LIMITS,
  TIMED_PAUSES,
  historyDetail,
  jobTitle,
  queueDetail,
  serverSummary,
  speedLimitOption,
} from "./rows";
import type { HistoryJob, QueueJob, SabData, SabSettings, Toast, Warning } from "./types";

// plugin.json "name", exactly. Decky lists the plugin by it and matches the
// installed copy by it when Update now replaces the plugin.
const PLUGIN_NAME = "SABnzbd Monitor";

type Snap = Snapshot<SabSettings, SabData>;

const backend = monitorBackend<SabSettings, SabData>();
const pauseAll = callable<[], ActionResult>("pause_all");
const resumeAll = callable<[], ActionResult>("resume_all");
const pauseFor = callable<[minutes: number], ActionResult>("pause_for");
const setSpeedLimit = callable<[percent: number], ActionResult>("set_speed_limit");
const jobAction = callable<[action: "pause" | "resume", nzoId: string], ActionResult>("job_action");
const setPriority = callable<[nzoId: string, priority: number], ActionResult>("set_priority");
const deleteJob = callable<[nzoId: string, deleteFiles: boolean], ActionResult>("delete_job");
const getWarnings = callable<[], { ok: boolean; warnings?: Warning[]; error?: BackendError }>("get_warnings");

const note: React.CSSProperties = { fontSize: 12, lineHeight: 1.35 };

function failed(res: ActionResult, what: string) {
  if (!res.ok) toaster.toast({ title: `${what} failed`, body: res.error?.message ?? res.message ?? "Try again." });
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

function JobModal({ job, closeModal }: { job: QueueJob; closeModal?: () => void }) {
  const run = async (fn: () => Promise<ActionResult>, what: string) => {
    closeModal?.();
    failed(await fn(), what);
  };
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: 8 }}>
        {job.name}
      </div>
      <div style={{ ...note, marginBottom: 16 }}>{queueDetail(job)}</div>
      <Focusable style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {job.paused ? (
          <DialogButton onClick={() => run(() => jobAction("resume", job.id), "Resume")}>Resume</DialogButton>
        ) : (
          <DialogButton onClick={() => run(() => jobAction("pause", job.id), "Pause")}>Pause</DialogButton>
        )}
        {PRIORITIES.filter((p) => p.value !== job.priority).map((p) => (
          <DialogButton key={p.value} onClick={() => run(() => setPriority(job.id, p.value), "Priority change")}>
            Priority: {p.label}
          </DialogButton>
        ))}
        <DialogButton
          onClick={() => {
            closeModal?.();
            showModal(<DeleteModal job={job} />);
          }}
        >
          Delete...
        </DialogButton>
        <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

function WarningsModal({ closeModal }: { closeModal?: () => void }) {
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
      <Focusable style={{ maxHeight: 360, overflowY: "auto", ...note }}>
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
      <DialogButton style={{ marginTop: 12 }} onClick={() => closeModal?.()}>
        Close
      </DialogButton>
    </ModalRoot>
  );
}

function QueueRow({ job }: { job: QueueJob }) {
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
        onClick={() => showModal(<JobModal job={job} />)}
      >
        <span style={{ fontSize: 13, wordBreak: "break-word" }}>{jobTitle(job)}</span>
      </ButtonItem>
    </PanelSectionRow>
  );
}

function HistoryRow({ job }: { job: HistoryJob }) {
  return (
    <PanelSectionRow>
      <Field label={<span style={{ fontSize: 13, wordBreak: "break-word" }}>{jobTitle(job)}</span>} focusable bottomSeparator="none">
        <span style={{ ...note, color: job.status === "Failed" ? "#e04848" : undefined }}>{historyDetail(job)}</span>
      </Field>
    </PanelSectionRow>
  );
}

function Controls({ data }: { data: SabData }) {
  const server = data.server;
  return (
    <>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={async () => (server.paused ? failed(await resumeAll(), "Resume") : failed(await pauseAll(), "Pause"))}
        >
          {server.paused ? "Resume downloads" : "Pause downloads"}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem
          label="Pause for"
          rgOptions={TIMED_PAUSES.map((m) => ({ data: m, label: `${m} minutes` }))}
          selectedOption={null}
          strDefaultLabel="Choose"
          onChange={async (o) => failed(await pauseFor(o.data as number), "Timed pause")}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem
          label="Speed limit"
          rgOptions={SPEED_LIMITS.map((p) => ({ data: p, label: `${p}%` }))}
          selectedOption={speedLimitOption(server.speedlimit)}
          onChange={async (o) => failed(await setSpeedLimit(o.data as number), "Speed limit change")}
        />
      </PanelSectionRow>
      {data.config_locked && (
        <PanelSectionRow>
          <div style={{ ...note, color: "#e0a030" }}>
            Configuration locked. Timed pause and speed limit need the config lock turned off in SABnzbd.
          </div>
        </PanelSectionRow>
      )}
      {server.warnings > 0 && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => showModal(<WarningsModal />)}>
            {server.warnings === 1 ? "1 warning" : `${server.warnings} warnings`}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}

function Content() {
  const visible = useQuickAccessVisible();
  const [snap, setSnap] = useState<Snap | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [data, setData] = useState<SabData | null>(null);
  const [update, setUpdate] = useState<UpdateInfo | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const apply = (s: Snap) => {
    setSnap(s);
    setStatus(s.status);
    setData(s.data);
    setUpdate(s.update);
  };

  useEffect(() => {
    backend.getSnapshot().then((s) => {
      apply(s);
      if (!s.settings.base_url) setShowSettings(true);
    });
  }, []);

  useEffect(() => {
    backend.setVisible(visible);
    return () => {
      backend.setVisible(false);
    };
  }, [visible]);

  useBackendEvent<Status>("status", setStatus);
  useBackendEvent<SabData>("data", setData);
  useBackendEvent<UpdateInfo | null>("update", setUpdate);

  if (!snap) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <div style={note}>Loading...</div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const online = status?.state === "online";

  return (
    <>
      <PanelSection>
        <StatusHeader
          status={status}
          summary={data && online ? <span style={note}>{serverSummary(data.server)}</span> : undefined}
        />
        <OfflineBanner status={status} />
        <UpdateBadge update={update} name={PLUGIN_NAME} />
        {online && data && <Controls data={data} />}
      </PanelSection>

      {online && data && data.post_processing.length > 0 && (
        <PanelSection title="Post-processing">
          {data.post_processing.map((job) => (
            <HistoryRow key={job.id} job={job} />
          ))}
        </PanelSection>
      )}

      {online && data && (
        <PanelSection title={`Queue (${data.server.jobs})`}>
          {data.queue.length === 0 && (
            <PanelSectionRow>
              <div style={note}>The queue is empty.</div>
            </PanelSectionRow>
          )}
          {data.queue.map((job) => (
            <QueueRow key={job.id} job={job} />
          ))}
        </PanelSection>
      )}

      {online && data && data.recent.length > 0 && (
        <PanelSection title="Recent">
          {data.recent.map((job) => (
            <HistoryRow key={job.id} job={job} />
          ))}
        </PanelSection>
      )}

      <PanelSection title="Settings">
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setShowSettings(!showSettings)}>
            {showSettings ? "Hide settings" : "Show settings"}
          </ButtonItem>
        </PanelSectionRow>
        {showSettings && (
          <ConnectionForm
            snapshot={snap}
            backend={backend}
            onSnapshot={apply}
            secretFields={[
              {
                name: "api_key",
                label: "API key",
                description: "Use the full API key from SABnzbd Config, General. The NZB key cannot read the queue.",
              },
            ]}
            urlPlaceholder="http://192.168.x.x:8090"
            urlDescription="The SABnzbd address, for example http://192.168.x.x:8090 or https://sab.example.com/sabnzbd. If you use a host name, add it to host_whitelist in SABnzbd Config, Special."
          />
        )}
        <PanelSectionRow>
          <Field label="Version" bottomSeparator="none" focusable={false}>
            <span style={note}>{snap.version}</span>
          </Field>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  const onNotify = addEventListener<[Toast]>("notify", (toast) => {
    if (shouldToast(toast.key)) toaster.toast({ title: toast.title, body: toast.body });
  });
  const stopWatching = watchGameRunning((running) => {
    backend.setGameRunning(running);
  });

  return {
    name: PLUGIN_NAME,
    titleView: <div className={staticClasses.Title}>SABnzbd Monitor</div>,
    content: <Content />,
    icon: <FaDownload />,
    onDismount() {
      removeEventListener("notify", onNotify);
      stopWatching();
    },
  };
});
