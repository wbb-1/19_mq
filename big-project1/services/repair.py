"""
repair.py - CE-PNR 修复模块
功能：
1. 诊断模型错误（消息/资源/同步/伪并发）
2. 应用修复算子
3. 生成修复后的模型 N1
"""

import copy
from typing import Dict, List, Tuple, Set, Optional
import pandas as pd

from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.petri_net.utils import petri_utils
from pm4py.objects.log.obj import EventLog


def diagnose_message_errors(net: PetriNet,
                            messages: Dict[str, Tuple[str, str]]) -> List[Dict]:
    """
    诊断消息相关错误
    检查消息 place 是否正确连接到发送/接收 transition
    """
    errors = []
    trans_labels = {t.label for t in net.transitions if t.label}
    
    for msg_id, (send_task, recv_task) in messages.items():
        msg_place_name = f"MSG:{msg_id}"
        msg_place = None
        for p in net.places:
            if p.name == msg_place_name:
                msg_place = p
                break
        
        if msg_place is None:
            errors.append({
                'type': 'missing_message_place',
                'message': msg_id,
                'description': f"消息 place {msg_place_name} 不存在"
            })
            continue
        
        has_send_arc = False
        has_recv_arc = False
        
        for arc in net.arcs:
            if arc.target == msg_place and arc.source.label == send_task:
                has_send_arc = True
            if arc.source == msg_place and arc.target.label == recv_task:
                has_recv_arc = True
        
        if send_task and not has_send_arc:
            errors.append({
                'type': 'missing_send_arc',
                'message': msg_id,
                'task': send_task,
                'description': f"消息 {msg_id} 缺少发送弧 ({send_task} -> {msg_place_name})"
            })
        
        if recv_task and not has_recv_arc:
            errors.append({
                'type': 'missing_recv_arc',
                'message': msg_id,
                'task': recv_task,
                'description': f"消息 {msg_id} 缺少接收弧 ({msg_place_name} -> {recv_task})"
            })
    
    return errors


def diagnose_resource_errors(net: PetriNet,
                              resources: Dict[str, Tuple[List[str], List[str]]]) -> List[Dict]:
    """
    诊断资源相关错误
    检查资源 place 是否正确连接到请求/释放 transition
    """
    errors = []
    trans_by_label = {t.label: t for t in net.transitions if t.label}
    
    for res_id, (req_tasks, rel_tasks) in resources.items():
        res_place_name = f"RES:{res_id}"
        res_place = None
        for p in net.places:
            if p.name == res_place_name:
                res_place = p
                break
        
        if res_place is None:
            errors.append({
                'type': 'missing_resource_place',
                'resource': res_id,
                'description': f"资源 place {res_place_name} 不存在"
            })
            continue
        
        for task in req_tasks:
            has_req_arc = False
            for arc in net.arcs:
                if arc.source == res_place:
                    if hasattr(arc.target, 'label') and arc.target.label == task:
                        has_req_arc = True
                        break
            
            if not has_req_arc:
                errors.append({
                    'type': 'missing_req_arc',
                    'resource': res_id,
                    'task': task,
                    'description': f"资源 {res_id} 缺少请求弧 ({res_place_name} -> {task})"
                })
        
        for task in rel_tasks:
            has_rel_arc = False
            for arc in net.arcs:
                if arc.target == res_place:
                    if hasattr(arc.source, 'label') and arc.source.label == task:
                        has_rel_arc = True
                        break
            
            if not has_rel_arc:
                errors.append({
                    'type': 'missing_rel_arc',
                    'resource': res_id,
                    'task': task,
                    'description': f"资源 {res_id} 缺少释放弧 ({task} -> {res_place_name})"
                })
    
    return errors


