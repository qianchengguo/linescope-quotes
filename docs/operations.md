# 本地启动、部署与排障

先读 README 的普通安装流程。默认本应用8765、Ollama11434。当前工作目录要可写，数据默认 `data/linescope.sqlite3`。本机实测可能使用专用11435端口，见 validation.md，避免与用户其他 Ollama 进程冲突。不要重复启动已占用端口。

## 本机专用 Ollama（这次任务）

官方来源：[下载页](https://ollama.com/download/mac)、[macOS安装说明](https://docs.ollama.com/macos)、[代理FAQ](https://docs.ollama.com/faq)。官方 ZIP 解压到项目 `.local/runtime/Ollama.app`，CLI 路径为 `.local/runtime/Ollama.app/Contents/Resources/ollama`。这是项目专用安装，未把 Ollama 链接到系统 PATH；模型目录 `.local/models`，不入 Git。首次运行 Ollama 可能在 `~/.ollama` 创建其身份配置，私钥不复制、不公开。

在项目根目录启动（macOS / zsh）：

```bash
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_MODELS="$PWD/.local/models"
export OLLAMA_NO_CLOUD=1
.local/runtime/Ollama.app/Contents/Resources/ollama serve
```

第二个终端：

```bash
OLLAMA_HOST=127.0.0.1:11435 .local/runtime/Ollama.app/Contents/Resources/ollama pull qwen3:1.7b
OLLAMA_MODEL=qwen3:1.7b OLLAMA_BASE_URL=http://127.0.0.1:11435 .venv/bin/python scripts/live_smoke.py
OLLAMA_MODEL=qwen3:1.7b OLLAMA_BASE_URL=http://127.0.0.1:11435 .venv/bin/python -m uvicorn linescope.app:app --host 127.0.0.1 --port 8765 --no-access-log --log-config logging.json
```

上述模型首次下载约GB级，精确大小看实际 manifest；不需要购买 API。服务器运行前若遇系统 Fake-IP 与 Ollama 下载地址检查冲突，应使用**用户已经配置、且自己确认的 HTTPS 代理**启动 Ollama；不要关闭地址检查、TLS校验或随意更换陌生镜像。本次配置的本机代理只是个别环境排障记录，不能写死到公开脚本。

根据 [Ollama FAQ](https://docs.ollama.com/faq)，模型下载代理用 `HTTPS_PROXY`，避免 `HTTP_PROXY` 干扰本地客户端。环境变量只传本次进程，不修改用户全局代理或网络设置。具体失败与恢复以验证记录为准。

## 常见故障

| 现象 | 先看什么 | 最小处理 / 验收 |
|---|---|---|
| 8765被占用 | 现有进程和用途 | 复用已启动服务或停止自己启动的实例；不要杀未知进程 |
| MODEL_NOT_CONFIGURED | 启动应用时是否设置OLLAMA_MODEL | 设置进程环境后重启应用；health的configured不是模型已验证 |
| MODEL_UNAVAILABLE | Ollama端口、进程、base URL | 先读取 `/api/tags`；确认11434/11435没有混用 |
| MODEL_HTTP_ERROR | 模型标签是否已下载 | `/api/tags`或`ollama list`确认，再用同一标签；响应正文不会写入应用日志 |
| MODEL_TIMEOUT | 冷加载、硬件、输入长度、其他请求 | 缩短文本，先做一次小输入；记录冷/热状态。不无条件加长超时掩盖问题 |
| MODEL_INCOMPLETE/INVALID_OUTPUT | 输出上限、schema复杂度、模型实际能力 | 保留失败并定位，不自动修造证据。用手工候选隔离核验层；不把它冒充AI抽取 |
| OUTSIDE_ITEM_SCOPE | 证据页号、scope、字段quote | 对照原文看是否串行；不能仅改字段值绕过来源 |
| AMBIGUOUS_EVIDENCE | 该quote是否重复 | 提供带标签/上下文但唯一的精确引用；数值证据只能含一个数值 |
| PARTIAL_NUMBER | 原文token是否比引用更长 | 引用完整原文数值，例如1200.00，不能截成1200 |
| TOTAL_MISMATCH | 原文总额与明细，计价边界 | 先判断原文是否错；复杂税费等不在MVP，不能假装均是算错 |
| NEEDS_REVIEW | 缺字段、歧义或人工确认 | 先核对完整来源再确认；不得为了得到绿灯随意勾选 |
| DATABASE_UNAVAILABLE | 数据目录权限、磁盘、是否锁定 | 保留原库，停止自己的应用，再用新路径恢复副本验证 |

模型可能在 schema 合法时抽错行、缺证据或给出多余 notes；这是应展示的真实失败边界，不要强行让每次模型调用得到通过。

## Docker 方式

Docker Desktop [官方 Mac 安装页](https://docs.docker.com/desktop/setup/install/mac-install/)提供 Apple silicon 安装包。首次启动涉及 Docker Subscription Service Agreement；用户自行查看/确认其适用许可，不自动用命令接受协议。个人学习适用情况以官网当前条款为准。

```bash
docker compose config
docker compose up --build -d --wait
docker compose ps
docker compose logs app
```

容器非root用户10001运行，数据为命名卷，端口只绑定宿主127.0.0.1。`/health` 检查 SQLite；不会触发模型。`docker compose down` 保留命名卷。不要运行带 `-v` 的删卷命令来“排障”。Docker镜像/权重初次下载需要网络。

容器内部的127.0.0.1是容器自身，不能直接用宿主Ollama的loopback。Compose示例使用`host.docker.internal:11434`；宿主11435或只监听loopback可能不可达。优先保持Ollama只在本机：宿主运行本应用完成AI抽取，Docker只测试规则流程；如要完整容器AI链路，另行设计仅宿主可达的受控转发并验证网络边界。当前未自动改变宿主监听地址。

本次Mac实测中，`OLLAMA_CONTAINER_BASE_URL=http://host.docker.internal:11435 OLLAMA_MODEL=qwen3:1.7b LINESCOPE_PORT=18765 docker compose -p linescope-review up --build -d --wait`成功调用宿主模型，宿主仍只监听127.0.0.1。该变量独立于宿主应用使用的OLLAMA_BASE_URL。其他机器先测试连通性，不直接扩大监听范围。若CLI不在PATH，使用Docker.app官方Resources/bin目录；不要删除凭据配置来处理找不到credential helper的问题。

## 数据备份与恢复

1. 正常停止本应用，保留数据库原文件。
2. 将`data/linescope.sqlite3`复制到日期命名的备份位置，不覆盖旧备份。
3. 复制备份到**新的恢复文件路径**，设置`LINESCOPE_DB`指向新文件再启动。
4. 读取原UUID并导出，用`python -m linescope.replay`验证固定核验器报告相同。

若未来启用SQLite WAL，需要SQLite backup API或同时处理WAL一致性；当前未启用WAL。容器卷备份需先停止容器，再只读挂载卷导出，保持原卷不动。本机数据库明文存储，备份和JSON导出都含来源文本，不上传公开仓库。

## 发布前干净环境复现

本地开发目录运行不等于干净克隆已通过。准备发布时应：新目录克隆具体commit→新venv→按README安装→pytest→规则评估→启动→三个演示→导出重放；在Windows和Docker分别记录真实结果。wheel和sdist均需包含静态页/demo。CI定义存在也不等于GitHub远程已运行。

所有官方安装文件、权重和日志保存在`.local`并忽略。需要清理下载、模型或数据库时，先由用户确认具体范围，保留所需证据。
