import { ButtonItem, ConfirmModal, Field, PanelSectionRow, TextField, ToggleField, showModal } from "@decky/ui";
import { useEffect, useState, type ReactNode } from "react";
import type { MonitorBackend, Snapshot, TestReport } from "./backend";
import { describeStep } from "./format";

export interface CommonSettings {
  base_url: string;
  tls_verify: boolean;
  ca_file: string;
  notifications: boolean;
  notify_in_game: boolean;
  update_check: boolean;
  remove_data_on_uninstall: boolean;
}

export interface SecretField {
  name: string;
  label: string;
  description?: string;
}

interface Props<S extends CommonSettings, D> {
  snapshot: Snapshot<S, D>;
  backend: MonitorBackend<S, D>;
  onSnapshot: (snapshot: Snapshot<S, D>) => void;
  secretFields: SecretField[];
  urlPlaceholder: string;
  urlDescription?: ReactNode;
  children?: ReactNode;
}

const note: React.CSSProperties = { fontSize: 12, lineHeight: 1.35 };

function SecretRow<S extends CommonSettings, D>({
  field,
  snapshot,
  backend,
  onSnapshot,
}: {
  field: SecretField;
  snapshot: Snapshot<S, D>;
  backend: MonitorBackend<S, D>;
  onSnapshot: (s: Snapshot<S, D>) => void;
}) {
  const [value, setValue] = useState("");
  const [message, setMessage] = useState("");
  const view = snapshot.secrets[field.name];
  const save = async () => {
    const res = await backend.setSecret(field.name, value);
    if (res.ok && res.snapshot) {
      onSnapshot(res.snapshot);
      setValue("");
      setMessage("Saved.");
    } else {
      setMessage(res.message ?? "Could not save.");
    }
  };
  const clear = async () => {
    const res = await backend.clearSecret(field.name);
    if (res.snapshot) onSnapshot(res.snapshot);
    setMessage("Cleared.");
  };
  return (
    <>
      <PanelSectionRow>
        <TextField
          label={field.label}
          description={
            <span style={note}>
              {view?.set ? `Stored (${view.masked}). Enter a new value to replace it.` : "Not set."}{" "}
              {field.description}
            </span>
          }
          bIsPassword
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!value} onClick={save}>
          Save {field.label}
        </ButtonItem>
      </PanelSectionRow>
      {view?.set && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={clear}>
            Clear {field.label}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {message && (
        <PanelSectionRow>
          <div style={note}>{message}</div>
        </PanelSectionRow>
      )}
    </>
  );
}

export function ConnectionForm<S extends CommonSettings, D>(props: Props<S, D>) {
  const { snapshot, backend, onSnapshot, secretFields } = props;
  const settings = snapshot.settings;
  const [url, setUrl] = useState(settings.base_url);
  const [caFile, setCaFile] = useState(settings.ca_file);
  const [report, setReport] = useState<TestReport | null>(null);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => setUrl(settings.base_url), [settings.base_url]);
  useEffect(() => setCaFile(settings.ca_file), [settings.ca_file]);

  const save = async (values: Partial<S>) => {
    const res = await backend.saveSettings(values);
    if (res.ok && res.snapshot) onSnapshot(res.snapshot);
    else setMessage(res.message ?? "Could not save.");
    return res.ok;
  };

  const test = async () => {
    setTesting(true);
    setReport(null);
    try {
      if (url !== settings.base_url) await save({ base_url: url } as Partial<S>);
      setReport(await backend.testConnection());
    } finally {
      setTesting(false);
    }
  };

  const importFile = async () => {
    const res = await backend.importFromFile();
    if (!res.ok) {
      setMessage(res.message ?? "Import failed.");
      return;
    }
    if (res.snapshot) onSnapshot(res.snapshot);
    setMessage(`Imported ${res.imported?.join(", ")}.`);
    showModal(
      <ConfirmModal
        strTitle="Delete the import file?"
        strDescription={`The file at ${res.path} still holds your credentials in plain text. Delete it now.`}
        strOKButtonText="Delete file"
        strCancelButtonText="Keep it"
        onOK={async () => {
          const del = await backend.deleteImportFile();
          setMessage(del.message ?? "");
        }}
      />,
    );
  };

  return (
    <>
      <PanelSectionRow>
        <TextField
          label="Server address"
          description={<span style={note}>{props.urlDescription}</span>}
          placeholder={props.urlPlaceholder}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={url === settings.base_url} onClick={() => save({ base_url: url } as Partial<S>)}>
          Save address
        </ButtonItem>
      </PanelSectionRow>
      {props.children}
      {secretFields.map((field) => (
        <SecretRow key={field.name} field={field} snapshot={snapshot} backend={backend} onSnapshot={onSnapshot} />
      ))}
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={importFile}
          description={<span style={note}>Reads {snapshot.import_path}</span>}
        >
          Import from file
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={testing} onClick={test}>
          {testing ? "Testing..." : "Test connection"}
        </ButtonItem>
      </PanelSectionRow>
      {report && (
        <PanelSectionRow>
          <Field focusable bottomSeparator="none" label={report.ok ? "Connection works" : "Connection failed"}>
            <div style={note}>
              {report.error && <div>{report.error.message}</div>}
              {report.steps.map((step, i) => (
                <div key={i}>{describeStep(step)}</div>
              ))}
              {report.warnings.map((w, i) => (
                <div key={`w${i}`} style={{ color: "#e0a030" }}>
                  {w}
                </div>
              ))}
              {report.server_version && <div>Server version {report.server_version}</div>}
            </div>
          </Field>
        </PanelSectionRow>
      )}
      {message && (
        <PanelSectionRow>
          <div style={note}>{message}</div>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ToggleField
          label="Verify TLS certificate"
          description={
            settings.tls_verify ? undefined : (
              <span style={{ ...note, color: "#e0a030" }}>
                Off. Anyone on the network path can read and change traffic. Use only on a trusted LAN.
              </span>
            )
          }
          checked={settings.tls_verify}
          onChange={(v) => save({ tls_verify: v } as Partial<S>)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Custom CA file (optional)"
          description={<span style={note}>Full path to a PEM file, for a self-signed server.</span>}
          value={caFile}
          onChange={(e) => setCaFile(e.target.value)}
          onBlur={() => caFile !== settings.ca_file && save({ ca_file: caFile } as Partial<S>)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Notifications"
          checked={settings.notifications}
          onChange={(v) => save({ notifications: v } as Partial<S>)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Notify during games"
          disabled={!settings.notifications}
          checked={settings.notify_in_game}
          onChange={(v) => save({ notify_in_game: v } as Partial<S>)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Check for updates daily"
          checked={settings.update_check}
          onChange={(v) => save({ update_check: v } as Partial<S>)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Remove settings on uninstall"
          checked={settings.remove_data_on_uninstall}
          onChange={(v) => save({ remove_data_on_uninstall: v } as Partial<S>)}
        />
      </PanelSectionRow>
    </>
  );
}