def diagnose_sync_errors(net: PetriNet,
                          sync_tasks: List[str],
                          departments: List[str]) -> List[Dict]:
    """
    诊断同步任务相关错误
    检查同步任务是否在多个部门间正确同步
    """
    errors = []
    
    for sync_task in sync_tasks:
        sync_trans = []
        for t in net.transitions:
            if t.label == sync_task:
                sync_trans.append(t)
        
        if len(sync_trans) == 0:
            errors.append({
                'type': 'missing_sync_task',
                'task': sync_task,
                'description': f"同步任务 {sync_task} 在模型中不存在"
            })
        elif len(sync_trans) > 1:
            errors.append({
                'type': 'duplicate_sync_task',
                'task': sync_task,
                'count': len(sync_trans),
                'description': f"同步任务 {sync_task} 存在 {len(sync_trans)} 个副本，应合并为一个"
            })
    
    return errors


def diagnose_all_errors(net: PetriNet,
                        messages: Dict[str, Tuple[str, str]],
                        resources: Dict[str, Tuple[List[str], List[str]]],
                        sync_tasks: List[str],
                        departments: List[str]) -> Dict[str, List[Dict]]:
    """
    执行完整的错误诊断
    """
    return {
        'message_errors': diagnose_message_errors(net, messages),
        'resource_errors': diagnose_resource_errors(net, resources),
        'sync_errors': diagnose_sync_errors(net, sync_tasks, departments)
    }


def repair_message_arcs(net: PetriNet,
                        messages: Dict[str, Tuple[str, str]]) -> Tuple[PetriNet, List[str]]:
    """
    修复消息弧
    确保每个消息 place 正确连接到发送和接收 transition
    """
    repairs = []
    trans_by_label = {t.label: t for t in net.transitions if t.label}
    
    for msg_id, (send_task, recv_task) in messages.items():
        msg_place_name = f"MSG:{msg_id}"
        msg_place = None
        for p in net.places:
            if p.name == msg_place_name:
                msg_place = p
                break
        
        if msg_place is None:
            msg_place = PetriNet.Place(msg_place_name)
            net.places.add(msg_place)
            repairs.append(f"创建消息 place: {msg_place_name}")
        
        if send_task:
            send_trans = None
            for t in net.transitions:
                if t.label == send_task:
                    send_trans = t
                    break
            
            if send_trans:
                has_arc = any(
                    arc.source == send_trans and arc.target == msg_place
                    for arc in net.arcs
                )
                if not has_arc:
                    petri_utils.add_arc_from_to(send_trans, msg_place, net)
                    repairs.append(f"添加发送弧: {send_task} -> {msg_place_name}")
        
        if recv_task:
            recv_trans = None
            for t in net.transitions:
                if t.label == recv_task:
                    recv_trans = t
                    break
            
            if recv_trans:
                has_arc = any(
                    arc.source == msg_place and arc.target == recv_trans
                    for arc in net.arcs
                )
                if not has_arc:
                    petri_utils.add_arc_from_to(msg_place, recv_trans, net)
                    repairs.append(f"添加接收弧: {msg_place_name} -> {recv_task}")
    
    return net, repairs


def repair_resource_arcs(net: PetriNet,
                         resources: Dict[str, Tuple[List[str], List[str]]],
                         initial_marking: Marking,
                         capacity: int = 1) -> Tuple[PetriNet, Marking, List[str]]:
    """
    修复资源弧
    确保每个资源 place 正确连接到请求和释放 transition
    """
    repairs = []
    
    for res_id, (req_tasks, rel_tasks) in resources.items():
        res_place_name = f"RES:{res_id}"
        res_place = None
        for p in net.places:
            if p.name == res_place_name:
                res_place = p
                break
        
        if res_place is None:
            res_place = PetriNet.Place(res_place_name)
            net.places.add(res_place)
            initial_marking[res_place] = capacity
            repairs.append(f"创建资源 place: {res_place_name} (容量={capacity})")
        
        for task in req_tasks:
            req_trans = None
            for t in net.transitions:
                if t.label == task:
                    req_trans = t
                    break
            
            if req_trans:
                has_arc = any(
                    arc.source == res_place and arc.target == req_trans
                    for arc in net.arcs
                )
                if not has_arc:
                    petri_utils.add_arc_from_to(res_place, req_trans, net)
                    repairs.append(f"添加请求弧: {res_place_name} -> {task}")
        
        for task in rel_tasks:
            rel_trans = None
            for t in net.transitions:
                if t.label == task:
                    rel_trans = t
                    break
            
            if rel_trans:
                has_arc = any(
                    arc.source == rel_trans and arc.target == res_place
                    for arc in net.arcs
                )
                if not has_arc:
                    petri_utils.add_arc_from_to(rel_trans, res_place, net)
                    repairs.append(f"添加释放弧: {task} -> {res_place_name}")
    
    return net, initial_marking, repairs


