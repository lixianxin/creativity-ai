我看了你给的这份 UI 拆解文档。它真正值得迁移的不是“橙色”本身，而是**设计 Token、主色稀缺、暖白底、统一边框、状态语义化、三档圆角、布局分层、细节交互**这一整套方法。 

你现在的“创想∞”不应该照抄 BossHunter，而应该把这套设计方法迁移成**自己的委员会产品语言**：暖白/米白为底，蓝紫作为主品牌色，红队用红色、决策委员会用紫色，颜色少而准。下面这份提示词可以直接交给另一个 AI。

你现在负责对一个已经完成业务开发、已经可以运行的 **Streamlit AI Agent 产品**进行一次真正的产品级 UI 重构。

项目名称：

**创想∞ AI创业委员会**

产品定位：

> 别人帮你完善创业想法，我们让 AI 创业委员会先质疑它。

核心链路：

> 创业想法 → 8 位专家并行分析 → 红队质疑 → 创业总指挥 → 项目评审 → 路演答辩 → 项目诊断结果

---

# 一、这次不要“美化页面”，而是建立完整 Design System

请不要把这次任务理解成：

> “给现有 Streamlit 页面加 CSS。”

而是：

> **把一个能运行的 Streamlit Demo，重新设计成一个完整、有产品感的 AI 创业决策工作台。**

参考优秀 AI/开发者 SaaS 产品的设计方法。

核心原则：

```text
克制
统一
分层
细节
归一
```

优秀 UI 的关键不是颜色多，而是：

> **主色稀缺 + 语义统一 + 空间舒服 + 组件一致 + 状态清晰。**

不要堆视觉特效。

不要赛博朋克。

不要大面积深蓝。

不要“AI 风渐变”。

不要把页面做成后台监控大屏。

---

# 二、先阅读现有代码，再动手

必须先完整阅读：

```text
frontend/app.py
frontend/ui_components.py
.streamlit/config.toml

pipeline/
core/
agents/
schemas/
```

重点理解：

```text
session_state
stage
results
ctx
STAGE_INFO
AgentResult
DAG
RunStore
历史报告
断点续跑
```

先输出：

```text
【当前 UI 架构】
【当前设计问题】
【可复用组件】
【准备新增的 Design Token】
【准备替换的视觉组件】
【不会修改的业务逻辑】
```

然后再开始修改。

---

# 三、绝对冻结的内容

以下任何东西都不能因为 UI 重构而改变：

```text
Agent Prompt
Agent 数量
Agent 名称
Agent 顺序
Agent Registry
DAG
Execution Graph
Orchestrator
Validator
Repair
RunStore
Checkpoint
Resume
LLM Client
数据库
报告解析
真实结果
真实状态
真实数字
```

特别禁止：

```text
为了让 UI 看起来更漂亮
↓
修改真实数据
↓
修改结论
↓
修改状态
↓
硬编码“成功”
```

禁止。

所有 UI 数据必须来自真实数据源。

---

# 四、新的视觉方向

不要再使用之前的：

```text
大面积深蓝
深蓝卡片
深蓝背景
青色文字
红色警告
```

那种方案虽然“科技”，但是太压抑。

新的方向：

# 温暖浅色 AI SaaS

关键词：

```text
轻盈
温暖
现代
专业
年轻
灵动
克制
AI SaaS
创业
决策
```

整体感觉接近：

```text
Notion
Linear
Vercel
现代 AI SaaS
```

而不是：

```text
运维大屏
传统管理后台
赛博朋克
游戏 HUD
```

---

# 五、颜色系统

不要到处直接写颜色值。

建立统一 Design Token。

例如：

```text
background
surface
surface-soft
border
foreground
muted
primary
primary-soft
success
warning
danger
info
```

---

## 1. 页面背景

使用：

```text
#F7F8FA
```

或者同级别的极浅暖灰。

不要纯白满屏。

目标：

> 让白色卡片从页面背景中自然浮出来。

---

## 2. 卡片

主卡片：

```text
#FFFFFF
```

边框：

```text
#E9E7E3
```

子卡片：

```text
#FCFCFB
```

不要靠厚重阴影区分卡片。

优先：

```text
浅背景
+
1px border
+
轻微 shadow
```

