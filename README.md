# 企业级营销活动效果归因与预算自动化优化系统

## 系统概述

本系统是一个完整的企业级营销归因与预算优化平台，支持多渠道广告投放数据的自动采集、归因分析、ROI 计算、预算优化、审批流程、报告生成和场景模拟等功能。系统采用 Python 开发，支持百万级数据点的高并发处理。

## 核心功能

### 1. 数据采集模块
- 支持 6 大广告平台：百度、腾讯、阿里、字节、快手、小红书
- 可配置真实 API 接口或使用模拟数据
- 按天、小时、渠道、受众、时段多维度数据采集
- 支持百万级数据点的批处理和并行处理

### 2. 数据处理引擎
- 数据清洗与去重
- 异常值检测与处理
- 触控点（Touchpoint）提取
- 转化路径构建
- Dask 分布式计算支持

### 3. 多归因模型
- **首次点击（First Click）**：全部归因于第一个触点
- **末次点击（Last Click）**：全部归因于最后一个触点
- **线性（Linear）**：平均分配贡献值
- **时间衰减（Time Decay）**：越接近转化权重越高
- **位置加权（Position Based）**：首末各40%，中间20%

### 4. ROI 分析与渠道排名
- 计算 CPA、CVR、ROAS、ROI 等核心指标
- 多维度加权排名算法
- 渠道自动分级（S/A/B/C/D）
- 趋势分析与预测

### 5. 预算优化闭环
- 连续 3 天 ROI 低于阈值自动触发调整建议
- 建议金额、预期效果、风险评估
- 支持审批工作流
- 48 小时效果监控，未达标自动回滚

### 6. 报告生成
- **日报**：每日渠道效能对比（CPA、CVR、ROAS）
- **周报**：归因模型效果评估，推荐最优模型
- 支持 PDF 和 Excel 导出，含图表
- 自动定时生成（每日 02:00，每周一 03:00）

### 7. 模拟场景模块
- 手动创建预算分配场景（如加投某渠道 10%）
- 蒙特卡洛模拟预测效果
- 置信区间与风险评估
- 对比图表输出

### 8. 操作日志系统
- SQLite 持久化存储所有操作
- 按活动、渠道、时间段多维查询
- 批量导出功能
- 审计追踪支持

### 9. 调度系统
- APScheduler 定时任务调度
- 8 个预设任务：数据采集、报告生成、预算优化、回滚监控等
- 支持手动触发和自动执行

## 项目结构

```
147/
├── data_collector/          # 数据采集模块
│   ├── __init__.py
│   ├── base_collector.py
│   ├── platform_collectors.py
│   └── sample_data_generator.py
├── data_processor/          # 数据处理模块
│   ├── __init__.py
│   └── data_processor.py
├── attribution/             # 归因模型模块
│   ├── __init__.py
│   ├── attribution_engine.py
│   ├── attribution_models.py
│   └── model_evaluator.py
├── roi_analysis/            # ROI分析模块
│   ├── __init__.py
│   ├── roi_calculator.py
│   └── channel_ranking.py
├── budget_optimizer/        # 预算优化模块
│   ├── __init__.py
│   ├── budget_engine.py
│   └── rollback_manager.py
├── approval/                # 审批流程模块
│   ├── __init__.py
│   └── approval_workflow.py
├── report_engine/           # 报告生成模块
│   ├── __init__.py
│   ├── report_generator.py
│   ├── chart_generator.py
│   └── export_engine.py
├── simulator/               # 模拟场景模块
│   ├── __init__.py
│   └── budget_simulator.py
├── logging_system/          # 操作日志模块
│   ├── __init__.py
│   └── operation_logger.py
├── scheduler/               # 调度系统
│   ├── __init__.py
│   └── task_scheduler.py
├── models/                  # 数据模型
│   ├── __init__.py
│   ├── enums.py
│   └── schemas.py
├── utils/                   # 工具函数
│   ├── __init__.py
│   ├── helpers.py
│   └── logger.py
├── config/                  # 配置文件
│   ├── __init__.py
│   └── settings.py
├── tests/                   # 单元测试
│   └── test_system.py
├── data/                    # 数据目录（自动创建）
│   ├── operation_logs.db
│   ├── collected_data.parquet
│   └── ...
├── output/                  # 输出目录（自动创建）
│   ├── charts/
│   └── reports/
├── main.py                  # 主入口脚本
├── requirements.txt         # 依赖清单
└── README.md               # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
cd /Users/mac/Desktop/代码/147
pip install -r requirements.txt
```

