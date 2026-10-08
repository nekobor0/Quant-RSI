# 30 篇论文 → Quant RSI HARNESS 设计约束
> 版本：v0.1（2026-09-28）  
> 用途：把“量化交易综述撰写”阶段的文献阅读，转换为可直接进入 Quant RSI HARNESS / Agent Research Harness 设计的工程约束。  
> 说明：本文件不是论文摘要合集，而是**文献对 Harness 的可执行启示**。来源统一按 `[Pxx] 论文名 — 文件名` 索引。
## 0. 最重要的跨文献结论
1. **Harness 的目标不是最大化历史 Sharpe，而是最大化“可信研究产出率”。** 一个 Agent 能快速找到高 Sharpe，并不代表它具备更强的量化研究能力；在搜索空间足够大时，这反而可能意味着更严重的 data snooping。[P13][P22][P23][P24][P28]
2. **数据、清洗、可得时点和市场制度属于 Eval 本体，而不是前置杂务。** 不固定这些条件，模型排名会混入 data engineering 差异，最终无法比较 Agent 能力。[P25][P28][P30]
3. **Agent 必须被奖励“证伪错误想法”，而不能只奖励发现正收益策略。** Research quality 应评价假设可证伪性、negative result 记录、竞争性解释、失败路径和 evidence discipline。[P12][P13][P28][P29]
4. **统计 Alpha 与可实现 Edge 是两层对象。** 最终必须从 gross predictability 走到 risk-adjusted、cost-adjusted、capacity-adjusted、portfolio-aware、scale-appropriate edge。[P02][P04][P06][P08][P11][P14]
5. **搜索预算本身就是实验变量。** 必须记录模型看过多少特征、多少参数组合、多少策略、多少次重试和多少轮自我改写；否则任何显著性都缺少分母。[P13][P22][P23][P24]
6. **市场不是静态数据生成器。** Alpha 会衰减，交易改变流动性，市场制度变化使旧回测失真，因此必须有 temporal OOS、regime compatibility 与 prospective shadow evaluation。[P15][P19][P26]
7. **模型复杂度不能替代经济定义。** Concept→Observable→Proxy→Feature→Experiment 的链条必须显式；正确的变量定义、基准和交易机制往往比更复杂模型更关键。[P07][P09][P21][P27]
8. **Agent 架构要拆分“提出/实现/批判/裁决”。** 让同一 Agent 同时生成假设、修改代码、选择最好结果并给自己打分，会系统性放大 confirmation bias 和 benchmark gaming。[P13][P22][P29][P30]
## 1. 分类后的 Harness 设计原则
### A. 科学对象与目标函数：先定义“什么算成功”
- 研究任务必须冻结 `target / horizon / benchmark / universe / execution timing`。
- Strategy score 与 Agent score 分离：前者评价经济结果，后者评价研究过程是否可靠。
- Alpha、风险控制、仓位管理、组合配置、执行优化应作为不同层，不允许一个高 Sharpe 掩盖其他层的缺陷。
- 应提供 trivial / naive baseline：随机、常数预测、简单线性、经典因子等，复杂模型必须证明增量价值。
- 任何理论模型都要有 assumption registry，越界使用需 BLOCK。
主要来源：[P01] [P02] [P03] [P04] [P05] [P06] [P07]
### B. 市场摩擦、容量与执行：从 paper alpha 到 realizable edge
- 所有 promotion 结果必须同时报告 `gross → fees → spread → slippage → impact → net`。
- Capacity 不是备注字段，而是 Edge 的组成部分；需要 position size / ADV / turnover / impact stress。
- 历史成交价不是无限容量报价；对低流动性、微盘、涨跌停、停牌等情形必须显式模拟不可成交。
- 高频/执行/RL 任务中，Env 的撮合规则、可见状态和 reward function 必须版本化并锁定。
- 策略依赖的 market-structure regime 必须记录，防止把旧制度收益外推到新制度。
主要来源：[P08] [P11] [P14] [P16] [P17] [P18] [P19]
### C. 因子、信号与模型：必须与基准、机制和定义绑定
- 每个因子先写经济机制与 competing explanation，再写公式。
- 标准报告至少包含 raw signal、risk/factor neutralized signal、incremental contribution 与 correlation map。
- Concept→Observable→Proxy→Feature 必须可追溯；替代定义要在预注册范围内比较。
- 复杂 ML 必须和相同输入下的简单模型比较，不能通过更宽的数据口径取得“模型优势”。
- 跨市场文献只形成 prior；A 股必须重新定义 universe、制度变量和 execution semantics。
主要来源：[P09] [P10] [P12] [P20] [P21] [P25] [P26] [P27]
### D. 过拟合、复现与研究治理：Harness 的核心防线
- Trial Ledger 必须不可篡改，记录失败和重试；`N trials` 是结果解释的一部分。
- 使用 DSR/PSR、Reality Check、PBO/CSCV 或功能等价方法控制 selection bias。
- “Replication before innovation”：先在固定实现中复现 canonical baseline，再允许 Agent 改模型/特征。
- Eval 中加入 negative controls、placebo、leakage traps、microcap sensitivity、equal-weight/value-weight sensitivity。
- 不能只设置一个 hidden holdout；还需控制搜索历史，因为同一 holdout 被反复看也会被拟合。
主要来源：[P13] [P22] [P23] [P24] [P28]
### E. 非平稳性与持续监控：历史通过不等于未来有效
- 数据切分必须沿时间轴，且至少包含 development / validation / sealed test / prospective shadow 四层。
- 评价稳定性时优先独立时期/市场/标的，而不是相邻参数网格。
- Promotion 必须带退化与 retirement 条件；live/shadow 失效时自动降级。
- State conditioning 可用于解释策略时变，但不得为了“挽救策略”而无限切 regime。
主要来源：[P15] [P19] [P20] [P26]
### F. Agentic Research 与 Benchmark：把研究流程本身变成被测对象
- 推荐 Principal Investigator / Orchestrator、Researcher、Implementer、Critic、Evaluator 分权。
- 生成者不得直接控制最终 Eval；Evaluator 使用固定 deterministic gates + sealed data。
- Agent 的能力评价包含：问题定义、假设质量、实现正确性、证伪行为、研究效率、OOS 泛化、审计性。
- Benchmark 必须固定数据、清洗与交易语义；否则比较的是 pipeline 差异而不是模型能力。
- 多 Agent 提高吞吐量，也提高多重检验风险；scheduler 必须与 search budget 联动。
主要来源：[P29] [P30] [P13] [P22] [P28]
## 2. 30 篇论文逐篇 → Harness Takeaway
### [P01] Theory of Speculation (Théorie de la spéculation)
- **来源文件**：`01-Foundations-Bachelier-1900.pdf`
- **作者/年份**：Louis Bachelier (1900)
- 用随机过程/概率分布而非确定性叙事描述价格；Harness 必须有“无预测能力/随机游走式”基线。
- 任何模式发现都要回答：相对简单随机基线究竟增加了多少可验证信息，而不是仅展示拟合图形。
### [P02] Portfolio Selection
- **来源文件**：`02-Portfolio-Markowitz-1952.pdf`
- **作者/年份**：Harry Markowitz (1952)
- 把策略价值放在组合层评价：收益、方差、协方差与分散化共同决定资本价值。
- Eval 不能只看单因子 IC/单策略 Sharpe；必须评估加入现有组合后的边际贡献、相关性与风险预算。
### [P03] A New Interpretation of Information Rate
- **来源文件**：`03-Sizing-Kelly-1956.pdf`
- **作者/年份**：J. L. Kelly Jr. (1956)
- Alpha 与 sizing 分离；即使预测正确，仓位函数错误也可导致不可接受的财富路径。
- 增长率目标高度依赖概率估计误差；Harness 应默认限制激进 sizing，并对估计不确定性、回撤和破产风险设置硬约束。
### [P04] Capital Asset Prices: A Theory of Market Equilibrium under Conditions of Risk
- **来源文件**：`04-Asset_Pricing-Sharpe-1964.pdf`
- **作者/年份**：William F. Sharpe (1964)
- “超额收益”必须相对明确 benchmark / risk model 定义；未控制系统性风险的收益不能直接称为 Alpha。
- 每个研究任务在实验前冻结 benchmark、horizon 与 target，避免结果出来后换基准。
### [P05] Efficient Capital Markets: A Review of Theory and Empirical Work
- **来源文件**：`05-Market_Efficiency-Fama-1970.pdf`
- **作者/年份**：Eugene F. Fama (1970)
- 市场效率检验与资产定价模型是 joint hypothesis；拒绝某个基准不自动证明发现了可交易异常。
- 预测性必须在信息可得时点、交易成本与风险调整后成立。
### [P06] On the Impossibility of Informationally Efficient Markets
- **来源文件**：`06-Information-Grossman_Stiglitz-1980.pdf`
- **作者/年份**：Sanford J. Grossman; Joseph E. Stiglitz (1980)
- 信息获取有成本，因此完全信息效率并非合理零成本基线；可交易 edge 必须覆盖数据、研究、执行等全部成本。
- Harness 应记录 information acquisition cost 与 operational cost，而不是只扣佣金/滑点。
### [P07] The Pricing of Options and Corporate Liabilities
- **来源文件**：`07-Derivatives-Black_Scholes-1973.pdf`
- **作者/年份**：Fischer Black; Myron Scholes (1973)
- 无套利推理的力量来自明确假设；模型结论与经验事实必须分离。
- 任何模型/策略都需要 assumption registry 与边界测试；超出假设域时不得继续沿用结论。
### [P08] Continuous Auctions and Insider Trading
- **来源文件**：`08-Microstructure-Kyle-1985.pdf`
- **作者/年份**：Albert S. Kyle (1985)
- 交易本身会影响价格；流动性、知情交易与 price impact 是收益可实现性的核心。
- 容量与冲击成本必须进入 strategy promotion gate；不能把历史中“被动观察到的价格”当成无限容量可成交价格。
### [P09] Common Risk Factors in the Returns on Stocks and Bonds
- **来源文件**：`09-Factors-Fama_French-1993.pdf`
- **作者/年份**：Eugene F. Fama; Kenneth R. French (1993)
- 因子既可能是风险补偿，也可能只是共同变动控制变量；新信号应在标准因子暴露后检验残差贡献。
- Harness 要把 factor exposure / orthogonalization / incremental contribution 作为标准报告，而不是把相关因子都称为独立 Alpha。
### [P10] Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency
- **来源文件**：`10-Momentum-Jegadeesh_Titman-1993.pdf`
- **作者/年份**：Narasimhan Jegadeesh; Sheridan Titman (1993)
- 动量是 horizon-specific 的经验规律；formation/holding 定义、跳月处理、交易成本和风险调整都会影响结论。
- 策略模板必须把 formation window、holding window、rebalance、skip rules 显式参数化并冻结；不得事后挑窗口。
### [P11] The Limits of Arbitrage
- **来源文件**：`11-Limits-Shleifer_Vishny-1997.pdf`
- **作者/年份**：Andrei Shleifer; Robert W. Vishny (1997)
- 错价可能因融资约束、委托代理、噪声交易者风险和资本撤出而持续；“存在套利者”不等于“错价会立刻消失”。
- Edge 评估需包含 capital/mandate/funding/holding-period fit，尤其适合识别小规模资本的 capacity/flexibility advantage。
### [P12] Foundations of Technical Analysis: Computational Algorithms, Statistical Inference, and Empirical Implementation
- **来源文件**：`12-Technical_Statistical-Lo_Mamaysky_Wang-2000.pdf`
- **作者/年份**：Andrew W. Lo; Harry Mamaysky; Jiang Wang (2000)
- 主观图形/技术分析可以被研究，但前提是先算法化定义，再做统计检验。
- Agent 不得以自然语言图形描述直接生成 Evidence；必须先转换为可复算的 detector/feature。
### [P13] A Reality Check for Data Snooping
- **来源文件**：`13-Snooping-White-2000.pdf`
- **作者/年份**：Halbert White (2000)
- 反复使用同一数据会产生 data snooping；搜索越多，偶然“最好策略”越容易出现。
- Harness 必须有不可篡改 trial/search ledger、search budget、多重检验校正与固定 benchmark；失败实验也要记录。
### [P14] Optimal Execution of Portfolio Transactions
- **来源文件**：`14-Execution-Almgren_Chriss-2001.pdf`
- **作者/年份**：Robert Almgren; Neil Chriss (2001)
- 执行是成本与风险之间的优化问题，不是回测末尾加一个固定滑点。
- Env 应将 execution policy、temporary/permanent impact、波动风险和订单规模显式建模；Eval 报告 gross→net 的完整桥接。
### [P15] The Adaptive Markets Hypothesis: Market Efficiency from an Evolutionary Perspective
- **来源文件**：`15-Adaptive_Markets-Lo-2004.pdf`
- **作者/年份**：Andrew W. Lo (2004)
- 市场规律随竞争、技术和参与者适应而变化；历史稳定性不能外推为永久稳定。
- 必须做时间分段、rolling/forward validation、状态条件检验和退化监控；策略需要 retirement 条件。
### [P16] Reinforcement Learning for Optimized Trade Execution
- **来源文件**：`16-RL_Execution-Nevmyvaka_Feng_Kearns-2006.pdf`
- **作者/年份**：Yuriy Nevmyvaka; Yi Feng; Michael Kearns (2006)
- RL/Agent 的表现高度依赖 state、action、reward 与模拟环境；错误环境可产生虚假的高分策略。
- Env 本身是 benchmark 的一部分：状态可见性、动作约束、撮合与奖励函数必须版本化；训练环境和 sealed eval 环境隔离。
### [P17] Pairs Trading: Performance of a Relative-Value Arbitrage Rule
- **来源文件**：`17-Stat_Arb-Gatev_Goetzmann_Rouwenhorst-2006.pdf`
- **作者/年份**：Evan Gatev; William N. Goetzmann; K. Geert Rouwenhorst (2006)
- 简单相对价值策略的表面收益会被 bid-ask bounce、异步交易、成本等显著侵蚀。
- 每个候选策略先做 microstructure sanity check；若 edge 只在不现实价格假设下存在，应直接淘汰。
### [P18] High-Frequency Trading in a Limit Order Book
- **来源文件**：`18-Market_Making-Avellaneda_Stoikov-2008.pdf`
- **作者/年份**：Marco Avellaneda; Sasha Stoikov (2008)
- 做市收益与库存风险不可分；最优报价围绕 reservation price 而非静态 mid。
- 任何高频/做市类 Eval 必须同时报告 PnL、inventory exposure、tail inventory 与 fill quality；不能只奖励成交/毛收益。
### [P19] Does Algorithmic Trading Improve Liquidity?
- **来源文件**：`19-Algo_Trading-Hendershott_Jones_Menkveld-2011.pdf`
- **作者/年份**：Terrence Hendershott; Charles M. Jones; Albert J. Menkveld (2011)
- 算法交易会改变流动性与价格发现，说明策略和市场环境存在内生反馈。
- 历史回测要标注 market-structure regime；对依赖旧制度/旧撮合机制的 edge 设置 regime compatibility gate。
### [P20] Time Series Momentum
- **来源文件**：`20-Trend-Moskowitz_Ooi_Pedersen-2012.pdf`
- **作者/年份**：Tobias J. Moskowitz; Yao Hua Ooi; Lasse Heje Pedersen (2012)
- 趋势信号的证据来自跨资产、跨市场的广泛复现，而不只是同一数据集上调参数。
- 鲁棒性优先使用真正独立的市场/时期/资产，而不是大量相邻参数变体；区分 time-series 与 cross-sectional momentum。
### [P21] The Other Side of Value: Good Growth and the Gross Profitability Premium
- **来源文件**：`21-Quality-Novy_Marx-2013.pdf`
- **作者/年份**：Robert Novy-Marx (2013)
- 变量定义本身可能比模型复杂度更重要；gross profitability 与传统盈利指标的差异体现 measurement choice 的经济含义。
- Agent 必须记录 Concept→Observable→Proxy→Feature 链条，并比较替代定义；不能把字段名当成经济概念。
### [P22] The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality
- **来源文件**：`22-Overfit-Bailey_LopezDePrado-2014.pdf`
- **作者/年份**：David H. Bailey; Marcos López de Prado (2014)
- 最高 Sharpe 存在 selection bias，且非正态收益进一步扭曲显著性。
- 候选策略必须报告试验数/有效独立试验数、PSR/DSR 或等价 trial-aware 指标；禁止只报原始 Sharpe。
### [P23] The Probability of Backtest Overfitting
- **来源文件**：`23-Overfit-Bailey_Borwein_LopezDePrado_Zhu-2017.pdf`
- **作者/年份**：David H. Bailey; Jonathan M. Borwein; Marcos López de Prado; Qiji Jim Zhu (2017)
- 传统单次 holdout 对金融回测过拟合并不充分；需要直接衡量选择过程导致的性能退化。
- Eval 应加入 PBO/CSCV 或同类 rank-degradation 诊断，尤其针对大量参数/策略搜索。
### [P24] ... and the Cross-Section of Expected Returns
- **来源文件**：`24-Factor_Zoo-Harvey_Liu_Zhu-2016.pdf`
- **作者/年份**：Campbell R. Harvey; Yan Liu; Heqing Zhu (2016)
- Factor Zoo 意味着 1.96 的传统显著性阈值在大规模挖掘中明显不足。
- 新因子 promotion 使用更严格、随研究家族与试验数调整的证据门槛；研究家族必须有 family_id。
### [P25] Size and Value in China
- **来源文件**：`25-China-Liu_Stambaugh_Yuan-2019.pdf`
- **作者/年份**：Jianan Liu; Robert F. Stambaugh; Yu Yuan (2019)
- A 股制度特征会改变因子定义与有效性；机械复制美股 size/value 构造会产生误导。
- 中国市场 Env 必须显式建模壳价值/微盘、ST/退市、涨跌停、停牌、T+1、上市状态、PIT 成分等本土制度；海外结论只作为 prior。
### [P26] Universal Features of Price Formation in Financial Markets: Perspectives from Deep Learning
- **来源文件**：`26-LOB_DL-Sirignano_Cont-2019.pdf`
- **作者/年份**：Justin Sirignano; Rama Cont (2019)
- 高频价格形成中存在可跨股票学习的通用结构，pooling 可优于逐股票模型；同时存在明显路径依赖。
- 允许 pooled model 与 nonlinear interaction，但 Eval 必须检查跨标的泛化、跨时间稳定性，并把预测准确率与净交易价值分开。
### [P27] Empirical Asset Pricing via Machine Learning
- **来源文件**：`27-ML_Asset_Pricing-Gu_Kelly_Xiu-2020.pdf`
- **作者/年份**：Shihao Gu; Bryan Kelly; Dacheng Xiu (2020)
- ML 的增益主要可来自非线性与交互；模型比较必须在相同数据和相同 OOS 协议下进行。
- 模型选择层必须固定特征可得性和数据切分，报告简单基线→复杂模型的 incremental gain、稳定性和经济价值。
### [P28] Replicating Anomalies
- **来源文件**：`28-Replication-Hou_Xue_Zhang-2020.pdf`
- **作者/年份**：Kewei Hou; Chen Xue; Lu Zhang (2020)
- 大量已发表异常在统一复制、微盘控制和更严格显著性下失效。
- Harness 应设置“replication before innovation”门槛：先复现 canonical baseline，再允许修改；微盘/等权驱动的收益单独标识。
### [P29] R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization
- **来源文件**：`29-Agentic_Quant-Li_et_al-2025.pdf`
- **作者/年份**：Yuante Li et al. (2025)
- Quant Agent 适合拆成 Research→Development→Feedback 循环，并用多代理协作完成 factor/model 共优化。
- 自动化会同时放大研究吞吐量与 data snooping；因此 Agent scheduler 必须受 search budget、trial ledger、独立 critic/evaluator 约束。
### [P30] An Open Benchmark for Evaluating Time Series Forecasting Methods across Financial Markets
- **来源文件**：`30-Benchmark-Bejarano_et_al-2026.pdf`
- **作者/年份**：Jeremiah Bejarano et al. (2026)
- 比较模型时必须固定数据与清洗流程；没有单一方法在所有金融序列上都占优，domain-specific benchmark 必不可少。
- Quant RSI Eval 的第一原则应是 fixed-data / fixed-cleaning / fixed-split；模型不能通过不同清洗路径获得不公平优势。
## 3. 可以直接写成 Harness Hard Gates 的规则
```text
HG-01  No Point-in-Time integrity -> BLOCK
HG-02  No frozen target/horizon/benchmark -> BLOCK
HG-03  No trial/search ledger -> BLOCK
HG-04  No transaction-cost/execution semantics -> BLOCK for tradable promotion
HG-05  No OOS/sealed evaluation -> BLOCK
HG-06  Same actor can alter candidate and final evaluator -> BLOCK
HG-07  Unknown/fabricated numeric fact -> BLOCK
HG-08  Candidate only works under microcap/untradeable assumptions -> FLAG/BLOCK by mandate
HG-09  Multiple testing not accounted for -> no PROMOTION
HG-10  Replication baseline fails -> no NOVELTY claim
HG-11  Strategy result has no factor/risk exposure decomposition -> no ALPHA claim
HG-12  Agent has inspected sealed labels/future data -> EVAL INVALID
HG-13  Research family has unbounded retries -> EVAL INVALID
HG-14  Gross return positive but modeled net return non-positive -> no IMPLEMENTABLE_EDGE
HG-15  Live/shadow degradation breaches retirement rule -> DEMOTE
```
## 4. 推荐的核心研究对象分层
```text
Mechanism
  ↓
Hypothesis
  ↓
Observable / Proxy
  ↓
Feature / Signal
  ↓
Experiment
  ↓
Evidence
  ↓
Candidate Strategy
  ↓
Implementation Test
  ↓
Portfolio Contribution
  ↓
Sealed OOS
  ↓
Prospective Shadow
  ↓
Promote / Revise / Reject / Retire
```

