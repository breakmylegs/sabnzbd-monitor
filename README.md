# SABnzbd Monitor

A Decky Loader plugin. Watch and control a SABnzbd server from the Quick Access Menu on any Decky handheld.

- Speed, time left and size left, with pause and resume.
- Timed pause for 15, 30 or 60 minutes, and a speed limit of 25, 50, 75 or 100 percent.
- Jobs in post-processing, with the current step.
- The first 8 jobs in the queue with progress, time left, status and priority. Pause, resume, move to the top or bottom, change priority or category, or delete each one.
- The last 5 completed or failed jobs. Retry a failed job, see which step failed, or remove a job from the history.
- A full-screen history of the last 50 jobs, with Retry all failed jobs and Remove all failed jobs.
- Free disk space for the download and complete folders, quota left, and download totals per day, week, month and server.
- A warnings badge when SABnzbd has warnings. Read and clear them.
- Optional: pause downloads, or limit them to 25 or 50 percent, while a game runs. They go back when it ends. Off by default.
- The connection test warns when the server is older than SABnzbd 5.1.3, which fixed ways to skip the login.
- A toast when a job completes or fails, with the reason. Optional during games.

Issues and source: [breakmylegs/decky-plugins](https://github.com/breakmylegs/decky-plugins). This repo is a mirror for releases.

## Install

1. Decky Settings, General, turn on Developer mode.
2. Decky Settings, Developer, Install Plugin from URL.
3. Enter:

```
https://github.com/breakmylegs/sabnzbd-monitor/releases/latest/download/sabnzbd-monitor.zip
```

Needs Decky Loader 3.0.4 or later. If you installed 0.1.0 or earlier, uninstall it first, then install this one. Your settings are kept.

## Updating

Open the plugin and scroll to Updates. It shows your version and what the last check found.

- **Check for updates** asks GitHub for the latest release now.
- **Update now** appears when a newer version is out. Confirm in Decky's prompt. Your settings and keys are kept.
- **Reinstall latest** appears otherwise, and installs the latest release again the same way.
- **Copy install link** copies the link for Decky Settings, Developer, Install Plugin from URL. The link is shown under it, in case copying is not available in Game Mode.

Leave "Remove settings on uninstall" off, because an update counts as an uninstall.

## Set up

1. Open the plugin in the Quick Access Menu, then Show settings.
2. Enter the SABnzbd address, for example `http://192.168.x.x:8090`. If SABnzbd runs under a path, include it, for example `https://sab.example.com/sabnzbd`.
3. Enter the **full API key** from SABnzbd Config, General. The NZB key only adds jobs and cannot read the queue.
4. Test connection. It reports each step.

To avoid typing the key on the on-screen keyboard, create `~/Documents/decky-import/sabnzbd-monitor.json` in Desktop Mode:

```json
{ "base_url": "http://192.168.x.x:8090", "api_key": "your full API key" }
```

Press Import from file, then delete the file when asked.

### Connecting by host name

SABnzbd checks the host name of each request. If you connect with a name such as `sab.example.com` rather than an IP address, add that name to `host_whitelist` in SABnzbd Config, Special, then restart SABnzbd. The connection test tells you when this is the problem.

### Configuration lock

If SABnzbd's configuration is locked, timed pause and the speed limit fail. The panel says so. Everything else keeps working.

### Port 8080

Steam and Decky use port 8080 on the handheld. SABnzbd defaults to 8080 too. If SABnzbd runs on the handheld itself, move it to another port, such as 8090. The connection test warns you.

## Screenshots

To follow after on-device testing.

## Supported versions

| Component | Version |
|---|---|
| SABnzbd | 5.1. The 5.2 betas keep the same API |
| Decky Loader | 3.0 and later. 3.3.0 tested |

## Data and privacy

The plugin talks only to the server you enter. The API key stays in `~/homebrew/settings/sabnzbd-monitor/secrets.json` (mode 600) and never reaches the panel, logs or events. Once a day it checks GitHub for a newer release. Turn that off in settings. Full detail in [PRIVACY.md](https://github.com/breakmylegs/decky-plugins/blob/main/docs/PRIVACY.md).

## Licence

GPL-3.0. See `LICENSE`.
