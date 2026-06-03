# 群聊 LLM 聊天开关

这个 AstrBot 插件用于单独关闭指定群聊的 LLM 聊天功能，同时保留 `/` 指令。

## 安装

在 AstrBot 插件管理里通过 GitHub 仓库安装：

```text
https://github.com/cgefw/astrbot_plugin_group_llm_guard
```

也可以手动把仓库克隆到 AstrBot 的 `data/plugins/` 下，然后在 WebUI 重载插件。

## 用法

群内管理员可以使用：

```text
/groupllm off
/groupllm on
/groupllm status
/groupllm list
```

也可以指定群号：

```text
/groupllm off 123456789
/groupllm on 123456789
/groupllm status 123456789
```

关闭后，目标群里的普通 LLM 聊天请求会被拦截；`/help`、`/reset` 和其他插件指令仍会走 AstrBot 原本的指令流程。

## 配置

- `disabled_group_ids`: 要关闭 LLM 聊天的群号列表。可填 `group_id`、`platform:group_id`、`platform_id:group_id` 或完整 UMO。
- `allow_command_llm`: 默认开启。开启时，指令触发的 LLM 请求会被放行。
- `blocked_reply`: 默认空字符串，表示静默拦截。填入文字后，拦截普通 LLM 聊天时会回复这段提示。

## 说明

插件通过 `on_llm_request` 钩子拦截目标群聊的非指令 LLM 请求。它不会调用 `event.stop_event()` 去提前终止普通消息事件，因此不会把 `/` 指令一并关掉。
