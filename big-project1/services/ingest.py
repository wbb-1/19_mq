"""
ingest.py - 日志导入与预处理模块
功能：
1. 读取 CSV/XES 事件日志
2. 解析字符串形式的列表字段（rec_msg, send_msg, req_res, rel_res, roles）
3. 按部门投影生成子日志
4. 转换为 PM4Py EventLog 格式
"""

import ast
import pandas as pd
from typing import Dict, List, Tuple, Optional
from pm4py.objects.log.obj import EventLog, Trace, Event
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.util import constants, xes_constants


def parse_list_field(value) -> List[str]:
    """解析字符串形式的列表字段为 Python list"""
    if pd.isna(value) or value == '' or value == '[]':
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = ast.literal_eval(str(value))
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return [str(parsed)]
    except (ValueError, SyntaxError):
        return []


def load_csv_log(filepath: str) -> pd.DataFrame:
    """
    读取 CSV 日志并进行预处理
    返回标准化的 DataFrame
    """
    df = pd.read_csv(filepath)
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    list_columns = ['rec_msg', 'send_msg', 'req_res', 'rel_res', 'roles']
    for col in list_columns:
        if col in df.columns:
            df[col] = df[col].apply(parse_list_field)
    
    df = df.sort_values(['case_id', 'timestamp']).reset_index(drop=True)
    
    return df


def extract_departments(df: pd.DataFrame) -> List[str]:
    """从日志中提取所有部门名称"""
    all_roles = set()
    for roles in df['roles']:
        all_roles.update(roles)
    return sorted(list(all_roles))


def project_by_department(df: pd.DataFrame, department: str) -> pd.DataFrame:
    """
    按部门投影日志
    返回包含该部门事件的子日志
    """
    mask = df['roles'].apply(lambda x: department in x)
    return df[mask].copy()


def identify_sync_tasks(df: pd.DataFrame) -> List[str]:
    """
    识别同步任务（|roles| >= 2 的事件对应的任务）
    返回同步任务名称列表
    """
    sync_tasks = set()
    for _, row in df.iterrows():
        if len(row['roles']) >= 2:
            sync_tasks.add(row['tran'])
    return sorted(list(sync_tasks))


def extract_messages(df: pd.DataFrame) -> Dict[str, Tuple[str, str]]:
    """
    提取消息交互关系
    返回 {message_id: (send_task, recv_task)} 的映射
    """
    send_map = {}  # message_id -> task
    recv_map = {}  # message_id -> task
    
    for _, row in df.iterrows():
        task = row['tran']
        for msg in row['send_msg']:
            if msg not in send_map:
                send_map[msg] = task
        for msg in row['rec_msg']:
            if msg not in recv_map:
                recv_map[msg] = task
    
    messages = {}
    all_msgs = set(send_map.keys()) | set(recv_map.keys())
    for msg in all_msgs:
        send_task = send_map.get(msg, None)
        recv_task = recv_map.get(msg, None)
        messages[msg] = (send_task, recv_task)
    
    return messages


def extract_resources(df: pd.DataFrame) -> Dict[str, Tuple[List[str], List[str]]]:
    """
    提取资源使用关系
    返回 {resource_id: (req_tasks, rel_tasks)} 的映射
    """
    req_map = {}  # resource_id -> [tasks]
    rel_map = {}  # resource_id -> [tasks]
    
    for _, row in df.iterrows():
        task = row['tran']
        for res in row['req_res']:
            if res not in req_map:
                req_map[res] = []
            if task not in req_map[res]:
                req_map[res].append(task)
        for res in row['rel_res']:
            if res not in rel_map:
                rel_map[res] = []
            if task not in rel_map[res]:
                rel_map[res].append(task)
    
    resources = {}
    all_res = set(req_map.keys()) | set(rel_map.keys())
    for res in all_res:
        resources[res] = (req_map.get(res, []), rel_map.get(res, []))
    
    return resources


def df_to_eventlog(df: pd.DataFrame, 
                   case_col: str = 'case_id',
                   activity_col: str = 'tran',
                   timestamp_col: str = 'timestamp') -> EventLog:
    """
    将 DataFrame 转换为 PM4Py EventLog
    """
    df_copy = df.copy()
    df_copy = df_copy.rename(columns={
        case_col: 'case:concept:name',
        activity_col: 'concept:name',
        timestamp_col: 'time:timestamp'
    })
    
    df_copy['case:concept:name'] = df_copy['case:concept:name'].astype(str)
    
    event_log = log_converter.apply(df_copy, variant=log_converter.Variants.TO_EVENT_LOG)
    
    return event_log


def load_and_prepare_log(filepath: str) -> Tuple[pd.DataFrame, EventLog, Dict]:
    """
    完整的日志加载与准备流程
    返回：
    - df: 原始 DataFrame（已解析）
    - event_log: PM4Py EventLog
    - metadata: 元数据字典（部门、同步任务、消息、资源）
    """
    df = load_csv_log(filepath)
    
    event_log = df_to_eventlog(df)
    
    metadata = {
        'departments': extract_departments(df),
        'sync_tasks': identify_sync_tasks(df),
        'messages': extract_messages(df),
        'resources': extract_resources(df),
        'total_cases': df['case_id'].nunique(),
        'total_events': len(df)
    }
    
    return df, event_log, metadata


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = 'Log_09.csv'
    
    df, log, meta = load_and_prepare_log(filepath)
    
    print("=== 日志加载完成 ===")
    print(f"总案例数: {meta['total_cases']}")
    print(f"总事件数: {meta['total_events']}")
    print(f"部门列表: {meta['departments']}")
    print(f"同步任务: {meta['sync_tasks']}")
    print(f"消息交互: {meta['messages']}")
    print(f"资源使用: {meta['resources']}")