def repair_sync_tasks(net: PetriNet,
                      sync_tasks: List[str]) -> Tuple[PetriNet, List[str]]:
    """
    修复同步任务
    合并同名同步 transition
    """
    repairs = []
    
    for sync_task in sync_tasks:
        sync_trans = [t for t in net.transitions if t.label == sync_task]
        
        if len(sync_trans) > 1:
            primary = sync_trans[0]
            
            for secondary in sync_trans[1:]:
                for arc in list(net.arcs):
                    if arc.source == secondary:
                        petri_utils.add_arc_from_to(primary, arc.target, net)
                        petri_utils.remove_arc(net, arc)
                    elif arc.target == secondary:
                        petri_utils.add_arc_from_to(arc.source, primary, net)
                        petri_utils.remove_arc(net, arc)
                
                net.transitions.remove(secondary)
            
            repairs.append(f"合并同步任务: {sync_task} ({len(sync_trans)} -> 1)")
    
    return net, repairs


def remove_resource_constraints(net: PetriNet,
                                 initial_marking: Marking) -> Tuple[PetriNet, Marking, List[str]]:
    """
    移除资源约束（当资源约束导致 fitness 过低时使用）
    保留消息约束以维持 precision
    """
    repairs = []
    places_to_remove = []
    
    for place in net.places:
        if place.name.startswith("RES:"):
            places_to_remove.append(place)
    
    for place in places_to_remove:
        arcs_to_remove = [arc for arc in net.arcs if arc.source == place or arc.target == place]
        for arc in arcs_to_remove:
            petri_utils.remove_arc(net, arc)
        net.places.remove(place)
        if place in initial_marking:
            del initial_marking[place]
        repairs.append(f"移除资源约束: {place.name}")
    
    return net, initial_marking, repairs


def adjust_resource_capacity(net: PetriNet,
                              initial_marking: Marking,
                              resources: Dict[str, Tuple[List[str], List[str]]],
                              capacity: int) -> Tuple[PetriNet, Marking, List[str]]:
    """
    调整资源容量
    """
    repairs = []
    
    for res_id in resources.keys():
        res_place_name = f"RES:{res_id}"
        for place in net.places:
            if place.name == res_place_name:
                old_capacity = initial_marking.get(place, 1)
                initial_marking[place] = capacity
                repairs.append(f"调整资源容量: {res_place_name} ({old_capacity} -> {capacity})")
                break
    
    return net, initial_marking, repairs


