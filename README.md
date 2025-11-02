# Meta Agent 项目说明

## 概述
本项目实现一个 Meta Agent：用户先创建 Agent（由大模型根据需求自动选择工具并生成名称/描述/prompt），再选择具体 Agent 执行任务。当前内置工具：
- 计算器（calculator）
- 谷歌搜索（web_search）
- 高德天气（amap_weather）

后端使用 FastAPI，前端使用 Vite + React。

![前端界面截图](agent-pic.png)

## 环境与依赖
- Python 3.10+
- Node.js 18+ / 20+

## 配置 .env（后端）
在 `backend/` 目录下新建一个 `.env` 文件，并配置如下环境变量：

```ini
# OpenAI APIKEY 必需（用于由大模型选择工具、生成 Agent 名称/描述/prompt）
OPENAI_API_KEY=

# Google Programmable Search（用于 web_search 工具）
GOOGLE_SEARCH_API_KEY=
GOOGLE_SEARCH_CX=

# AMap (Gaode) Web API（用于 amap_weather 工具）
AMAP_API_KEY=
```

说明：
- 未配置 `GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_CX` 时，`web_search` 工具不可用。
- 未配置 `AMAP_API_KEY` 时，`amap_weather` 工具不可用。

## 启动步骤
1) 启动后端（FastAPI）
- 创建 conda 虚拟环境并安装依赖：
```bash
cd backend
conda create -n meta-agent python=3.10 -y
conda activate meta-agent
pip install -r requirements.txt
```
- 启动服务：
```bash
python -m uvicorn app.main:app --reload
```
默认地址：`http://127.0.0.1:8000`
- 健康检查：`GET /api/health`

2) 启动前端（Vite + React）
- 安装依赖并启动：
```bash
cd frontend
npm install
npm run dev
```
默认地址：`http://localhost:5173`，先启动后端再启动前端之后，打开该地址即可。


## 主要 API
- 创建 Agent
  - `POST /api/agents`
  - body: `{ "user_requirement": "创建一个搜索新闻的agent" }`
  - 返回：AgentDefinition（包含 `agent_id/name/description/prompt/tools` 等）

- 列出 Agents
  - `GET /api/agents`

- 获取单个 Agent
  - `GET /api/agents/{agent_id}`

- 让 Agent 执行任务
  - `POST /api/agents/{agent_id}/tasks`
  - body: `{ "task": "搜索 OpenAI 最新新闻" }`

## 运行日志与可观测性
- 创建 Agent 时：
  - 工具选择日志（大模型原文与解析后 JSON）
    - `[ToolSelection] Raw LLM content`
    - `[ToolSelection] Parsed payload`
    - `[ToolSelection] Final tool configs`
  - 元数据生成日志（名称/描述/prompt）
    - `[AgentMetadata] Raw LLM content`
    - `[AgentMetadata] Parsed metadata`

这些日志打印在后端控制台，便于排查大模型决策过程。

## 常见问题
- 搜索/天气工具未生效：检查对应 API Key 是否配置；查看后端日志确认大模型是否选择了相应工具；任务执行阶段是否正常调用工具（错误会在 `tool_traces` 返回与日志中体现）。
- 跨域/代理问题：前端走 `/api` 代理到后端 8000 端口；如端口不同或后端地址变化，更新 `frontend/vite.config.ts`。

## 文件结构（简要）
- `backend/app/main.py`：FastAPI 入口
- `backend/app/api/routes.py`：API 路由
- `backend/app/services/agent_factory.py`：创建 Agent（调用 LLM 选择工具并生成元数据）
- `backend/app/services/task_runner.py`：执行任务（由 LLM 规划或回退逻辑驱动工具调用）
- `backend/app/services/tools.py`：工具协议与实现（calculator/web_search/amap_weather）
- `backend/app/services/registry.py`：Agent 注册表（内存 + JSON 持久化）
- `backend/app/models/agent.py`：Pydantic 数据模型
- `frontend/`：前端工程（Vite + React）

## 备注
- 该实现尽量避免硬编码判断，工具选择、名称与描述尽可能由大模型决定；仅在解析失败或无模型可用时走通用回退。
- 如需新增工具：在 `ToolName` 中增加枚举，补充 `tools.py` 实现，并在 `AgentFactory._select_tools` 的 `available_tools` 列表中声明其描述与参数 schema。
