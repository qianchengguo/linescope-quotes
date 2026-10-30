# v0.1.0 发布说明

标题：LineScope Quotes v0.1.0 — item-scoped quotation evidence checks

设备报价抽取可能引用到同页其他明细的数字，即使 JSON 合法、数字真实存在，仍不可靠。v0.1.0 提供本地候选抽取、当前明细范围来源验证、完整数值边界检查、Decimal 金额复算、人工复核门禁和可重放修订记录。

## 内容

- 文本逻辑页、人民币简单计价、最多20条明细。
- 本地 Ollama 结构化抽取；无需模型的手工/模拟候选路径。
- 三个可演示场景：串行引用、原文少计金额、未人工确认。
- SQLite 新增修订、JSON 导出、固定版本离线重放。
- Python测试、Docker配置、CI定义、中英文README及贡献文档。

实际验证和未验证项请直接读 [validation.md](validation.md)，不能把这个清单当所有环境均已通过。内置样本为自制模拟，无真实客户或业务效果数据。

## 已知限制

无PDF/OCR、复杂税费/折扣、多币种、自动完整性/语义证明、身份认证或防篡改审计。scope是候选，需要人核对。仅本地单人，不宜直接开放公网。模型、OCR或格式失败不能包装成已解决。

## 发布验证

- [公开源码](https://github.com/qianchengguo/linescope-quotes)，原创代码、文档和模拟样例采用MIT许可。
- 从公开HTTPS地址重新克隆并安装，55项测试、8个规则案例、打包和API烟测通过。
- [GitHub CI](https://github.com/qianchengguo/linescope-quotes/actions/runs/41077223158)的Ubuntu/Python3.12与3.14、macOS/Python3.12、Windows/Python3.12，以及Linux Docker作业均通过。
- 首次Windows中文样例默认编码错误已修复，详情及现存依赖警告见验证记录。
- Ollama实测使用自制模拟文本，没有真实用户数量、泛化准确率或提效比例声明。

模型权重、第三方安装包、真实数据库、本地环境及密钥不在发布内容中；模型保留自己的许可证。实际Release标签和下载文件以[GitHub Releases](https://github.com/qianchengguo/linescope-quotes/releases)为准。
