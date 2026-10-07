from __future__ import annotations

import asyncio
import types


class CommandFilter:
    """Same class name as AstrBot's CommandFilter, which is what the plugin checks."""


COMMAND_HANDLER = types.SimpleNamespace(event_filters=[CommandFilter()])


def test_wake_filter_only_matches_wake_messages(plugin_module, make_event):
    wake_filter = plugin_module.WakeMessageFilter()

    assert wake_filter.filter(make_event("123", is_wake=True), None)
    assert not wake_filter.filter(make_event("123", is_wake=False), None)


def test_default_chat_disabled_before_llm_in_blocked_group(
    make_plugin, make_event
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")

    asyncio.run(plugin.block_group_default_llm(event))

    assert event.call_llm is True
    assert event.sent == ["已关闭"]
    assert not event.stopped


def test_default_chat_untouched_in_other_group(make_plugin, make_event):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("999")

    asyncio.run(plugin.block_group_default_llm(event))

    assert event.call_llm is False
    assert event.sent == []


def test_silent_command_cannot_fall_through_to_default_chat(
    make_plugin, make_event
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")
    event.set_extra("activated_handlers", [COMMAND_HANDLER])

    asyncio.run(plugin.block_group_default_llm(event))

    # Default chat is off even though a command matched; the command itself
    # still runs (event not stopped) and gets no "blocked" notice.
    assert event.call_llm is True
    assert event.sent == []
    assert not event.stopped


def test_command_request_llm_allowed_when_configured(
    make_plugin, make_event, llm_blocked
):
    plugin = make_plugin(disabled_group_ids=["123"])
    event = make_event("123")
    event.set_extra("activated_handlers", [COMMAND_HANDLER])

    assert not llm_blocked(plugin, event)


def test_command_request_llm_blocked_when_disallowed(
    make_plugin, make_event, llm_blocked
):
    plugin = make_plugin(disabled_group_ids=["123"], allow_command_llm=False)
    event = make_event("123")
    event.set_extra("activated_handlers", [COMMAND_HANDLER])

    assert llm_blocked(plugin, event)


def test_plugin_request_stopped_at_waiting_hook_with_single_notice(
    make_plugin, make_event
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")

    asyncio.run(plugin.block_group_llm_waiting(event))
    assert event.stopped
    # Older AstrBot ignores the waiting hook's result and still calls the
    # request hook; the notice must not be sent twice.
    asyncio.run(plugin.block_group_llm_chat(event, types.SimpleNamespace(prompt="hi")))

    assert event.sent == ["已关闭"]


def test_default_chat_notice_not_repeated_by_later_hooks(
    make_plugin, make_event
):
    plugin = make_plugin(disabled_group_ids=["123"], blocked_reply="已关闭")
    event = make_event("123")

    asyncio.run(plugin.block_group_default_llm(event))
    asyncio.run(plugin.block_group_llm_chat(event, types.SimpleNamespace(prompt="hi")))

    assert event.sent == ["已关闭"]
