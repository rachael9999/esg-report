import os
import json
import time
from pyexpat import model
from dotenv import load_dotenv
from pydantic import SecretStr
from db.db import get_conn

load_dotenv()


def _ai_to_text(ai_result):
    """Normalize model output to a string. Handles dict/list or objects with .content gracefully."""
    # Prefer dict access, otherwise use getattr to avoid static analyzer attribute errors
    content = None
    if isinstance(ai_result, dict):
        content = ai_result.get("content")
    else:
        content = getattr(ai_result, "content", None)

    if content is None:
        content = ai_result if isinstance(ai_result, (str, int, float)) else str(ai_result)

    if isinstance(content, (list, dict)):
        try:
            return json.dumps(content, ensure_ascii=False)
        except Exception:
            return str(content)
    return str(content).strip()


def get_llm():
    from langchain_community.chat_models import ChatTongyi
    from pydantic import SecretStr
    api_key = os.environ.get("DASHSCOPE_API_KEY") or ""
    return ChatTongyi(model="qwen-flash", api_key=SecretStr(api_key))


def get_vectorstore(session_id):
    from langchain_postgres.vectorstores import PGVector
    from langchain_community.embeddings import DashScopeEmbeddings

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    embeddings = DashScopeEmbeddings(model="text-embedding-v1", dashscope_api_key=api_key)
    vectorstore = PGVector(
        embeddings,
        connection=os.getenv("PGVECTOR_CONN", "postgresql://admin:admin@db:5432/esg_memory"),
        collection_name=f"session_{session_id}",
        use_jsonb=True,
    )
    return vectorstore


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


def get_vl_llm(model: str = "qwen3-vl-flash"):
    """Return a vision-capable LLM (e.g., qwen-3-vl)."""
    from langchain_community.chat_models import ChatTongyi
    from pydantic import SecretStr
    api_key = os.environ.get("DASHSCOPE_API_KEY") or ""
    return ChatTongyi(model=model, api_key=SecretStr(api_key))