关键原则：**Evidence 更新 belief；漂亮叙事不更新 Evidence。Agent 的解释能力用于提出机制、竞争解释和检查错误，但不能直接生成事实。**
## 5. Source Index
- [P01] **Theory of Speculation (Théorie de la spéculation)** — `01-Foundations-Bachelier-1900.pdf`
- [P02] **Portfolio Selection** — `02-Portfolio-Markowitz-1952.pdf`
- [P03] **A New Interpretation of Information Rate** — `03-Sizing-Kelly-1956.pdf`
- [P04] **Capital Asset Prices: A Theory of Market Equilibrium under Conditions of Risk** — `04-Asset_Pricing-Sharpe-1964.pdf`
- [P05] **Efficient Capital Markets: A Review of Theory and Empirical Work** — `05-Market_Efficiency-Fama-1970.pdf`
- [P06] **On the Impossibility of Informationally Efficient Markets** — `06-Information-Grossman_Stiglitz-1980.pdf`
- [P07] **The Pricing of Options and Corporate Liabilities** — `07-Derivatives-Black_Scholes-1973.pdf`
- [P08] **Continuous Auctions and Insider Trading** — `08-Microstructure-Kyle-1985.pdf`
- [P09] **Common Risk Factors in the Returns on Stocks and Bonds** — `09-Factors-Fama_French-1993.pdf`
- [P10] **Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency** — `10-Momentum-Jegadeesh_Titman-1993.pdf`
- [P11] **The Limits of Arbitrage** — `11-Limits-Shleifer_Vishny-1997.pdf`
- [P12] **Foundations of Technical Analysis: Computational Algorithms, Statistical Inference, and Empirical Implementation** — `12-Technical_Statistical-Lo_Mamaysky_Wang-2000.pdf`
- [P13] **A Reality Check for Data Snooping** — `13-Snooping-White-2000.pdf`
- [P14] **Optimal Execution of Portfolio Transactions** — `14-Execution-Almgren_Chriss-2001.pdf`
- [P15] **The Adaptive Markets Hypothesis: Market Efficiency from an Evolutionary Perspective** — `15-Adaptive_Markets-Lo-2004.pdf`
- [P16] **Reinforcement Learning for Optimized Trade Execution** — `16-RL_Execution-Nevmyvaka_Feng_Kearns-2006.pdf`
- [P17] **Pairs Trading: Performance of a Relative-Value Arbitrage Rule** — `17-Stat_Arb-Gatev_Goetzmann_Rouwenhorst-2006.pdf`
- [P18] **High-Frequency Trading in a Limit Order Book** — `18-Market_Making-Avellaneda_Stoikov-2008.pdf`
- [P19] **Does Algorithmic Trading Improve Liquidity?** — `19-Algo_Trading-Hendershott_Jones_Menkveld-2011.pdf`
- [P20] **Time Series Momentum** — `20-Trend-Moskowitz_Ooi_Pedersen-2012.pdf`
- [P21] **The Other Side of Value: Good Growth and the Gross Profitability Premium** — `21-Quality-Novy_Marx-2013.pdf`
- [P22] **The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality** — `22-Overfit-Bailey_LopezDePrado-2014.pdf`
- [P23] **The Probability of Backtest Overfitting** — `23-Overfit-Bailey_Borwein_LopezDePrado_Zhu-2017.pdf`
- [P24] **... and the Cross-Section of Expected Returns** — `24-Factor_Zoo-Harvey_Liu_Zhu-2016.pdf`
- [P25] **Size and Value in China** — `25-China-Liu_Stambaugh_Yuan-2019.pdf`
- [P26] **Universal Features of Price Formation in Financial Markets: Perspectives from Deep Learning** — `26-LOB_DL-Sirignano_Cont-2019.pdf`
- [P27] **Empirical Asset Pricing via Machine Learning** — `27-ML_Asset_Pricing-Gu_Kelly_Xiu-2020.pdf`
- [P28] **Replicating Anomalies** — `28-Replication-Hou_Xue_Zhang-2020.pdf`
- [P29] **R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization** — `29-Agentic_Quant-Li_et_al-2025.pdf`
- [P30] **An Open Benchmark for Evaluating Time Series Forecasting Methods across Financial Markets** — `30-Benchmark-Bejarano_et_al-2026.pdf`
