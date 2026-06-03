from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star


PLUGIN_MARK_BLOCKED = "astrbot_plugin_group_llm_guard_blocked"
COMMAND_FILTER_CLASS_NAMES = {"CommandFilter", "CommandGroupFilter"}


class GroupLLMGuard(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.on_llm_request(priority=10_000)
    async def block_group_llm_chat(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """Block LLM requests from configured groups unless they come from commands."""
        group_id = self._group_id(event)
        if not group_id or not self._is_group_disabled(event, group_id):
            return

        if self._allow_command_llm() and self._is_command_event(event):
            return

        event.set_extra(PLUGIN_MARK_BLOCKED, True)
        notice = str(self.config.get("blocked_reply", "") or "").strip()
        if notice:
            await event.send(event.plain_result(notice))

        logger.info(
            "GroupLLMGuard blocked LLM chat: group=%s umo=%s prompt=%s",
            group_id,
            event.unified_msg_origin,
            (getattr(req, "prompt", "") or "")[:80],
        )
        event.stop_event()

    @filter.command_group("groupllm", alias={"群llm", "gllm"})
    def groupllm(self):
        """管理指定群聊的 LLM 聊天开关。"""
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @groupllm.command("off", alias={"disable", "关闭"})
    async def disable_group_llm(self, event: AstrMessageEvent, group_id: str = ""):
        """关闭当前群或指定群的 LLM 聊天。"""
        target_group = self._resolve_group_arg(event, group_id)
        if not target_group:
            yield event.plain_result("请在群聊中使用，或追加群号：/groupllm off <群号>")
            return

        disabled_groups = self._disabled_groups()
        if target_group not in disabled_groups:
            disabled_groups.append(target_group)
            self._set_disabled_groups(disabled_groups)

        yield event.plain_result(f"已关闭群 {target_group} 的 LLM 聊天。/ 指令仍可使用。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @groupllm.command("on", alias={"enable", "开启"})
    async def enable_group_llm(self, event: AstrMessageEvent, group_id: str = ""):
        """恢复当前群或指定群的 LLM 聊天。"""
        target_group = self._resolve_group_arg(event, group_id)
        if not target_group:
            yield event.plain_result("请在群聊中使用，或追加群号：/groupllm on <群号>")
            return

        disabled_groups = [gid for gid in self._disabled_groups() if gid != target_group]
        self._set_disabled_groups(disabled_groups)

        yield event.plain_result(f"已恢复群 {target_group} 的 LLM 聊天。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @groupllm.command("status", alias={"状态"})
    async def group_llm_status(self, event: AstrMessageEvent, group_id: str = ""):
        """查看当前群或指定群的 LLM 聊天状态。"""
        target_group = self._resolve_group_arg(event, group_id)
        if not target_group:
            yield event.plain_result("请在群聊中使用，或追加群号：/groupllm status <群号>")
            return

        status = "关闭" if target_group in self._disabled_groups() else "开启"
        yield event.plain_result(f"群 {target_group} 的 LLM 聊天当前为：{status}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @groupllm.command("list", alias={"列表"})
    async def list_disabled_groups(self, event: AstrMessageEvent):
        """列出已关闭 LLM 聊天的群。"""
        disabled_groups = self._disabled_groups()
        if not disabled_groups:
            yield event.plain_result("当前没有关闭 LLM 聊天的群。")
            return

        yield event.plain_result("已关闭 LLM 聊天的群：\n" + "\n".join(disabled_groups))

    def _disabled_groups(self) -> list[str]:
        groups = self.config.get("disabled_group_ids", [])
        if not isinstance(groups, list):
            return []
        return [str(group).strip() for group in groups if str(group).strip()]

    def _set_disabled_groups(self, groups: list[str]) -> None:
        seen: set[str] = set()
        normalized_groups: list[str] = []
        for group in groups:
            normalized = str(group).strip()
            if normalized and normalized not in seen:
                normalized_groups.append(normalized)
                seen.add(normalized)

        self.config["disabled_group_ids"] = normalized_groups
        self.config.save_config()

    def _allow_command_llm(self) -> bool:
        return bool(self.config.get("allow_command_llm", True))

    def _group_id(self, event: AstrMessageEvent) -> str:
        return str(event.get_group_id() or "").strip()

    def _resolve_group_arg(self, event: AstrMessageEvent, group_id: str) -> str:
        return str(group_id or self._group_id(event) or "").strip()

    def _is_group_disabled(self, event: AstrMessageEvent, group_id: str) -> bool:
        disabled_groups = set(self._disabled_groups())
        candidates = {
            group_id,
            event.session_id,
            event.unified_msg_origin,
            f"{event.get_platform_name()}:{group_id}",
            f"{event.get_platform_id()}:{group_id}",
        }
        return any(candidate in disabled_groups for candidate in candidates if candidate)

    def _is_command_event(self, event: AstrMessageEvent) -> bool:
        activated_handlers = event.get_extra("activated_handlers", []) or []
        for handler in activated_handlers:
            for event_filter in getattr(handler, "event_filters", []) or []:
                if type(event_filter).__name__ in COMMAND_FILTER_CLASS_NAMES:
                    return True
        return False

    async def terminate(self) -> None:
        logger.info("GroupLLMGuard terminated.")
