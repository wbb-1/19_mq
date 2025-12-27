"""
visualize.py - Petri 网可视化模块
功能：
1. 生成 Petri 网可视化图像
2. 导出 PNML 格式
3. 导出 SVG/PNG 格式
"""

import os
import tempfile
import subprocess
from typing import Optional, Tuple
from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.visualization.petri_net import visualizer as pn_visualizer
from pm4py.objects.petri_net.exporter import exporter as pnml_exporter

# 确保 Graphviz 在 PATH 中
GRAPHVIZ_PATH = r'C:\Program Files\Graphviz\bin'
if GRAPHVIZ_PATH not in os.environ.get('PATH', ''):
    os.environ['PATH'] = os.environ.get('PATH', '') + ';' + GRAPHVIZ_PATH


def visualize_petri_net(net: PetriNet,
                        im: Marking,
                        fm: Marking,
                        format: str = "png") -> Tuple[bytes, str]:
    """
    生成 Petri 网可视化图像
    返回 (图像字节数据, 格式类型)
    如果 Graphviz 不可用，返回 (DOT 源码字节, 'dot')
    """
    # 生成 DOT 源码
    gviz = pn_visualizer.apply(net, im, fm)
    dot_source = gviz.source
    
    # 尝试使用 Graphviz 渲染
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False, encoding='utf-8') as dot_file:
            dot_file.write(dot_source)
            dot_path = dot_file.name
        
        output_path = dot_path.replace('.dot', f'.{format}')
        
        # 直接调用 dot 命令
        dot_exe = os.path.join(GRAPHVIZ_PATH, 'dot.exe')
        if not os.path.exists(dot_exe):
            dot_exe = 'dot'  # 尝试使用 PATH 中的 dot
        
        result = subprocess.run(
            [dot_exe, f'-T{format}', dot_path, '-o', output_path],
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0 and os.path.exists(output_path):
            with open(output_path, 'rb') as f:
                img_bytes = f.read()
            # 清理临时文件
            os.unlink(dot_path)
            os.unlink(output_path)
            return img_bytes, format
        else:
            os.unlink(dot_path)
            return dot_source.encode('utf-8'), 'dot'
    except Exception as e:
        # 回退到 DOT 源码
        return dot_source.encode('utf-8'), 'dot'


def save_petri_net_image(net: PetriNet,
                         im: Marking,
                         fm: Marking,
                         filepath: str,
                         format: str = "svg") -> str:
    """
    保存 Petri 网可视化图像到文件
    如果 Graphviz 不可用，保存 DOT 源码
    """
    try:
        parameters = {
            pn_visualizer.Variants.WO_DECORATION.value.Parameters.FORMAT: format
        }
        
        gviz = pn_visualizer.apply(net, im, fm, parameters=parameters)
        
        pn_visualizer.save(gviz, filepath)
        
        return filepath
    except Exception as e:
        gviz = pn_visualizer.apply(net, im, fm)
        dot_filepath = filepath.rsplit('.', 1)[0] + '.dot'
        with open(dot_filepath, 'w', encoding='utf-8') as f:
            f.write(gviz.source)
        return dot_filepath


def export_pnml(net: PetriNet,
                im: Marking,
                fm: Marking,
                filepath: str) -> str:
    """
    导出 Petri 网为 PNML 格式
    """
    pnml_exporter.apply(net, im, filepath, final_marking=fm)
    return filepath


def get_net_statistics(net: PetriNet) -> dict:
    """
    获取 Petri 网统计信息
    """
    msg_places = [p for p in net.places if p.name.startswith("MSG:")]
    res_places = [p for p in net.places if p.name.startswith("RES:")]
    logic_places = [p for p in net.places if not p.name.startswith("MSG:") and not p.name.startswith("RES:")]
    
    sync_trans = [t for t in net.transitions if t.name.startswith("SYNC:")]
    
    return {
        'total_places': len(net.places),
        'total_transitions': len(net.transitions),
        'total_arcs': len(net.arcs),
        'message_places': len(msg_places),
        'resource_places': len(res_places),
        'logic_places': len(logic_places),
        'sync_transitions': len(sync_trans),
        'message_place_names': [p.name for p in msg_places],
        'resource_place_names': [p.name for p in res_places],
        'sync_transition_names': [t.name for t in sync_trans]
    }


if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    
    from services.discovery import discover_integrated_model
    
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'Log_09.csv'
    
    print("发现模型...")
    net, im, fm, meta, df, log = discover_integrated_model(filepath, noise_threshold=0.2)
    
    print("\n模型统计:")
    stats = get_net_statistics(net)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n保存可视化...")
    save_petri_net_image(net, im, fm, "petri_net_n0.svg", "svg")
    print("  -> petri_net_n0.svg")
    
    print("\n导出 PNML...")
    export_pnml(net, im, fm, "petri_net_n0.pnml")
    print("  -> petri_net_n0.pnml")
