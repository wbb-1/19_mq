"""
evaluation.py - 质量评价模块
功能：
1. 计算 Fitness（拟合度）
2. 计算 Precision（精确度）
3. 计算 F-measure
4. 生成对齐偏差统计（用于错误诊断）
"""

from typing import Dict, Tuple, List, Optional
import pandas as pd

from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.log.obj import EventLog
from pm4py.algo.conformance.tokenreplay import algorithm as token_replay
from pm4py.algo.evaluation.replay_fitness import algorithm as fitness_evaluator
from pm4py.algo.evaluation.precision import algorithm as precision_evaluator


def calculate_fitness_token_replay(log: EventLog,
                                    net: PetriNet,
                                    im: Marking,
                                    fm: Marking) -> Tuple[float, Dict]:
    """
    使用 Token Replay 计算 Fitness
    返回：(fitness_value, detailed_results)
    """
    try:
        replayed_traces = token_replay.apply(log, net, im, fm)
        
        total_consumed = 0
        total_produced = 0
        total_missing = 0
        total_remaining = 0
        
        for trace_result in replayed_traces:
            total_consumed += trace_result.get('consumed_tokens', 0)
            total_produced += trace_result.get('produced_tokens', 0)
            total_missing += trace_result.get('missing_tokens', 0)
            total_remaining += trace_result.get('remaining_tokens', 0)
        
        if total_consumed + total_produced > 0:
            fitness = 0.5 * (1 - total_missing / max(total_consumed, 1)) + \
                      0.5 * (1 - total_remaining / max(total_produced, 1))
        else:
            fitness = 0.0
        
        details = {
            'total_consumed': total_consumed,
            'total_produced': total_produced,
            'total_missing': total_missing,
            'total_remaining': total_remaining,
            'trace_count': len(replayed_traces)
        }
        
        return max(0.0, min(1.0, fitness)), details
        
    except Exception as e:
        return 0.0, {'error': str(e)}


def calculate_fitness_alignment(log: EventLog,
                                 net: PetriNet,
                                 im: Marking,
                                 fm: Marking) -> Tuple[float, Dict]:
    """
    使用 Alignment 计算 Fitness（更准确但更慢）
    返回：(fitness_value, detailed_results)
    """
    try:
        fitness_result = fitness_evaluator.apply(
            log, net, im, fm,
            variant=fitness_evaluator.Variants.TOKEN_BASED
        )
        
        fitness_value = fitness_result.get('average_trace_fitness', 0.0)
        
        return fitness_value, fitness_result
        
    except Exception as e:
        return 0.0, {'error': str(e)}


def calculate_precision(log: EventLog,
                        net: PetriNet,
                        im: Marking,
                        fm: Marking) -> Tuple[float, Dict]:
    """
    计算 Precision（精确度）
    返回：(precision_value, detailed_results)
    """
    try:
        precision_value = precision_evaluator.apply(
            log, net, im, fm,
            variant=precision_evaluator.Variants.ETCONFORMANCE_TOKEN
        )
        
        return precision_value, {'precision': precision_value}
        
    except Exception as e:
        return 0.0, {'error': str(e)}


def calculate_f_measure(fitness: float, precision: float) -> float:
    """
    计算 F-measure（调和平均）
    """
    if fitness + precision == 0:
        return 0.0
    return 2 * fitness * precision / (fitness + precision)


def evaluate_model(log: EventLog,
                   net: PetriNet,
                   im: Marking,
                   fm: Marking,
                   use_alignment: bool = False) -> Dict:
    """
    完整的模型质量评价
    返回包含所有指标的字典
    """
    if use_alignment:
        fitness, fitness_details = calculate_fitness_alignment(log, net, im, fm)
    else:
        fitness, fitness_details = calculate_fitness_token_replay(log, net, im, fm)
    
    precision, precision_details = calculate_precision(log, net, im, fm)
    
    f_measure = calculate_f_measure(fitness, precision)
    
    return {
        'fitness': fitness,
        'precision': precision,
        'f_measure': f_measure,
        'fitness_details': fitness_details,
        'precision_details': precision_details
    }


def get_alignment_diagnostics(log: EventLog,
                               net: PetriNet,
                               im: Marking,
                               fm: Marking) -> Dict:
    """
    获取对齐诊断信息（用于错误分析）
    返回 log-move 和 model-move 统计
    """
    try:
        replayed_traces = token_replay.apply(log, net, im, fm)
        
        total_traces = len(replayed_traces)
        fitting_traces = sum(1 for t in replayed_traces if t.get('trace_is_fit', False))
        
        total_missing = sum(t.get('missing_tokens', 0) for t in replayed_traces)
        total_remaining = sum(t.get('remaining_tokens', 0) for t in replayed_traces)
        
        return {
            'total_traces': total_traces,
            'fitting_traces': fitting_traces,
            'non_fitting_traces': total_traces - fitting_traces,
            'fitting_ratio': fitting_traces / max(total_traces, 1),
            'total_missing_tokens': total_missing,
            'total_remaining_tokens': total_remaining,
            'avg_missing_per_trace': total_missing / max(total_traces, 1),
            'avg_remaining_per_trace': total_remaining / max(total_traces, 1)
        }
        
    except Exception as e:
        return {'error': str(e)}


def format_evaluation_report(metrics: Dict) -> str:
    """
    格式化评价报告为可读字符串
    """
    lines = [
        "=" * 50,
        "模型质量评价报告",
        "=" * 50,
        f"Fitness (拟合度):    {metrics['fitness']:.4f}",
        f"Precision (精确度):  {metrics['precision']:.4f}",
        f"F-measure:           {metrics['f_measure']:.4f}",
        "=" * 50
    ]
    
    if 'fitness_details' in metrics and 'error' not in metrics['fitness_details']:
        details = metrics['fitness_details']
        lines.extend([
            "\nFitness 详情:",
            f"  - 消耗 tokens: {details.get('total_consumed', 'N/A')}",
            f"  - 产生 tokens: {details.get('total_produced', 'N/A')}",
            f"  - 缺失 tokens: {details.get('total_missing', 'N/A')}",
            f"  - 残留 tokens: {details.get('total_remaining', 'N/A')}"
        ])
    
    return "\n".join(lines)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    
    from services.discovery import discover_integrated_model
    
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'Log_09.csv'
    
    print("=== 发现模型 ===")
    net, im, fm, meta, df, log = discover_integrated_model(filepath, noise_threshold=0.2)
    
    print(f"\n=== 评价模型 (使用全局日志) ===")
    
    from services.ingest import df_to_eventlog
    global_log = df_to_eventlog(df)
    
    metrics = evaluate_model(global_log, net, im, fm, use_alignment=False)
    
    print(format_evaluation_report(metrics))
    
    print("\n=== 对齐诊断 ===")
    diagnostics = get_alignment_diagnostics(global_log, net, im, fm)
    for key, value in diagnostics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
