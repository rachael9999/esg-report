CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(128) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    session_token VARCHAR(128) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(128) REFERENCES sessions(id),
    filename VARCHAR(255),
    content TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vectors (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    chunk_index INTEGER,
    content TEXT,
    embedding vector(1536), -- 按实际embedding维度调整
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questionnaires (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    questions JSONB
);

CREATE TABLE IF NOT EXISTS answers (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(128) REFERENCES sessions(id),
    questionnaire_id INTEGER REFERENCES questionnaires(id),
    answers JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chats (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(128) REFERENCES sessions(id),
    user_input TEXT,
    ai_response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
