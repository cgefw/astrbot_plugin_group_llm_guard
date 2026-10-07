# 群聊 LLM 聊天开关

这个 AstrBot 插件用于单独关闭指定群聊的 LLM 聊天功能，同时保留 `/` 指令。支持黑名单与白名单两种模式。

## 安装

在 AstrBot 插件管理里通过 GitHub 仓库安装：

```text
https://github.com/cgefw/astrbot_plugin_group_llm_guard
```

也可以手动把仓库克隆到 AstrBot 的 `data/plugins/` 下，然后在 WebUI 重载插件。

## 用法

AstrBot 管理员（WebUI 里配置的管理员 ID，不是 QQ 群管理员）可以使用：

```text
/groupllm off
/groupllm on
/groupllm status
/groupllm list
/groupllm mode
```

也可以指定群号：

```text
/groupllm off 123456789
/groupllm on 123456789
/groupllm status 123456789
```

切换工作模式：

```text
/groupllm mode blacklist    # 黑名单模式（默认）：仅黑名单中的群被关闭 LLM 聊天
/groupllm mode whitelist    # 白名单模式：仅白名单中的群可以使用 LLM 聊天
```

`on` / `off` 的语义始终是“开启/关闭该群的 LLM 聊天”：

- 黑名单模式下，`off` 把群加入黑名单，`on` 把群移出黑名单。
- 白名单模式下，`on` 把群加入白名单，`off` 把群移出白名单。

被拦截群里的普通 LLM 聊天请求会被拦截；`/help`、`/reset` 和其他插件指令仍会走 AstrBot 原本的指令流程。

## 配置

- `whitelist_mode`: 默认关闭。开启后切换到白名单模式，仅 `enabled_group_ids` 中的群可以使用 LLM 聊天。
- `disabled_group_ids`: 黑名单，要关闭 LLM 聊天的群号列表。可填 `group_id`、`platform:group_id`、`platform_id:group_id` 或完整 UMO。
- `enabled_group_ids`: 白名单，允许 LLM 聊天的群号列表，仅在白名单模式生效。格式同黑名单。
- `allow_command_llm`: 默认开启。开启时，指令触发的 LLM 请求会被放行。
- `blocked_reply`: 默认空字符串，表示静默拦截。填入文字后，拦截普通 LLM 聊天时会回复这段提示。

## 说明

插件通过 `on_llm_request` 钩子拦截目标群聊的非指令 LLM 请求，在钩子内调用 `event.stop_event()` 终止这次 LLM 请求。这个钩子在指令处理之后才触发，所以不会把 `/` 指令一并关掉。
