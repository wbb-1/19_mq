"""
discovery.py - 过程发现模块
功能：
1. 对每个部门用 Inductive Miner 发现控制流 Petri 网
2. 注入消息 place 和资源 place（构建 RM_WF_net）
3. 集成各部门子网为全局模型 N0
"""

import copy
from typing import Dict, List, Tuple, Optional, Set
import pandas as pd

from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.petri_net.utils import petri_utils
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.objects.conversion.process_tree import converter as pt_converter
from pm4py.objects.log.obj import EventLog

from services.ingest import (
    load_and_prepare_log, 
    project_by_department, 
    df_to_eventlog,
    extract_messages,
    extract_resources,
    identify_sync_tasks
)


def discover_department_net(df: pd.DataFrame, 
                            department: str,
                            noise_threshold: float = 0.0) -> Tuple[PetriNet, Marking, Marking]:
    """
    对单个部门发现控制流 Petri 网
    使用 Inductive Miner (infrequent variant if noise_threshold > 0)
    """
    dept_df = project_by_department(df, department)
    
    if len(dept_df) == 0:
        net = PetriNet(f"Empty_{department}")
        source = PetriNet.Place(f"source_{department}")
        sink = PetriNet.Place(f"sink_{department}")
        net.places.add(source)
        net.places.add(sink)
        return net, Marking({source: 1}), Marking({sink: 1})
    
    dept_log = df_to_eventlog(dept_df)
    
    if noise_threshold > 0:
        tree = inductive_miner.apply(
            dept_log, 
            variant=inductive_miner.Variants.IMf,
            parameters={'noise_threshold': noise_threshold}
        )
    else:
        tree = inductive_miner.apply(dept_log)
    
    net, im, fm = pt_converter.apply(tree)
    
    net.name = f"Net_{department}"
    
    return net, im, fm


def discover_all_department_nets(df: pd.DataFrame,
                                  departments: List[str],
                                  noise_threshold: float = 0.0) -> Dict[str, Tuple[PetriNet, Marking, Marking]]:
    """
    对所有部门发现 Petri 网
    返回 {department: (net, initial_marking, final_marking)}
    """
    nets = {}
    for dept in departments:
        net, im, fm = discover_department_net(df, dept, noise_threshold)
        nets[dept] = (net, im, fm)
    return nets


def add_message_places(net: PetriNet, 
                       messages: Dict[str, Tuple[str, str]]) -> PetriNet:
    """
    向 Petri 网中添加消息 place
    messages: {msg_id: (send_task, recv_task)}
    """
    trans_by_label = {t.label: t for t in net.transitions if t.label is not None}
    
    for msg_id, (send_task, recv_task) in messages.items():
        msg_place = PetriNet.Place(f"MSG:{msg_id}")
        net.places.add(msg_place)
        
        if send_task and send_task in trans_by_label:
            send_trans = trans_by_label[send_task]
            petri_utils.add_arc_from_to(send_trans, msg_place, net)
        
        if recv_task and recv_task in trans_by_label:
            recv_trans = trans_by_label[recv_task]
            petri_utils.add_arc_from_to(msg_place, recv_trans, net)
    
    return net


def add_resource_places(net: PetriNet,
                        resources: Dict[str, Tuple[List[str], List[str]]],
                        initial_marking: Marking,
                        capacity: int = 1) -> Tuple[PetriNet, Marking]:
    """
    向 Petri 网中添加资源 place
    resources: {res_id: (req_tasks, rel_tasks)}
    capacity: 资源初始 token 数（容量）
    """
    trans_by_label = {t.label: t for t in net.transitions if t.label is not None}
    
    for res_id, (req_tasks, rel_tasks) in resources.items():
        res_place = PetriNet.Place(f"RES:{res_id}")
        net.places.add(res_place)
        
        initial_marking[res_place] = capacity
        
        for task in req_tasks:
            if task in trans_by_label:
                trans = trans_by_label[task]
                petri_utils.add_arc_from_to(res_place, trans, net)
        
        for task in rel_tasks:
            if task in trans_by_label:
                trans = trans_by_label[task]
                petri_utils.add_arc_from_to(trans, res_place, net)
    
    return net, initial_marking


