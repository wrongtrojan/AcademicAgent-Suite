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

## 💻 Quickstart

```bash
# Ubuntu 系统环境
# 拉取项目
git clone git@github.com:wrongtrojan/ContextMap.git
# 或者 git clone https://github.com/wrongtrojan/ContextMap.git

cd ContextMap

# 部署容器
sudo bash deploy/installer.sh
sudo docker compose -f deploy/docker-compose.yml up -d

# 下载模型权重
bash models/downloader.sh

# 下载后端环境
pip install huggingface_hub
python envs/downloader.py

# 校准配置
python configs/calibrator.py

# 填写api
nano .env

# 启动后端
source envs/AgentLogic/bin/activate
uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload

# 启动前端(新bash内)
cd Context/web/frontend
npm install | npm run bulid | npm run start

```
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

