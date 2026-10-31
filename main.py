"""Decky entry point. A thin adapter over sabmon.service.SabService."""

import os

import decky

from plugin_core.service import error_result
from sabmon.service import SabService


def _version() -> str:
    return os.environ.get("DECKY_PLUGIN_VERSION", "0.0.0")


class Plugin:
    service: SabService

    async def _main(self):
        self.service = SabService(
            settings_dir=decky.DECKY_PLUGIN_SETTINGS_DIR,
            runtime_dir=decky.DECKY_PLUGIN_RUNTIME_DIR,
            plugin_dir=decky.DECKY_PLUGIN_DIR,
            user_home=decky.DECKY_USER_HOME,
            version=_version(),
            emit=decky.emit,
            logger=decky.logger,
        )
        await self.service.start()
        decky.logger.info("sabnzbd-monitor started")

    async def _unload(self):
        await self.service.stop()

    async def _uninstall(self):
        await self.service.uninstall()

    # Frontend API. Every method returns plain JSON and never a secret.

    async def get_snapshot(self):
        return self.service.snapshot()

    async def save_settings(self, values):
        try:
            return {"ok": True, "snapshot": self.service.save_settings(values)}
        except ValueError as err:
            return {"ok": False, "message": str(err)}

    async def set_secret(self, name, value):
        try:
            return {"ok": True, "snapshot": self.service.set_secret(name, value)}
        except ValueError as err:
            return {"ok": False, "message": str(err)}

    async def clear_secret(self, name):
        return {"ok": True, "snapshot": self.service.clear_secret(name)}

    async def import_from_file(self):
        return self.service.import_from_file()

    async def delete_import_file(self):
        return self.service.delete_import_file()

    async def test_connection(self):
        try:
            return await self.service.test_connection()
        except Exception as exc:  # noqa: BLE001
            return error_result(exc)

    async def set_visible(self, visible):
        self.service.set_visible(visible)

    async def set_route_visible(self, visible):
        self.service.set_route_visible(visible)

    async def set_game_running(self, running):
        self.service.set_game_running(running)

    async def refresh(self):
        self.service.poller.wake()

    async def check_update(self, force=False):
        return await self.service.check_update(force)

    async def _guard(self, coro):
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001
            return error_result(exc)

    async def pause_all(self):
        return await self._guard(self.service.pause_all())

    async def resume_all(self):
        return await self._guard(self.service.resume_all())

    async def pause_for(self, minutes):
        return await self._guard(self.service.pause_for(minutes))

    async def set_speed_limit(self, percent):
        return await self._guard(self.service.set_speed_limit(percent))

    async def job_action(self, action, nzo_id):
        return await self._guard(self.service.job_action(action, nzo_id))

    async def set_priority(self, nzo_id, priority):
        return await self._guard(self.service.set_priority(nzo_id, priority))

    async def delete_job(self, nzo_id, delete_files):
        return await self._guard(self.service.delete_job(nzo_id, delete_files))

    async def get_warnings(self):
        return await self._guard(self.service.get_warnings())

    async def clear_warnings(self):
        return await self._guard(self.service.clear_warnings())

    async def move_job(self, nzo_id, where):
        return await self._guard(self.service.move_job(nzo_id, where))

    async def get_categories(self):
        return await self._guard(self.service.get_categories())

    async def change_category(self, nzo_id, category):
        return await self._guard(self.service.change_category(nzo_id, category))

    async def get_history(self, failed_only=False):
        return await self._guard(self.service.get_history(failed_only))

    async def retry_job(self, nzo_id):
        return await self._guard(self.service.retry_job(nzo_id))

    async def retry_all(self):
        return await self._guard(self.service.retry_all())

    async def delete_history(self, nzo_id, delete_files=False):
        return await self._guard(self.service.delete_history(nzo_id, delete_files))

    async def get_server_stats(self):
        return await self._guard(self.service.get_server_stats())
