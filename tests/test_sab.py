import asyncio
import json
import logging

import pytest

from plugin_core.errors import AUTH, FORBIDDEN, PluginError
from plugin_core.http import parse_base_url
from sabmon import states
from sabmon.client import HINT_CONFIG_LOCKED, HINT_KEY_INCORRECT, SabClient
from sabmon.service import SabService, parse_version
from sabmon.sync import SabState, TransitionTracker, project

mock_sabnzbd = pytest.importorskip("mock_sabnzbd")

KEY = "f" * 32
NZB_KEY = "e" * 32


@pytest.fixture()
def mock():
    servers = []

    def make(**kwargs):
        kwargs.setdefault("api_key", KEY)
        kwargs.setdefault("nzb_key", NZB_KEY)
        server = mock_sabnzbd.MockSab(**kwargs)
        server.start()
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.stop()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def make_service(tmp_path, events=None):
    events = events if events is not None else []

    async def emit(name, payload):
        events.append((name, payload))

    return SabService(
        settings_dir=str(tmp_path / "settings"),
        runtime_dir=str(tmp_path / "runtime"),
        plugin_dir=str(tmp_path / "plugin"),
        user_home=str(tmp_path / "home"),
        version="0.1.0",
        emit=emit,
        logger=logging.getLogger("test"),
    )


def configured(server, tmp_path, events=None):
    service = make_service(tmp_path, events)
    service.save_settings({"base_url": server.url})
    service.set_secret("api_key", KEY)
    return service


# Mapping and coercion


@pytest.mark.parametrize(
    "status,label",
    [("Downloading", "Downloading"), ("Queued", "Queued"), ("Paused", "Paused"),
     ("Propagating", "Waiting for propagation"), ("Fetching", "Fetching extra par2"),
     ("Checking", "Pre-checking"), ("Grabbing", "Fetching NZB")],
)
def test_queue_labels(status, label):
    assert states.queue_label(status) == label


@pytest.mark.parametrize(
    "status,label",
    [("Queued", "Waiting for post-processing"), ("QuickCheck", "Verifying"), ("Verifying", "Verifying"),
     ("Repairing", "Repairing"), ("Extracting", "Extracting"), ("Moving", "Moving"),
     ("Running", "Running script"), ("Fetching", "Fetching extra par2"), ("Completed", "Completed"),
     ("Failed", "Failed")],
)
def test_history_labels(status, label):
    assert states.history_label(status) == label


def test_unknown_status_shows_the_raw_value():
    assert states.queue_label("Brandnew") == "Brandnew"
    assert states.history_label(None) == "Unknown"


@pytest.mark.parametrize(
    "raw,value", [("Normal", 0), ("high", 1), ("Low", -1), ("Force", 2), (1, 1), ("2", 2), ("-1", -1),
                  ("Repair", None), (True, None), (9, None)]
)
def test_priority_coercion(raw, value):
    assert states.priority_value(raw) == value


def test_numbers_and_times_coerce_from_strings():
    assert states.num("5324.80") == 5324.8
    assert states.num("") == 0.0 and states.num(None, 7) == 7
    assert states.seconds("0:12:00") == 720
    assert states.seconds("1:02:03:04") == 93784
    assert states.seconds("0:00:00") is None and states.seconds("soon") is None
    assert states.pause_seconds("14:30") == 870
    assert states.pause_seconds("0") is None and states.pause_seconds("-0:05") is None


