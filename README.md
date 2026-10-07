# 群聊 LLM 聊天开关

这个 AstrBot 插件用于单独关闭指定群聊的 LLM 聊天功能，同时保留 `/` 指令。支持黑名单与白名单两种模式。

## 安装

在 AstrBot 插件管理里通过 GitHub 仓库安装：

```text
https://github.com/cgefw/astrbot_plugin_group_llm_guard
```

也可以手动把仓库克隆到 AstrBot 的 `data/plugins/` 下，然后在 WebUI 重载插件。

## 用法

默认只有 AstrBot 管理员可以使用，即 WebUI 里配置的管理员 ID（`admins_id`，可用 `/sid` 查看自己的 ID）。各平台的群管理员不算 AstrBot 管理员。指令权限可以在 WebUI 的指令管理里调整。

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
- `allow_command_llm`: 默认开启。开启时，指令内主动调用的 LLM 请求会被放行；关闭后这些请求也会被拦截，该指令会在调用 LLM 处终止。不调用 LLM 的 `/` 指令不受影响。
- `blocked_reply`: 默认空字符串，表示静默拦截。填入文字后，拦截普通 LLM 聊天时会回复这段提示。

## 说明

插件通过 `on_llm_request` 钩子拦截目标群聊的 LLM 请求，在钩子内调用 `event.stop_event()`。这会终止整个消息事件：本次 LLM 请求不会发出，优先级更低的其他 `on_llm_request` 钩子也不会再执行。

普通聊天的 LLM 请求在指令处理完之后才发起，所以拦截它不会影响 `/` 指令。指令自己调用 LLM（`yield event.request_llm(...)`）时，钩子会在指令执行过程中触发，是否放行由 `allow_command_llm` 决定。

已知限制：

- 拦截发生在 AstrBot 准备 LLM 请求之后。在此之前，“正在输入”提示、会话与对话记录的准备、图片转述（如果配置了图片转述模型）等预处理仍会执行。
- 只拦截经过 AstrBot LLM 流程的请求，即普通聊天和 `event.request_llm`。其他插件直接调用 `context.llm_generate()` 或提供商接口时不经过这个钩子，不会被拦截。
