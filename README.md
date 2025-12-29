# ESG Demo Application

This is a comprehensive ESG (Environmental, Social, and Governance) analysis demo application built with FastAPI, Streamlit, PostgreSQL, and LangChain. It allows users to upload documents, automatically fill questionnaires using RAG (Retrieval-Augmented Generation), engage in AI-powered chat with source citations, and manually edit questionnaire answers. All data persists across sessions and app restarts.

## Features

- **Document Upload**: Upload PDF documents for ESG analysis.
- **RAG-Based Questionnaire Filling**: Automatically populate ESG questionnaires from uploaded documents using local HuggingFace embeddings and vector search.
- **AI Chat with Sources**: Interact with an AI chatbot that provides answers based on uploaded documents, including source citations.
- **Manual Questionnaire Editing**: Edit questionnaire answers manually with various input types (text, number, multiselect).
- **Session Management**: Create and manage multiple sessions, with data persistence in PostgreSQL.
- **Data Persistence**: Sessions, answers, chats, and documents are stored in the database and load on app restart.

## Architecture

- **Backend**: FastAPI server handling API endpoints for upload, chat, questionnaire, sessions, and answers.
- **Frontend**: Streamlit UI for user interaction, including file upload, questionnaire forms, and chat interface.
- **Database**: PostgreSQL with PGVector for vector embeddings and relational data storage.
- **RAG Components**: LangChain for document processing, embeddings (HuggingFace), and chat chains.

## Setup Instructions

### Prerequisites

- Python 3.8+
- PostgreSQL with PGVector extension
- Virtual environment (recommended)

### Installation

1. Clone or download the project.
2. Create a virtual environment:
   ```
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Linux/Mac: `source .venv/bin/activate`
4. Install dependencies:
   ```
   cd backend
   pip install -r requirements.txt
   ```
5. Set up environment variables in a `.env` file:
   ```
   PGVECTOR_CONN=postgresql://admin:admin@localhost:5432/postgres
   DASHSCOPE_API_KEY=your_api_key_if_needed (though now using local embeddings)
   ```
6. Initialize the database:
   - Run the SQL script in `schema.sql` to create tables.
   - Ensure PGVector is installed and configured.

### Running the Application

1. Start the backend:
   ```
   cd backend
   uvicorn app:app --reload
   ```
2. Start the frontend:
   ```
   cd frontend
   streamlit run app.py
   ```
3. Access the app at `http://localhost:8501` (Streamlit) and API at `http://localhost:8000` (FastAPI).

## API Endpoints

- `POST /upload`: Upload a document and process it for RAG.
- `POST /chat`: Send a chat message and get AI response.
- `GET /questionnaire?session_id=<id>`: Retrieve questionnaire data for a session.
- `POST /create_session`: Create a new session with a name.
- `POST /update_answers`: Update questionnaire answers for a session.
- `GET /chats?session_id=<id>`: Retrieve chat history for a session.
- `GET /sessions`: List all sessions.

## Usage

1. Create a new session from the sidebar.
2. Upload ESG-related documents (e.g., PDFs).
3. The questionnaire will auto-fill based on document content.
4. Edit answers manually if needed.
5. Use the chat feature to ask questions about the documents, with sources provided.
6. Data persists across restarts.

## Technologies Used

- **FastAPI**: Backend API framework.
- **Streamlit**: Frontend UI framework.
- **PostgreSQL + PGVector**: Database for relational and vector data.
- **LangChain**: RAG and chat chain implementation.
- **HuggingFace Embeddings**: Local embeddings for document search.
- **PDFPlumber**: PDF text extraction.
- **Python Libraries**: psycopg2, dotenv, pydantic, etc.

## Troubleshooting

- Ensure PostgreSQL is running and PGVector is installed.
- Check environment variables in `.env`.
- For embedding issues, verify HuggingFace model download.
- If proxy errors occur, the app now uses local embeddings.

## Future Enhancements

- Add user authentication.
- Support for more document types.
- Advanced RAG tuning.
- Export questionnaire results to PDF/Excel.

## License

This project is for demonstration purposes. Use at your own risk.