def test_projection_shapes_and_post_processing():
    state = SabState()
    state.apply(
        {"status": "Downloading", "paused": False, "kbpersec": "1000.00", "timeleft": "0:10:00",
         "sizeleft": "1.2 GB", "mbleft": "1200.00", "noofslots_total": 12, "speedlimit": "50",
         "have_warnings": "2", "pause_int": "0",
         "slots": [{"nzo_id": f"SABnzbd_nzo_{i}", "filename": f"job{i}", "status": "Queued",
                    "percentage": "10", "timeleft": "0:01:00", "priority": "Normal", "cat": "*"} for i in range(12)]},
        {"last_history_update": 5, "slots": [
            {"nzo_id": "p1", "name": "unpacking", "status": "Extracting", "loaded": True, "action_line": "Unpacking"},
            {"nzo_id": "d1", "name": "done", "status": "Completed", "loaded": False},
            {"nzo_id": "f1", "name": "broken", "status": "Failed", "fail_message": "Repair failed", "loaded": False},
        ]},
    )
    out = project(state)
    assert out["server"]["speed"] == 1_024_000 and out["server"]["warnings"] == 2
    assert out["server"]["speedlimit"] == 50 and out["server"]["timeleft"] == 600
    assert len(out["queue"]) == 8 and out["queue"][0]["category"] == ""
    assert [p["label"] for p in out["post_processing"]] == ["Extracting"]
    assert [r["id"] for r in out["recent"]] == ["d1", "f1"]
    assert state.last_history_update == 5


def test_history_none_keeps_the_cache():
    state = SabState()
    state.apply({}, {"last_history_update": 3, "slots": [{"nzo_id": "a", "status": "Completed"}]})
    state.apply({}, None)
    assert len(state.history_slots) == 1 and state.last_history_update == 3


def test_tracker_skips_baseline_and_toasts_once_with_fail_message():
    state, tracker = SabState(), TransitionTracker()
    state.apply({}, {"slots": [{"nzo_id": "old", "name": "old", "status": "Completed"}]})
    assert tracker.changes(state) == []
    state.apply({}, {"slots": [
        {"nzo_id": "new", "name": "new", "status": "Failed", "fail_message": "Out of retention"},
        {"nzo_id": "pp", "name": "pp", "status": "Extracting"},
        {"nzo_id": "old", "name": "old", "status": "Completed"},
    ]})
    toasts = tracker.changes(state)
    assert [(t["kind"], t["body"]) for t in toasts] == [("failed", "new. Out of retention")]
    state.apply({}, {"slots": [{"nzo_id": "pp", "name": "pp", "status": "Completed"},
                               {"nzo_id": "new", "name": "new", "status": "Failed"}]})
    assert [t["key"] for t in tracker.changes(state)] == ["completed:pp"]
    assert tracker.changes(state) == []


# Client against the mock


def test_version_needs_no_key(mock):
    server = mock()
    assert SabClient(parse_base_url(server.url), "").version() == "5.1.3"


def test_key_errors_are_403_and_classified(mock):
    server = mock()
    base = parse_base_url(server.url)
    with pytest.raises(PluginError) as info:
        SabClient(base, "x" * 32).queue()
    assert info.value.kind == AUTH and info.value.message == HINT_KEY_INCORRECT
    with pytest.raises(PluginError) as info:
        SabClient(base, NZB_KEY).queue()
    assert info.value.kind == AUTH and "NZB key" in info.value.message


def test_empty_403_body_still_fails_cleanly(mock):
    server = mock(api_warnings=False)
    with pytest.raises(PluginError) as info:
        SabClient(parse_base_url(server.url), "x" * 32).queue()
    assert info.value.kind == FORBIDDEN and "full key" in info.value.message


def test_config_locked_is_reported(mock):
    server = mock(config_locked=True)
    client = SabClient(parse_base_url(server.url), KEY)
    with pytest.raises(PluginError) as info:
        client.set_speed_limit(50)
    assert info.value.message == HINT_CONFIG_LOCKED


def test_history_incremental(mock):
    server = mock()
    client = SabClient(parse_base_url(server.url), KEY)
    first = client.history(limit=10)
    assert client.history(limit=10, last_update=first["last_history_update"]) is None
    server.state.finish_first()
    assert client.history(limit=10, last_update=first["last_history_update"]) is not None


def test_job_actions_send_opaque_ids(mock):
    server = mock()
    client = SabClient(parse_base_url(server.url), KEY)
    nzo = server.state.queue[0]["nzo_id"]
    client.pause_job(nzo)
    assert server.state.queue[0]["status"] == "Paused"
    client.set_priority(nzo, 2)
    assert server.state.queue[0]["priority"] == "Force"
    client.delete_jobs([nzo], delete_files=True)
    assert server.state.calls[-1] == {"mode": "queue", "output": "json", "apikey": KEY, "name": "delete",
                                      "value": nzo, "del_files": "1"}
    with pytest.raises(ValueError):
        client.delete_jobs(["a,b"], delete_files=False)
    with pytest.raises(ValueError):
        client.set_priority(nzo, 5)


