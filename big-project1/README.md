# CMIP 过程挖掘软件

基于 CMIP-IMR 算法的跨部门协作过程挖掘与可视化系统

## 项目概述

本项目实现了论文 *"C. Liu, H. Li, S. Zhang, et al. Cross-department collaborative healthcare process model discovery from event logs. IEEE TASE, 2023, 20(3):2115-2125."* 中提出的跨部门协作过程挖掘方法，并在此基础上提出了改进算法 **CMIP-IMR**（Constraint-aware Multi-department Inductive Miner with Repair）。

### 功能特点

- **过程发现**：使用 Inductive Miner 从事件日志中发现 Petri 网模型
- **协作模式识别**：自动识别消息交互、资源共享、任务同步三类协作模式
- **质量评价**：计算 Fitness、Precision、F-measure 三项指标
- **错误诊断**：分析模型质量问题并定位错误类型
- **模型修复**：CE-PNR 约束增强修复策略
- **可视化**：Petri 网图形化展示与导出

---

## 环境要求

### 系统要求

- **操作系统**：Windows 10/11
- **Python 版本**：3.9 或更高

### 必需软件

1. **Python 3.9+**
   - 下载地址：https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. **Graphviz**（用于 Petri 网可视化）
   - 安装方式（任选一种）：
     ```powershell
     # 方式1：使用 winget
     winget install graphviz
     
     # 方式2：使用 chocolatey
     choco install graphviz
     ```
   - 或从官网下载：https://graphviz.org/download/
   - **重要**：安装后需要将 `C:\Program Files\Graphviz\bin` 添加到系统 PATH 环境变量

---

## 安装步骤

### 1. 克隆/下载项目

将项目文件夹复制到本地目录，例如 `D:\pyhon\big-project1`

### 2. 安装 Python 依赖

打开 PowerShell 或命令提示符，进入项目目录：

```powershell
cd D:\pyhon\big-project1
pip install -r requirements.txt
```

### 3. 验证安装

```powershell
python -c "import pm4py; print('PM4Py 版本:', pm4py.__version__)"
```

如果没有报错，说明安装成功。

### 4. 验证 Graphviz

```powershell
dot -V
```

如果显示版本号（如 `dot - graphviz version 14.1.1`），说明 Graphviz 安装成功。

如果提示找不到命令，需要：
1. 将 `C:\Program Files\Graphviz\bin` 添加到系统 PATH
2. 重启终端/IDE

---

## 运行方式

### 方式一：Streamlit Web 应用（推荐）

```powershell
cd D:\pyhon\big-project1
streamlit run app.py --server.port 8888
```

然后在浏览器打开：http://localhost:8888

### 方式二：命令行运行

```powershell
cd D:\pyhon\big-project1

# 运行完整的 CMIP-IMR 流程
python -m services.cmip_imr Log_09.csv

# 运行验证脚本（验证所有 6 个问题）
python verify_all.py
```

---

## 使用指南

### Web 应用使用步骤

1. **启动应用**
   ```powershell
   streamlit run app.py --server.port 8888
   ```

2. **上传日志**
   - 左侧边栏可以上传 CSV 或 XES 格式的事件日志
   - 或勾选"使用示例日志 (Log_09.csv)"使用内置示例

3. **配置参数**
   - **噪声阈值 (IMf)**：0.0-0.5，越高过滤越多低频行为
   - **目标 F-measure**：修复迭代的目标值
   - **最大迭代次数**：CE-PNR 修复的最大迭代次数
   - **启用 CE-PNR 修复**：是否启用约束增强修复

4. **开始挖掘**
   - 点击"开始挖掘"按钮
   - 等待处理完成（约 10-30 秒）

5. **查看结果**
   - **质量评价**：显示 N0 和 N1 的 Fitness/Precision/F-measure
   - **Petri 网可视化**：切换 N0/N1 标签页查看模型图
   - **导出**：下载 SVG、PNML、验证报告

### CSV 日志格式要求

日志文件需包含以下字段：

