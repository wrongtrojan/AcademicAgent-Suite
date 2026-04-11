# ContextMap 架构说明（`feature/full-dev`）

## 会话推理：混合模式（推荐渐进路线）

当前默认实现为 **D2 混合**：

- **Gateway 进程内**：`gateway/chat_graph.py` 使用 LangGraph 执行「检索 → 合成」，通过 **SSE** 向浏览器流式输出，降低首字延迟。
- **异步重任务**：PDF/视频解析、嵌入、入库等经 **Redis Streams**（`cm:ingress` → `cm:work:*`）由 `service_manager` 与各类 **worker** 处理。

这与「所有推理必须经 broker」的严格形态不同；若未来需要 **D1 全 broker**（会话检索/LLM 也队列化），需要额外设计：结果回传（Pub/Sub、轮询 `job_records`、或长连接聚合）与延迟预算。当前未实现 D1，会话检索与合成仍在 Gateway 内。

**对象存储**：默认使用本地 `STORAGE_ROOT` + Gateway 静态挂载。若需 **MinIO 为唯一路径**，需统一上传 URL 生成、worker 拉取与 `PUBLIC_BASE_URL` / 预签名策略（见 `shared/storage/minio_client.py`）；属后续里程碑而非默认路径。

## 资产与任务

- **上传与登记**：`core/asset_manager.py` 写库并发 `cm:ingress`，并写入 `job_records`（含 `idempotency_key`）。
- **路由**：`core/service_manager.py` 消费 ingress，按服务信号量转发到各 `cm:work:{service}`，并对已完成幂等任务跳过路由。
- **URL 策略**：`shared/url_policy.py` 可在生产禁用 `file://`（`ALLOW_FILE_URL`）。对象存储见 `shared/storage/minio_client.py` 与 `MINIO_*` 环境变量。

## 数据与检索

- **全文**：`content_tsv`（迁移 `002_fulltext_embedding.sql`）支持 `ts_rank_cd` 与关键词类排序。
- **向量**：`EMBEDDING_BACKEND=hash|bge`，BGE-M3 见 `shared/embedding.py`。

## 声明式工作流

- DSL：[`compiler/dsl/workflow.yaml`](compiler/dsl/workflow.yaml)
- 编译：[`compiler/translator/build_workflow_from_dsl`](compiler/translator/__init__.py) 将节点名映射到 Python 可调用对象；修改 YAML 边与节点即可调整图结构（需注册对应 handler）。
- **检索 → 钩子 → 合成**：`retrieve` 之后有 **`post_retrieve_hooks`**（[`gateway/chat_hooks.py`](../gateway/chat_hooks.py)），预留 README「科学沙盒 / 视觉推理」的接入点；当前为无操作透传，可改为向 `sandbox_inference` / `visual_inference` 投递 Redis 任务并合并结果。

## 代码布局（现状与可选演进）

Python 采用顶层包 `gateway/`、`core/`、`shared/`、`services/`，运行与自检时 **`PYTHONPATH=.`** 指向仓库根（见 [`Makefile`](../Makefile) 的 `test` 目标）。模块与路径索引见 [`CODEMAP.zh.md`](CODEMAP.zh.md)。若将来要统一命名空间（例如 `src/contextmap/`），需要全量改 import 与 Docker `COPY`，单独里程碑处理。项目元数据见根目录 [`pyproject.toml`](../pyproject.toml)。
