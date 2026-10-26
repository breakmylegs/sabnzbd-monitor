import { describe, expect, it } from "vitest";
import { historyDetail, jobTitle, queueDetail, serverSummary, speedLimitOption } from "./rows";
import type { HistoryJob, QueueJob, SabData } from "./types";

const job: QueueJob = {
  id: "SABnzbd_nzo_1",
  name: "Example",
  status: "Downloading",
  label: "Downloading",
  percent: 40,
  timeleft: 600,
  sizeleft: "1.2 GB",
  priority: 0,
  priority_label: "Normal",
  category: "",
  paused: false,
};

const server: SabData["server"] = {
  status: "Downloading",
  paused: false,
  speed: 5_000_000,
  timeleft: 720,
  sizeleft: "3.1 GB",
  mbleft: 3200,
  jobs: 2,
  speedlimit: 100,
  warnings: 0,
  pause_left: null,
};

const done: HistoryJob = {
  id: "h",
  name: "Done",
  status: "Completed",
  label: "Completed",
  fail_message: "",
  size: "2.0 GB",
  completed: 1,
  action_line: "",
};

describe("queue rows", () => {
  it("shows label, percent, time and size", () => {
    expect(queueDetail(job)).toBe("Downloading | 40% | 10m 0s | 1.2 GB left");
  });

  it("drops time while paused and shows a non-normal priority", () => {
    expect(queueDetail({ ...job, paused: true, label: "Paused", priority_label: "High" })).toBe(
      "Paused | 40% | 1.2 GB left | High",
    );
  });

  it("names unnamed jobs", () => {
    expect(jobTitle({ name: "" })).toBe("Unnamed job");
  });
});

describe("history rows", () => {
  it("shows the fail message", () => {
    expect(historyDetail({ ...done, status: "Failed", label: "Failed", fail_message: "Out of retention" })).toBe(
      "Failed. Out of retention",
    );
  });

  it("shows the post-processing step", () => {
    expect(historyDetail({ ...done, status: "Extracting", label: "Extracting", action_line: "Unpacking 1/3" })).toBe(
      "Extracting. Unpacking 1/3",
    );
  });

  it("shows size when complete", () => {
    expect(historyDetail(done)).toBe("Completed | 2.0 GB");
  });
});

describe("server summary", () => {
  it("summarises a download", () => {
    expect(serverSummary(server)).toBe("5.00 MB/s | 12m 0s left | 3.1 GB");
  });

  it("shows a timed pause and idle", () => {
    expect(serverSummary({ ...server, paused: true, pause_left: 900 })).toBe("Paused, resumes in 15m 0s");
    expect(serverSummary({ ...server, jobs: 0 })).toBe("Idle");
  });

  it("snaps the speed limit to a preset", () => {
    expect(speedLimitOption(60)).toBe(50);
    expect(speedLimitOption(100)).toBe(100);
    expect(speedLimitOption(0)).toBe(25);
  });
});