| 字段名 | 说明 | 示例 |
|--------|------|------|
| case_id | 案例编号 | 1, 2, 3... |
| tran | 活动名称 | T0, T1, T2... |
| timestamp | 时间戳 | 2018-01-02 08:46:00 |
| roles | 部门/角色列表 | ['Research'] |
| send_msg | 发送的消息列表 | ['m1'] |
| rec_msg | 接收的消息列表 | ['m1'] |
| req_res | 请求的资源列表 | ['r1'] |
| rel_res | 释放的资源列表 | ['r1'] |

---

## 项目结构

```
big-project1/
├── app.py                    # Streamlit Web 应用入口
├── requirements.txt          # Python 依赖列表
├── verify_all.py             # 验证脚本（验证 6 个问题）
├── Log_09.csv                # 示例事件日志
├── services/                 # 核心服务模块
│   ├── __init__.py
│   ├── ingest.py             # 日志导入与预处理
│   ├── discovery.py          # 过程发现（Inductive Miner）
│   ├── evaluation.py         # 质量评价（Fitness/Precision/F）
│   ├── repair.py             # CE-PNR 修复算子
│   ├── cmip_imr.py           # CMIP-IMR 主流程
│   └── visualize.py          # Petri 网可视化与导出
├── petri_net_n0.svg          # 生成的 Petri 网图像
├── petri_net_n0.pnml         # 生成的 PNML 模型文件
├── verification_report.md    # 验证报告
├── cmip_imr_result.json      # JSON 格式结果
└── CMIP_市场投资09_过程挖掘需求与实现路径.md  # 需求分析文档
```

---

## 问题对应关系

| 问题 | 对应模块 | 说明 |
|------|----------|------|
| 问题1 | `services/discovery.py` | 基于论文方法挖掘过程模型 N |
| 问题2 | `services/evaluation.py` | Fitness/Precision/F-measure 评价 |
| 问题3 | `services/repair.py` (diagnose) | 分析质量低下原因和错误类型 |
| 问题4 | `services/repair.py` (CE-PNR) | Petri 网修复策略移除错误 |
| 问题5 | `services/cmip_imr.py` | 改进算法 CMIP-IMR |
| 问题6 | `app.py` | PM4Py 过程挖掘软件 |

---

## 运行结果示例

使用 `Log_09.csv` 运行的结果：

| 指标 | N0（初始模型） | N1（最优模型） |
|------|---------------|---------------|
| Fitness | 0.9663 | 0.9663 |
| Precision | 0.9051 | 0.9051 |
| F-measure | 0.9347 | 0.9347 |

- **日志规模**：18909 案例，501439 事件
- **部门**：Compliance, Decision, Research, Risk, Transaction
- **同步任务**：T4_T30
- **消息交互**：m1, m2, m3, m4
- **共享资源**：r1, r2, riskReport

---

## 常见问题

### Q1: Graphviz 报错 "ExecutableNotFound"

**原因**：Graphviz 未安装或未添加到 PATH

**解决方案**：
1. 安装 Graphviz：`winget install graphviz`
2. 将 `C:\Program Files\Graphviz\bin` 添加到系统 PATH
3. 重启终端/IDE

### Q2: Streamlit 启动时提示端口被占用

**解决方案**：换一个端口

```powershell
streamlit run app.py --server.port 8889
```

### Q3: 第一次运行 Streamlit 要求输入邮箱

**说明**：这是 Streamlit 的欢迎提示，直接按 Enter 跳过即可

### Q4: 中文显示乱码

**解决方案**：确保终端使用 UTF-8 编码

```powershell
chcp 65001
```

---

## 参考文献

- C. Liu, H. Li, S. Zhang, et al. "Cross-department collaborative healthcare process model discovery from event logs." IEEE Transactions on Automation Science and Engineering, 2023, 20(3): 2115-2125.
- PM4Py 官方文档：https://pm4py.fit.fraunhofer.de/
- Inductive Miner API：https://processintelligence.solutions/static/api/2.7.11/api.html

---

## 联系方式

如有问题，请联系项目开发者。