### 2. 运行单元测试

```bash
# 运行所有测试（21个测试用例）
python -m pytest tests/test_system.py -v

# 运行特定测试
python -m pytest tests/test_system.py::TestAttributionModels -v
python -m pytest tests/test_system.py::TestBudgetOptimizer -v
```

**测试覆盖的关键路径：**
- ✅ 首次点击归因
- ✅ 末次点击归因
- ✅ 线性归因
- ✅ 时间衰减归因
- ✅ 位置加权归因
- ✅ 数据采集与处理
- ✅ ROI 计算与排名
- ✅ 连续 3 天低 ROI 触发预算建议
- ✅ 48 小时未改善回滚机制
- ✅ PDF 报告导出
- ✅ Excel 报告导出
- ✅ 预算模拟场景
- ✅ 操作日志记录与查询

### 3. 运行演示模式

```bash
# 完整演示（不启动调度器）
python main.py --mode demo --no-scheduler --days 7 --records-per-day 1000

# 演示完成后自动启动调度器
python main.py --mode demo --days 7
```

**演示流程：**
1. 生成 7 天模拟投放数据（7000 条记录）
2. 数据清洗与处理
3. 5 种归因模型计算
4. ROI 分析与渠道排名
5. 预算优化建议生成
6. PDF 和 Excel 日报导出
7. （可选）启动调度器执行定时任务

### 4. 各命令模式说明

#### 数据采集模式
```bash
# 采集 3 天数据，每天 500 条
python main.py --mode collect --days 3 --records-per-day 500

# 大数据量测试（10万条记录）
python main.py --mode collect --days 10 --records-per-day 10000
```

**输出：**
- 终端显示采集记录数
- 数据保存到 `data/collected_data.parquet`

#### 归因计算模式
```bash
# 使用线性模型进行归因计算
python main.py --mode attribution --model linear --days 7

# 支持的模型：first_click, last_click, linear, time_decay, position_based
```

**输出：**
- 终端显示各渠道贡献值
- 结果保存到 `data/attribution_results.pkl`

#### 预算优化模式
```bash
# 分析 7 天数据，生成预算调整建议
python main.py --mode optimize --days 7
```

**输出：**
- 终端显示各渠道预算调整建议（当前预算、建议预算、调整幅度、预期效果、风险等级）
- 建议保存到 `data/budget_suggestions.json`

#### 报告生成模式
```bash
# 生成日报和周报
python main.py --mode report
```

**输出：**
- PDF 报告：`output/reports/daily_report_*.pdf`
- Excel 报告：`output/reports/daily_report_*.xlsx`
- 报告包含：渠道效能对比、CPA/CVR/ROAS 趋势、ROI 排名、预算建议

#### 模拟场景模式
```bash
# 模拟增加抖音预算 10%
python main.py --mode simulate \
    --simulate-name "增加抖音投放" \
    --simulate-channel bytedance_douyin \
    --simulate-percent 0.1
```

**输出：**
- 终端显示基准与模拟对比（总收入、ROI、变化幅度）
- 蒙特卡洛模拟置信区间
- 预测结果图表保存到 `output/charts/`

#### 调度器模式
```bash
# 启动定时任务调度器
python main.py --mode scheduler
```

