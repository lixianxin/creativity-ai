# 创想∞ AI创业委员会

> 2026 全球智能体大赛作品
> 核心理念：**AI 创业委员会先质疑创业想法**

面向大学生创新创业教育的 12 智能体评审系统。学生输入创业想法，12 个 AI 专家委员模拟真实创业委员会，从用户洞察到路演答辩做全链路审查，输出结构化诊断结果。

## 委员会架构

### 专家委员会（8 员）—— 各维度专业分析
| Agent | 职责 | Prompt |
|---|---|---|
| 用户洞察官 | 画像+需求证据四级（行为>态度>推导>无证据） | `agents/prompts/user_insight_v1.md` |
| 市场分析官 | TAM/SAM/SOM 推导，严禁 TAM×1% | `agents/prompts/market_analysis_v1.md` |
| 竞品分析官 | 三分法（直接/间接/免费替代）+去中介化 | `agents/prompts/competitor_analysis_v1.md` |
| 产品设计官 | 砍功能做 MVP，核心任务+人工 MVP 优先 | `agents/prompts/product_design_v1.md` |
| 商业模式官 | 价值交换逻辑，付费方识别，不算金额 | `agents/prompts/business_model_v1.md` |
| 财务分析官 | 三情景测算，假设清单，不做商业判断 | `agents/prompts/finance_v1.md` |
| 增长运营官 | AARRR 飞轮，冷启动渠道，不算 CAC | `agents/prompts/growth_ops_v1.md` |
| 风险审查官 | 六类风险，法条罚款一律"待核验" | `agents/prompts/risk_review_v1.md` |

### 对抗委员会（1 员）—— 独立质疑
| Agent | 职责 | Prompt |
|---|---|---|
| 红队质疑官 | 假设攻击五维，致命/高风险判定 | `agents/prompts/red_team_v1.md` |

### 决策委员会（3 员）—— 收口与答辩
| Agent | 职责 | Prompt |
|---|---|---|
| 创业总指挥 | 项目阶段+核心矛盾+3 行动（管"现在做什么"） | `agents/prompts/commander_v1.md` |
| 项目评审官 | 五维评分+红线一票否决（管"够不够格路演"） | `agents/prompts/project_review_v1.md` |
| 路演答辩官 | 评委追问+手牌评估+口径雷区（管"上台会不会穿"） | `agents/prompts/pitch_defense_v1.md` |

## 全链路闭环

```
想法输入
  → 用户洞察 → 市场分析 → 竞品分析 → 产品设计
  → 商业模式 → 财务分析 → 增长运营 → 风险审查
  → 红队攻击（独立）
  → 创业总指挥（阶段+行动）
  → 项目评审（五维终审+红线门禁）
  → 路演答辩（压力测试）
  → 创业项目诊断结果
```

**三个终局角色的分工：**
- 创业总指挥：**现在该做什么？**
- 项目评审官：**现在够不够资格进入路演？**
- 路演答辩官：**真的坐上答辩席后，会不会被问穿？**

## 目录结构

```
agents/
├── prompts/              # 12 个系统 Prompt（V1.0 冻结）
├── knowledge/            # 12 Agent 知识库（每 Agent 6 md，共 72 篇）
├── qa/                   # 12 Agent 核心 QA（每 Agent 10 条，共 120 条）
└── context/
    └── project_context_template.md  # 统一项目上下文模板

tests/
├── <agent>/              # 12 套独立测试脚本 + 5 案例真实输出
└── pipeline/
    ├── run_pipeline.py          # 3 Agent 最小闭环联调
    └── run_full_pipeline.py     # 12 Agent 全链路联调
```

## 运行方式

### 单 Agent 测试
```bash
python tests/redteam/run_redteam_test.py        # 红队 5 案例
python tests/finance/run_finance_test.py        # 财务 5 案例
# ... 其余 Agent 同理
```

### 12 Agent 全链路联调
```bash
python tests/pipeline/run_full_pipeline.py
```
输出落盘 `tests/pipeline/outputs/full_run_<时间戳>/`，每棒一个 md。

### 平台
默认 DeepSeek `deepseek-v4-flash`，自动降级百炼 `qwen-plus` / 智谱 `glm-5.1`。

## 铁律

1. 不回头修改已冻结 Agent。
2. 不编造数据，缺失标"待验证"。
3. 每个 Agent 独立知识边界，禁止复制 Prompt/QA。
4. 法条编号、罚款金额一律"待核验"。
5. 风险红线一票否决，不得用话术掩盖。

## 验收标准

每个 Agent 均经过 **5 案例真实 LLM 测试 + 8 项验收** 后冻结。
