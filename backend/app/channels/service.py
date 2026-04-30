"""ChannelService — manages the lifecycle of all IM channels."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.channels.base import Channel
from app.channels.manager import DEFAULT_GATEWAY_URL, DEFAULT_LANGGRAPH_URL, ChannelManager
from app.channels.message_bus import MessageBus
from app.channels.store import ChannelStore

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from deerflow.config.app_config import AppConfig

# Channel name → import path for lazy loading
_CHANNEL_REGISTRY: dict[str, str] = {
    "discord": "app.channels.discord:DiscordChannel",
    "feishu": "app.channels.feishu:FeishuChannel",
    "slack": "app.channels.slack:SlackChannel",
    "telegram": "app.channels.telegram:TelegramChannel",
    "wechat": "app.channels.wechat:WechatChannel",
    "wecom": "app.channels.wecom:WeComChannel",
}

# Keys that indicate a user has configured credentials for a channel.
_CHANNEL_CREDENTIAL_KEYS: dict[str, list[str]] = {
    "discord": ["bot_token"],
    "feishu": ["app_id", "app_secret"],
    "slack": ["bot_token", "app_token"],
    "telegram": ["bot_token"],
    "wecom": ["bot_id", "bot_secret"],
    "wechat": ["bot_token"],
}

_CHANNELS_LANGGRAPH_URL_ENV = "DEER_FLOW_CHANNELS_LANGGRAPH_URL"
_CHANNELS_GATEWAY_URL_ENV = "DEER_FLOW_CHANNELS_GATEWAY_URL"
_CHANNEL_SERVICE_LOCK_FILENAME = "channel-service.lock"


def _read_process_start_time(pid: int) -> str | None:
    """Return the Linux /proc start time for a pid when available."""
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return None

    try:
        raw = stat_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    closing_paren = raw.rfind(")")
    if closing_paren == -1:
        return None

    parts = raw[closing_paren + 2 :].split()
    if len(parts) <= 19:
        return None
    return parts[19]


def _build_process_signature(pid: int | None = None) -> dict[str, str | int | None]:
    resolved_pid = os.getpid() if pid is None else pid
    return {
        "pid": resolved_pid,
        "start_time": _read_process_start_time(resolved_pid),
    }


def _is_process_signature_running(signature: dict[str, Any]) -> bool:
    try:
        pid = int(signature.get("pid"))
    except (TypeError, ValueError):
        return False

    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The process exists but belongs to another user; treat as alive.
        pass
    except OSError:
        return False

    expected_start_time = signature.get("start_time")
    if expected_start_time is None:
        return True

    return _read_process_start_time(pid) == str(expected_start_time)


class _ChannelServiceLock:
    """Best-effort cross-process lock for singleton IM channel startup."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._held = False

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_build_process_signature()).encode("utf-8")

        while True:
            try:
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._clear_if_stale():
                    continue
                return False
            else:
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(payload)
                        handle.flush()
                except Exception:
                    try:
                        os.remove(self._path)
                    except OSError:
                        pass
                    raise
                self._held = True
                return True

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            self._path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            logger.warning("Failed to remove channel service lock file: %s", self._path)

    def _clear_if_stale(self) -> bool:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return True
        except (json.JSONDecodeError, OSError):
            payload = None

        if isinstance(payload, dict) and _is_process_signature_running(payload):
            return False

        try:
            self._path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True


def _channel_service_lock_path() -> Path:
    home = Path(os.getenv("DEER_FLOW_HOME", "."))
    return home / "channels" / _CHANNEL_SERVICE_LOCK_FILENAME


def _has_enabled_channel(config: dict[str, Any]) -> bool:
    return any(
        name in _CHANNEL_REGISTRY and isinstance(channel_config, dict) and channel_config.get("enabled", False)
        for name, channel_config in config.items()
    )


def _resolve_service_url(config: dict[str, Any], config_key: str, env_key: str, default: str) -> str:
    value = config.pop(config_key, None)
    if isinstance(value, str) and value.strip():
        return value
    env_value = os.getenv(env_key, "").strip()
    if env_value:
        return env_value
    return default


