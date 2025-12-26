from langchain_community.document_loaders import TextLoader, PDFPlumberLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_postgres.vectorstores import PGVector
import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.environ.get("DASHSCOPE_API_KEY")

def process_and_store_document(file_path, session_id):
    # 1. 加载文档
    if file_path.endswith('.pdf'):
        docs = []
        # 1. mineru 提取表格
        try:
            import mineru
            pdf_tables = mineru.read_pdf(file_path)
            for i, df in enumerate(pdf_tables):
                table_text = df.to_string(index=False)
                from langchain_core.documents import Document
                doc = Document(page_content=table_text, metadata={"source_file": os.path.basename(file_path), "table_index": i, "type": "table"})
                docs.append(doc)
        except Exception as e:
            print(f"mineru 解析失败: {e}")
        # 2. PDFPlumberLoader 或 pdfplumber 提取全文
        try:
            try:
                import pdfplumber
                from langchain_core.documents import Document
                with pdfplumber.open(file_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        page_text = page.extract_text() or ""
                        doc = Document(page_content=page_text, metadata={"source_file": os.path.basename(file_path), "page": i, "type": "text"})
                        docs.append(doc)
            except Exception as e:
                print(f"pdfplumber 解析失败: {e}, 尝试 PDFPlumberLoader")
                loader = PDFPlumberLoader(file_path)
                text_docs = loader.load()
                for doc in text_docs:
                    doc.metadata["source_file"] = os.path.basename(file_path)
                    doc.metadata["type"] = "text"
                docs.extend(text_docs)
        except Exception as e:
            print(f"PDFPlumberLoader 解析失败: {e}")
    elif file_path.endswith('.docx'):
        from langchain_community.document_loaders import Docx2txtLoader
        loader = Docx2txtLoader(file_path)
        docs = loader.load()
    else:
        loader = TextLoader(file_path)
        docs = loader.load()
    # 2. 分块
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    # 3. 向量化
    embeddings = DashScopeEmbeddings(model="text-embedding-v1", dashscope_api_key=api_key)
    # 4. 存入 pgvector
    vectorstore = PGVector(
        embeddings,
        connection=os.getenv("PGVECTOR_CONN", "postgresql+psycopg2://admin:admin@db:5432/postgres"),
        collection_name=f"session_{session_id}",
        use_jsonb=True
    )
    vectorstore.add_documents(chunks)
