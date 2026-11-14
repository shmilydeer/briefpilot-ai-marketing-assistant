# BriefPilot｜高保真三阶段前端

本目录是 BriefPilot 当前主工作流的原生 HTML / CSS / JavaScript 前端，由项目根目录的 Python HTTP 服务托管并连接真实本地 API。

它不使用 React、Next.js 或构建工具；业务状态与版本规则保留在 Python，而不是在 JavaScript 中重复实现。

## 页面

- `index.html`：Capture｜采集需求。提交原始需求、市场、渠道和运行模式。
- `clarify.html`：Clarify｜澄清与确认。读取当前 Workspace，编辑 Brief、处理问题、保存和确认。
- `deliver.html`：Deliver｜生成与审核。读取 DraftPackage、编辑渠道内容、内部审核、查看历史并导出。

页面顶部使用同一套三阶段导航。主要工作界面为简体中文。

## 共享样式与脚本

- `styles.css`：全局视觉 token、品牌栏、步骤导航、Capture 和通用控件。
- `workspace.css`：Clarify / Deliver 工作区布局与状态组件扩展；不建立第二套视觉 token。
- `script.js`：Capture API、fixture/live AI 模式和输入保留。
- `clarify.js`：Workspace、Brief 草稿、澄清、保存、确认和进入 Deliver。
- `deliver.js`：生成、交付包读取、渠道编辑、内部审核、历史和后端导出。

## 本地启动

不要用 `file://` 直接打开页面；真实 API 需要由项目根目录的服务托管。

```powershell
cd <briefpilot-project>
.\.venv\Scripts\python.exe integration_api.py
```

浏览器打开：

```text
http://127.0.0.1:8767/
```

对应页面：

- Capture：`/`
- Clarify：`/clarify.html`
- Deliver：`/deliver.html`

服务重启会清空内存会话；直接进入 Clarify 或 Deliver 且没有有效 Cookie 会显示会话失效/返回 Capture 提示。

## 数据与状态来源

- 所有结构化 Brief、来源、核实状态、澄清问题、版本和确认状态来自 Python API。
- Clarify 的回答不会自动覆盖字段；只有显式应用后才更新草稿。
- 保存和确认是独立 API 操作。
- Deliver 的三类内容读取所选 DraftPackage 的 Brief 与澄清快照。
- 英文正文编辑保存到服务端会话，并使审核失效、中文释义待更新。
- current / stale、Change Impact 和导出内容由 Python 规则决定，不是前端演示硬编码。

## 运行模式

- `local_fixture`：默认；固定虚构随行杯案例，不调用 OpenAI。
- `live_ai`：用户显式选择并确认后，通过服务端适配器调用 OpenAI；可能产生费用。

两种模式都会在页面与 API 响应中明确展示。live AI 失败不会伪装为 fixture 成功。

## API 路径

- `POST /api/capture/analyze`
- `GET /api/workspace`
- `PATCH /api/brief/draft`
- `POST /api/brief/save`
- `POST /api/brief/confirm`
- `POST /api/clarifications/{id}`
- `POST /api/clarifications/{id}/apply`
- `POST /api/deliver/generate`
- `GET /api/deliver`
- `PATCH /api/deliver/draft`
- `POST /api/deliver/review`
- `GET /api/deliver/export`

## 当前限制

- 会话只保存在 Python 进程内存，没有数据库持久化。
- 没有登录、多用户权限、限流或生产安全能力。
- 自动化中的 live AI 是 Mock 验证；尚未完成真实模型三阶段端到端测试。
- 设计截图和早期 smoke 文件是视觉/开发证据，不是应用运行依赖。
- 尚未完成移动端、跨浏览器和完整无障碍审计。
