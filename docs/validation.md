# 验证记录：实际运行与待验收项

调研开始于2026-10-29，下面本机验证完成于2026-10-30（北京时间）。这是 Codex 执行的建设与验证，不等于用户个人技能验收。原有学习知识库和求职资料未修改；新项目单独建仓，尚无GitHub远程、tag或已发布Release。

## 环境

- macOS 26.2 / arm64，24 GiB内存；Python3.14.9。
- 本机依赖精确版本见 requirements.lock.txt；`python -m pip check`实际返回无损坏依赖。
- 官方 Ollama ZIP：`https://ollama.com/download/Ollama-darwin.zip`，229,773,910字节；SHA-256 `da3189f87034d224beb0708d77b95180bc03872f6e269d59bd888a216055c58a`，`codesign --verify --deep --strict`成功。安装在项目`.local/runtime/Ollama.app`，CLI版本0.40.13；模型在`.local/models`，云功能关闭，监听127.0.0.1:11435。
- 官方 Docker DMG：`https://desktop.docker.com/mac/main/arm64/Docker.dmg`，571,487,013字节；SHA-256 `94e4ccec4a035b7dcdf67cfff0520d4b46ee873ae04b155abc0d22b333cc90ad`，镜像CRC和其中应用代码签名校验成功。下载过程中发现 `/Applications/Docker.app` 已存在且服务可用，保留并复用，没有覆盖应用，也没有用命令自动接受协议。Docker Engine29.9.2；容器Python3.12。
- Qwen3 `qwen3:1.7b`，本地digest `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`。权重从Ollama官方registry下载并由Ollama校验digest，不随代码发布。

这些哈希用于核对本次文件，不表示另行比对了厂商公布的校验和。实际代码签名校验与Ollama下载完整性校验已执行。

## 已完成

| 检查 | 命令 / 方法 | 实际结果 | 限制 |
|---|---|---|---|
| 自动测试 | `python -m pytest -q` | **55 passed，1条依赖弃用警告** | 本机Python3.14；不是用户能力验收 |
| 合成核验回归 | `python scripts/evaluate.py` | **8/8符合手工期望结论及关键错误码** | 自制候选、已知规则反例，不是模型准确率 |
| 真模型正常报价 | `OLLAMA_MODEL=qwen3:1.7b OLLAMA_BASE_URL=http://127.0.0.1:11435 python scripts/live_smoke.py` | 返回2条明细及7个来源一致的数值，NEEDS_REVIEW | 一份自制文本；名称多带A1/A2前缀，未证明字段语义完全正确 |
| 真模型原文合计错误 | 把合计4500改为4200，仅发送来源到`POST /api/extract` | 模型保留4200；核验器给TOTAL_MISMATCH、差额-300、BLOCKED | 受控变体，不能代表未见版式检出率 |
| 真模型错误标签 | 指定不存在模型，真实调用Ollama | HTTP503 / MODEL_HTTP_ERROR | 无mock；没有改全局模型配置 |
| 浏览器演示 | 实际点击三场景、核验、复核、新版本、证据定位 | 串行阻止、差额-300、正常待复核→确认后限定通过 | UI确认是Codex对模拟输入的测试，非用户本人验收 |
| 输入改变撤销确认 | 浏览器先勾选再改候选 | 两个确认字段都变回false，结果清除 | 后端Review仍为本地自报，不是认证审批 |
| 导出与离线重放 | `python -m linescope.replay .local/ui-export.json` | identical=true，CHECKS_PASSED | 固定核验器重算，不重新生成模型输出 |
| API修订持久化 | 创建、修订、读旧UUID、重新打开数据库 | 父版本保留、源哈希相同，旧内容不变 | API无覆盖不等于文件防篡改 |
| 备份恢复 | SQLite online backup API→独立恢复文件→读取旧UUID→复算 | 原记录与重放报告一致，源库保留 | 本次使用一致性备份API；不是断电灾难恢复测试 |
| Docker构建/健康 | `LINESCOPE_PORT=18765 docker compose -p linescope-review up --build -d --wait`（本机补CLI PATH） | 容器实际Healthy，HTTP可访问 | 这是Mac上的Linux容器；Windows未实测 |
| Docker业务 | 容器API创建→修订→导出→重启后读取 | 限定检查通过、父记录保留、导出一致、重启记录保留 | 测试卷保留，未删卷 |
| Docker真实AI | 容器`host.docker.internal:11435`→宿主Ollama | POST /api/extract实际201、NEEDS_REVIEW | 本机可达不代表其他Docker网络也可达；宿主未改为公网监听 |
| 打包 | `python -m build`，检查wheel内容 | wheel/sdist生成，含demo.json和静态HTML/JS | 干净克隆/安装记录另列于本文件末尾 |

