from __future__ import annotations


def test_status_of_other_group_ignores_blacklisted_current_group(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["123"])

    replies = collect(plugin.group_llm_status(make_event("123"), "999"))

    assert replies == ["群 999 的 LLM 聊天当前为：开启（模式：blacklist）"]


def test_status_of_other_group_ignores_whitelisted_current_group(
    make_plugin, make_event, collect
):
    plugin = make_plugin(whitelist_mode=True, enabled_group_ids=["123"])

    replies = collect(plugin.group_llm_status(make_event("123"), "999"))

    assert replies == ["群 999 的 LLM 聊天当前为：关闭（模式：whitelist）"]


def test_status_of_other_group_matches_its_umo(make_plugin, make_event, collect):
    plugin = make_plugin(disabled_group_ids=["default:GroupMessage:999"])

    from_group = collect(plugin.group_llm_status(make_event("123"), "999"))
    from_private = collect(plugin.group_llm_status(make_event(), "999"))

    assert from_group == ["群 999 的 LLM 聊天当前为：关闭（模式：blacklist）"]
    assert from_private == from_group


def test_status_of_other_group_matches_platform_prefix(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["aiocqhttp:999"])

    replies = collect(plugin.group_llm_status(make_event("123"), "999"))

    assert replies == ["群 999 的 LLM 聊天当前为：关闭（模式：blacklist）"]


def test_private_session_id_does_not_match_target_group(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["10001"])

    replies = collect(plugin.group_llm_status(make_event(sender_id="10001"), "999"))

    assert replies == ["群 999 的 LLM 聊天当前为：开启（模式：blacklist）"]


def test_llm_hook_blocks_only_listed_group(make_plugin, make_event, llm_blocked):
    plugin = make_plugin(disabled_group_ids=["123"])

    assert llm_blocked(plugin, make_event("123"))
    assert not llm_blocked(plugin, make_event("999"))


def test_llm_hook_matches_current_session_umo(make_plugin, make_event, llm_blocked):
    plugin = make_plugin(disabled_group_ids=["default:GroupMessage:123"])

    assert llm_blocked(plugin, make_event("123"))


def test_llm_hook_whitelist_blocks_unlisted_group(
    make_plugin, make_event, llm_blocked
):
    plugin = make_plugin(whitelist_mode=True, enabled_group_ids=["aiocqhttp:123"])

    assert not llm_blocked(plugin, make_event("123"))
    assert llm_blocked(plugin, make_event("999"))