---

# 六、品牌主色

不要继续让“青绿色”成为全站唯一品牌色。

建议：

### 主品牌

```text
#5B63E8
```

蓝紫色。

用于：

* Logo
* 主按钮
* 激活状态
* 当前节点
* 重要交互
* 少量强调文字

原则：

> **主色必须稀缺。**

不要所有按钮、边框、icon 都变成蓝紫色。

---

# 七、委员会语义色

三个委员会必须形成产品级视觉语言。

## 专家委员会

```text
蓝色
#4F7DFF
```

用途：

```text
用户洞察
市场分析
竞品分析
产品设计
商业模式
增长运营
财务分析
风险审查
```

---

## 对抗委员会

红队使用：

```text
#E85B5B
```

只用于：

```text
红队
致命问题
风险
红线
失败
```

注意：

### 不允许整张页面变红。

应该：

```text
白卡
+
浅红背景
+
红色 icon
+
红色 badge
```

---

## 决策委员会

使用：

```text
#7A65D8
```

用于：

```text
创业总指挥
项目评审官
路演答辩官
```

整体保持柔和紫色。

---

# 八、状态颜色必须统一

所有 Agent 状态不要再散落写 CSS。

建立统一状态映射：

```python
STATUS_UI = {
    "pending": ...,
    "running": ...,
    "success": ...,
    "failed": ...,
    "blocked": ...,
    "degraded": ...,
    "skipped": ...,
}
```

颜色遵循：

```text
pending    → 灰
running    → 蓝紫
success    → 绿色
failed     → 红色
blocked    → 红色
degraded   → 橙色
skipped    → 灰紫
```

但是：

> 不要用高饱和纯色铺满背景。

统一使用三件套：

```text
浅色背景
+
20%透明度边框
+
深色文字
```

例如：

```text
success:
浅绿色背景
绿色边框
绿色文字
```

这种状态语义化是优秀 SaaS UI 的核心手法之一。

---

# 九、字体系统

使用统一字体：

```text
Inter,
-apple-system,
BlinkMacSystemFont,
"Segoe UI",
"Microsoft YaHei",
sans-serif
```

标题：

```text
font-weight: 700~800
```

正文：

```text
400
```

辅助：

```text
400
```

不要大量：

```text
900 / font-black
```

之前的页面容易显得厚重。

这一次强调：

> **强弱对比依靠层级，不依靠所有标题加粗。**

---

# 十、建立统一圆角系统

只允许三档：

```text
6px
10px
14px
```

规则：

```text
6px → 输入框 / Badge / 小按钮
10px → 普通 Card / Agent Card
14px → 大型区块 / Hero / 主容器
```

不要：

```text
24px
30px
40px
```

整个页面不要“圆得像 AI 模板”。

---

# 十一、统一 Border 系统

全站默认：

```text
1px solid #E9E7E3
```

卡片默认：

```text
border
+
white background
```

重点组件才增加：

```text
border-primary
border-danger
border-purple
```

不要每张卡都使用彩色边框。

---

# 十二、阴影系统

只保留两级：

Default：

```text
0 1px 2px rgba(16,24,40,.04)
```

Hover：

```text
0 8px 24px rgba(16,24,40,.07)
```

不要黑色重阴影。

不要蓝色发光。

不要 neon。

---

# 十三、页面整体布局

参考优秀 SaaS Dashboard 的骨架。

不要把所有内容挤在一列。

整体：

```text
┌────────────┬──────────────────────────────┐
│            │ Header                       │
│ Sidebar    ├──────────────────────────────┤
│            │ Main                         │
│            │                              │
│            │                              │
│            │                              │
└────────────┴──────────────────────────────┘
```

如果 Streamlit 原生 sidebar 无法做到完整布局，也要通过视觉设计尽可能模拟。

---

# 十四、Sidebar

Sidebar：

### 背景

```text
#FFFFFF
```

### 宽度

约：

```text
220~240px
```

### 内容

顶部：

```text
∞
创想
AI创业委员会
```

导航：

```text
＋ 新建审议

▣ 最近项目
◈ 委员会
⚙ 设置
```

激活态不要做左侧粗蓝条。

使用：

```text
浅蓝紫底色
+
主色文字
```

