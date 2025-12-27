"""
CMIP 过程挖掘软件 - Streamlit UI
基于 CMIP-IMR 算法的跨部门协作过程挖掘与可视化

功能：
1. 上传 CSV/XES 事件日志
2. 字段映射配置
3. 参数配置（噪声阈值、资源容量等）
4. 过程发现与质量评价
5. Petri 网可视化
6. 导出 PNML/SVG/指标报告
"""

import streamlit as st
import pandas as pd
import json
import tempfile
import os
from datetime import datetime

# 确保 Graphviz 在 PATH 中
os.environ['PATH'] = os.environ.get('PATH', '') + ';C:\\Program Files\\Graphviz\\bin'

from services.ingest import load_and_prepare_log, df_to_eventlog
from services.discovery import discover_integrated_model


@st.cache_data
def cached_load_log(filepath: str):
    """缓存日志加载结果"""
    from services.ingest import load_and_prepare_log
    df, event_log, metadata = load_and_prepare_log(filepath)
    return df, metadata


@st.cache_data
def cached_run_cmip_imr(_filepath: str, noise_threshold: float, target_f_measure: float, max_iterations: int):
    """缓存 CMIP-IMR 运行结果"""
    from services.cmip_imr import run_cmip_imr
    return run_cmip_imr(_filepath, noise_threshold, target_f_measure, max_iterations)


from services.evaluation import evaluate_model, get_alignment_diagnostics
from services.repair import apply_ce_pnr, diagnose_all_errors
from services.visualize import visualize_petri_net, export_pnml, get_net_statistics
from services.cmip_imr import run_cmip_imr, generate_verification_report


st.set_page_config(
    page_title="CMIP 过程挖掘软件",
    page_icon="🔄",
    layout="wide"
)

st.title("🔄 CMIP 过程挖掘软件")
st.markdown("**基于 CMIP-IMR 算法的跨部门协作过程挖掘与可视化**")

with st.sidebar:
    st.header("📁 日志上传")
    
    uploaded_file = st.file_uploader(
        "上传事件日志 (CSV/XES)",
        type=['csv', 'xes'],
        help="支持 CSV 和 XES 格式的事件日志"
    )
    
    use_sample = st.checkbox("使用示例日志 (Log_09.csv)", value=True)
    
    st.header("⚙️ 参数配置")
    
    noise_threshold = st.slider(
        "噪声阈值 (IMf)",
        min_value=0.0,
        max_value=0.5,
        value=0.2,
        step=0.05,
        help="Inductive Miner 噪声过滤阈值，越高过滤越多低频行为"
    )
    
    target_f_measure = st.slider(
        "目标 F-measure",
        min_value=0.8,
        max_value=1.0,
        value=0.95,
        step=0.01,
        help="修复迭代的目标 F-measure"
    )
    
    max_iterations = st.number_input(
        "最大迭代次数",
        min_value=1,
        max_value=10,
        value=3,
        help="CE-PNR 修复的最大迭代次数"
    )
    
    enable_repair = st.checkbox("启用 CE-PNR 修复", value=True)
    
    st.divider()
    if st.button("🔄 清除缓存", help="清除缓存后，修改参数会重新计算"):
        st.cache_data.clear()
        st.session_state.result = None
        st.rerun()

if 'result' not in st.session_state:
    st.session_state.result = None
if 'log_path' not in st.session_state:
    st.session_state.log_path = None
if 'df' not in st.session_state:
    st.session_state.df = None
if 'metadata' not in st.session_state:
    st.session_state.metadata = None

# 确定日志路径并加载（只在需要时）
log_path = None
if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
        tmp.write(uploaded_file.getvalue())
        log_path = tmp.name
elif use_sample:
    log_path = "Log_09.csv"
    if not os.path.exists(log_path):
        log_path = None

# 只在路径变化时重新加载
if log_path and log_path != st.session_state.log_path:
    try:
        df, metadata = cached_load_log(log_path)
        st.session_state.log_path = log_path
        st.session_state.df = df
        st.session_state.metadata = metadata
    except Exception as e:
        st.error(f"加载日志失败: {str(e)}")

# 使用 session_state 中的数据
df = st.session_state.df
metadata = st.session_state.metadata

# 主内容区域
main_container = st.container()

with main_container:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📊 日志信息")
        
        if uploaded_file is not None:
            st.success(f"已上传: {uploaded_file.name}")
        elif use_sample and st.session_state.log_path:
            st.info("使用示例日志: Log_09.csv")
        
        if metadata:
            st.subheader("日志统计")
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("总案例数", metadata['total_cases'])
                st.metric("部门数", len(metadata['departments']))
            with col_b:
                st.metric("总事件数", metadata['total_events'])
                st.metric("同步任务数", len(metadata['sync_tasks']))
            
            st.subheader("部门列表")
            st.write(", ".join(metadata['departments']))
            
            st.subheader("协作模式")
            st.write(f"**消息交互**: {list(metadata['messages'].keys())}")
            st.write(f"**共享资源**: {list(metadata['resources'].keys())}")
            st.write(f"**同步任务**: {metadata['sync_tasks']}")
    
    with col2:
        st.header("🚀 过程挖掘")
        
        start_button = st.button("开始挖掘", type="primary", use_container_width=True)
        
        if start_button:
            if st.session_state.log_path:
                with st.spinner("正在执行 CMIP-IMR 算法..."):
                    try:
                        result = cached_run_cmip_imr(
                            st.session_state.log_path,
                            noise_threshold=noise_threshold,
                            target_f_measure=target_f_measure,
                            max_iterations=max_iterations if enable_repair else 0
                        )
                        st.session_state.result = result
                        st.success("挖掘完成!")
                    except Exception as e:
                        st.error(f"挖掘失败: {str(e)}")
            else:
                st.warning("请先上传或选择日志文件")
    
    # 日志预览
    if df is not None:
        with st.expander("📋 查看日志预览（前100行）"):
            st.dataframe(df.head(100), use_container_width=True)

