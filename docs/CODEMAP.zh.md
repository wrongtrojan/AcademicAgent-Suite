# 代码路径说明（CODEMAP）

本文档按**仓库相对路径**说明各模块职责，便于调试与协作。更新代码时请同步维护对应行（不必在每个 `.py` 文件重复长注释）。

**相关入口**

- 架构概览：[`ARCHITECTURE.md`](ARCHITECTURE.md)
- 部署与调试：[`DEPLOYMENT.md`](DEPLOYMENT.md)
- 环境变量模板：[`../.env.example`](../.env.example)

---

## `gateway/` — HTTP API 与对话图

| 路径 | 说明 |
|------|------|
| [`gateway/app.py`](../gateway/app.py) | FastAPI 应用：上传、资产状态、预览、大纲、会话 SSE、专家/审计；OpenAPI 分组；挂载静态存储。 |
| [`gateway/chat_graph.py`](../gateway/chat_graph.py) | LangGraph 对话轮次：检索与 LLM 流式输出。 |
| [`gateway/chat_hooks.py`](../gateway/chat_hooks.py) | 检索后钩子占位（沙盒/视觉扩展）。 |
| [`gateway/http_logging_middleware.py`](../gateway/http_logging_middleware.py) | ASGI 中间件：请求耗时、`X-Request-ID`、访问日志行。 |
| [`gateway/outline_utils.py`](../gateway/outline_utils.py) | 将 DB 中结构大纲转为前端树形展示格式。 |
| [`gateway/__init__.py`](../gateway/__init__.py) | 包标记。 |

## `core/` — 领域与管线编排

| 路径 | 说明 |
|------|------|
| [`core/asset_manager.py`](../core/asset_manager.py) | 资产登记、上传落盘、入队 PDF/视频处理管线（Redis ingress）。 |
| [`core/service_manager.py`](../core/service_manager.py) | 从 ingress 读任务、并发门控、转发到各 worker 流。 |
| [`core/session_manager.py`](../core/session_manager.py) | 会话与聊天消息持久化。 |
| [`core/prompt_manager.py`](../core/prompt_manager.py) | 提示词模板加载与种子数据。 |
| [`core/__init__.py`](../core/__init__.py) | 包标记。 |

## `shared/` — 跨进程共享库

| 路径 | 说明 |
|------|------|
| [`shared/logging_config.py`](../shared/logging_config.py) | 统一日志格式；可选 `LOG_DIR` 轮转文件。 |
| [`shared/request_context.py`](../shared/request_context.py) | HTTP 请求级 `request_id`（contextvars）。 |
| [`shared/database/pool.py`](../shared/database/pool.py) | asyncpg 连接池与查询入口。 |
| [`shared/database/__init__.py`](../shared/database/__init__.py) | 包标记。 |
| [`shared/messaging/redis_streams.py`](../shared/messaging/redis_streams.py) | Redis Streams：ingress、work 流、消费组、ack。 |
| [`shared/messaging/reliability.py`](../shared/messaging/reliability.py) | 任务幂等、完成/失败标记、是否应路由。 |
| [`shared/messaging/__init__.py`](../shared/messaging/__init__.py) | 包标记。 |
| [`shared/protocol/envelope.py`](../shared/protocol/envelope.py) | 任务信封与枚举（服务名、状态）。 |
| [`shared/protocol/errors.py`](../shared/protocol/errors.py) | 协议层错误类型。 |
| [`shared/protocol/__init__.py`](../shared/protocol/__init__.py) | 包标记。 |
| [`shared/resource/semaphore.py`](../shared/resource/semaphore.py) | 按服务类型的并发上限（环境变量）。 |
| [`shared/resource/__init__.py`](../shared/resource/__init__.py) | 包标记。 |
| [`shared/embedding.py`](../shared/embedding.py) | 向量嵌入：hash / BGE 后端。 |
| [`shared/evidence_format.py`](../shared/evidence_format.py) | 检索证据 JSON 与前端 Evidence 对齐。 |
| [`shared/http_utils.py`](../shared/http_utils.py) | 将 localhost Gateway URL 改写为容器内可达地址。 |
| [`shared/paths.py`](../shared/paths.py) | 存储路径规范化。 |
| [`shared/url_policy.py`](../shared/url_policy.py) | 是否允许 `file://` 等资源策略。 |
| [`shared/__init__.py`](../shared/__init__.py) | 包标记。 |

## `services/*/worker/` — 异步 Worker

各服务消费 `cm:work:{service}`，处理完后 ack；具体见各 `processor.py`。

