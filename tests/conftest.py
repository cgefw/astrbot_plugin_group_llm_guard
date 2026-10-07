"""Test helpers: stub the parts of astrbot.api that main.py imports."""

from __future__ import annotations

import asyncio
import enum
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest


class AstrBotConfig(dict):
    def save_config(self) -> None:
        pass


class MessageType(enum.Enum):
    GROUP_MESSAGE = "GroupMessage"
    FRIEND_MESSAGE = "FriendMessage"


class _CommandGroup:
    def command(self, *args, **kwargs):
        return lambda func: func


def _passthrough(*args, **kwargs):
    return lambda func: func


class _Star:
    def __init__(self, context) -> None:
        self.context = context


def _astrbot_stubs() -> dict[str, types.ModuleType]:
    api = types.ModuleType("astrbot.api")
    api.AstrBotConfig = AstrBotConfig
    api.logger = logging.getLogger("astrbot")

    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = object
    event.filter = types.SimpleNamespace(
        PermissionType=types.SimpleNamespace(ADMIN="admin"),
        on_llm_request=_passthrough,
        permission_type=_passthrough,
        command_group=lambda *args, **kwargs: lambda func: _CommandGroup(),
    )

    platform = types.ModuleType("astrbot.api.platform")
    platform.MessageType = MessageType

    provider = types.ModuleType("astrbot.api.provider")
    provider.ProviderRequest = object

    star = types.ModuleType("astrbot.api.star")
    star.Context = object
    star.Star = _Star

    return {
        "astrbot": types.ModuleType("astrbot"),
        "astrbot.api": api,
        "astrbot.api.event": event,
        "astrbot.api.platform": platform,
        "astrbot.api.provider": provider,
        "astrbot.api.star": star,
    }


def _load_plugin_main() -> types.ModuleType:
    # Stubs only live in sys.modules while main.py is imported, so a real
    # astrbot package in the same interpreter is left untouched.
    stubs = _astrbot_stubs()
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            "group_llm_guard_main", Path(__file__).resolve().parent.parent / "main.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


plugin_main = _load_plugin_main()


class FakeEvent:
    """Mimics an aiocqhttp event: a group's session_id is its group_id unless
    session isolation (unique_session) gives it a per-user session_id."""

    def __init__(
        self,
        group_id: str = "",
        sender_id: str = "10001",
        platform_name: str = "aiocqhttp",
        platform_id: str = "default",
        session_id: str = "",
    ) -> None:
        self.group_id = group_id
        self.platform_name = platform_name
        self.platform_id = platform_id
        self.session_id = session_id or group_id or sender_id
        message_type = MessageType.GROUP_MESSAGE if group_id else MessageType.FRIEND_MESSAGE
        self.unified_msg_origin = f"{platform_id}:{message_type.value}:{self.session_id}"
        self.extras: dict = {}
        self.stopped = False
        self.sent: list = []

    def get_group_id(self) -> str:
        return self.group_id

    def get_platform_name(self) -> str:
        return self.platform_name

    def get_platform_id(self) -> str:
        return self.platform_id

    def get_extra(self, key, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        return text

    async def send(self, result) -> None:
        self.sent.append(result)


@pytest.fixture
def make_event():
    return FakeEvent


@pytest.fixture
def make_plugin():
    def factory(**config):
        return plugin_main.GroupLLMGuard(None, AstrBotConfig(config))

    return factory


@pytest.fixture
def collect():
    """Run an async-generator command handler and return what it yielded."""

    def run(agen) -> list:
        async def drain():
            return [item async for item in agen]

        return asyncio.run(drain())

    return run


@pytest.fixture
def llm_blocked():
    """Run the on_llm_request hook and report whether it stopped the event."""

    def run(plugin, event) -> bool:
        request = types.SimpleNamespace(prompt="hello")
        asyncio.run(plugin.block_group_llm_chat(event, request))
        return event.stopped

    return run
