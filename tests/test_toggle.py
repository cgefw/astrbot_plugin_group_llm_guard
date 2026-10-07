from __future__ import annotations


def test_on_removes_platform_prefixed_blacklist_entry(
    make_plugin, make_event, collect, llm_blocked
):
    plugin = make_plugin(disabled_group_ids=["aiocqhttp:123"])

    replies = collect(plugin.enable_group_llm(make_event("123")))

    assert replies == ["已恢复群 123 的 LLM 聊天。"]
    assert plugin.config["disabled_group_ids"] == []
    assert not llm_blocked(plugin, make_event("123"))


def test_on_removes_every_form_of_the_group_and_keeps_others(
    make_plugin, make_event, collect
):
    plugin = make_plugin(
        disabled_group_ids=["123", "default:GroupMessage:123", "default:123", "456"]
    )

    collect(plugin.enable_group_llm(make_event("123")))

    assert plugin.config["disabled_group_ids"] == ["456"]


def test_on_for_other_group_keeps_current_group(make_plugin, make_event, collect):
    plugin = make_plugin(disabled_group_ids=["123", "999"])

    replies = collect(plugin.enable_group_llm(make_event("123"), "999"))

    assert replies == ["已恢复群 999 的 LLM 聊天。"]
    assert plugin.config["disabled_group_ids"] == ["123"]


def test_on_reports_group_not_in_blacklist(make_plugin, make_event, collect):
    plugin = make_plugin(disabled_group_ids=["456"])

    replies = collect(plugin.enable_group_llm(make_event("123")))

    assert replies == ["群 123 不在黑名单中，LLM 聊天已是开启状态。"]
    assert plugin.config["disabled_group_ids"] == ["456"]


def test_off_does_not_duplicate_existing_blacklist_entry(
    make_plugin, make_event, collect
):
    plugin = make_plugin(disabled_group_ids=["aiocqhttp:123"])

    collect(plugin.disable_group_llm(make_event("123")))

    assert plugin.config["disabled_group_ids"] == ["aiocqhttp:123"]


def test_whitelist_off_removes_umo_entry(
    make_plugin, make_event, collect, llm_blocked
):
    plugin = make_plugin(
        whitelist_mode=True, enabled_group_ids=["default:GroupMessage:123"]
    )

    replies = collect(plugin.disable_group_llm(make_event("123")))

    assert replies == ["已将群 123 移出白名单，LLM 聊天已关闭。/ 指令仍可使用。"]
    assert plugin.config["enabled_group_ids"] == []
    assert llm_blocked(plugin, make_event("123"))


def test_whitelist_off_reports_group_not_in_whitelist(
    make_plugin, make_event, collect
):
    plugin = make_plugin(whitelist_mode=True, enabled_group_ids=["456"])

    replies = collect(plugin.disable_group_llm(make_event("123")))

    assert replies == ["群 123 不在白名单中，LLM 聊天已是关闭状态。"]
    assert plugin.config["enabled_group_ids"] == ["456"]


def test_whitelist_on_does_not_duplicate_existing_entry(
    make_plugin, make_event, collect
):
    plugin = make_plugin(whitelist_mode=True, enabled_group_ids=["aiocqhttp:123"])

    collect(plugin.enable_group_llm(make_event("123")))

    assert plugin.config["enabled_group_ids"] == ["aiocqhttp:123"]
