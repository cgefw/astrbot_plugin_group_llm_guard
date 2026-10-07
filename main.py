from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.platform import MessageType
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star


PLUGIN_MARK_BLOCKED = "astrbot_plugin_group_llm_guard_blocked"
COMMAND_FILTER_CLASS_NAMES = {"CommandFilter", "CommandGroupFilter"}
MODE_BLACKLIST = "blacklist"
MODE_WHITELIST = "whitelist"


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
        if not group_id or not self._is_group_blocked(event, group_id):
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

        if self._whitelist_mode():
            enabled_groups = [gid for gid in self._enabled_groups() if gid != target_group]
            self._set_enabled_groups(enabled_groups)
            yield event.plain_result(f"已将群 {target_group} 移出白名单，LLM 聊天已关闭。/ 指令仍可使用。")
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

        if self._whitelist_mode():
            enabled_groups = self._enabled_groups()
            if target_group not in enabled_groups:
                enabled_groups.append(target_group)
                self._set_enabled_groups(enabled_groups)
            yield event.plain_result(f"已将群 {target_group} 加入白名单，LLM 聊天已开启。")
            return

        disabled_groups = [gid for gid in self._disabled_groups() if gid != target_group]
        self._set_disabled_groups(disabled_groups)

        yield event.plain_result(f"已恢复群 {target_group} 的 LLM 聊天。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @groupllm.command("mode", alias={"模式"})
    async def switch_mode(self, event: AstrMessageEvent, mode: str = ""):
        """查看或切换工作模式：blacklist（黑名单）或 whitelist（白名单）。"""
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode in {"black", "黑名单"}:
            normalized_mode = MODE_BLACKLIST
        elif normalized_mode in {"white", "白名单"}:
            normalized_mode = MODE_WHITELIST

        if not normalized_mode:
            current = MODE_WHITELIST if self._whitelist_mode() else MODE_BLACKLIST
            yield event.plain_result(
                f"当前模式：{current}\n"
                "切换模式：/groupllm mode whitelist 或 /groupllm mode blacklist"
            )
            return

        if normalized_mode not in {MODE_BLACKLIST, MODE_WHITELIST}:
            yield event.plain_result("未知模式，仅支持 blacklist 或 whitelist。")
            return

        self.config["whitelist_mode"] = normalized_mode == MODE_WHITELIST
        self.config.save_config()

        if normalized_mode == MODE_WHITELIST:
            yield event.plain_result(
                "已切换到白名单模式。仅白名单内的群可以使用 LLM 聊天，"
                "使用 /groupllm on <群号> 加入白名单。"
            )
        else:
            yield event.plain_result(
                "已切换到黑名单模式。仅黑名单内的群会被关闭 LLM 聊天，"
                "使用 /groupllm off <群号> 加入黑名单。"
            )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @groupllm.command("status", alias={"状态"})
    async def group_llm_status(self, event: AstrMessageEvent, group_id: str = ""):
        """查看当前群或指定群的 LLM 聊天状态。"""
        target_group = self._resolve_group_arg(event, group_id)
        if not target_group:
            yield event.plain_result("请在群聊中使用，或追加群号：/groupllm status <群号>")
            return

        status = "关闭" if self._is_group_blocked(event, target_group) else "开启"
        mode = MODE_WHITELIST if self._whitelist_mode() else MODE_BLACKLIST
        yield event.plain_result(f"群 {target_group} 的 LLM 聊天当前为：{status}（模式：{mode}）")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @groupllm.command("list", alias={"列表"})
    async def list_disabled_groups(self, event: AstrMessageEvent):
        """列出当前模式下的黑名单或白名单。"""
        if self._whitelist_mode():
            enabled_groups = self._enabled_groups()
            if not enabled_groups:
                yield event.plain_result("白名单为空，当前所有群的 LLM 聊天均被关闭。")
                return
            yield event.plain_result("白名单（允许 LLM 聊天的群）：\n" + "\n".join(enabled_groups))
            return

        disabled_groups = self._disabled_groups()
        if not disabled_groups:
            yield event.plain_result("当前没有关闭 LLM 聊天的群。")
            return

        yield event.plain_result("黑名单（已关闭 LLM 聊天的群）：\n" + "\n".join(disabled_groups))

    def _disabled_groups(self) -> list[str]:
        return self._normalize_groups(self.config.get("disabled_group_ids", []))

    def _set_disabled_groups(self, groups: list[str]) -> None:
        self.config["disabled_group_ids"] = self._dedupe_groups(groups)
        self.config.save_config()

    def _enabled_groups(self) -> list[str]:
        return self._normalize_groups(self.config.get("enabled_group_ids", []))

    def _set_enabled_groups(self, groups: list[str]) -> None:
        self.config["enabled_group_ids"] = self._dedupe_groups(groups)
        self.config.save_config()

    def _normalize_groups(self, groups) -> list[str]:
        if not isinstance(groups, list):
            return []
        return [str(group).strip() for group in groups if str(group).strip()]

    def _dedupe_groups(self, groups: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized_groups: list[str] = []
        for group in groups:
            normalized = str(group).strip()
            if normalized and normalized not in seen:
                normalized_groups.append(normalized)
                seen.add(normalized)
        return normalized_groups

    def _allow_command_llm(self) -> bool:
        return bool(self.config.get("allow_command_llm", True))

    def _whitelist_mode(self) -> bool:
        return bool(self.config.get("whitelist_mode", False))

    def _group_id(self, event: AstrMessageEvent) -> str:
        return str(event.get_group_id() or "").strip()

    def _resolve_group_arg(self, event: AstrMessageEvent, group_id: str) -> str:
        return str(group_id or self._group_id(event) or "").strip()

    def _is_group_blocked(self, event: AstrMessageEvent, group_id: str) -> bool:
        if self._whitelist_mode():
            return not self._is_group_listed(event, group_id, self._enabled_groups())
        return self._is_group_listed(event, group_id, self._disabled_groups())

    def _is_group_listed(
        self, event: AstrMessageEvent, group_id: str, groups: list[str]
    ) -> bool:
        return not self._group_candidates(event, group_id).isdisjoint(groups)

    def _group_candidates(self, event: AstrMessageEvent, group_id: str) -> set[str]:
        platform_name = event.get_platform_name()
        platform_id = event.get_platform_id()
        umo_prefix = f"{platform_id}:{MessageType.GROUP_MESSAGE.value}:"
        # 指令参数可能带有当前平台的前缀，先还原成群号，避免认不出当前群。
        for prefix in (umo_prefix, f"{platform_name}:", f"{platform_id}:"):
            if group_id.startswith(prefix):
                group_id = group_id[len(prefix) :]
                break
        candidates = {
            group_id,
            f"{platform_name}:{group_id}",
            f"{platform_id}:{group_id}",
            f"{umo_prefix}{group_id}",
        }
        # session_id 和 UMO 描述的是当前会话，只有目标群就是当前群时才能参与匹配。
        if group_id and group_id == self._group_id(event):
            candidates.update({event.session_id, event.unified_msg_origin})
        return {candidate for candidate in candidates if candidate}

    def _is_command_event(self, event: AstrMessageEvent) -> bool:
        activated_handlers = event.get_extra("activated_handlers", []) or []
        for handler in activated_handlers:
            for event_filter in getattr(handler, "event_filters", []) or []:
                if type(event_filter).__name__ in COMMAND_FILTER_CLASS_NAMES:
                    return True
        return False

    async def terminate(self) -> None:
        logger.info("GroupLLMGuard terminated.")
