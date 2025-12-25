import streamlit as st

def questionnaire_page():
    st.header("环境政策")
    options_map = {
        "0": [
            "能源消耗与温室气体 (GHG)",
            "水资源",
            "大气污染 (非温室气体)",
            "材料、化学品与废弃物",
            "生物多样性",
            "产品使用寿命终止 (如回收)"
        ],
        "12": [
            "排放核算符合 ISO 14064-1 或 GHG Protocol 标准",
            "排放数据经过第三方验证 (ISAE 3410 等)",
            "报告已向公众披露"
        ],
        "13": [
            "已公开承诺科学碳目标 (SBTi)",
            "已有经 SBTi 批准的减排目标",
            "设有年度减排目标达成进度的审查机制"
        ]
    }

    # Fetch answers
    import requests
    session_id = st.session_state.get("session_id", "default")
    answers = {}
    try:
        resp = requests.get(f"http://localhost:8000/questionnaire?session_id={session_id}")
        if resp.ok:
            answers = resp.json().get("answers", {})
    except Exception:
        pass

    # 1. 环境政策
    st.subheader("环境政策")
    policy_options = st.multiselect(
        "贵公司是否有关于以下环境议题的正式政策？(多选)",
        options_map["0"],
        default=answers.get("policy_options", [])
    )
    quantitative_target = st.text_input("政策中是否包含定量目标？(需提供目标数值与年份)", value=answers.get("quantitative_target", ""))

    # 2. 减排与废弃物措施
    st.subheader("减排与废弃物措施")
    energy_measures = st.text_area("在减少能源消耗和温室气体排放方面，采取了哪些措施？", value=answers.get("energy_measures", ""))
    waste_measures = st.text_area("在废弃物与化学品管理方面，采取了哪些措施？", value=answers.get("waste_measures", ""))

    # 3. 关键绩效指标 (KPIs)
    st.subheader("关键绩效指标 (KPIs)")
    def safe_float(val, default=0.0):
        if isinstance(val, (int, float)):
            return float(val)
        elif isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return default
        else:
            return default

    scope1 = st.number_input("Scope 1 (直接排放)：______ 吨 CO2 当量", min_value=0.0, value=safe_float(answers.get("scope1", 0)), format="%.2f")
    scope2 = st.number_input("Scope 2 (能源间接排放)：______ 吨 CO2 当量", min_value=0.0, value=safe_float(answers.get("scope2", 0)), format="%.2f")
    scope3 = st.number_input("Scope 3 (上下游其他间接排放)：______ 吨 CO2 当量", min_value=0.0, value=safe_float(answers.get("scope3", 0)), format="%.2f")
    energy_total = st.number_input("总能耗：______ kWh", min_value=0.0, value=safe_float(answers.get("energy_total", 0)), format="%.2f")
    renewable_ratio = st.number_input("可再生能源占比：______ %", min_value=0.0, max_value=100.0, value=safe_float(answers.get("renewable_ratio", 0)), format="%.2f")
    hazardous_waste = st.number_input("危险废弃物总量：______ kg", min_value=0.0, value=safe_float(answers.get("hazardous_waste", 0)), format="%.2f")
    nonhazardous_waste = st.number_input("非危险废弃物总量：______ kg", min_value=0.0, value=safe_float(answers.get("nonhazardous_waste", 0)), format="%.2f")
    recycled_waste = st.number_input("回收/再利用废弃物总量：______ kg", min_value=0.0, value=safe_float(answers.get("recycled_waste", 0)), format="%.2f")

    # 4. 碳管理实践
    st.subheader("碳管理实践")
    ghg_practice = st.multiselect("关于 GHG 监测和报告实践，以下哪些适用？", options_map["12"], default=answers.get("ghg_practice", []))
    carbon_target = st.multiselect("关于碳减排目标，以下哪些适用？", options_map["13"], default=answers.get("carbon_target", []))

    # 导出 Markdown 摘要
    if st.button("导出 Markdown 摘要"):
        md = f"""# ESG 环境问卷摘要\n\n## 环境政策\n- 政策议题: {', '.join(policy_options)}\n- 定量目标: {quantitative_target}\n\n## 减排与废弃物措施\n- 能源/温室气体措施: {energy_measures}\n- 废弃物/化学品措施: {waste_measures}\n\n## 关键绩效指标 (KPIs)\n- Scope 1: {scope1} 吨 CO2 当量\n- Scope 2: {scope2} 吨 CO2 当量\n- Scope 3: {scope3} 吨 CO2 当量\n- 总能耗: {energy_total} kWh\n- 可再生能源占比: {renewable_ratio} %\n- 危险废弃物: {hazardous_waste} kg\n- 非危险废弃物: {nonhazardous_waste} kg\n- 回收/再利用废弃物: {recycled_waste} kg\n\n## 碳管理实践\n- GHG 监测/报告: {', '.join(ghg_practice)}\n- 碳减排目标: {', '.join(carbon_target)}\n"""
        st.download_button("下载 Markdown 文件", md, file_name="esg_summary.md")