class ChannelService:
    """Manages the lifecycle of all configured IM channels.

    Reads configuration from ``config.yaml`` under the ``channels`` key,
    instantiates enabled channels, and starts the ChannelManager dispatcher.
    """

    def __init__(self, channels_config: dict[str, Any] | None = None) -> None:
        self.bus = MessageBus()
        self.store = ChannelStore()
        config = dict(channels_config or {})
        langgraph_url = _resolve_service_url(config, "langgraph_url", _CHANNELS_LANGGRAPH_URL_ENV, DEFAULT_LANGGRAPH_URL)
        gateway_url = _resolve_service_url(config, "gateway_url", _CHANNELS_GATEWAY_URL_ENV, DEFAULT_GATEWAY_URL)
        default_session = config.pop("session", None)
        channel_sessions = {name: channel_config.get("session") for name, channel_config in config.items() if isinstance(channel_config, dict)}
        self.manager = ChannelManager(
            bus=self.bus,
            store=self.store,
            langgraph_url=langgraph_url,
            gateway_url=gateway_url,
            default_session=default_session if isinstance(default_session, dict) else None,
            channel_sessions=channel_sessions,
        )
        self._channels: dict[str, Any] = {}  # name -> Channel instance
        self._config = config
        self._running = False
        self._passive_worker = False
        self._startup_lock: _ChannelServiceLock | None = None

    @classmethod
    def from_app_config(cls, app_config: AppConfig | None = None) -> ChannelService:
        """Create a ChannelService from the application config."""
        if app_config is None:
            from deerflow.config.app_config import get_app_config

            app_config = get_app_config()
        channels_config = {}
        # extra fields are allowed by AppConfig (extra="allow")
        extra = app_config.model_extra or {}
        if "channels" in extra:
            channels_config = extra["channels"]
        return cls(channels_config=channels_config)

    async def start(self) -> None:
        """Start the manager and all enabled channels."""
        if self._running:
            return

        if _has_enabled_channel(self._config):
            self._startup_lock = _ChannelServiceLock(_channel_service_lock_path())
            if not self._startup_lock.acquire():
                self._running = True
                self._passive_worker = True
                logger.warning(
                    "Skipping IM channel startup in this worker because another gateway worker owns %s",
                    self._startup_lock.path,
                )
                return

        try:
            await self.manager.start()

            for name, channel_config in self._config.items():
                if not isinstance(channel_config, dict):
                    continue
                if not channel_config.get("enabled", False):
                    cred_keys = _CHANNEL_CREDENTIAL_KEYS.get(name, [])
                    has_creds = any(not isinstance(channel_config.get(k), bool) and channel_config.get(k) is not None and str(channel_config[k]).strip() for k in cred_keys)
                    if has_creds:
                        logger.warning(
                            "Channel '%s' has credentials configured but is disabled. Set enabled: true under channels.%s in config.yaml to activate it.",
                            name,
                            name,
                        )
                    else:
                        logger.info("Channel %s is disabled, skipping", name)
                    continue

                await self._start_channel(name, channel_config)

            self._running = True
            logger.info("ChannelService started with channels: %s", list(self._channels.keys()))
        except Exception:
            self._release_startup_lock()
            raise

    async def stop(self) -> None:
        """Stop all channels and the manager."""
        if not self._running:
            return

        if self._passive_worker:
            self._passive_worker = False
            self._running = False
            self._release_startup_lock()
            logger.info("ChannelService stopped in passive worker")
            return

        for name, channel in list(self._channels.items()):
            try:
                await channel.stop()
                logger.info("Channel %s stopped", name)
            except Exception:
                logger.exception("Error stopping channel %s", name)
        self._channels.clear()

        await self.manager.stop()
        self._running = False
        self._release_startup_lock()
        logger.info("ChannelService stopped")

    async def restart_channel(self, name: str) -> bool:
        """Restart a specific channel. Returns True if successful."""
        if name in self._channels:
            try:
                await self._channels[name].stop()
            except Exception:
                logger.exception("Error stopping channel %s for restart", name)
            del self._channels[name]

        config = self._config.get(name)
        if not config or not isinstance(config, dict):
            logger.warning("No config for channel %s", name)
            return False

        return await self._start_channel(name, config)

    async def _start_channel(self, name: str, config: dict[str, Any]) -> bool:
        """Instantiate and start a single channel."""
        import_path = _CHANNEL_REGISTRY.get(name)
        if not import_path:
            logger.warning("Unknown channel type: %s", name)
            return False

        try:
            from deerflow.reflection import resolve_class

            channel_cls = resolve_class(import_path, base_class=None)
        except Exception:
            logger.exception("Failed to import channel class for %s", name)
            return False

        try:
            channel = channel_cls(bus=self.bus, config=config)
            await channel.start()
            self._channels[name] = channel
            logger.info("Channel %s started", name)
            return True
        except Exception:
            logger.exception("Failed to start channel %s", name)
            return False

    def _release_startup_lock(self) -> None:
        if self._startup_lock is None:
            return
        self._startup_lock.release()
        self._startup_lock = None

    def get_status(self) -> dict[str, Any]:
        """Return status information for all channels."""
        channels_status = {}
        for name in _CHANNEL_REGISTRY:
            config = self._config.get(name, {})
            enabled = isinstance(config, dict) and config.get("enabled", False)
            running = name in self._channels and self._channels[name].is_running
            channels_status[name] = {
                "enabled": enabled,
                "running": running,
            }
        return {
            "service_running": self._running,
            "active_instance": self._running and not self._passive_worker,
            "channels": channels_status,
        }

    def get_channel(self, name: str) -> Channel | None:
        """Return a running channel instance by name when available."""
        return self._channels.get(name)


# -- singleton access -------------------------------------------------------

_channel_service: ChannelService | None = None


def get_channel_service() -> ChannelService | None:
    """Get the singleton ChannelService instance (if started)."""
    return _channel_service


async def start_channel_service(app_config: AppConfig | None = None) -> ChannelService:
    """Create and start the global ChannelService from app config."""
    global _channel_service
    if _channel_service is not None:
        return _channel_service
    _channel_service = ChannelService.from_app_config(app_config)
    await _channel_service.start()
    return _channel_service


async def stop_channel_service() -> None:
    """Stop the global ChannelService."""
    global _channel_service
    if _channel_service is not None:
        await _channel_service.stop()
        _channel_service = None
