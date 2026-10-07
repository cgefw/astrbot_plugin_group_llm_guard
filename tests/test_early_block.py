from __future__ import annotations

import asyncio
import types

import pytest


class CommandFilter:
    """Same class name as AstrBot's CommandFilter, which is what the plugin checks."""


COMMAND_HANDLER = types.SimpleNamespace(event_filters=[CommandFilter()])


def command_event(make_event, group_id="123", plugin_request=False):
    event = make_event(group_id)
    event.set_extra("activated_handlers", [COMMAND_HANDLER])
    if plugin_request:
        # ProcessStage stores a handler-yielded request before calling the agent.
        event.set_extra("provider_request", types.SimpleNamespace(prompt="from cmd"))
    return event


def waiting(plugin, event):
    asyncio.run(plugin.block_group_llm_waiting(event))
    return event.stopped


def requested(plugin, event):
    asyncio.run(plugin.block_group_llm_chat(event, types.SimpleNamespace(prompt="hi")))
    return event.stopped


def test_handlers_are_registered_as_intended(plugin_module):
    guard = plugin_module.GroupLLMGuard
    early = guard.block_group_default_llm.registrations

    assert ("custom_filter", (plugin_module.GroupWakeMessageFilter,), {}) in early
    assert (
        "event_message_type",
        (plugin_module.filter.EventMessageType.ALL,),
        {"priority": -10_000},
    ) in early
    assert guard.block_group_llm_waiting.registrations == [
        ("on_waiting_llm_request", (), {"priority": 10_000})
    ]
    assert guard.block_group_llm_chat.registrations == [
        ("on_llm_request", (), {"priority": 10_000})
    ]


def test_wake_filter_only_matches_group_wake_messages(plugin_module, make_event):
    wake_filter = plugin_module.GroupWakeMessageFilter()

    assert wake_filter.filter(make_event("123", is_wake=True), None)
    assert not wake_filter.filter(make_event("123", is_wake=False), None)
    assert not wake_filter.filter(make_event("", is_wake=True), None)


def test_default_chat_disabled_before_llm_in_blocked_group(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")

    replies = collect(plugin.block_group_default_llm(event))

    assert event.call_llm is True
    assert replies == ["已关闭"]
    assert not event.stopped


def test_default_chat_disabled_in_unlisted_whitelist_group(
    make_plugin, make_event, collect
):
    plugin = make_plugin(whitelist_mode=True, enabled_group_ids=["123"])

    blocked = make_event("999")
    allowed = make_event("123")
    collect(plugin.block_group_default_llm(blocked))
    collect(plugin.block_group_default_llm(allowed))

    assert blocked.call_llm is True
    assert allowed.call_llm is False


def test_default_chat_untouched_in_other_group(make_plugin, make_event, collect):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("999")

    replies = collect(plugin.block_group_default_llm(event))

    assert event.call_llm is False
    assert replies == []


def test_no_notice_when_another_handler_already_replied(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")
    event._has_send_oper = True

    replies = collect(plugin.block_group_default_llm(event))

    assert event.call_llm is True
    assert replies == []


def test_silent_command_cannot_fall_through_to_default_chat(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = command_event(make_event)

    replies = collect(plugin.block_group_default_llm(event))

    # Default chat is off even though a command matched; the command itself
    # still runs (event not stopped) and gets no "blocked" notice.
    assert event.call_llm is True
    assert replies == []
    assert not event.stopped


def test_default_chat_after_command_blocked_in_hooks_too(make_plugin, make_event):
    plugin = make_plugin(disabled_group_ids=["123"])

    # Built-in agent: the waiting hook sees no provider_request yet.
    assert waiting(plugin, command_event(make_event))
    # Third-party agent: only on_llm_request fires, with no provider_request.
    assert requested(plugin, command_event(make_event))


def test_command_request_llm_allowed_when_configured(make_plugin, make_event):
    plugin = make_plugin(disabled_group_ids=["123"])

    event = command_event(make_event, plugin_request=True)
    assert not waiting(plugin, event)
    assert not requested(plugin, event)
    assert not requested(plugin, command_event(make_event, plugin_request=True))


def test_command_request_llm_blocked_when_disallowed(make_plugin, make_event):
    plugin = make_plugin(disabled_group_ids=["123"], allow_command_llm=False)

    assert waiting(plugin, command_event(make_event, plugin_request=True))
    assert requested(plugin, command_event(make_event, plugin_request=True))


def test_plugin_request_stopped_at_waiting_hook_with_single_notice(
    make_plugin, make_event
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")
    event.set_extra("provider_request", types.SimpleNamespace(prompt="from plugin"))

    assert waiting(plugin, event)
    # Older AstrBot ignores the waiting hook's result and still calls the
    # request hook; the notice must not be sent twice.
    requested(plugin, event)

    assert event.sent == ["已关闭"]


def test_default_chat_notice_not_repeated_by_later_hooks(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")

    replies = collect(plugin.block_group_default_llm(event))
    requested(plugin, event)

    assert replies == ["已关闭"]
    assert event.sent == []


def test_event_stopped_even_if_notice_fails(make_plugin, make_event):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")

    async def failing_send(result):
        raise RuntimeError("bot muted")

    event.send = failing_send

    with pytest.raises(RuntimeError):
        requested(plugin, event)
    assert event.stopped