def merge_petri_nets(nets: Dict[str, Tuple[PetriNet, Marking, Marking]],
                     messages: Dict[str, Tuple[str, str]],
                     resources: Dict[str, Tuple[List[str], List[str]]],
                     sync_tasks: List[str]) -> Tuple[PetriNet, Marking, Marking]:
    """
    合并多个部门 Petri 网为集成模型
    - 合并同名消息 place
    - 合并同名资源 place
    - 处理同步任务
    """
    integrated_net = PetriNet("Integrated_CMIP")
    integrated_im = Marking()
    integrated_fm = Marking()
    
    place_map = {}  # old_place -> new_place
    trans_map = {}  # old_trans -> new_trans
    
    for dept, (net, im, fm) in nets.items():
        for place in net.places:
            new_name = f"{dept}:{place.name}"
            new_place = PetriNet.Place(new_name)
            integrated_net.places.add(new_place)
            place_map[(dept, place.name)] = new_place
            
            if place in im:
                integrated_im[new_place] = im[place]
            if place in fm:
                integrated_fm[new_place] = fm[place]
        
        for trans in net.transitions:
            if trans.label in sync_tasks:
                new_name = f"SYNC:{trans.label}"
            else:
                new_name = f"{dept}:{trans.name}"
            
            if trans.label in sync_tasks and new_name in [t.name for t in integrated_net.transitions]:
                existing_trans = [t for t in integrated_net.transitions if t.name == new_name][0]
                trans_map[(dept, trans.name)] = existing_trans
            else:
                new_trans = PetriNet.Transition(new_name, trans.label)
                integrated_net.transitions.add(new_trans)
                trans_map[(dept, trans.name)] = new_trans
        
        for arc in net.arcs:
            if isinstance(arc.source, PetriNet.Place):
                source = place_map[(dept, arc.source.name)]
                target = trans_map[(dept, arc.target.name)]
            else:
                source = trans_map[(dept, arc.source.name)]
                target = place_map[(dept, arc.target.name)]
            
            petri_utils.add_arc_from_to(source, target, integrated_net)
    
    msg_places = {}
    for msg_id, (send_task, recv_task) in messages.items():
        msg_place = PetriNet.Place(f"MSG:{msg_id}")
        integrated_net.places.add(msg_place)
        msg_places[msg_id] = msg_place
        
        for trans in integrated_net.transitions:
            if trans.label == send_task:
                petri_utils.add_arc_from_to(trans, msg_place, integrated_net)
            if trans.label == recv_task:
                petri_utils.add_arc_from_to(msg_place, trans, integrated_net)
    
    res_places = {}
    for res_id, (req_tasks, rel_tasks) in resources.items():
        res_place = PetriNet.Place(f"RES:{res_id}")
        integrated_net.places.add(res_place)
        res_places[res_id] = res_place
        
        integrated_im[res_place] = 1
        
        for trans in integrated_net.transitions:
            if trans.label in req_tasks:
                petri_utils.add_arc_from_to(res_place, trans, integrated_net)
            if trans.label in rel_tasks:
                petri_utils.add_arc_from_to(trans, res_place, integrated_net)
    
    return integrated_net, integrated_im, integrated_fm


def discover_integrated_model(filepath: str,
                               noise_threshold: float = 0.0) -> Tuple[PetriNet, Marking, Marking, Dict]:
    """
    完整的集成模型发现流程
    返回：
    - net: 集成 Petri 网
    - im: 初始标识
    - fm: 终止标识
    - metadata: 元数据
    """
    df, event_log, metadata = load_and_prepare_log(filepath)
    
    dept_nets = discover_all_department_nets(
        df, 
        metadata['departments'],
        noise_threshold
    )
    
    integrated_net, im, fm = merge_petri_nets(
        dept_nets,
        metadata['messages'],
        metadata['resources'],
        metadata['sync_tasks']
    )
    
    metadata['department_nets'] = {
        dept: (net.name, len(net.places), len(net.transitions))
        for dept, (net, _, _) in dept_nets.items()
    }
    
    return integrated_net, im, fm, metadata, df, event_log


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = 'Log_09.csv'
    
    print("=== 开始过程发现 ===")
    net, im, fm, meta, df, log = discover_integrated_model(filepath, noise_threshold=0.2)
    
    print(f"\n=== 集成模型 N0 ===")
    print(f"Places: {len(net.places)}")
    print(f"Transitions: {len(net.transitions)}")
    print(f"Arcs: {len(net.arcs)}")
    
    print(f"\n=== 部门子网统计 ===")
    for dept, (name, places, trans) in meta['department_nets'].items():
        print(f"  {dept}: {places} places, {trans} transitions")
    
    print(f"\n=== 协作模式 ===")
    print(f"消息 places: {len(meta['messages'])}")
    print(f"资源 places: {len(meta['resources'])}")
    print(f"同步任务: {meta['sync_tasks']}")
