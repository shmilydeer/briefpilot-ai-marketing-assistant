# Changelog

本文件按实际开发阶段记录 BriefPilot Lean MVP 的变化，不代表公开发布或生产部署。

## Core MVP checkpoint

- 完成 Capture → Clarify → Deliver 三阶段本地工作流。
- 建立 Pydantic Brief、字段来源、核实状态与结构化澄清问题。
- 分离保存草稿和人工确认；仅实质变化增加 Brief 版本。
- 增加关键字段 Change Impact Review，并使原确认失效。
- DraftPackage 绑定 Brief 版本、Brief 深拷贝快照与澄清快照。
- 保留旧交付包；关键 Brief 变化后将关联 current 稿标记为 stale。
- 增加内容修订、内部审核失效和中文释义待更新规则。
- Markdown / JSON 由后端按选定交付包生成，并保留版本、状态、未解决事项与风险提示。
- 增加 51 项自动化测试；fixture 流程不调用收费模型，live AI 边界使用 Mock。

## AI Integration 04

- 增加 `local_fixture` 与 `live_ai` 两种明确模式。
- 默认 fixture 使用固定虚构随行杯案例，不调用外部服务。
- `live_ai` 复用现有 `parse_brief` 与 `generate_drafts` structured output 逻辑。
- API Key 只从服务端进程环境读取；前端不会接收密钥。
- 缺失密钥、调用失败或响应校验失败时返回明确错误，不静默降级为 fixture。
- AI 失败不会清除原始输入、已保存 Brief 或已有交付包。
- 本阶段仅完成适配代码和 Mock 测试；没有宣称真实模型端到端验证通过。

## Integration 03

- 打通 Deliver 生成、三类交付物、人工编辑、内部审核与后端导出。
- 只有已保存且当前人工确认的 Brief 可以生成交付包。
- 每次成功生成追加新包，旧稿不被静默覆盖。
- 英文正文修改后增加内容修订号、撤销审核，并将中文释义标记为待更新。
- 支持查看和导出旧版本交付包。

## Integration 02

- Capture API 的 Brief、来源和澄清问题接入 Clarify 页面。
- 增加基于 HttpOnly Cookie 的单用户本地浏览器会话隔离。
- 增加回答、暂缓、不适用和显式应用澄清建议。
- 接入保存、确认、版本与关键字段影响规则。
- 明确刷新、返回和服务重启时的状态边界。

## Integration Spike 01

- 使用 Python 标准库 HTTP 服务托管高保真前端与 JSON API。
- 实现 `POST /api/capture/analyze` 的 fixture 集成验证。
- 固定响应经现有 Pydantic Brief 模型校验。
- 网络错误保留 Capture 输入，不伪装成 AI 分析结果。

## Visual Prototype V1 / V2

- 在 `design_prototype/` 建立统一的 Capture、Clarify、Deliver 高保真页面。
- 统一冷白背景、蓝紫品牌色、卡片、控件、三阶段导航和中文界面。
- Clarify 采用 Brief 主工作区与 AI 澄清侧栏。
- Deliver 提供营销简报、客户澄清表和创意交接稿三个标签。
- 视觉原型阶段的静态演示状态随后已替换为真实 Python API 数据绑定。

## Earlier Streamlit implementation

- 建立 Python + Streamlit + Pydantic + OpenAI API 的早期 MVP。
- 实现需求解析、人工编辑、渠道生成、风险提示和 Markdown / JSON 导出。
- 该实现继续保留，但当前主工作流已迁移到独立 HTML / CSS / JavaScript + Python HTTP API。

## 尚未完成

- 未完成真实 OpenAI API 的三阶段端到端验收。
- 未部署生产或公开服务。
- 未实现数据库、登录、多用户权限、限流或长期持久化。
- 未完成完整移动端、跨浏览器和无障碍审计。