def apply_ce_pnr(net: PetriNet,
                 initial_marking: Marking,
                 final_marking: Marking,
                 messages: Dict[str, Tuple[str, str]],
                 resources: Dict[str, Tuple[List[str], List[str]]],
                 sync_tasks: List[str],
                 remove_resources: bool = False,
                 resource_capacity: int = 1) -> Tuple[PetriNet, Marking, Marking, Dict]:
    """
    应用 CE-PNR（Constraint-Enhanced Petri Net Repair）
    返回修复后的模型和修复报告
    
    参数：
    - remove_resources: 是否移除资源约束（当资源约束导致 fitness 过低时）
    - resource_capacity: 资源容量（增大可提高 fitness 但降低 precision）
    """
    net = copy.deepcopy(net)
    im = copy.deepcopy(initial_marking)
    fm = copy.deepcopy(final_marking)
    
    all_repairs = []
    
    net, msg_repairs = repair_message_arcs(net, messages)
    all_repairs.extend(msg_repairs)
    
    if remove_resources:
        net, im, res_repairs = remove_resource_constraints(net, im)
        all_repairs.extend(res_repairs)
    else:
        net, im, res_repairs = repair_resource_arcs(net, resources, im, resource_capacity)
        all_repairs.extend(res_repairs)
        
        if resource_capacity > 1:
            net, im, cap_repairs = adjust_resource_capacity(net, im, resources, resource_capacity)
            all_repairs.extend(cap_repairs)
    
    net, sync_repairs = repair_sync_tasks(net, sync_tasks)
    all_repairs.extend(sync_repairs)
    
    repair_report = {
        'total_repairs': len(all_repairs),
        'message_repairs': len(msg_repairs),
        'resource_repairs': len(res_repairs),
        'sync_repairs': len(sync_repairs),
        'repair_actions': all_repairs,
        'remove_resources': remove_resources,
        'resource_capacity': resource_capacity
    }
    
    return net, im, fm, repair_report


def format_diagnosis_report(diagnosis: Dict[str, List[Dict]]) -> str:
    """
    格式化诊断报告
    """
    lines = [
        "=" * 50,
        "错误诊断报告",
        "=" * 50
    ]
    
    for category, errors in diagnosis.items():
        lines.append(f"\n{category}:")
        if not errors:
            lines.append("  (无错误)")
        else:
            for err in errors:
                lines.append(f"  - {err['description']}")
    
    total_errors = sum(len(e) for e in diagnosis.values())
    lines.append(f"\n总计: {total_errors} 个错误")
    
    return "\n".join(lines)


def format_repair_report(report: Dict) -> str:
    """
    格式化修复报告
    """
    lines = [
        "=" * 50,
        "修复报告",
        "=" * 50,
        f"总修复操作: {report['total_repairs']}",
        f"  - 消息修复: {report['message_repairs']}",
        f"  - 资源修复: {report['resource_repairs']}",
        f"  - 同步修复: {report['sync_repairs']}",
        "\n修复动作:"
    ]
    
    for action in report['repair_actions']:
        lines.append(f"  - {action}")
    
    return "\n".join(lines)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    
    from services.discovery import discover_integrated_model
    from services.evaluation import evaluate_model, format_evaluation_report
    from services.ingest import df_to_eventlog
    
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'Log_09.csv'
    
    print("=== 发现初始模型 N0 ===")
    net, im, fm, meta, df, log = discover_integrated_model(filepath, noise_threshold=0.2)
    
    print(f"N0: {len(net.places)} places, {len(net.transitions)} transitions")
    
    print("\n=== 诊断错误 ===")
    diagnosis = diagnose_all_errors(
        net, 
        meta['messages'], 
        meta['resources'],
        meta['sync_tasks'],
        meta['departments']
    )
    print(format_diagnosis_report(diagnosis))
    
    print("\n=== 应用 CE-PNR 修复 ===")
    net_repaired, im_repaired, fm_repaired, repair_report = apply_ce_pnr(
        net, im, fm,
        meta['messages'],
        meta['resources'],
        meta['sync_tasks']
    )
    print(format_repair_report(repair_report))
    
    print(f"\nN1: {len(net_repaired.places)} places, {len(net_repaired.transitions)} transitions")
    
    print("\n=== 评价修复后模型 N1 ===")
    global_log = df_to_eventlog(df)
    metrics = evaluate_model(global_log, net_repaired, im_repaired, fm_repaired)
    print(format_evaluation_report(metrics))
