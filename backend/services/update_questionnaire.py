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

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    embeddings = DashScopeEmbeddings(model="text-embedding-v1", dashscope_api_key=api_key)
    vectorstore = PGVector(
        embeddings,
        connection=os.getenv("PGVECTOR_CONN", "postgresql://admin:admin@db:5432/postgres"),
        collection_name=f"session_{session_id}",
        use_jsonb=True
    )

    # 1. 如 files 存在，先写入向量库
    if files:
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        for file in files:
            docs = []
            if file.endswith('.pdf'):
                # 1. mineru 提取表格
                try:
                    import mineru
                    pdf_tables = mineru.read_pdf(file)
                    for i, df in enumerate(pdf_tables):
                        table_text = df.to_string(index=False)
                        from langchain_core.documents import Document
                        doc = Document(page_content=table_text, metadata={"source_file": os.path.basename(file), "table_index": i, "type": "table"})
                        docs.append(doc)
                except Exception as e:
                    print(f"mineru 解析失败: {e}")
                # 2. pdfplumber 提取每页文本
                try:
                    import pdfplumber
                    from langchain_core.documents import Document
                    with pdfplumber.open(file) as pdf:
                        for i, page in enumerate(pdf.pages):
                            page_text = page.extract_text() or ""
                            doc = Document(page_content=page_text, metadata={"source_file": os.path.basename(file), "page": i, "type": "text"})
                            docs.append(doc)
                except Exception as e:
                    print(f"pdfplumber 解析失败: {e}, 尝试 PDFPlumberLoader")
                    loader = PDFPlumberLoader(file)
                    text_docs = loader.load()
                    for doc in text_docs:
                        doc.metadata["source_file"] = os.path.basename(file)
                        doc.metadata["type"] = "text"
                    docs.extend(text_docs)
            elif file.endswith('.docx'):
                loader = Docx2txtLoader(file)
                docs = loader.load()
            else:
                loader = TextLoader(file)
                docs = loader.load()
            for doc in docs:
                doc.metadata["source_file"] = os.path.basename(file)
            chunks = splitter.split_documents(docs)
            vectorstore.add_documents(chunks)

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
        docs_for_name = vectorstore.similarity_search("本文档提到的企业或公司名称是什么？", k=1)
        if docs_for_name:
            from langchain_community.chat_models import ChatTongyi
            from pydantic import SecretStr
            api_key = os.environ.get("DASHSCOPE_API_KEY")
            llm = ChatTongyi(model="qwen-flash", api_key=SecretStr(api_key))
            name_prompt = f"请从以下内容中提取企业或公司名称，只输出名称，不要解释。\n内容：{docs_for_name[0].page_content}"
            name_result = llm.invoke(name_prompt)
            if hasattr(name_result, "content"):
                extracted_name = name_result.content.strip()
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
        docs = vectorstore.similarity_search(question, k=3)
        if docs:
            from langchain_community.chat_models import ChatTongyi
            from pydantic import SecretStr
            import re
            api_key = os.environ.get("DASHSCOPE_API_KEY")
            llm = ChatTongyi(model="qwen-flash", api_key=SecretStr(api_key))
            values = []
            sources = []

            for doc in docs:
                if qtype == "list" and options:
                    rag_prompt = (
                        "请根据以下内容回答问卷问题。"
                        "只能从给定选项中选择，输出JSON数组，不要解释。\n"
                        f"问题：{question}\n"
                        f"可选项：{options}\n"
                        f"内容：{doc.page_content}"
                    )
                else:
                    rag_prompt = f"请根据以下内容回答问卷问题，只输出答案，不要解释。\n问题：{question}\n内容：{doc.page_content}"
                ai_result = llm.invoke(rag_prompt)
                if hasattr(ai_result, "content"):
                    value = ai_result.content.strip()
                else:
                    value = str(ai_result).strip()
                print(f"RAG for {key}: Question: {question}")
                print(f"Content: {doc.page_content[:200]}...")
                print(f"AI Response: {value}")

                if qtype == "float":
                    # 先去掉千分位逗号，保证能正确提取如86,543.13
                    value_clean = value.replace(",", "")
                    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", value_clean)
                    if match:
                        values.append(float(match.group()))
                        sources.append(format_source(doc.metadata))
                elif qtype == "text":
                    if value:
                        values.append(value)
                        sources.append(format_source(doc.metadata))
                elif qtype == "list":
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            normalized = [
                                item.strip().strip("'").strip('"')
                                for item in parsed
                                if isinstance(item, str)
                            ]
                        else:
                            normalized = []
                    except Exception:
                        normalized = [v.strip().strip("'").strip('"') for v in value.split(',') if v.strip()]
                    if options:
                        normalized = [item for item in normalized if item in options]
                    if normalized:
                        values.append(normalized)
                        sources.append(format_source(doc.metadata))

            if qtype == "float":
                if values:
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
        else:
            if qtype == "float":
                answer_update[key] = None
            elif qtype == "text":
                answer_update[key] = ""
            elif qtype == "list":
                answer_update[key] = []
            print(f"No docs found for {key}")
    # 更新 answers 表
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, answers FROM answers WHERE session_id=%s ORDER BY created_at DESC LIMIT 1", (session_id,))
            row = cur.fetchone()
            if row:
                answer_id, answers = row
                if not answers:
                    answers = {}
                else:
                    answers = dict(answers)
                answers.update(answer_update)
                answers["_sources"] = answer_sources
                answers["_conflicts"] = answer_conflicts
                cur.execute("UPDATE answers SET answers=%s WHERE id=%s", (json.dumps(answers), answer_id))
            else:
                answer_update["_sources"] = answer_sources
                answer_update["_conflicts"] = answer_conflicts
                cur.execute("INSERT INTO answers (session_id, questionnaire_id, answers) VALUES (%s, %s, %s)", (session_id, 1, json.dumps(answer_update)))
    conn.close()

def update_from_chat(session_id, message):
    # 结合聊天内容，更新问卷答案
    # 让 AI 生成结构化 JSON
    from langchain_community.chat_models import ChatTongyi
    from pydantic import SecretStr
    import os
    from db.db import get_conn
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    llm = ChatTongyi(model="qwen-flash", api_key=SecretStr(api_key))

    # prompt: 让 AI 把 message 转成问卷 JSON
    prompt = (
        "你是ESG问卷助手。请根据用户输入，将相关信息以JSON格式输出。"
        "字段名请用英文（scope1, scope2, scope3, energy_total, ...），"
        "支持用户用“范围一/范围二/范围三/Scope1/Scope2/Scope3”等中文或英文表达，"
        "自动映射到正确字段。"
        "例如：{'scope1': 500}。只输出JSON，不要解释。\n用户输入：" + message
    )
    ai_result = llm.invoke(prompt)
    # 提取 JSON 字符串
    if isinstance(ai_result, dict) and "content" in ai_result:
        json_str = ai_result["content"]
    elif hasattr(ai_result, "content"):
        json_str = ai_result.content
    else:
        json_str = str(ai_result)

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
                cur.execute("UPDATE answers SET answers=%s WHERE id=%s", (json.dumps(answers), answer_id))
            else:
                cur.execute("INSERT INTO answers (session_id, questionnaire_id, answers) VALUES (%s, %s, %s)", (session_id, 1, json.dumps(answer_update)))
    conn.close()