# Service


def test_service_poll_toasts_and_no_key_leak(mock, tmp_path):
    server = mock()
    events = []
    service = configured(server, tmp_path, events)

    async def scenario():
        await service.poller.poll_once()
        server.state.finish_first(failed=True)
        await service.poller.poll_once()
        await service.poller.poll_once()

    _run(scenario())
    toasts = [p for n, p in events if n == "notify"]
    assert len(toasts) == 1 and toasts[0]["kind"] == "failed" and "repair" in toasts[0]["body"].lower()
    assert service.last_data["server"]["jobs"] == 1
    assert KEY not in json.dumps(events) + json.dumps(service.snapshot())


def test_service_post_processing_and_recent(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    server.state.start_post_processing("Repairing")
    _run(service.poller.poll_once())
    data = service.last_data
    assert [p["label"] for p in data["post_processing"]] == ["Repairing"]
    assert [r["label"] for r in data["recent"]] == ["Completed"]


def test_service_actions(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    assert _run(service.pause_for(30)) == {"ok": True}
    assert server.state.paused and server.state.pause_int == "30:00"
    assert _run(service.resume_all()) == {"ok": True}
    assert _run(service.set_speed_limit(75)) == {"ok": True} and server.state.speedlimit == "75"
    assert _run(service.pause_for(45))["ok"] is False
    assert _run(service.set_speed_limit(10))["ok"] is False
    nzo = server.state.queue[0]["nzo_id"]
    assert _run(service.job_action("pause", nzo)) == {"ok": True}
    assert _run(service.job_action("explode", nzo))["ok"] is False
    assert _run(service.delete_job(nzo, False)) == {"ok": True}
    assert _run(service.delete_job("", False))["ok"] is False


def test_service_flags_config_lock(mock, tmp_path):
    server = mock(config_locked=True)
    service = configured(server, tmp_path)
    result = _run(service.set_speed_limit(50))
    assert result["ok"] is False and result["error"]["message"] == HINT_CONFIG_LOCKED
    _run(service.poller.poll_once())
    assert service.last_data["config_locked"] is True
    server.state.config_locked = False
    assert _run(service.set_speed_limit(50))["ok"]
    _run(service.poller.poll_once())
    assert service.last_data["config_locked"] is False


def test_warnings(mock, tmp_path):
    server = mock()
    server.state.have_warnings = "1"
    service = configured(server, tmp_path)
    result = _run(service.get_warnings())
    assert result["ok"] and result["warnings"][0]["type"] == "WARNING"


def test_connection_test(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    report = _run(service.test_connection())
    assert report["ok"] and report["server_version"] == "5.1.3" and report["auth_path"] == "api_key"

    service.set_secret("api_key", NZB_KEY)
    report = _run(service.test_connection())
    assert report["failed_step"] == "auth" and "NZB key" in report["steps"][-1]["detail"]

    service.clear_secret("api_key")
    report = _run(service.test_connection())
    assert report["failed_step"] == "auth"

    service.save_settings({"base_url": server.url + "/nope"})
    service.set_secret("api_key", KEY)
    report = _run(service.test_connection())
    assert report["failed_step"] == "version"


def test_url_base_prefix(mock, tmp_path):
    server = mock(url_base="/sabnzbd")
    service = make_service(tmp_path)
    service.save_settings({"base_url": server.url + "/sabnzbd/"})
    service.set_secret("api_key", KEY)
    assert _run(service.test_connection())["ok"]


def test_connection_test_warns_on_local_8080(tmp_path):
    service = make_service(tmp_path)
    service.save_settings({"base_url": "http://127.0.0.1:8080"})
    report = _run(service.test_connection())
    assert any("8090" in w for w in report["warnings"])


# Disk, quota, queue order, categories, warnings, history page and stats


def test_projection_disk_quota_index_and_stage_log(mock, tmp_path):
    server = mock()
    server.state.finish_first(failed=True)
    service = configured(server, tmp_path)
    _run(service.poller.poll_once())
    data = service.last_data
    assert data["server"]["disk_incomplete"] == 120.5 and data["server"]["disk_complete"] == 1450.25
    assert data["server"]["quota_left"] is None
    assert data["queue"][0]["index"] == 0
    failed = data["recent"][0]
    assert failed["status"] == "Failed"
    # HTML from SABnzbd is stripped.
    assert failed["stage_log"] == [{"name": "Repair", "actions": ["Repair failed, not enough repair blocks  (need 12)"]}]


def test_quota_shows_only_when_set():
    state = SabState()
    state.apply({"have_quota": "True", "left_quota": "50 G", "diskspace1": ""}, None)
    out = project(state)["server"]
    assert out["quota_left"] == "50 G" and out["disk_incomplete"] is None
    state.apply({"have_quota": "False", "left_quota": "50 G"}, None)
    assert project(state)["server"]["quota_left"] is None


def test_move_job_top_and_bottom(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    _run(service.poller.poll_once())
    first, second = (s["nzo_id"] for s in server.state.queue)
    assert _run(service.move_job(second, "top")) == {"ok": True}
    assert [s["nzo_id"] for s in server.state.queue] == [second, first]
    assert server.state.calls[-1]["value2"] == "0"
    _run(service.poller.poll_once())
    assert _run(service.move_job(second, "bottom")) == {"ok": True}
    assert server.state.calls[-1]["value2"] == "1"
    assert [s["nzo_id"] for s in server.state.queue] == [first, second]
    assert _run(service.move_job(second, "sideways"))["ok"] is False


def test_move_job_refuses_before_the_queue_loads_and_reports_no_move(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    job = server.state.queue[0]["nzo_id"]
    # No poll yet, so the job count is unknown.
    result = _run(service.move_job(job, "bottom"))
    assert result["ok"] is False and "queue to load" in result["error"]["message"]
    _run(service.poller.poll_once())
    server.state.queue.pop()
    # The panel still thinks there are two jobs. SABnzbd answers position -1.
    result = _run(service.move_job(job, "bottom"))
    assert result["ok"] is False and "did not move" in result["error"]["message"]


def test_categories_are_cached_and_checked(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    job = server.state.queue[0]["nzo_id"]
    assert _run(service.get_categories()) == {"ok": True, "categories": ["*", "movies", "software"]}
    server.state.categories.append("games")
    assert "games" in _run(service.get_categories())["categories"], "each opening fetches again"
    assert _run(service.change_category(job, "software")) == {"ok": True}
    assert server.state.queue[0]["cat"] == "software"
    assert _run(service.change_category(job, "*")) == {"ok": True}
    assert _run(service.change_category(job, "nonsense"))["ok"] is False


def test_clear_warnings(mock, tmp_path):
    server = mock()
    server.state.have_warnings = "1"
    service = configured(server, tmp_path)
    assert _run(service.clear_warnings()) == {"ok": True}
    assert server.state.have_warnings == "0"


def test_history_page_retry_and_delete(mock, tmp_path):
    server = mock()
    server.state.finish_first(failed=True)
    service = configured(server, tmp_path)
    page = _run(service.get_history())
    assert page["ok"] and page["total"] == 2 and page["limit"] == 50
    failed = _run(service.get_history(failed_only=True))
    assert [j["status"] for j in failed["jobs"]] == ["Failed"]
    assert server.state.calls[-1]["failed_only"] == "1"

    job = failed["jobs"][0]["id"]
    assert _run(service.retry_job(job)) == {"ok": True}
    assert [h["status"] for h in server.state.history] == ["Completed"]
    assert server.state.queue[-1]["filename"] == "Example.Linux.ISO"

    done = server.state.history[0]["nzo_id"]
    assert _run(service.delete_history(done, False)) == {"ok": True}
    assert server.state.history == [] and "del_files" not in server.state.calls[-1]
    assert _run(service.delete_history("", False))["ok"] is False


def test_retry_all_and_clear_failed(mock, tmp_path):
    server = mock()
    server.state.finish_first(failed=True)
    server.state.finish_first(failed=True)
    service = configured(server, tmp_path)
    assert _run(service.retry_all()) == {"ok": True}
    assert server.state.history[0]["status"] == "Completed" and len(server.state.history) == 1

    server.state.finish_first(failed=True)
    assert _run(service.delete_history("failed", True)) == {"ok": True}
    assert server.state.calls[-1]["value"] == "failed" and server.state.calls[-1]["del_files"] == "1"
    assert all(h["status"] != "Failed" for h in server.state.history)


def test_server_stats(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    stats = _run(service.get_server_stats())
    assert stats["ok"] and stats["totals"] == {"day": 2e9, "week": 9e9, "month": 4e10, "total": 9e11}
    assert [s["name"] for s in stats["servers"]] == ["news.example.com", "backup.example.net"]
    assert stats["servers"][1]["day"] == 0


@pytest.mark.parametrize(
    "text,version",
    [("5.1.3", (5, 1, 3)), ("5.2.0Beta1", (5, 2, 0)), ("4.5.5", (4, 5, 5)), ("develop", ())],
)
def test_parse_version(text, version):
    assert parse_version(text) == version


def test_connection_test_warns_on_old_server(mock, tmp_path):
    server = mock(version="5.1.0")
    service = configured(server, tmp_path)
    report = _run(service.test_connection())
    assert report["ok"] and any("5.1.3" in w for w in report["warnings"])
    current = mock(version="5.1.3")
    service.save_settings({"base_url": current.url})
    report = _run(service.test_connection())
    assert not any("5.1.3" in w for w in report["warnings"])


def test_unknown_game_action_is_rejected(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError):
        service.save_settings({"game_action": "explode"})
    assert service.settings.get("game_action") == "off"


# Game-time pause or speed limit


def _game(service, running):
    async def scenario():
        service.set_game_running(running)
        if service._game_task:
            await service._game_task

    _run(scenario())


def test_game_action_off_by_default(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    _game(service, True)
    assert server.state.paused is False and server.state.speedlimit == "100"


def test_game_pause_and_resume(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    service.save_settings({"game_action": "pause"})
    _game(service, True)
    assert server.state.paused is True
    _game(service, False)
    assert server.state.paused is False and service.game_memory.get() is None


def test_game_pause_leaves_user_pauses_alone(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    service.save_settings({"game_action": "pause"})
    server.state.paused = True
    _game(service, True)
    _game(service, False)
    assert server.state.paused is True

    # A timed pause set during the game stays.
    server.state.paused = False
    _game(service, True)
    server.state.pause_int = "25:00"
    _game(service, False)
    assert server.state.paused is True and service.game_memory.get() is None


def test_game_speed_limit_and_restore(mock, tmp_path):
    server = mock()
    server.state.speedlimit = "75"
    service = configured(server, tmp_path)
    service.save_settings({"game_action": "limit_25"})
    _game(service, True)
    assert server.state.speedlimit == "25"
    record = service.game_memory.get()
    assert record["limit"] == 25 and record["previous"] == 75 and record["server"]
    _game(service, False)
    assert server.state.speedlimit == "75"

    # Already slower than the game limit: nothing changes.
    server.state.speedlimit = "10"
    _game(service, True)
    assert server.state.speedlimit == "10" and service.game_memory.get() is None

    # The user picks another limit during the game. It stays.
    server.state.speedlimit = "100"
    _game(service, True)
    server.state.speedlimit = "50"
    _game(service, False)
    assert server.state.speedlimit == "50"


def test_game_undo_waits_until_the_panel_reports(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    service.save_settings({"game_action": "pause"})
    _game(service, True)
    fresh = make_service(tmp_path)
    _run(fresh.poller.poll_once())
    assert server.state.paused is True, "a game may still be running"
    _game(fresh, False)
    assert server.state.paused is False


def test_game_limit_restore_gives_up_when_config_locked(mock, tmp_path):
    server = mock()
    service = configured(server, tmp_path)
    service.save_settings({"game_action": "limit_50"})
    _game(service, True)
    assert server.state.speedlimit == "50"
    server.state.config_locked = True
    _game(service, False)
    # A lock will not clear by itself, so the plugin stops trying.
    assert service.game_memory.get() is None
