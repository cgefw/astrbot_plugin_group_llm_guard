from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.platform import MessageType
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star


PLUGIN_MARK_BLOCKED = "astrbot_plugin_group_llm_guard_blocked"
PLUGIN_MARK_DEFAULT_CHAT = "astrbot_plugin_group_llm_guard_default_chat"
COMMAND_FILTER_CLASS_NAMES = {"CommandFilter", "CommandGroupFilter"}
MODE_BLACKLIST = "blacklist"
MODE_WHITELIST = "whitelist"


class GroupWakeMessageFilter(filter.CustomFilter):
    """只匹配群里会触发默认 LLM 聊天的唤醒消息，不改变其他消息的唤醒状态。"""

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return bool(event.is_at_or_wake_command and event.get_group_id())


class GroupLLMGuard(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    # 以最低优先级尽量最后执行，此时其他插件的回复基本都已发出，可以据此决定是否提示。
    # priority 只在最先生效（最下面）的装饰器上起作用。
    @filter.custom_filter(GroupWakeMessageFilter)
    @filter.event_message_type(filter.EventMessageType.ALL, priority=-10_000)
    async def block_group_default_llm(self, event: AstrMessageEvent):
        """在默认 LLM 聊天开始前关闭它，避免“正在输入”、图片转述等请求准备工作。"""
        group_id = self._blocked_group_id(event)
        # 其他插件已经关掉默认聊天时，这条消息本来就不会到 LLM，不必再提示。
        if not group_id or getattr(event, "call_llm", False):
            return

        # 传 True 表示禁止 AstrBot 默认的 LLM 请求；指令和插件自己的 request_llm 不受影响。
        # 指令执行后如果什么都没回复，AstrBot 也不会再转去默认聊天。
        event.should_call_llm(True)
        if self._is_command_event(event):
            return
        notice = self._mark_blocked(event, group_id, event.message_str)
        if notice:
            yield event.plain_result(notice)

    @filter.on_waiting_llm_request(priority=10_000)
    async def block_group_llm_waiting(self, event: AstrMessageEvent) -> None:
        """较新的 AstrBot 会在此结束请求，跳过加锁和请求准备。"""
        # 插件 yield 的请求在此之前就放进了 provider_request，默认聊天要到之后才放。
        provider_request = event.get_extra("provider_request")
        event.set_extra(PLUGIN_MARK_DEFAULT_CHAT, provider_request is None)
        prompt = getattr(provider_request, "prompt", "") or event.message_str
        await self._block_llm_request(event, prompt)

    @filter.on_llm_request(priority=10_000)
    async def block_group_llm_chat(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """Block LLM requests from configured groups unless they come from commands."""
        await self._block_llm_request(event, getattr(req, "prompt", ""))

    async def _block_llm_request(self, event: AstrMessageEvent, prompt: str) -> None:
        group_id = self._blocked_group_id(event)
        if not group_id:
            return

        if (
            not self._is_default_chat(event)
            and self._allow_command_llm()
            and self._is_command_event(event)
        ):
            return

        event.stop_event()
        notice = self._mark_blocked(event, group_id, prompt)
        if notice:
            await event.send(event.plain_result(notice))

    def _is_default_chat(self, event: AstrMessageEvent) -> bool:
        is_default_chat = event.get_extra(PLUGIN_MARK_DEFAULT_CHAT)
        if is_default_chat is None:
            # 第三方 Agent 不触发 on_waiting_llm_request，也不会自己设置 provider_request。
            return event.get_extra("provider_request") is None
        return bool(is_default_chat)

    def _mark_blocked(self, event: AstrMessageEvent, group_id: str, prompt: str) -> str:
        """记录拦截并返回要发送的提示。

        同一事件只在第一次拦截时返回提示；这条消息已经有其他回复时也不提示。
        """
        if event.get_extra(PLUGIN_MARK_BLOCKED):
            return ""
        event.set_extra(PLUGIN_MARK_BLOCKED, True)
        logger.info(
            "GroupLLMGuard blocked LLM chat: group=%s umo=%s prompt=%s",
            group_id,
            event.unified_msg_origin,
            (prompt or "")[:80],
        )
        if getattr(event, "_has_send_oper", False):
            return ""
        return str(self.config.get("blocked_reply", "") or "").strip()

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
            remaining_groups, removed_groups = self._split_group(
                event, target_group, self._enabled_groups()
            )
            if not removed_groups:
                yield event.plain_result(f"白名单中没有与群 {target_group} 匹配的条目，未做修改。")
                return
            self._set_enabled_groups(remaining_groups)
            yield event.plain_result(
                f"已将群 {target_group} 移出白名单，LLM 聊天已关闭。/ 指令仍可使用。"
                + self._removed_note(target_group, removed_groups)
            )
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

        remaining_groups, removed_groups = self._split_group(
            event, target_group, self._disabled_groups()
        )
        if not removed_groups:
            yield event.plain_result(f"黑名单中没有与群 {target_group} 匹配的条目，未做修改。")
            return
        self._set_disabled_groups(remaining_groups)

        yield event.plain_result(
            f"已恢复群 {target_group} 的 LLM 聊天。"
            + self._removed_note(target_group, removed_groups)
        )

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

    def _split_group(
        self, event: AstrMessageEvent, group_id: str, groups: list[str]
    ) -> tuple[list[str], list[str]]:
        """把名单拆成 (保留的条目, 与该群匹配而被移除的条目)。"""
        candidates = self._group_candidates(event, group_id)
        remaining = [group for group in groups if group not in candidates]
        removed = [group for group in groups if group in candidates]
        return remaining, removed

    def _removed_note(self, group_id: str, removed: list[str]) -> str:
        if removed == [group_id]:
            return ""
        return "（已移除条目：" + "、".join(removed) + "）"

    def _allow_command_llm(self) -> bool:
        return bool(self.config.get("allow_command_llm", True))

    def _whitelist_mode(self) -> bool:
        return bool(self.config.get("whitelist_mode", False))

    def _group_id(self, event: AstrMessageEvent) -> str:
        return str(event.get_group_id() or "").strip()

    def _resolve_group_arg(self, event: AstrMessageEvent, group_id: str) -> str:
        return str(group_id or self._group_id(event) or "").strip()

    def _blocked_group_id(self, event: AstrMessageEvent) -> str:
        """事件所在群被拦截时返回群号，否则返回空字符串。"""
        group_id = self._group_id(event)
        if group_id and self._is_group_blocked(event, group_id):
            return group_id
        return ""

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
