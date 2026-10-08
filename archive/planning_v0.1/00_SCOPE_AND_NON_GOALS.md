# Quant RSI HARNESS：首轮范围

状态：DESIGN_DRAFT；日期：2026-09-28。

本项目是完全独立的新项目。最新用户指示优先于输入任务书中关于复用外部系统的叙述。本轮唯一设计依据为根目录原始 00–06 七份 Markdown/YAML；不导入其他项目的代码、schema、测试结果、研究结论或历史数据。早先扩大范围的读取已撤回其证据资格，产生的临时测试文件已移除。原始七份输入保持不变。

本轮交付 Current-State Audit、Gap Matrix、Target Architecture、Env/Eval/Agent drafts、单一职责 work items 及 planning_report.yaml。只验证规划产物，不实现 Harness，不运行策略搜索，不分派实现，不读取论文正文、不联网核对文献、不使用交易数据。

## 工作假设与非目标

- 北极星：受控搜索下的可信研究产出；Agent quality 与 strategy economics 分离。
- 推荐首版只覆盖 A 股日频 Research Agent；D01/D02 尚待明确冻结。合成数据用于工程校准，不能支持真实市场有效性结论。
- 首版不做实盘、不做高频/RL 撮合、不扩展港股/ETF，不训练模型，不优化收益排行榜。
- D03–D09 推荐默认值只用于本次设计；数字预算、统计阈值、切分日期、资本规模、shadow 长度均不得伪装为已批准或实测。
- reuse before new schema：沿用七份输入中的研究对象、H01–H15、G0–G7、E0–E9、角色和版本键；新增字段先做对象归属审查，同一事实只由一个对象维护。
- 所有实现 work items 均为 NOT_STARTED / DESIGN_ONLY；本轮授权不包含执行这些实现任务。

## 证据等级

文档规定 ≠ 可执行实现 ≠ 测试通过 ≠ 市场有效。此次“当前状态”是获准七份输入范围内的文档基线，不是对其他目录的能力盘点。ABSENT 表示未提供可执行证据，不能解释为所有潜在实现都已穷尽搜索。

## 冻结顺序

先冻结市场与评价对象、对象归属，再冻结 Task/Data/Cleaning/Split/Env/Eval/成本/预算；之后实现和合成校准。真实数据接入必须另有可追溯的数据授权、来源与 PIT 证据。sealed 未隔离、trial 未完整登记或统计协议未冻结时，禁止模型比较和策略晋升。
