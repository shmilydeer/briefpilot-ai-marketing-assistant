# BriefPilot｜本地 HTTP 集成与 AI 适配

## 当前状态

当前 HTTP 主工作流已经打通：

```text
Capture → Clarify → Deliver → 人工编辑与审核 → Markdown / JSON 导出
```

服务同时托管 `design_prototype/` 中的三个高保真页面与 JSON API。默认模式为 `local_fixture`；`live_ai` 代码适配已经实现并由 Mock 覆盖，但尚未完成真实 OpenAI 的三阶段端到端验证。

## 启动

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe integration_api.py
```

打开：`http://127.0.0.1:8767/`

健康检查：

```text
GET /api/health
```

可通过参数覆盖本地地址：

```powershell
.\.venv\Scripts\python.exe integration_api.py --host 127.0.0.1 --port 8767
```

默认只绑定回环地址，不应把当前无认证服务直接暴露到公网。

## 架构

```text
index.html / clarify.html / deliver.html
                    ↓ fetch
       LocalIntegrationHandler
                    ↓
        SessionStore / WorkspaceSession
                    ↓
 models.py + logic.py + LiveAIAdapter
```

- HTTP 层使用 Python 标准库 `ThreadingHTTPServer`。
- 请求和响应由 Pydantic 校验。
- 浏览器通过 HttpOnly `briefpilot_session` Cookie 关联进程内 WorkspaceSession。
- 不同浏览器 Cookie 相互隔离；同一浏览器刷新、返回和页面导航保留状态。
- 服务重启后内存会话清空，Clarify / Deliver 会明确提示重新 Capture。
- 没有数据库、登录、多租户或长期持久化。

## 运行模式

### `local_fixture`

- 默认模式，不调用 OpenAI。
- 使用明确标注的虚构英国/美国随行杯 Brief 和渠道稿。
- HTTP、会话、版本、确认、stale、审核和导出仍走真实后端代码。
- fixture 结果不冒充模型输出。

### `live_ai`

- 用户必须在 Capture 显式选择，并确认可能产生费用的操作。
- Capture 通过 `LiveAIAdapter` 调用 `parse_brief`。
- Deliver 通过同一适配层调用 `generate_drafts`。
- BriefExtraction 与 GeneratedDraftPackage structured output 经 Pydantic 验证后，才进入 WorkspaceSession。
- 服务端保守建立字段来源；无法对应原文的模型内容标记为 AI 推断和待核对。
- 缺少密钥、认证/额度/超时错误或无效模型响应都会返回结构化错误，不切换成 fixture。
- 失败不会替换已有 Workspace 或删除已有 DraftPackage。

API Key 只从服务端进程环境 `OPENAI_API_KEY` 读取，不返回前端、不写入响应或日志。当前仓库不包含真实密钥。

## API

### Capture

#### `POST /api/capture/analyze`

请求字段：

- `raw_text`：1–5000 字符。
- `market`：`unknown`、`UK` 或 `US`。
- `channels`：`TikTok` / `Instagram`，至少一个且不重复。
- `mode`：`local_fixture` 或 `live_ai`。

成功后创建或替换当前浏览器的 WorkspaceSession，并返回结构化 Brief、来源、澄清问题、版本和确认状态。

### Clarify

- `GET /api/workspace`：读取当前草稿、渠道、来源、问题、版本、确认、dirty 和影响状态。
- `PATCH /api/brief/draft`：更新允许编辑的 Brief 字段，不保存、不升版。
- `POST /api/clarifications/{id}`：回答、暂缓或标记不适用。
- `POST /api/clarifications/{id}/apply`：显式应用已回答建议。
- `POST /api/brief/save`：保存草稿；只有实质变化才增加版本并撤销确认。
- `POST /api/brief/confirm`：确认已保存版本；存在未保存修改时返回冲突错误。

问题回答不会自动覆盖 Brief。open 和 deferred 继续作为未解决项；answered、applied 和 not_applicable 会从对应未解决列表中协调移除。

### Deliver

- `POST /api/deliver/generate`：仅基于已保存且当前确认的 Brief 生成新交付包。
- `GET /api/deliver?package_id={id}`：读取指定包及历史摘要；不指定时读取当前或最新包。
- `PATCH /api/deliver/draft`：保存指定渠道英文正文编辑。
- `POST /api/deliver/review`：更新内部审核状态并绑定当前内容修订。
- `GET /api/deliver/export?package_id={id}&format=markdown|json`：后端按指定包快照导出。

每个 DraftPackage 保存：

- `source_brief_revision`
- 独立 `source_brief_snapshot`
- `clarification_snapshot`
- `generation_mode`
- `content_revision` 与 `reviewed_content_revision`
- `review_status`
- `lifecycle_status`：`current` 或 `stale`
- `stale_reason`

编辑英文正文会增加内容修订、撤销内部审核，并将中文释义标记为 `pending_update`。新稿成功后追加到历史；生成失败保留旧稿。

## 版本与影响规则

- 草稿 PATCH 不升版。
- 保存相同实质内容不升版。
- 实质变化保存后版本增加，原确认失效。
- 当前关键字段为 `audience`、`campaign_goal`、`key_message`、`region`。
- 关键字段变化后，已有 current 包标记为 stale、审核状态变为需要修改，并记录整包复审原因。
- 当前规则只定位到交付物级别，不声称具备内容片段级语义影响分析。
- stale 包可查看和带风险提示导出，但不能标记为当前内部审核完成。

## 导出边界

Markdown 和 JSON 都由服务端生成，并使用所选 DraftPackage 的 Brief 与澄清快照，而不是最新全局 Brief。导出包含：

- 用途与批准边界；
- Brief 版本、生成模式和内容修订；
- 内部审核状态；
- current / stale 和过期原因；
- 未解决事项；
- 待核实营销声明与风险说明。

内部审核不代表客户、市场或法律批准，也不代表未核实营销声明已经真实。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

最近一次核心 checkpoint 验证结果为 `51 passed`。测试覆盖 fixture 完整 API 流程、会话隔离、失败状态保留、版本、确认、澄清、快照、stale、审核、旧稿和导出；`live_ai` 成功与失败路径使用注入 Mock。

Mock 测试证明适配边界和状态保护按预期工作，不证明真实模型质量、额度、网络或 structured output 的端到端表现。

## 真实 AI 验证仍缺少的证据

- 使用操作者明确授权的 API Key 运行 Capture → Clarify → Deliver。
- 记录 UK / US 英文表达及中文释义的人工一致性判断。
- 验证认证、额度、超时和模型校验错误在真实服务上的信息表现。
- 确认失败前后 Workspace 与旧稿在真实请求中的状态不变。
- 记录费用边界；在完成前不得把 Mock 结果描述为真实模型验证。