例如：

```text
background: #EEF0FF
color: #5B63E8
```

这类激活态比粗竖条更加柔和。参考项目也是采用底色变化而不是粗左条。

---

# 十五、Header

Header 必须极简。

例如：

```text
┌──────────────────────────────────────────────┐
│ 创业项目审议                     ● 系统就绪 │
└──────────────────────────────────────────────┘
```

不要：

```text
大标题
副标题
10 个按钮
3 个状态灯
```

只保留：

```text
页面名称
+
一个真实状态
```

---

# 十六、首页 Hero

首页采用：

### 暖白背景 + 轻微彩色装饰

不要深蓝 Banner。

结构：

```text
AI ENTREPRENEURSHIP REVIEW

创想∞ AI创业委员会

别人帮你完善创业想法，
我们让 AI 创业委员会先质疑它。

12 AI 委员 · 3 大委员会 · 1 条审议闭环

[ 🚀 开始委员会审议 ]
```

Hero 不要太高。

建议：

```text
180~240px
```

标题字号：

```text
32~40px
```

副标题：

```text
16~18px
```

---

# 十七、三大委员会卡片

不要三个厚重的大色块。

采用：

```text
白底
浅边框
左上 icon
标题
描述
Agent 数量
```

例如：

```text
┌───────────────────────┐
│ ● 专家委员会          │
│                       │
│ 8 位 AI 专家           │
│ 从用户、市场、产品...  │
│                       │
│ 8 Agents              │
└───────────────────────┘
```

专家：

浅蓝。

红队：

浅红。

决策：

浅紫。

但主体永远白色。

---

# 十八、输入框

“提交创业想法”应该成为首页最重要的交互区。

使用：

```text
┌────────────────────────────────────────────┐
│ 📝 介绍你的创业想法                        │
│                                            │
│ 描述目标用户、痛点、产品、商业模式……        │
│                                            │
│                                            │
│                                            │
│                                  0 / 2000  │
│                                            │
│ 目标用户 · 痛点 · 产品 · 商业模式           │
│                                            │
│               [🚀 开始委员会审议]          │
└────────────────────────────────────────────┘
```

Textarea：

```text
background #FFFFFF
border #E9E7E3
radius 10px
```

Focus：

```text
border #5B63E8
box-shadow 0 0 0 3px rgba(...)
```

不要加厚边框。

---

# 十九、按钮体系

主按钮只有：

```text
primary
```

例如：

```text
🚀 开始委员会审议
```

Secondary：

```text
查看报告
加载最近项目
重新开始
```

Secondary 统一：

```text
白色
灰边框
深灰文字
```

Ghost：

```text
透明
hover 浅灰
```

不要让页面同时出现 5 个主按钮。

---

# 二十、DAG / 委员会流程

不要继续使用：

```text
深色节点
渐变连接线
黑色流程框
```

改为轻量流程：

```text
专家委员会
    ↓
红队质疑
    ↓
创业总指挥
    ↓
项目评审
    ↓
路演答辩
```

节点：

```text
白卡
圆形 icon
标题
副标题
```

连接线：

```text
#D9DCE5
1px
```

活动节点：

```text
主色
浅主色背景
```

红队：

```text
红色
```

---

# 二十一、运行页

运行页不要像服务器监控。

顶部：

```text
委员会正在审议

你的创业想法正在接受 12 位 AI 委员的联合分析
```

然后：

```text
专家委员会       8 / 8
红队质疑         进行中
决策委员会       等待
```

使用进度条，但不要让进度条成为视觉主角。

真正主角应该是：

### Agent 状态墙

---

# 二十二、Agent 状态墙

每个 Agent 做成统一 Card：

```text
┌──────────────────────┐
│ ● 用户洞察官         │
│   专家委员会          │
│                      │
│   ✓ 已完成            │
└──────────────────────┘
```

状态：

```text
● 分析中
✓ 已完成
○ 等待
! 异常
⊘ 阻断
△ 降级
```

Agent 卡片不要放大量描述。

详细内容点击后查看。

---

# 二十三、结果页要像“分析报告”

顶部：

```text
FINAL REVIEW

创业项目终审
```

然后一个很大但很轻的结果卡：