if st.session_state.result:
    result = st.session_state.result
    
    st.header("📈 质量评价")
    
    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        st.subheader("初始模型 N0")
        st.metric("Fitness", f"{result.n0_metrics['fitness']:.4f}")
        st.metric("Precision", f"{result.n0_metrics['precision']:.4f}")
        st.metric("F-measure", f"{result.n0_metrics['f_measure']:.4f}")
    
    with col_m2:
        st.subheader("最优模型 N1")
        delta_f = result.n1_metrics['fitness'] - result.n0_metrics['fitness']
        delta_p = result.n1_metrics['precision'] - result.n0_metrics['precision']
        delta_fm = result.n1_metrics['f_measure'] - result.n0_metrics['f_measure']
        
        st.metric("Fitness", f"{result.n1_metrics['fitness']:.4f}", 
                  delta=f"{delta_f:+.4f}" if delta_f != 0 else None)
        st.metric("Precision", f"{result.n1_metrics['precision']:.4f}",
                  delta=f"{delta_p:+.4f}" if delta_p != 0 else None)
        st.metric("F-measure", f"{result.n1_metrics['f_measure']:.4f}",
                  delta=f"{delta_fm:+.4f}" if delta_fm != 0 else None)
    
    st.header("🔍 Petri 网可视化")
    
    tab1, tab2 = st.tabs(["N0 (初始模型)", "N1 (最优模型)"])
    
    with tab1:
        try:
            img_data, img_format = visualize_petri_net(result.n0_net, result.n0_im, result.n0_fm, "png")
            if img_format == 'dot':
                st.warning("Graphviz 未正确配置，显示 DOT 源码。请安装 Graphviz 并添加到 PATH。")
                st.code(img_data.decode('utf-8'), language='dot')
            else:
                st.image(img_data, use_container_width=True)
            
            stats = get_net_statistics(result.n0_net)
            st.write(f"**Places**: {stats['total_places']} | **Transitions**: {stats['total_transitions']} | **Arcs**: {stats['total_arcs']}")
        except Exception as e:
            st.error(f"可视化失败: {str(e)}")
    
    with tab2:
        try:
            img_data, img_format = visualize_petri_net(result.n1_net, result.n1_im, result.n1_fm, "png")
            if img_format == 'dot':
                st.warning("Graphviz 未正确配置，显示 DOT 源码。请安装 Graphviz 并添加到 PATH。")
                st.code(img_data.decode('utf-8'), language='dot')
            else:
                st.image(img_data, use_container_width=True)
            
            stats = get_net_statistics(result.n1_net)
            st.write(f"**Places**: {stats['total_places']} | **Transitions**: {stats['total_transitions']} | **Arcs**: {stats['total_arcs']}")
        except Exception as e:
            st.error(f"可视化失败: {str(e)}")
    
    st.header("📥 导出")
    
    col_e1, col_e2, col_e3 = st.columns(3)
    
    with col_e1:
        try:
            png_data, png_format = visualize_petri_net(result.n1_net, result.n1_im, result.n1_fm, "png")
            svg_data, svg_format = visualize_petri_net(result.n1_net, result.n1_im, result.n1_fm, "svg")
            
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                if png_format == 'png':
                    st.download_button(
                        label="下载 PNG",
                        data=png_data,
                        file_name="petri_net_n1.png",
                        mime="image/png"
                    )
                else:
                    st.download_button(
                        label="下载 DOT",
                        data=png_data,
                        file_name="petri_net_n1.dot",
                        mime="text/plain"
                    )
            with col_img2:
                if svg_format == 'svg':
                    st.download_button(
                        label="下载 SVG",
                        data=svg_data,
                        file_name="petri_net_n1.svg",
                        mime="image/svg+xml"
                    )
        except:
            st.button("下载图像", disabled=True)
    
    with col_e2:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pnml') as tmp:
                export_pnml(result.n1_net, result.n1_im, result.n1_fm, tmp.name)
                with open(tmp.name, 'r') as f:
                    pnml_data = f.read()
            st.download_button(
                label="下载 PNML",
                data=pnml_data,
                file_name="petri_net_n1.pnml",
                mime="application/xml"
            )
        except:
            st.button("下载 PNML", disabled=True)
    
    with col_e3:
        report = generate_verification_report(result)
        st.download_button(
            label="下载验证报告",
            data=report,
            file_name="verification_report.txt",
            mime="text/plain"
        )
    
    with st.expander("查看完整验证报告"):
        st.text(report)
    
    with st.expander("查看 JSON 结果"):
        st.json(result.to_dict())

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    CMIP 过程挖掘软件 v1.0 | 基于 PM4Py 和 CMIP-IMR 算法<br>
    参考文献: C. Liu et al., "Cross-department collaborative healthcare process model discovery from event logs," IEEE TASE, 2023
    </div>
    """,
    unsafe_allow_html=True
)