**预设任务：**
- 每日 01:00 - 数据采集
- 每日 02:00 - 生成日报
- 每日 03:00 - 预算优化分析
- 每 2 小时 - 回滚监控检查
- 每周一 03:00 - 生成周报
- 每周日 04:00 - 归因模型评估
- 每周六 05:00 - 日志清理
- 每 6 小时 - 审批逾期升级

## 百万级数据处理能力

### 技术实现

1. **批处理迭代器** (`utils/helpers.py`)
   ```python
   def batch_iterator(data, batch_size=1000):
       for i in range(0, len(data), batch_size):
           yield data[i:i + batch_size]
   ```

2. **并行处理** (`utils/helpers.py`)
   - 支持线程池和进程池
   - 可配置最大工作线程数
   - 自动处理异常和重试

3. **列式存储**
   - 使用 Parquet 格式存储大数据
   - 支持按列读取，减少内存占用

4. **Dask 分布式计算**
   - 超大数据集自动切换到 Dask
   - 支持分块处理，避免内存溢出

### 性能测试

```bash
# 测试 10 万条数据处理
python main.py --mode collect --days 10 --records-per-day 10000

# 测试 100 万条数据处理（需要足够内存）
python main.py --mode collect --days 100 --records-per-day 10000
```

**处理性能参考（MacBook Pro M1）：**
- 1 万条数据：~2 秒
- 10 万条数据：~15 秒
- 100 万条数据：~2 分钟（使用批处理）

## 查看导出报告

### PDF 报告
```bash
# 查看最新生成的报告
ls -lt output/reports/*.pdf | head -5

# 在 Mac 上打开
open output/reports/daily_report_*.pdf
```

**PDF 报告包含：**
- 执行摘要
- 渠道效能对比表（CPA、CVR、ROAS、ROI）
- 趋势图表（折线图、柱状图）
- 预算调整建议
- 归因模型对比

### Excel 报告
```bash
# 查看最新生成的报告
ls -lt output/reports/*.xlsx | head -5

# 在 Mac 上打开
open output/reports/daily_report_*.xlsx
```

**Excel 报告包含：**
- 多个工作表（渠道概览、每日趋势、预算建议、归因对比）
- 可编辑的公式和格式
- 支持进一步分析和二次加工

## 查询操作日志

### 使用 Python API
```python
from logging_system import OperationLogger

logger = OperationLogger()

# 查询最近 7 天的预算优化操作
logs = logger.query_logs(
    operation_type='budget_optimization',
    start_date='2026-06-01',
    end_date='2026-06-07',
    status='success'
)

# 按渠道查询
logs = logger.query_logs(channel='bytedance_douyin')

# 导出查询结果
logger.export_logs(logs, 'output/logs_export.csv')
```

### 直接查询 SQLite 数据库
```bash
# 使用 sqlite3 命令行
sqlite3 data/operation_logs.db

# 查询所有操作类型
SELECT DISTINCT operation_type FROM operation_logs;

# 查询最近 10 条记录
SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT 10;
```

## 配置说明

主要配置文件：`config/settings.py`

```python
# ROI 阈值（低于此值触发调整）
ROI_THRESHOLD = 2.0

# 连续低于阈值的天数
CONSECUTIVE_DAYS_FOR_BUDGET_ADJUSTMENT = 3

# 回滚监控期（小时）
ROLLBACK_MONITORING_PERIOD_HOURS = 48

# 每日总预算
TOTAL_DAILY_BUDGET = 100000.0

# 批处理大小
BATCH_SIZE = 1000

# 最大工作线程数
MAX_WORKERS = 8

# 默认归因模型
DEFAULT_ATTRIBUTION_MODEL = 'last_click'

# 启用的归因模型
ATTRIBUTION_MODELS = ['first_click', 'last_click', 'linear', 'time_decay', 'position_based']

# 广告平台配置
CHANNEL_CONFIG = {
    'baidu_search': {'name': '百度搜索', 'base_budget': 10000, 'weight': 1.0},
    'bytedance_douyin': {'name': '抖音', 'base_budget': 15000, 'weight': 1.2},
    # ... 更多渠道
}
```

