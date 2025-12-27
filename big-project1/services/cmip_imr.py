"""
cmip_imr.py - CMIP-IMR 主流程模块
Constraint-aware Multi-department Inductive Miner with Repair

完整流程：
1. 预处理：解析日志字段、按 case 排序、抽取部门视角
2. 初始发现：对每部门用 IMf 发现局部 Petri 网
3. 协作抽取：抽取消息依赖、同步点候选、共享资源
4. 集成组合：合并为初始集成网 N0
5. 质量评价：计算 Fitness/Precision/F
6. 约束增强修复：执行 CE-PNR 得到 N1
7. 再评价：若 F-measure 未达到阈值则迭代
"""

import json
from typing import Dict, Tuple, Optional
from datetime import datetime

from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.log.obj import EventLog

from services.ingest import load_and_prepare_log, df_to_eventlog
from services.discovery import discover_integrated_model
from services.evaluation import evaluate_model, get_alignment_diagnostics, format_evaluation_report
from services.repair import apply_ce_pnr, diagnose_all_errors, format_diagnosis_report, format_repair_report


class CMIPIMRResult:
    """CMIP-IMR 执行结果"""
    
    def __init__(self):
        self.n0_net: Optional[PetriNet] = None
        self.n0_im: Optional[Marking] = None
        self.n0_fm: Optional[Marking] = None
        self.n0_metrics: Optional[Dict] = None
        
        self.n1_net: Optional[PetriNet] = None
        self.n1_im: Optional[Marking] = None
        self.n1_fm: Optional[Marking] = None
        self.n1_metrics: Optional[Dict] = None
        
        self.metadata: Optional[Dict] = None
        self.diagnosis: Optional[Dict] = None
        self.repair_report: Optional[Dict] = None
        self.iterations: int = 0
        
    def to_dict(self) -> Dict:
        return {
            'n0_metrics': self.n0_metrics,
            'n1_metrics': self.n1_metrics,
            'metadata': {
                'departments': self.metadata.get('departments', []),
                'sync_tasks': self.metadata.get('sync_tasks', []),
                'messages': {k: list(v) for k, v in self.metadata.get('messages', {}).items()},
                'resources': {k: [list(v[0]), list(v[1])] for k, v in self.metadata.get('resources', {}).items()},
                'total_cases': self.metadata.get('total_cases', 0),
                'total_events': self.metadata.get('total_events', 0)
            },
            'repair_report': self.repair_report,
            'iterations': self.iterations
        }


def run_cmip_imr(filepath: str,
                  noise_threshold: float = 0.2,
                  target_f_measure: float = 0.95,
                  max_iterations: int = 3,
                  remove_resources_if_low_fitness: bool = True,
                  fitness_threshold: float = 0.8) -> CMIPIMRResult:
    """
    执行 CMIP-IMR 完整流程
    
    参数：
    - filepath: 日志文件路径
    - noise_threshold: IMf 噪声阈值
    - target_f_measure: 目标 F-measure
    - max_iterations: 最大迭代次数
    - remove_resources_if_low_fitness: 当 fitness 过低时是否移除资源约束
    - fitness_threshold: fitness 阈值（低于此值时考虑移除资源约束）
    
    返回：CMIPIMRResult 对象
    """
    result = CMIPIMRResult()
    
    print("=" * 60)
    print("CMIP-IMR: 跨部门协作过程挖掘与修复")
    print("=" * 60)
    
    print("\n[Step 1] 发现初始模型 N0...")
    n0_net, n0_im, n0_fm, metadata, df, log = discover_integrated_model(
        filepath, 
        noise_threshold=noise_threshold
    )
    
    result.n0_net = n0_net
    result.n0_im = n0_im
    result.n0_fm = n0_fm
    result.metadata = metadata
    
    print(f"  - Places: {len(n0_net.places)}")
    print(f"  - Transitions: {len(n0_net.transitions)}")
    print(f"  - 部门: {metadata['departments']}")
    print(f"  - 同步任务: {metadata['sync_tasks']}")
    print(f"  - 消息: {list(metadata['messages'].keys())}")
    print(f"  - 资源: {list(metadata['resources'].keys())}")
    
    print("\n[Step 2] 评价 N0...")
    global_log = df_to_eventlog(df)
    n0_metrics = evaluate_model(global_log, n0_net, n0_im, n0_fm)
    result.n0_metrics = n0_metrics
    
    print(f"  - Fitness:   {n0_metrics['fitness']:.4f}")
    print(f"  - Precision: {n0_metrics['precision']:.4f}")
    print(f"  - F-measure: {n0_metrics['f_measure']:.4f}")
    
    print("\n[Step 3] 诊断错误...")
    diagnosis = diagnose_all_errors(
        n0_net,
        metadata['messages'],
        metadata['resources'],
        metadata['sync_tasks'],
        metadata['departments']
    )
    result.diagnosis = diagnosis
    
    total_errors = sum(len(e) for e in diagnosis.values())
    print(f"  - 发现 {total_errors} 个潜在错误")
    
    print("\n[Step 4] 应用 CE-PNR 修复...")
    
    current_net = n0_net
    current_im = n0_im
    current_fm = n0_fm
    current_metrics = n0_metrics
    
    best_net = n0_net
    best_im = n0_im
    best_fm = n0_fm
    best_metrics = n0_metrics
    best_f = n0_metrics['f_measure']
    
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n  --- 迭代 {iteration} ---")
        
        remove_resources = (
            remove_resources_if_low_fitness and 
            current_metrics['fitness'] < fitness_threshold
        )
        
        resource_capacity = 1
        if not remove_resources and current_metrics['fitness'] < 0.9:
            resource_capacity = 2
        
        repaired_net, repaired_im, repaired_fm, repair_report = apply_ce_pnr(
            current_net, current_im, current_fm,
            metadata['messages'],
            metadata['resources'],
            metadata['sync_tasks'],
            remove_resources=remove_resources,
            resource_capacity=resource_capacity
        )
        
        print(f"  - 修复操作: {repair_report['total_repairs']}")
        print(f"  - 移除资源约束: {remove_resources}")
        print(f"  - 资源容量: {resource_capacity}")
        
        repaired_metrics = evaluate_model(global_log, repaired_net, repaired_im, repaired_fm)
        
        print(f"  - Fitness:   {repaired_metrics['fitness']:.4f}")
        print(f"  - Precision: {repaired_metrics['precision']:.4f}")
        print(f"  - F-measure: {repaired_metrics['f_measure']:.4f}")
        
        if repaired_metrics['f_measure'] > best_f:
            best_net = repaired_net
            best_im = repaired_im
            best_fm = repaired_fm
            best_metrics = repaired_metrics
            best_f = repaired_metrics['f_measure']
            result.repair_report = repair_report
        
        if repaired_metrics['f_measure'] >= target_f_measure:
            print(f"\n  达到目标 F-measure ({target_f_measure})，停止迭代")
            break
        
        if abs(repaired_metrics['f_measure'] - current_metrics['f_measure']) < 0.005:
            print(f"\n  F-measure 提升不明显，停止迭代")
            break
        
        current_net = repaired_net
        current_im = repaired_im
        current_fm = repaired_fm
        current_metrics = repaired_metrics
    
    result.n1_net = best_net
    result.n1_im = best_im
    result.n1_fm = best_fm
    result.n1_metrics = best_metrics
    result.iterations = iteration
    
    print("\n" + "=" * 60)
    print("CMIP-IMR 完成")
    print("=" * 60)
    print(f"\nN0 指标:")
    print(f"  - Fitness:   {result.n0_metrics['fitness']:.4f}")
    print(f"  - Precision: {result.n0_metrics['precision']:.4f}")
    print(f"  - F-measure: {result.n0_metrics['f_measure']:.4f}")
    print(f"\nN1 指标 (最优):")
    print(f"  - Fitness:   {result.n1_metrics['fitness']:.4f}")
    print(f"  - Precision: {result.n1_metrics['precision']:.4f}")
    print(f"  - F-measure: {result.n1_metrics['f_measure']:.4f}")
    print(f"\n迭代次数: {result.iterations}")
    
    return result