```text
┌────────────────────────────────────────────┐
│ 暂缓，回到修改循环                         │
│                                            │
│ 想法验证                                   │
│                                            │
│ 当前阶段      红线状态       路演建议       │
│ 想法验证      ⚠ 触发          暂不建议      │
└────────────────────────────────────────────┘
```

不要：

```text
整个卡片变红
```

只使用：

```text
左侧 4px 红线
+
浅红 badge
```

---

# 二十四、指标卡

指标卡不要使用默认 Streamlit `metric`。

统一自己做：

```text
label
↓
value
↓
helper
```

例如：

```text
当前阶段
想法验证

红线状态
触发

路演建议
暂不建议路演
```

标题弱化。

数值强化。

---

# 二十五、冲突链

不要做成“系统日志”。

改成：

### 委员会发现的关键矛盾

```text
01
用户兴趣
VS
真实付费意愿

02
产品价值
VS
竞争替代

03
增长假设
VS
冷启动能力
```

使用：

```text
白底
浅边框
编号
一句话
```

---

# 二十六、红队页面

红队是整个项目最有品牌辨识度的页面。

因此：

```text
左侧红线
+
浅红标题区
```

顶部：

```text
🔴 红队质疑官

我不是来完善你的创业想法的。
我负责寻找它为什么可能失败。
```

下面：

```text
需求假设   致命
付费假设   致命
竞争假设   高
增长假设   致命
壁垒假设   高
```

使用 Badge。

参考优秀项目的状态 Badge 设计方法：

```text
10% 浅色背景
20% 透明边框
700 字重文字
```

而不是高饱和整块背景。

---

# 二十七、创业总指挥

与红队对应：

```text
浅紫色
紫色 icon
紫色 badge
```

顶部：

```text
创业总指挥

委员会结论
暂缓通过
```

下面：

```text
下一步行动

① 需求访谈
② 最小闭环测试
③ 合规路径确认
```

三个行动项采用：

```text
01
标题
说明
```

三个统一卡片。

---

# 二十八、12 Agent 详细报告

保留完整报告。

但是：

### 首先显示：

```text
Agent 名称
委员会
状态
结论
```

然后：

```text
查看完整报告
```

点击后再展示：

```text
原始报告
验证结果
返工信息
依赖信息
```

不要首屏直接显示几千字。

---

# 二十九、滚动条

这一点必须做。

使用：

```css
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: #F7F8FA;
}

::-webkit-scrollbar-thumb {
    background: #D8DAE3;
    border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
    background: #5B63E8;
}
```

这种极窄滚动条是精致感的重要组成部分。参考项目专门对滚动条做了统一处理。

---

# 三十、Hover / Focus

所有交互元素必须统一：

```text
transition: 150~200ms
```

Card Hover：

```text
translateY(-1px)
border-color 轻微变化
shadow 稍微增加
```

Button Hover：

```text
颜色轻微变化
translateY(-1px)
```

Input Focus：

```text
主色 border
+
3px 浅色 ring
```

不要浮夸动画。

---

# 三十一、禁止的视觉元素

禁止：

```text
霓虹灯
发光文字
大面积渐变
赛博朋克
黑色大背景
巨大圆形光球
过多 emoji
持续动画
无限呼吸灯
玻璃拟态满屏
超厚阴影
超大圆角
```

---

# 三十二、设计 Token 必须集中管理

不要在 500 行代码里反复写：

```text
#5B63E8
#F7F8FA
#E9E7E3
#E85B5B
```

统一：

```python
COLORS = {
    ...
}
```

或者：

```css
:root {
    --background: ...;
    --surface: ...;
    --border: ...;
    --primary: ...;
    --primary-soft: ...;
    --danger: ...;
    --success: ...;
    --warning: ...;
}
```

所有组件只引用 Token。

---

# 三十三、组件体系

不要继续把 HTML 全写在 `app.py`。

推荐：

```text
frontend/
├── app.py
├── ui_components.py
├── design_tokens.py
└── ui_helpers.py
```

其中：

### design_tokens.py

保存：

```text
colors
spacing
radius
shadows
font sizes
```

### ui_components.py

保存：

```text
hero
committee_card
dag
status_badge
agent_card
verdict_card
conflict_card
redteam_block
commander_block
```