def ingest_files(session_id, files, chunk_size=500, chunk_overlap=50):
    """Ingest given files into session vectorstore."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import TextLoader, PDFPlumberLoader, Docx2txtLoader

    vectorstore = get_vectorstore(session_id)
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    for file in files:
        docs = []
        try:
            if file.endswith('.pdf'):
                # try mineru first
                try:
                    from langchain_community.document_loaders import MineruPDFLoader
                    loader = MineruPDFLoader(file)
                    docs = loader.load()
                except Exception:
                    pass

                # pages
                try:
                    import pdfplumber
                    from langchain_core.documents import Document
                    with pdfplumber.open(file) as pdf:
                        for i, page in enumerate(pdf.pages):
                            page_text = page.extract_text() or ""
                            doc = Document(page_content=page_text, metadata={"source_file": os.path.basename(file), "page": i, "type": "text"})
                            docs.append(doc)
                except Exception:
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

            import os
            for doc in docs:
                doc.metadata["source_file"] = os.path.basename(file)
                # 仅当文件真实存在时才保存 source_path
                if os.path.isfile(file):
                    doc.metadata["source_path"] = os.path.abspath(file)
                else:
                    # 若文件不存在，避免写入无效路径
                    doc.metadata.pop("source_path", None)

            chunks = splitter.split_documents(docs)
            if chunks:
                vectorstore.add_documents(chunks)
        except Exception as e:
            print(f"Ingest 文件失败 {file}: {e}")


def search_docs(session_id, query, k=3):
    """Return top-k documents for a session vectorstore."""
    vectorstore = get_vectorstore(session_id)
    try:
        return vectorstore.similarity_search(query, k=k)
    except Exception as e:
        print(f"search_docs 异常: {e}")
        return []


def run_rag_on_question(session_id, question, qtype, options=None, k=3):
    """Run RAG for a single question and return (values, sources).
    values: list of extracted values (floats, strings, or list for list-type)
    sources: corresponding list of source strings
    """
    docs = search_docs(session_id, question, k=k)
    if not docs:
        return [], []

    llm = get_llm()
    import re

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
        value = _ai_to_text(ai_result)

        if qtype == "float":
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

    return values, sources


def run_module_level_rag(session_id, key, company_name, docs):
    """Detect modules from docs, then run per-module RAG to extract measures and provide a summary."""
    if not docs:
        return [], {}, ""
    llm = get_llm()
    try:
        contents = "\n\n".join([d.page_content[:2000] for d in docs])

        modules_prompt = (
            "请从以下内容中提取与问题相关的职能/模块或业务单元列表（例如: 生产, 运营, 采购, 研发, 物流, 能源管理, 废弃物处理），"
            "只输出JSON数组，例如 ['生产','能源管理']，不要解释。\n内容："
            + contents
        )
        modules_ai = llm.invoke(modules_prompt)
        modules_text = _ai_to_text(modules_ai)
        try:
            modules_list = json.loads(modules_text.replace("'", '"'))
            if not isinstance(modules_list, list):
                raise ValueError
            modules = [m.strip() for m in modules_list if isinstance(m, str) and m.strip()]
        except Exception:
            import re
            modules = [m.strip() for m in re.split(r'[,\n;]+', modules_text) if m.strip()]

        modules = list(dict.fromkeys(modules))

        module_details = {}
        for module in modules:
            module_q = (
                f"请根据以下内容，列出{company_name}在模块“{module}”方面采取的具体措施（列要点列表），"
                "只输出JSON对象：{'module': '模块名', 'measures': ['...']}，不要解释。\n内容：" + contents
            )
            mod_ai = llm.invoke(module_q)
            mod_text = _ai_to_text(mod_ai)
            try:
                parsed = json.loads(mod_text.replace("'", '"'))
                measures = parsed.get("measures") if isinstance(parsed, dict) else None
                if isinstance(measures, list):
                    module_details[module] = [m for m in measures if isinstance(m, str) and m.strip()]
                else:
                    module_details[module] = [mod_text]
            except Exception:
                module_details[module] = [mod_text]

        # Additional: if the question is KPI-style (numeric), attempt to extract numbers from images on matched pages using a VL model
        if key in ["scope1", "scope2", "scope3", "energy_total", "renewable_ratio", "hazardous_waste", "nonhazardous_waste", "recycled_waste"]:
            vl_responses = run_vl_kpi_extraction(docs, key)
            if vl_responses:
                module_details["_vl_extraction"] = vl_responses

        summary_prompt = (
            "请基于下面的模块信息，针对每个模块写一句总结性的概括，指出涉及哪些模块以及主要措施的亮点，"
            "输出为一句中文简短总结，不要解释。\n模块信息：" + json.dumps(module_details, ensure_ascii=False)
        )
        summ_ai = llm.invoke(summary_prompt)
        summary_text = _ai_to_text(summ_ai)
        return modules, module_details, summary_text
    except Exception as e:
        print(f"run_module_level_rag failed: {e}")
        return [], {}, ""


def save_answers(session_id, answer_update, answer_sources, answer_conflicts, questionnaire_id=1):
    """Merge and save answers into the database, preserving existing fields and adding _sources/_conflicts."""
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
                cur.execute("INSERT INTO answers (session_id, questionnaire_id, answers) VALUES (%s, %s, %s)", (session_id, questionnaire_id, json.dumps(answer_update)))
    conn.close()

from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage

def qwen_vl_langchain_qa(img_bytes, question, timeout_s=30):
    api_key = os.environ.get("DASHSCOPE_API_KEY") or ""
    if not api_key:
        print("VL调用跳过：未设置DASHSCOPE_API_KEY")
        return ""
    chatLLM = ChatTongyi(model="qwen-vl-max", api_key=SecretStr(api_key))
    image_message = {"image": img_bytes}
    text_message = {"text": question}
    message = HumanMessage(content=[text_message, image_message])
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    with ThreadPoolExecutor(max_workers=1) as executor:
        print(f"VL调用开始：timeout={timeout_s}s")
        future = executor.submit(chatLLM.invoke, [message])
        try:
            result = future.result(timeout=timeout_s)
        except TimeoutError:
            print("VL调用超时")
            return ""
    print("VL调用完成")
    return result.content


def run_vl_kpi_extraction(docs, key, timeout_s=30):
    print(f"VL抽取开始：key={key}, docs={len(docs)}")
    pages_by_file = {}
    for d in docs:
        src = d.metadata.get("source_path") or d.metadata.get("source_file")
        p = d.metadata.get("page")
        try:
            pi = int(p)
        except Exception:
            continue
        if src not in pages_by_file:
            pages_by_file[src] = set()
        pages_by_file[src].add(pi)

    vl_responses = {}
    for src, page_set in pages_by_file.items():
        try:
            import fitz
            start_open = time.time()
            with fitz.open(src) as doc:
                print(f"打开PDF耗时: {time.time() - start_open:.2f}s, 文件: {os.path.basename(src)}")
                for pi in sorted(page_set):
                    try:
                        page_start = time.time()
                        page = doc[pi]
                        pix = page.get_pixmap()
                        img_bytes = pix.tobytes("png")
                        print(f"[VL整页截图] {os.path.basename(src)} page {pi+1}: 已生成整页图片, 耗时: {time.time() - page_start:.2f}s")
                        prompt = (
                            "根据整页图片内容，回答以下指标的数值（如果图片中无相关信息请直接返回空）：\n"
                            f"指标：{key}\n"
                            "请直接输出纯数字或百分比（例如：12345 或 12.3%），不要解释。"
                        )
                        text = qwen_vl_langchain_qa(img_bytes, prompt, timeout_s=timeout_s)
                        if text:
                            vl_responses[f\"{os.path.basename(src)}:page_{pi+1}_fullpage\"] = text
                    except Exception as e:
                        print(f"整页截图失败: {e}")
                        continue
        except Exception as e:
            print(f"打开PDF失败: {e}")
            continue
    print(f"VL抽取完成：key={key}, responses={len(vl_responses)}")
    return vl_responses