真实正常模型原始候选和报告在 [model-smoke.json](model-smoke.json)，错误总额的真实API记录在 [model-wrong-total.json](model-wrong-total.json)，规则结果在 [evaluation.json](evaluation.json)，容器摘要在 [docker-validation.json](docker-validation.json)。所有这些来源都是自制模拟文本。

正常报价烟测观察13.661秒；错误总额API观察17.876秒（可能含同一模型的排队）。没有严格区分冷/热、重复采样或收集P95，不能当性能保证。正常烟测的名称抽取带A1/A2前缀，核验只证明这段文本存在，**不能证明规范化或业务语义正确**。没有真实客户、业务节省时间、真实用户数量或泛化准确率结论。

## 实际遇到的问题与最小处理

1. **模型下载的网络问题**：初次Ollama拉取因系统Fake-IP解析与下载地址检查冲突失败。检查现有系统代理后，根据官方FAQ仅给Ollama进程配置现有HTTPS_PROXY；没有关闭地址/TLS检查或修改全局网络。下载随后完成。原始带签名URL的下载日志留在被忽略的`.local`，不进入发布包。
2. **Docker客户端PATH**：首次构建提示找不到`docker-credential-desktop`。将现有官方Docker资源目录加入该命令的PATH后，公共镜像构建成功；没有读取或公开凭据，没有改用户Docker登录配置。
3. **完整数值边界**：仅解析引用中的数值会把1200接受为1200.00的子串；新增对完整来源token边界的核对与PARTIAL_NUMBER反例。
4. **模型schema与输入验证不一致**：Pydantic的Decimal默认schema允许JSON number，但业务要求字符串防浮点精度损失。用WithJsonSchema明确只接受string/null，保留运行时严格验证，并用模型适配器契约测试覆盖。
5. **旧确认残留**：编辑来源/候选会让先前确认不再适用。页面现在清除确认和旧结果，重核后才可重新确认；请求期间暂时锁定输入以避免结果与编辑内容混淆。

## 仍未完成 / 不能宣称通过

- Windows本机、Intel Mac的实际安装和模型运行。
- GitHub远程CI、公开clone、公开Release v0.1.0；用户尚未检查和授权公开推送。
- 独立未见样本集的字段准确率/漏行率、模板抽取公平基线、人工用户试用。
- PDF/OCR、复杂计价、身份认证、自动完整性证明、语义蕴含证明或防篡改审计。
- 用户本人独立修改、解释、部署与故障定位能力；`personal-understanding.md`保持未填写。

依赖警告原文为Starlette TestClient使用httpx将弃用并建议httpx2。当前55项测试实际通过，没有隐藏该警告；后续升级需按实际FastAPI/Starlette版本验证，不能为了清警告而未经验证更换客户端。

## 独立复现入口

安装后先运行 `python -m pytest -q` 和 `python scripts/evaluate.py`，再打开本地页面的三个场景。若验证真实AI，按operations.md启动本地模型、指定正确端口，再运行live_smoke；每次输出可能不同，逐字段对照原文。下载JSON后用replay复算。先读本机结果与限制，再决定可以在简历中写哪些个人已验收的能力。

## 干净克隆与软件包补充验证

对本地提交 `0971a1b` 执行 `git clone --no-local . .local/clone-check`，另建全新venv，安装该克隆的`.[dev]`：**55 passed / 1 warning**，8/8合成规则结果符合预期，wheel/sdist实际构建成功。随后在该新环境卸载editable安装、安装构建的wheel，并从克隆目录之外导入，确认模块来自site-packages；内置HTML/JS、demo读取和API创建待复核记录均通过。

这是**本地干净克隆和安装验收**，不是GitHub公开clone或Windows验收。后续改动仅为验证记录和演示截图裁切；运行代码对应上述提交及之前代码提交。临时测试环境和原始日志留在被忽略的`.local`。

Docker测试项目`linescope-review`验证结束后已停止其app容器，保留命名卷和现有Docker Desktop；本机原生服务8765与项目专用Ollama11435保留供检查。官方Docker DMG测试挂载已正常卸载，下载文件保留。