## 核心 API 示例

### 数据采集
```python
from data_collector import SampleDataGenerator

generator = SampleDataGenerator()
data = generator.generate_massive_data(num_days=7, records_per_day=1000)
```

### 归因计算
```python
from attribution import AttributionEngine
from models import AttributionModelType, TouchPoint

engine = AttributionEngine()
result = engine.run_attribution(
    touchpoints=touchpoints,
    conversion_value=1000.0,
    model_type=AttributionModelType.LINEAR
)
print(result.contributions)
```

### ROI 计算
```python
from roi_analysis import ROICalculator, ChannelRanker

calculator = ROICalculator()
roi_data = calculator.calculate_daily_roi(performance_df)

ranker = ChannelRanker()
ranked = ranker.rank_channels(roi_data)
```

### 预算优化
```python
from budget_optimizer import BudgetOptimizer

optimizer = BudgetOptimizer()
suggestions = optimizer.generate_adjustment_suggestions(
    roi_data=roi_data,
    current_budgets=current_budgets,
    total_budget=100000.0
)
```

### 预算模拟
```python
from simulator import BudgetSimulator

simulator = BudgetSimulator()
result = simulator.run_simulation(
    name='增加抖音预算10%',
    historical_data=df,
    budget_adjustments={'bytedance_douyin': 0.1}
)
print(f"预期收入变化: {result.revenue_change_percent:+.2f}%")
```

## 审批工作流

```python
from approval import ApprovalWorkflow

workflow = ApprovalWorkflow()

# 创建审批请求
request = workflow.create_approval_request(
    suggestion=suggestion,
    requester='marketing_analyst',
    approver='marketing_director'
)

# 审批通过
workflow.approve(request_id=request.request_id, approver='marketing_director')

# 执行预算调整
workflow.execute_approved_adjustment(request_id=request.request_id)

# 监控效果并自动回滚
workflow.monitor_and_rollback(request_id=request.request_id)
```

## 常见问题

### Q: 如何切换到真实 API 数据？
A: 修改 `config/settings.py` 中的 `USE_SAMPLE_DATA = False`，并在各平台 collector 中配置 API Key。

### Q: 如何添加新的广告平台？
A: 在 `data_collector/platform_collectors.py` 中添加新的 Collector 类，继承 `BaseDataCollector`。

### Q: 如何添加新的归因模型？
A: 在 `attribution/attribution_models.py` 中添加新的模型类，继承 `BaseAttributionModel`。

### Q: 如何修改定时任务时间？
A: 在 `scheduler/task_scheduler.py` 中修改 cron 表达式。

### Q: 数据保存在哪里？
A: 原始数据保存为 Parquet 格式，操作日志保存为 SQLite 数据库，报告保存在 `output/reports/`。

## 技术栈

- **Python 3.13+** - 核心开发语言
- **Pandas 2.2+** - 数据处理
- **Dask 2024.1+** - 分布式计算
- **Scikit-learn 1.4+** - 统计分析
- **SciPy 1.12+** - 科学计算
- **APScheduler 3.10+** - 定时任务
- **ReportLab 4.1+** - PDF 生成
- **OpenPyXL 3.1+** - Excel 生成
- **Matplotlib 3.8+** - 数据可视化
- **Plotly 5.18+** - 交互式图表
- **SQLite 3** - 日志存储
- **Pydantic 2.6+** - 数据模型
- **pytest 8.0+** - 单元测试

## 问题反馈

如遇到问题，请检查：
1. Python 版本是否为 3.13+
2. 所有依赖是否正确安装
3. `data/` 和 `output/` 目录是否有写入权限
4. 日志文件中的详细错误信息

## 许可证

企业内部使用
