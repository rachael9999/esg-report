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
        loader = PDFPlumberLoader(file_path)
    elif file_path.endswith('.docx'):
        from langchain_community.document_loaders import Docx2txtLoader
        loader = Docx2txtLoader(file_path)
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
        connection=os.getenv("PGVECTOR_CONN", "postgresql+psycopg2://admin:admin@localhost:5432/postgres"),
        collection_name=f"session_{session_id}",
        use_jsonb=True
    )
    vectorstore.add_documents(chunks)