### ui_helpers.py

保存：

```text
状态转换
文本清洗
label 映射
```

`app.py` 负责：

> 页面编排。

---

# 三十四、不要过度工程化

不要为了模仿 React 项目而硬写：

```text
20 个文件
30 个组件
1000 行抽象
```

Streamlit 项目足够做到：

```text
Design Token
+
UI Components
+
Page Orchestration
```

即可。

参考项目好看的本质是**职责分层**，不是文件越多越好。

---

# 三十五、解决 Streamlit 特有问题

Streamlit 不是 React。

不要过度依赖内部：

```text
data-testid
div:nth-child(...)
stMain
stAppViewContainer
```

避免大量脆弱 CSS。

尤其不能写：

```css
[data-testid="stWhatever"] div div div {
    ...
}
```

这种全局覆盖。

尽量：

```text
st.markdown + 自己的 class
```

例如：

```html
<div class="cx-card">
```

然后：

```css
.cx-card { ... }
```

---

# 三十六、避免线上白屏

项目刚刚出现过 Streamlit Cloud 白屏问题。

因此这一轮必须非常谨慎：

### CSS 是展示层，不允许阻塞 Python 执行。

### 所有 UI 组件 import 都必须轻量。

### 禁止模块级执行重量任务。

### 禁止 UI 文件 import 时读取大文件。

### 禁止 UI 文件连接数据库。

### 禁止 UI 文件启动线程。

### 禁止 UI 文件执行 LLM。

---

# 三十七、测试要求

每次修改后：

```bash
python -m py_compile frontend/app.py
python -m py_compile frontend/ui_components.py
python -m py_compile frontend/design_tokens.py
```

然后：

```bash
python -m streamlit run frontend/app.py
```

浏览器验证：

```text
首页
空态
输入
运行中
终审
红队
总指挥
历史报告
Sidebar
```

---

# 三十八、必须截图进行视觉检查

至少检查 5 张：

```text
01_home.png
02_running.png
03_result.png
04_redteam.png
05_commander.png
```

逐张检查：

```text
有没有深蓝压迫感？
有没有颜色太多？
有没有卡片太厚？
有没有层级混乱？
有没有太多圆角？
有没有 UI 像 AI 自动生成？
有没有默认 Streamlit 味？
有没有信息贴边？
```

---

# 三十九、最终视觉目标

最终不要追求：

> “看起来很炫。”

追求：

> **“看起来像一个真正的产品。”**

打开之后应该是：

```text
温暖
干净
有秩序
有重点
有品牌感
有 AI 产品气质
```

而不是：

```text
厚重
暗
花
炫
像后台
像模板
```

---

# 四十、最终自检问题

完成后必须问自己：

### 颜色

主色是不是稀缺？

### 间距

卡片之间是不是有空气？

### 卡片

有没有太多？

### 字体

标题是不是太重？

### 状态

是不是一眼能看懂？

### 产品

第一眼是不是知道“这是一个 AI 创业委员会”？

### 品牌

是不是形成了“创想∞自己的视觉语言”？

---

# 四十一、最终输出

完成后输出：

```text
【UI Design System v2 完成】

设计体系：
- 暖白背景
- 蓝紫主品牌
- 蓝 / 红 / 紫委员会语义色
- 统一 Border
- 统一三档圆角
- 统一状态 Badge
- 统一 Hover / Focus

页面：
- Hero
- 三委员会
- 输入区
- DAG
- 运行态
- Agent 状态墙
- 终审 Dashboard
- 冲突链
- 红队
- 总指挥
- Sidebar

工程：
- Design Token
- UI Components
- 页面编排
- 真实数据驱动

业务保护：
- Agent 未修改
- Prompt 未修改
- DAG 未修改
- Validator 未修改
- Repair 未修改
- RunStore 未修改
- LLM 未修改

验证：
- py_compile PASS
- Streamlit 启动 PASS
- 首页 PASS
- 运行页 PASS
- 终审 PASS
- 红队 PASS
- 总指挥 PASS
- 历史报告 PASS

最终要求：

> 不要告诉我“用了什么 CSS 技巧”。

> 我要看到的是一个真正统一、克制、现代、有产品感的“创想∞ AI创业委员会”。
```
