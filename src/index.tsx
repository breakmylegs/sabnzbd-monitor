import {
  addEventListener,
  callable,
  definePlugin,
  removeEventListener,
  routerHook,
  toaster,
  useQuickAccessVisible,
} from "@decky/api";
import { ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, showModal, staticClasses } from "@decky/ui";
import { useEffect, useState } from "react";
import { FaDownload } from "react-icons/fa";
import { monitorBackend, type ActionResult, type Snapshot, type Status, type UpdateInfo } from "./shared/backend";
import { ConnectionForm } from "./shared/ConnectionForm";
import { openPage } from "./shared/FullPage";
import { watchGameRunning } from "./shared/gameState";
import { OfflineBanner } from "./shared/OfflineBanner";
import { StatusHeader } from "./shared/StatusHeader";
import { shouldToast } from "./shared/toastOnce";
import { PanelBoundary } from "./shared/PanelBoundary";
import { UpdateBadge } from "./shared/UpdateBadge";
import { UpdatesSection } from "./shared/UpdatesSection";
import { useBackendEvent } from "./shared/useBackendEvent";
import { HISTORY_ROUTE, HistoryPage } from "./HistoryPage";
import { HistoryRow, QueueRow, StatsModal, WarningsModal, failed, note } from "./jobs";
import {
  GAME_ACTION_OPTIONS,
  SPEED_LIMITS,
  TIMED_PAUSES,
  diskSummary,
  serverSummary,
  speedLimitOption,
} from "./rows";
import type { GameAction, SabData, SabSettings, Toast } from "./types";

// plugin.json "name", exactly. Decky lists the plugin by it and matches the
// installed copy by it when Update now replaces the plugin.
const PLUGIN_NAME = "SABnzbd Monitor";

type Snap = Snapshot<SabSettings, SabData>;

const backend = monitorBackend<SabSettings, SabData>();
const pauseAll = callable<[], ActionResult>("pause_all");
const resumeAll = callable<[], ActionResult>("resume_all");
const pauseFor = callable<[minutes: number], ActionResult>("pause_for");
const setSpeedLimit = callable<[percent: number], ActionResult>("set_speed_limit");

function Controls({ data }: { data: SabData }) {
  const server = data.server;
  const disk = diskSummary(server);
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
      {disk && (
        <PanelSectionRow>
          <Field focusable bottomSeparator="none" childrenLayout="below">
            <span style={note}>{disk}</span>
          </Field>
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
            <HistoryRow key={job.id} job={job} actions={false} />
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
            <QueueRow key={job.id} job={job} jobs={data.server.jobs} />
          ))}
        </PanelSection>
      )}

      {online && data && (
        <PanelSection title="Recent">
          {data.recent.map((job) => (
            <HistoryRow key={job.id} job={job} />
          ))}
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => openPage(HISTORY_ROUTE)}>
              Full history...
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => showModal(<StatsModal />)}>
              Download totals...
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}

      <UpdatesSection update={update} name={PLUGIN_NAME} check={() => backend.checkUpdate(true)} />
      <PanelSection title="Settings">
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setShowSettings(!showSettings)}>
            {showSettings ? "Hide settings" : "Show settings"}
          </ButtonItem>
        </PanelSectionRow>
        {showSettings && (
          <>
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
            <PanelSectionRow>
              <DropdownItem
                label="While gaming"
                description={
                  <span style={note}>
                    When a game starts, pause or slow downloads. They go back when it ends, unless you changed them
                    yourself. Speed limits need a maximum line speed set in SABnzbd Config, General.
                  </span>
                }
                rgOptions={GAME_ACTION_OPTIONS}
                selectedOption={snap.settings.game_action}
                onChange={async (o) => {
                  const res = await backend.saveSettings({ game_action: o.data as GameAction });
                  if (res.snapshot) apply(res.snapshot);
                }}
              />
            </PanelSectionRow>
          </>
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
  routerHook.addRoute(HISTORY_ROUTE, () => (
    <PanelBoundary>
      <HistoryPage />
    </PanelBoundary>
  ));
  const onNotify = addEventListener<[Toast]>("notify", (toast) => {
    if (shouldToast(toast.key)) toaster.toast({ title: toast.title, body: toast.body });
  });
  const stopWatching = watchGameRunning((running) => {
    backend.setGameRunning(running);
  });

  return {
    name: PLUGIN_NAME,
    titleView: <div className={staticClasses.Title}>SABnzbd Monitor</div>,
    content: (
      <PanelBoundary>
        <Content />
      </PanelBoundary>
    ),
    icon: <FaDownload />,
    onDismount() {
      routerHook.removeRoute(HISTORY_ROUTE);
      removeEventListener("notify", onNotify);
      stopWatching();
    },
  };
});
