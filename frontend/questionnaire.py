import streamlit as st
import html

def questionnaire_page():
    session_id = st.session_state.get("session_id", "default")
    last_questionnaire_session = st.session_state.get("questionnaire_session_id")
    session_changed = last_questionnaire_session != session_id
    if session_changed:
        questionnaire_keys = [
            "policy_options",
            "quantitative_target",
            "energy_measures",
            "waste_measures",
            "scope1",
            "scope2",
            "scope3",
            "energy_total",
            "renewable_ratio",
            "hazardous_waste",
            "nonhazardous_waste",
            "recycled_waste",
            "ghg_practice",
            "carbon_target",
        ]
        review_msg = None
        try:
            import requests
            import os
            backend_url = os.environ.get("BACKEND_URL", "http://fastapi-backend:8000")
            resp = requests.get(f"{backend_url}/questionnaire?session_id={session_id}")
            if resp.ok:
                data = resp.json()
                answers = data.get("answers", {})
                rag_contexts = data.get("rag_contexts", {})
                summary = data.get("summary", "")
                answer_sources = data.get("answer_sources", {}) or answers.get("_sources", {})
                answer_conflicts = data.get("answer_conflicts", {}) or answers.get("_conflicts", {})
                if "review" in data:
                    review_msg = data["review"]
        except Exception as e:
            st.error(f"问卷接口异常: {e}")

        # 页面顶部统一展示审核结果
        if review_msg:
            st.warning(f"审核结果：{review_msg}")
            return
        else:
            pass  # fallback, assume already in ton

    def convert_to_kwh(value, unit):
        """
        Convert value to kWh.
        Supported units: 'mj', 'gj', 'wh', 'kwh', 'mwh'
        """
        unit = str(unit).lower().replace(' ', '')
        if unit == 'mj':
            return value / 3.6
        elif unit == 'gj':
            return value * 277.78
        elif unit == 'wh':
            return value / 1000.0
        elif unit == 'mwh':
            return value * 1000.0
        elif unit == 'kwh':
            return value
        else:
            return value  # fallback, assume already in kWh

    def convert_to_ton_co2(value, unit):
        """
        Convert value to tons of CO2 equivalent.
        Supported units: 'kg', '吨', 't', 'ton', 'tons'
        """
        unit = str(unit).lower().replace(' ', '')
        if unit in ['kg']:
            return value / 1000.0
        elif unit in ['吨', 't', 'ton', 'tons']:
            return value
        elif unit in ['g']:
            return value / 1_000_000.0
        elif unit in ['mg']:
            return value / 1_000_000_000.0
        elif unit in ['lb', 'lbs', 'pound', 'pounds']:
            return value * 0.000453592
        elif unit in ['oz', 'ounce', 'ounces']:
            return value * 0.0000283495
        elif unit in ['st']:
            return value * 6.35029
        elif unit in ['metricton', 'metrictone']:
            return value
        elif unit in ['shortton', 'us ton']:
            return value * 0.907185
        elif unit in ['longton', 'imperial ton']:
            return value * 1.01605
        elif unit in ['gton', 'gigaton']:
            return value * 1_000_000_000.0
        elif unit in ['mton', 'megaton']:
            return value * 1_000_000.0
        elif unit in ['kt', 'kiloton']:
            return value * 1000.0   
        elif unit in ['lbm']:
            return value * 0.000453592
        elif unit in ['slug']:
            return value * 14.5939
        elif unit in ['grain']:
            return value * 0.00000006479891
        elif unit in ['carat']:
            return value * 0.0000002
        else:
            return value  # fallback, assume already in tons

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
    answers = {}
    rag_contexts = {}
    summary = ""
    answer_sources = {}
    answer_conflicts = {}
    try:
        import os
        backend_url = os.environ.get("BACKEND_URL", "http://fastapi-backend:8000")
        resp = requests.get(f"{backend_url}/questionnaire?session_id={session_id}")
        if resp.ok:
            data = resp.json()
            answers = data.get("answers", {})
            rag_contexts = data.get("rag_contexts", {})
            summary = data.get("summary", "")
            answer_sources = data.get("answer_sources", {}) or answers.get("_sources", {})
            answer_conflicts = data.get("answer_conflicts", {}) or answers.get("_conflicts", {})
            # 展示审核结果
            if "review" in data:
                st.warning(f"审核结果：{data['review']}")
    except Exception:
        pass

    if isinstance(answers, dict):
        answers.pop("_sources", None)
        answers.pop("_conflicts", None)

    def render_label(field_key, text):
        source_items = answer_sources.get(field_key, [])
        if source_items:
            tooltip = html.escape("\n".join(source_items))
            st.markdown(f"{text} <span title=\"{tooltip}\">📎</span>", unsafe_allow_html=True)
        else:
            st.markdown(text)

    def render_conflict(field_key):
        conflict_items = answer_conflicts.get(field_key, [])
        if conflict_items:
            st.warning("检测到多个来源存在冲突，请展开查看详情。")
            with st.expander("查看冲突详情"):
                details = "\n".join(
                    f"- <b>{item.get('value')}</b>（{item.get('source', '未知来源')}）"
                    for item in conflict_items
                )
                st.markdown(
                    f"<div style='word-break: break-all; white-space: pre-wrap;'>{details}</div>",
                    unsafe_allow_html=True
                )
    def normalize_multiselect_defaults(value, options):
        if not value:
            return []
        normalized = []
        for item in value:
            if isinstance(item, str):
                item = item.strip().strip("'").strip('"')
                if item in options:
                    normalized.append(item)
        return normalized

    # 1. 环境政策
    st.subheader("环境政策")
    render_label("policy_options", "贵公司是否有关于以下环境议题的正式政策？(多选)")
    # 只用 default 初始化，不赋值 session_state，避免冲突
    policy_options = st.multiselect(
        "政策议题",
        options_map["0"],
        default=normalize_multiselect_defaults(answers.get("policy_options", []), options_map["0"]),
        key="policy_options",
        label_visibility="collapsed"
    )
    render_label("quantitative_target", "政策中是否包含定量目标？(需提供目标数值与年份)")
    quantitative_target = st.text_input(
        "定量目标",
        value=answers.get("quantitative_target", ""),
        key="quantitative_target",
        label_visibility="collapsed"
    )
    render_conflict("quantitative_target")

    # 2. 减排与废弃物措施
    st.subheader("减排与废弃物措施")
    render_label("energy_measures", "在减少能源消耗和温室气体排放方面，采取了哪些措施？")
    if session_changed:
        st.session_state["energy_measures"] = answers.get("energy_measures", "")
    energy_measures = st.text_area(
        "能源/温室气体措施",
        value=answers.get("energy_measures", ""),
        key="energy_measures",
        label_visibility="collapsed"
    )
    render_conflict("energy_measures")
    render_label("waste_measures", "在废弃物与化学品管理方面，采取了哪些措施？")
    if session_changed:
        st.session_state["waste_measures"] = answers.get("waste_measures", "")
    waste_measures = st.text_area(
        "废弃物/化学品措施",
        value=answers.get("waste_measures", ""),
        key="waste_measures",
        label_visibility="collapsed"
    )
    render_conflict("waste_measures")

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

    render_label("scope1", "Scope 1 (直接排放)：______ 吨 CO2 当量")
    scope1_value = safe_float(answers.get("scope1", 0))
    scope1_unit = answers.get("scope1_unit", "吨")  # default to 吨
    scope1_value = convert_to_ton_co2(scope1_value, scope1_unit)
    if session_changed:
        st.session_state["scope1"] = scope1_value
    scope1 = st.number_input(
        "Scope 1 (吨 CO2)",
        min_value=0.0,
        value=scope1_value,
        format="%.2f",
        key="scope1",
        label_visibility="collapsed"
    )
    render_conflict("scope1")
    render_label("scope2", "Scope 2 (能源间接排放)：______ 吨 CO2 当量")
    scope2_value = safe_float(answers.get("scope2", 0))
    scope2_unit = answers.get("scope2_unit", "吨")
    scope2_value = convert_to_ton_co2(scope2_value, scope2_unit)
    if session_changed:
        st.session_state["scope2"] = scope2_value
    scope2 = st.number_input(
        "Scope 2 (吨 CO2)",
        min_value=0.0,
        value=scope2_value,
        format="%.2f",
        key="scope2",
        label_visibility="collapsed"
    )
    render_conflict("scope2")
    render_label("scope3", "Scope 3 (上下游其他间接排放)：______ 吨 CO2 当量")
    scope3_value = safe_float(answers.get("scope3", 0))
    scope3_unit = answers.get("scope3_unit", "吨")
    scope3_value = convert_to_ton_co2(scope3_value, scope3_unit)
    if session_changed:
        st.session_state["scope3"] = scope3_value
    scope3 = st.number_input(
        "Scope 3 (吨 CO2)",
        min_value=0.0,
        value=scope3_value,
        format="%.2f",
        key="scope3",
        label_visibility="collapsed"
    )
    render_conflict("scope3")
    render_label("energy_total", "总能耗：______ kWh")
    energy_total_value = safe_float(answers.get("energy_total", 0))
    energy_total_unit = answers.get("energy_total_unit", "kWh")
    energy_total_value = convert_to_kwh(energy_total_value, energy_total_unit)
    if session_changed:
        st.session_state["energy_total"] = energy_total_value
    energy_total = st.number_input(
        "总能耗 (kWh)",
        min_value=0.0,
        value=energy_total_value,
        format="%.2f",
        key="energy_total",
        label_visibility="collapsed"
    )
    render_conflict("energy_total")
    render_label("renewable_ratio", "可再生能源占比：______ %")
    renewable_ratio_value = safe_float(answers.get("renewable_ratio", 0))
    if renewable_ratio_value < 0.0:
        renewable_ratio_value = 0.0
    elif renewable_ratio_value > 100.0:
        renewable_ratio_value = 0.0
    else:
        renewable_ratio_value = min(max(renewable_ratio_value, 0.0), 100.0)
    if session_changed:
        st.session_state["renewable_ratio"] = renewable_ratio_value
    renewable_ratio = st.number_input(
        "可再生能源占比",
        min_value=0.0,
        max_value=100.0,
        value=renewable_ratio_value,
        format="%.2f",
        key="renewable_ratio",
        label_visibility="collapsed"
    )
    render_conflict("renewable_ratio")
    render_label("hazardous_waste", "危险废弃物总量：______ kg")
    if session_changed:
        st.session_state["hazardous_waste"] = safe_float(answers.get("hazardous_waste", 0))
    hazardous_waste = st.number_input(
        "危险废弃物总量",
        min_value=0.0,
        value=safe_float(answers.get("hazardous_waste", 0)),
        format="%.2f",
        key="hazardous_waste",
        label_visibility="collapsed"
    )
    render_conflict("hazardous_waste")
    render_label("nonhazardous_waste", "非危险废弃物总量：______ kg")
    if session_changed:
        st.session_state["nonhazardous_waste"] = safe_float(answers.get("nonhazardous_waste", 0))
    nonhazardous_waste = st.number_input(
        "非危险废弃物总量",
        min_value=0.0,
        value=safe_float(answers.get("nonhazardous_waste", 0)),
        format="%.2f",
        key="nonhazardous_waste",
        label_visibility="collapsed"
    )
    render_conflict("nonhazardous_waste")
    render_label("recycled_waste", "回收/再利用废弃物总量：______ kg")
    if session_changed:
        st.session_state["recycled_waste"] = safe_float(answers.get("recycled_waste", 0))
    recycled_waste = st.number_input(
        "回收/再利用废弃物总量",
        min_value=0.0,
        value=safe_float(answers.get("recycled_waste", 0)),
        format="%.2f",
        key="recycled_waste",
        label_visibility="collapsed"
    )
    render_conflict("recycled_waste")

    # 4. 碳管理实践
    st.subheader("碳管理实践")
    render_label("ghg_practice", "关于 GHG 监测和报告实践，以下哪些适用？")
    if session_changed:
        st.session_state["ghg_practice"] = normalize_multiselect_defaults(
            answers.get("ghg_practice", []),
            options_map["12"],
        )
    ghg_practice = st.multiselect(
        "GHG 监测/报告",
        options_map["12"],
        default=normalize_multiselect_defaults(answers.get("ghg_practice", []), options_map["12"]),
        key="ghg_practice",
        label_visibility="collapsed"
    )
    render_label("carbon_target", "关于碳减排目标，以下哪些适用？")
    if session_changed:
        st.session_state["carbon_target"] = normalize_multiselect_defaults(
            answers.get("carbon_target", []),
            options_map["13"],
        )
    carbon_target = st.multiselect(
        "碳减排目标",
        options_map["13"],
        default=normalize_multiselect_defaults(answers.get("carbon_target", []), options_map["13"]),
        key="carbon_target",
        label_visibility="collapsed"
    )

    # 导出 Markdown 摘要
    if st.button("导出 Markdown 摘要"):
        rag_section = "\n## RAG 检索内容\n\n"
        for key, content in rag_contexts.items():
            rag_section += f"### {key}\n{content}\n\n"
        md = f"""# ESG 环境问卷摘要\n\n## 环境政策\n- 政策议题: {', '.join(policy_options)}\n- 定量目标: {quantitative_target}\n\n## 减排与废弃物措施\n- 能源/温室气体措施: {energy_measures}\n- 废弃物/化学品措施: {waste_measures}\n\n## 关键绩效指标 (KPIs)\n- Scope 1: {scope1} 吨 CO2 当量\n- Scope 2: {scope2} 吨 CO2 当量\n- Scope 3: {scope3} 吨 CO2 当量\n- 总能耗: {energy_total} kWh\n- 可再生能源占比: {renewable_ratio} %\n- 危险废弃物: {hazardous_waste} kg\n- 非危险废弃物: {nonhazardous_waste} kg\n- 回收/再利用废弃物: {recycled_waste} kg\n\n## 碳管理实践\n- GHG 监测/报告: {', '.join(ghg_practice)}\n- 碳减排目标: {', '.join(carbon_target)}\n\n{rag_section}\n## RAG 摘要\n{summary}"""
        st.download_button("下载 Markdown 文件", md, file_name="esg_summary.md")

    # 保存更改
    if st.button("保存问卷更改"):
        updated_answers = {
            "policy_options": policy_options,
            "quantitative_target": quantitative_target,
            "energy_measures": energy_measures,
            "waste_measures": waste_measures,
            "scope1": scope1,
            "scope2": scope2,
            "scope3": scope3,
            "energy_total": energy_total,
            "renewable_ratio": renewable_ratio,
            "hazardous_waste": hazardous_waste,
            "nonhazardous_waste": nonhazardous_waste,
            "recycled_waste": recycled_waste,
            "ghg_practice": ghg_practice,
            "carbon_target": carbon_target
        }
        import requests
        import json
        import os
        backend_url = os.environ.get("BACKEND_URL", "http://fastapi-backend:8000")
        response = requests.post(f"{backend_url}/update_answers", data={"session_id": session_id, "answers": json.dumps(updated_answers)})
        if response.ok:
            st.success("问卷已保存！即将刷新页面……")
            st.rerun()
        else:
            st.error("保存失败")
    if session_changed:
        st.session_state["questionnaire_session_id"] = session_id
