import os
import json
from db.db import get_conn
from dotenv import load_dotenv

load_dotenv()

def update_from_document(session_id, files=None):
    # 可选 files: 若有则加载、分块、向量化，否则仅用 session_id 检索
    from langchain_postgres.vectorstores import PGVector
    from langchain_community.document_loaders import TextLoader, PDFPlumberLoader, Docx2txtLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.embeddings import DashScopeEmbeddings

    # Vectorstore and RAG utilities moved to services.rag_service
    from services.rag_service import ingest_files, search_docs, run_rag_on_question, run_module_level_rag, save_answers, get_llm, _ai_to_text

    # 1. 如 files 存在，先写入向量库（委托给 rag_service）
    if files:
        ingest_files(session_id, files)


    def format_source(metadata):
        source_file = metadata.get("source_file") or os.path.basename(metadata.get("source", ""))
        page = metadata.get("page")
        if page is None:
            return source_file or "未知来源"
        try:
            page_num = int(page) + 1
            return f"{source_file}:{page_num}"
        except (TypeError, ValueError):
            return source_file or "未知来源"

    # Extract company name
    company_name = "该企业"
    try:
        docs_for_name = search_docs(session_id, "本文档提到的企业或公司名称是什么？", k=1)
        if docs_for_name:
            llm = get_llm()
            name_prompt = f"请从以下内容中提取企业或公司名称，只输出名称，不要解释。\n内容：{docs_for_name[0].page_content}"
            name_result = llm.invoke(name_prompt)
            extracted_name = _ai_to_text(name_result)
            if extracted_name and len(extracted_name) < 50:  # reasonable length
                company_name = extracted_name
    except Exception:
        pass

    # 2. 确保 session_id 存在于 sessions 表，避免外键错误
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, session_token) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                (session_id, session_id)
            )
    conn.close()

    # 3. RAG 检索并自动更新 answers
    questions = {
        "policy_options": {
            "question": f"{company_name}是否有关于以下环境议题的正式政策？选项: 能源消耗与温室气体 (GHG), 水资源, 大气污染 (非温室气体), 材料、化学品与废弃物, 生物多样性, 产品使用寿命终止 (如回收)。输出选中的选项列表，如 ['能源消耗与温室气体 (GHG)']",
            "type": "list",
            "options": [
                "能源消耗与温室气体 (GHG)",
                "水资源",
                "大气污染 (非温室气体)",
                "材料、化学品与废弃物",
                "生物多样性",
                "产品使用寿命终止 (如回收)"
            ]
        },
        "quantitative_target": {
            "question": f"{company_name}的政策中是否包含定量目标？输出目标数值与年份，如 减少排放20% by 2030",
            "type": "text"
        },
        "energy_measures": {
            "question": f"{company_name}在减少能源消耗和温室气体排放方面，采取了哪些措施？",
            "type": "text"
        },
        "waste_measures": {
            "question": f"{company_name}在废弃物与化学品管理方面，采取了哪些措施？",
            "type": "text"
        },
        "ghg_practice": {
            "question": f"{company_name}关于 GHG 监测和报告实践，以下哪些适用？选项: 排放核算符合 ISO 14064-1 或 GHG Protocol 标准, 排放数据经过第三方验证 (ISAE 3410 等), 报告已向公众披露。输出选中的选项列表",
            "type": "list",
            "options": [
                "排放核算符合 ISO 14064-1 或 GHG Protocol 标准",
                "排放数据经过第三方验证 (ISAE 3410 等)",
                "报告已向公众披露"
            ]
        },
        "carbon_target": {
            "question": f"{company_name}关于碳减排目标，以下哪些适用？选项: 已公开承诺科学碳目标 (SBTi), 已有经 SBTi 批准的减排目标, 设有年度减排目标达成进度的审查机制。输出选中的选项列表",
            "type": "list",
            "options": [
                "已公开承诺科学碳目标 (SBTi)",
                "已有经 SBTi 批准的减排目标",
                "设有年度减排目标达成进度的审查机制"
            ]
        },
        "scope1": {
            "question": f"{company_name}的Scope 1（直接排放）是多少？单位为吨 CO2 当量",
            "type": "float"
        },
        "scope2": {
            "question": f"{company_name}的Scope 2（能源间接排放）是多少？单位为吨 CO2 当量",
            "type": "float"
        },
        "scope3": {
            "question": f"{company_name}的Scope 3（上下游其他间接排放）是多少？单位为吨 CO2 当量",
            "type": "float"
        },
        "energy_total": {
            "question": f"{company_name}的总能耗是多少？单位为kWh",
            "type": "float"
        },
        "renewable_ratio": {
            "question": f"{company_name}的可再生能源占比是多少？单位为%",
            "type": "float"
        },
        "hazardous_waste": {
            "question": f"{company_name}的危险废弃物总量是多少？单位为kg",
            "type": "float"
        },
        "nonhazardous_waste": {
            "question": f"{company_name}的非危险废弃物总量是多少？单位为kg",
            "type": "float"
        },
        "recycled_waste": {
            "question": f"{company_name}的回收/再利用废弃物总量是多少？单位为kg",
            "type": "float"
        }
    }
    answer_update = {}
    answer_sources = {}
    answer_conflicts = {}
    for key, qinfo in questions.items():
        question = qinfo["question"]
        qtype = qinfo["type"]
        options = qinfo.get("options", [])
        docs = search_docs(session_id, question, k=3)
        values, sources = ([], [])
        if docs:
            values, sources = run_rag_on_question(session_id, question, qtype, options, k=3)

        if qtype == "float":
            vl_value = None
            # KPI类字段通过API调用VL模型抽取
            if key in ["scope1", "scope2", "scope3", "energy_total", "renewable_ratio", "hazardous_waste", "nonhazardous_waste", "recycled_waste"]:
                try:
                    from services.rag_service import run_vl_kpi_extraction
                    vl_docs = docs or search_docs(session_id, question, k=3)
                    vl_extraction = run_vl_kpi_extraction(vl_docs, key)
                    vl_ref = None
                    for ref, v in vl_extraction.items():
                        try:
                            vl_value = float(str(v).replace("%", "").replace(",", "").strip())
                            vl_ref = ref
                            break
                        except Exception:
                            continue
                except Exception as e:
                    print(f"VL KPI抽取失败: {e}")
            if vl_value is not None:
                answer_update[key] = vl_value
                # 记录VL图片来源ref
                if 'vl_ref' in locals() and vl_ref:
                    answer_sources[key] = [vl_ref]
                else:
                    answer_sources[key] = ["VL图片抽取"]
            elif values:
                answer_update[key] = values[0]
                answer_sources[key] = [sources[0]]
                unique_values = []
                for val in values:
                    if all(abs(val - existing) > 1e-6 for existing in unique_values):
                        unique_values.append(val)
                if len(unique_values) > 1:
                    answer_conflicts[key] = [
                        {"value": val, "source": src}
                        for val, src in zip(values, sources)
                    ]
            else:
                answer_update[key] = None
        elif qtype == "text":
            if values:
                answer_update[key] = values[0]
                answer_sources[key] = [sources[0]]
                unique_values = list(dict.fromkeys(values))
                if len(unique_values) > 1:
                    answer_conflicts[key] = [
                        {"value": val, "source": src}
                        for val, src in zip(values, sources)
                    ]
            else:
                answer_update[key] = ""
        elif qtype == "list":
            merged = []
            for value_list in values:
                for item in value_list:
                    if item not in merged:
                        merged.append(item)
            answer_update[key] = merged
            if sources:
                answer_sources[key] = sorted(set(sources))

        if key in ["quantitative_target", "energy_measures", "waste_measures"]:
            modules, module_details, summary_text = run_module_level_rag(session_id, key, company_name, docs)
            answer_update[f"{key}_modules"] = modules
            answer_update[f"{key}_module_details"] = module_details
            answer_update[f"{key}_module_summary"] = summary_text
    # 更新 answers 表
    # 将结果保存到数据库
    print("[问卷自动抽取结果]")
    for k, v in answer_update.items():
        print(f"完成题目: {k}，答案: {v}")
    save_answers(session_id, answer_update, answer_sources, answer_conflicts)