def generate_verification_report(result: CMIPIMRResult, output_path: str = None) -> str:
    """
    生成验证报告
    """
    lines = [
        "=" * 60,
        "CMIP-IMR 验证报告",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        "## 1. 日志统计",
        f"- 总案例数: {result.metadata.get('total_cases', 'N/A')}",
        f"- 总事件数: {result.metadata.get('total_events', 'N/A')}",
        f"- 部门: {', '.join(result.metadata.get('departments', []))}",
        "",
        "## 2. 协作模式",
        f"- 同步任务: {', '.join(result.metadata.get('sync_tasks', []))}",
        f"- 消息交互: {list(result.metadata.get('messages', {}).keys())}",
        f"- 共享资源: {list(result.metadata.get('resources', {}).keys())}",
        "",
        "## 3. 初始模型 N0 质量",
        f"- Fitness:   {result.n0_metrics['fitness']:.4f}",
        f"- Precision: {result.n0_metrics['precision']:.4f}",
        f"- F-measure: {result.n0_metrics['f_measure']:.4f}",
        "",
        "## 4. 修复后模型 N1 质量",
        f"- Fitness:   {result.n1_metrics['fitness']:.4f}",
        f"- Precision: {result.n1_metrics['precision']:.4f}",
        f"- F-measure: {result.n1_metrics['f_measure']:.4f}",
        "",
        "## 5. 质量提升",
        f"- Fitness 变化:   {result.n1_metrics['fitness'] - result.n0_metrics['fitness']:+.4f}",
        f"- Precision 变化: {result.n1_metrics['precision'] - result.n0_metrics['precision']:+.4f}",
        f"- F-measure 变化: {result.n1_metrics['f_measure'] - result.n0_metrics['f_measure']:+.4f}",
        "",
        f"## 6. 迭代次数: {result.iterations}",
        "",
        "## 7. 修复动作摘要"
    ]
    
    if result.repair_report:
        lines.append(f"- 总修复操作: {result.repair_report.get('total_repairs', 0)}")
        lines.append(f"- 消息修复: {result.repair_report.get('message_repairs', 0)}")
        lines.append(f"- 资源修复: {result.repair_report.get('resource_repairs', 0)}")
        lines.append(f"- 同步修复: {result.repair_report.get('sync_repairs', 0)}")
    else:
        lines.append("- 无需修复")
    
    report = "\n".join(lines)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
    
    return report


if __name__ == '__main__':
    import sys
    
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'Log_09.csv'
    
    result = run_cmip_imr(
        filepath,
        noise_threshold=0.2,
        target_f_measure=0.95,
        max_iterations=3
    )
    
    print("\n" + "=" * 60)
    print("验证报告")
    print("=" * 60)
    report = generate_verification_report(result)
    print(report)
    
    with open('cmip_imr_result.json', 'w', encoding='utf-8') as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
    print("\n结果已保存到 cmip_imr_result.json")
