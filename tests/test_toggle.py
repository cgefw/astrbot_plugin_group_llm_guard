from __future__ import annotations


def test_on_removes_platform_prefixed_blacklist_entry(
    make_plugin, make_event, collect, llm_blocked
):
    plugin = make_plugin(disabled_group_ids=["aiocqhttp:123"])

    replies = collect(plugin.enable_group_llm(make_event("123")))

    assert replies == ["已恢复群 123 的 LLM 聊天。（已移除条目：aiocqhttp:123）"]
    assert plugin.config["disabled_group_ids"] == []
    assert not llm_blocked(plugin, make_event("123"))


def test_on_removes_every_form_of_the_group_and_keeps_others(
    make_plugin, make_event, collect
):
    plugin = make_plugin(
        disabled_group_ids=["123", "default:GroupMessage:123", "default:123", "456"]
    )

    replies = collect(plugin.enable_group_llm(make_event("123")))

    assert replies == [
        "已恢复群 123 的 LLM 聊天。"
        "（已移除条目：123、default:GroupMessage:123、default:123）"
    ]
    assert plugin.config["disabled_group_ids"] == ["456"]


def test_on_for_other_group_keeps_current_group(make_plugin, make_event, collect):
    plugin = make_plugin(disabled_group_ids=["123", "999"])

    replies = collect(plugin.enable_group_llm(make_event("123"), "999"))

    assert replies == ["已恢复群 999 的 LLM 聊天。"]
    assert plugin.config["disabled_group_ids"] == ["123"]


def test_on_reports_no_matching_blacklist_entry(make_plugin, make_event, collect):
    plugin = make_plugin(disabled_group_ids=["456"])

    replies = collect(plugin.enable_group_llm(make_event("123")))

    assert replies == ["黑名单中没有与群 123 匹配的条目，未做修改。"]
    assert plugin.config["disabled_group_ids"] == ["456"]


def test_off_still_adds_bare_id_next_to_narrower_entry(
    make_plugin, make_event, collect
):
    # "default:123" only covers one bot; a bare `off` should cover every bot.
    plugin = make_plugin(disabled_group_ids=["default:123"])

    collect(plugin.disable_group_llm(make_event("123")))

    assert plugin.config["disabled_group_ids"] == ["default:123", "123"]


def test_whitelist_off_removes_umo_entry(
    make_plugin, make_event, collect, llm_blocked
):
    plugin = make_plugin(
        whitelist_mode=True, enabled_group_ids=["default:GroupMessage:123"]
    )

    replies = collect(plugin.disable_group_llm(make_event("123")))

    assert replies == [
        "已将群 123 移出白名单，LLM 聊天已关闭。/ 指令仍可使用。"
        "（已移除条目：default:GroupMessage:123）"
    ]
    assert plugin.config["enabled_group_ids"] == []
    assert llm_blocked(plugin, make_event("123"))


def test_whitelist_off_reports_no_matching_entry(make_plugin, make_event, collect):
    plugin = make_plugin(whitelist_mode=True, enabled_group_ids=["456"])

    replies = collect(plugin.disable_group_llm(make_event("123")))

    assert replies == ["白名单中没有与群 123 匹配的条目，未做修改。"]
    assert plugin.config["enabled_group_ids"] == ["456"]


def test_whitelist_on_still_adds_bare_id_next_to_narrower_entry(
    make_plugin, make_event, collect
):
    plugin = make_plugin(whitelist_mode=True, enabled_group_ids=["default:123"])

    collect(plugin.enable_group_llm(make_event("123")))

    assert plugin.config["enabled_group_ids"] == ["default:123", "123"]


def test_prefixed_argument_matches_bare_entry_and_is_stored_verbatim(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["123"])

    collect(plugin.enable_group_llm(make_event("456"), "aiocqhttp:123"))
    assert plugin.config["disabled_group_ids"] == []

    collect(plugin.disable_group_llm(make_event("456"), "aiocqhttp:999"))
    assert plugin.config["disabled_group_ids"] == ["aiocqhttp:999"]


def test_prefix_only_argument_does_not_match_private_session(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["10001"])

    replies = collect(
        plugin.enable_group_llm(make_event(sender_id="10001"), "aiocqhttp:")
    )

    assert replies == ["黑名单中没有与群 aiocqhttp: 匹配的条目，未做修改。"]
    assert plugin.config["disabled_group_ids"] == ["10001"]