def update_from_chat(session_id, message):
    # 结合聊天内容，更新问卷答案
    # 让 AI 生成结构化 JSON
    from services.rag_service import get_llm, _ai_to_text
    llm = get_llm()

    # prompt: 让 AI 把 message 转成问卷 JSON
    prompt = (
        "你是ESG问卷助手。请根据用户输入，将相关信息以JSON格式输出。"
        "字段名请用英文（scope1, scope2, scope3, energy_total, ...），"
        "支持用户用“范围一/范围二/范围三/Scope1/Scope2/Scope3”等中文或英文表达，"
        "自动映射到正确字段。"
        "例如：{'scope1': 500}。只输出JSON，不要解释。\n用户输入：" + message
    )
    ai_result = llm.invoke(prompt)
    # 提取 JSON 字符串并规范为文本
    json_str = _ai_to_text(ai_result)

    import json
    try:
        answer_update = json.loads(json_str.replace("'", '"'))
        # Sanitize values to be floats or None
        for key in answer_update:
            val = answer_update[key]
            if isinstance(val, str):
                try:
                    answer_update[key] = float(val)
                except ValueError:
                    answer_update[key] = None
            elif not isinstance(val, (int, float)):
                answer_update[key] = None
    except Exception:
        return

    mapping = {
        "范围一": "scope1", "范围二": "scope2", "范围三": "scope3",
        "Scope1": "scope1", "Scope2": "scope2", "Scope3": "scope3"
    }
    for k in list(answer_update.keys()):
        if k in mapping:
            answer_update[mapping[k]] = answer_update.pop(k)

    # 更新 answers 表
    # 确保关键环境字段总是存在于数据库记录中（即使值为 null）
    required_fields = ["scope1", "scope2", "scope3", "energy_total", "hazardous_waste", "nonhazardous_waste", "recycled_waste"]
    for f in required_fields:
        if f not in answer_update:
            answer_update[f] = None

    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            # 查找最新问卷答案
            cur.execute("SELECT id, answers FROM answers WHERE session_id=%s ORDER BY created_at DESC LIMIT 1", (session_id,))
            row = cur.fetchone()
            if row:
                answer_id, answers = row
                if not answers:
                    answers = {}
                else:
                    answers = dict(answers)
                answers.update(answer_update)
                # 确保合并后的记录也包含所有 required_fields
                for f in required_fields:
                    if f not in answers:
                        answers[f] = None
                cur.execute("UPDATE answers SET answers=%s WHERE id=%s", (json.dumps(answers), answer_id))
            else:
                # 已确保 answer_update 包含所有 required_fields
                cur.execute("INSERT INTO answers (session_id, questionnaire_id, answers) VALUES (%s, %s, %s)", (session_id, 1, json.dumps(answer_update)))
    conn.close()
