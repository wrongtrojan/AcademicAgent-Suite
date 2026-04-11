# ContextMap

<p>
    <a href="#"><img src="https://img.shields.io/badge/python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="http://choosealicense.com/licenses/mit/"><img src="https://img.shields.io/badge/license-MIT-2E7D32?style=flat-square&logo=bookstack&logoColor=white" alt="License"></a>
    <a href="#"><img src="https://img.shields.io/badge/AI--Agent-ContextMap-008080?style=flat-square&logo=openai&logoColor=white" alt="AI-Agent"></a>
    <a href="#"><img src="https://img.shields.io/badge/Linux-Ubuntu-333333?style=flat-square&logo=linux&logoColor=white" alt="Linux"></a>
    <a href="#"><img src="https://img.shields.io/badge/Shell-Bash-E34C26?style=flat-square&logo=gnu-bash&logoColor=white" alt="Shell"></a>
    <a href="#"><img src="https://img.shields.io/badge/Container-Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"></a>
</p>

*一个多模态解析资料 (PDF/视频), 生成结构化大纲, 溯源证据并进行增强验证 (调用科学沙盒/视觉推理) 的Agent.*

---

## 📸 Screenshots

| Uploading | Handling |
| --- | --- |
| ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_uploading.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_handling.png) |

| Structural Outline - PDF | Structural Outline - Video |
| --- | --- |
| ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_structuraloutline1.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_structuraloutline2.png) |

| Querying | Finalizing |
| --- | --- |
| ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_querying.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_finalizing.png) |

| Chat Session | Evidence Trace |
| --- | --- |
|![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_chatsession.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_evidencetrace.png) |

---

## Quickstart（三条命令跑通后端 + 前端）

后端入口为 **FastAPI** [`gateway/app.py`](gateway/app.py)。编排入口为仓库根目录 [`docker-compose.yml`](docker-compose.yml)（GPU/BGE 叠加见 [`deploy/`](deploy/)），推荐用 Makefile。各目录职责见 **[`docs/CODEMAP.zh.md`](docs/CODEMAP.zh.md)**。

```bash
git clone https://github.com/wrongtrojan/ContextMap.git
cd ContextMap

cp .env.example .env    # 唯一完整环境模板；按需改密钥与 URL

make demo               # 启动完整 CPU 栈（Postgres、Redis、MinIO、Gateway、service_manager、全部 workers）
make dev-frontend       # 另开终端：Next.js，默认连 http://localhost:8000
```

默认 API：`http://localhost:8000`（与 [`frontend/lib/api-config.ts`](frontend/lib/api-config.ts) 中 `BASE_URL` 一致）。

本地开发（不用 Compose 里的 gateway）可先起 `postgres` / `redis`，再：`export PYTHONPATH=$(pwd)`，`uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --no-access-log --reload`（访问日志由应用内中间件统一输出，勿与 uvicorn access 重复）。`LOG_LEVEL`、`LOG_DIR`、`CONTEXTMAP_LOG_HTTP_SKIP_PREFIXES` 见 `.env.example`。Compose 启动后：**Pgweb** 浏览数据库 `http://localhost:8088`；落盘日志在仓库 `./logs/*.log`（`tail -f`）。`make db-psql` 进入 `psql`。Python 依赖：`pip install -r requirements.txt`。自检：`make test`（编译 + 导入 Gateway）。

<details>
<summary>进阶：GPU / BGE、验证脚本、迁移</summary>

| | CPU（默认） | Full GPU (NVIDIA) | + BGE 向量 GPU（可选） |
|---|-------------|-------------------|------------------------|
| 一键 | `make demo` | `make demo-gpu` | `make demo-gpu-bge` |
| 等价 compose | `docker compose --env-file .env up -d` | `-f docker-compose.yml -f deploy/docker-compose.gpu.yml` | 再叠加 `-f deploy/docker-compose.gpu-bge.yml` |
| 说明 | slim worker 镜像 | MinerU / Whisper / Qwen-VL 等 | `data_embedding` BGE + CUDA，利于与 `mixture_searching` 语义一致 |

- 验证：`make verify-e2e`（上传 fixture PDF 并等到 Ready）、`make verify-e2e-gpu` / `make verify-e2e-gpu-bge`
- 文档：[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)、[`docs/MODELS_AND_GPU.md`](docs/MODELS_AND_GPU.md)、[`deploy/images/README.md`](deploy/images/README.md)
- 重型依赖汇总（仅 worker 镜像/本机调试）：[`requirements-ml-gpu.txt`](requirements-ml-gpu.txt)

</details>

<details>
<summary>旧版单体部署（<code>envs/AgentLogic</code>、<code>web.main</code>）已弃用</summary>

若你仍使用旧分支上的 `installer.sh`、`models/downloader.sh`、`uvicorn web.main:app`，请切换到对应 Git 分支；当前默认开发流以上述 Gateway + Compose 为准。

</details>

---

## 🛠️ Features

**📑 多模态解析**

| PDF处理 | 视频处理 |
| --- | --- |
|支持含复杂的表格/公式/双栏PDF的解析|自动提取视频关键帧/转录语音并对齐|

<br>

**🗺️ 结构化大纲**

| 逻辑层级重构 | 精准跳转 |
| --- | --- |
|将冗长资料重组为层级清晰的思维大纲|支持页数(PDF)/时间戳(视频)精准跳转|

<br>

**🚀 增强验证**

| 科学沙盒 | 视觉推理 |
| --- | --- |
|验证数学/物理/计算机公式/算法准确性|验证复杂表格/图表/视频关键帧帧语义|

<br>

**📍 证据回溯**

| PDF | 视频 |
| --- | --- |
|定位至PDF的具体页码与高亮段落(点击跳转)|定位至视频对应时间戳(点击跳转)|

---

## 🔗 Citation

*如果你在学术研究或工程项目中使用了本项目, 请考虑以下列方式引用*

```bibtex
@misc{contextmap,
  author = {wrongtrojan},
  title = {ContextMap: AI-powered Multimodal Structural Outline and Evidence Localization Agent},
  year = {2026},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{[https://github.com/wrongtrojan/ContextMap](https://github.com/wrongtrojan/ContextMap)}}
}