| 路径 | 说明 |
|------|------|
| [`services/pdf_recognition/worker/`](../services/pdf_recognition/worker/) | PDF 解析（MinerU 等）→ 更新资产与下游任务。 |
| [`services/video_recognition/worker/`](../services/video_recognition/worker/) | 视频解析、语音与时间轴相关处理。 |
| [`services/data_embedding/worker/`](../services/data_embedding/worker/) | 块向量嵌入写入。 |
| [`services/data_ingesting/worker/`](../services/data_ingesting/worker/) | 结构化块入库、全文等。 |
| [`services/mixture_searching/worker/`](../services/mixture_searching/worker/) | 混合检索（关键词 + 向量）。 |
| [`services/llm_calling/worker/`](../services/llm_calling/worker/) | 独立 LLM 调用任务（队列化场景）。 |
| [`services/sandbox_inference/worker/`](../services/sandbox_inference/worker/) | 科学沙盒执行占位/扩展。 |
| [`services/visual_inference/worker/`](../services/visual_inference/worker/) | 视觉模型推理任务。 |

## `compiler/` — 声明式工作流

| 路径 | 说明 |
|------|------|
| [`compiler/dsl/workflow.yaml`](../compiler/dsl/workflow.yaml) | DSL 图：节点与边。 |
| [`compiler/translator/__init__.py`](../compiler/translator/__init__.py) | 将 DSL 编译为可执行结构。 |
| [`compiler/parser/__init__.py`](../compiler/parser/__init__.py) | 解析占位。 |
| [`compiler/__init__.py`](../compiler/__init__.py) | 包标记。 |

## `frontend/` — Next.js UI

| 路径 | 说明 |
|------|------|
| [`frontend/app/page.tsx`](../frontend/app/page.tsx) | 主页面：资产列表、上传、同步、预览、对话与证据。 |
| [`frontend/app/layout.tsx`](../frontend/app/layout.tsx) | 根布局与全局样式。 |
| [`frontend/lib/api-config.ts`](../frontend/lib/api-config.ts) | API 基地址与端点常量。 |
| [`frontend/lib/types.ts`](../frontend/lib/types.ts) | 前端类型定义。 |
| [`frontend/components/AssetCard.tsx`](../frontend/components/AssetCard.tsx) | 资产卡片。 |
| [`frontend/components/EvidenceCard.tsx`](../frontend/components/EvidenceCard.tsx) | 证据条目与跳转。 |
| [`frontend/components/MarkdownRenderer.tsx`](../frontend/components/MarkdownRenderer.tsx) | Markdown 渲染。 |
| [`frontend/components/PdfViewer.tsx`](../frontend/components/PdfViewer.tsx) | PDF 预览与页码/高亮。 |

## `scripts/` — 运维与验证

| 路径 | 说明 |
|------|------|
| [`scripts/verify_stack.sh`](../scripts/verify_stack.sh) | 一键拉起/检测 Postgres、Redis、Gateway、上传与 worker（环境变量开关）。 |
| [`scripts/fixtures/minimal.pdf`](../scripts/fixtures/minimal.pdf) | 验证脚本用最小 PDF 样例。 |

## `deploy/` — 镜像与叠加 Compose

| 路径 | 说明 |
|------|------|
| [`deploy/Dockerfile.gateway`](../deploy/Dockerfile.gateway) | Gateway 镜像。 |
| [`deploy/Dockerfile.service_manager`](../deploy/Dockerfile.service_manager) | service_manager 镜像。 |
| [`deploy/docker-compose.gpu.yml`](../deploy/docker-compose.gpu.yml) | GPU worker 镜像与设备约束叠加。 |
| [`deploy/docker-compose.gpu-bge.yml`](../deploy/docker-compose.gpu-bge.yml) | BGE GPU 嵌入叠加。 |
| [`deploy/postgres/init.sql`](../deploy/postgres/init.sql) | 数据库初始化 DDL。 |
| [`deploy/images/`](../deploy/images/) | 各重型 worker 的 Dockerfile.gpu 等。 |
| 各 `services/*/Dockerfile` | CPU 默认 worker 镜像（相对仓库根）。 |

## 根目录

| 路径 | 说明 |
|------|------|
| [`docker-compose.yml`](../docker-compose.yml) | 默认 CPU 全栈：Postgres、Redis、MinIO、Gateway、workers、**pgweb**、日志卷。 |
| [`Makefile`](../Makefile) | `make demo`、`verify*`、`db-psql`、`test`（编译+导入自检）。 |
| [`requirements.txt`](../requirements.txt) | Python 运行时依赖。 |
| [`requirements-dev.txt`](../requirements-dev.txt) | 可选开发依赖（当前可为空）。 |
| [`pyproject.toml`](../pyproject.toml) | 项目元数据。 |
