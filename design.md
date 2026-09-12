# NeuralRAG: System Design Document

## 1. System Overview

NeuralRAG is an Enterprise-scale Retrieval-Augmented Generation (RAG) pipeline. The system is designed to ingest PDF documents, process them into chunked vector embeddings asynchronously, and serve a conversational retrieval interface that answers queries based strictly on the uploaded document's context. 

The architecture separates heavy compute operations (like PDF parsing and LLM embedding generation) from the main API layer using an asynchronous task queue, ensuring the API remains highly responsive.

## 2. Architecture & Components

The system is composed of five main containerized components managed via Docker Compose:

### 2.1 React Frontend (Vite)
- **Role:** Provides a responsive Chat and Upload user interface.
- **Tech:** React 18, TypeScript, Vite, Axios, Lucide-React.
- **Key Flows:**
  - `Upload Flow`: Sends multipart/form-data to the backend, receives a task ID, and polls for completion status.
  - `Chat Flow`: Sends user queries to the backend and dynamically renders the streaming or returned LLM response with citations.

### 2.2 FastAPI Backend (API Layer)
- **Role:** Handles incoming HTTP requests and orchestrates tasks.
- **Tech:** FastAPI, Uvicorn (ASGI), Python 3.12.
- **Key Flows:**
  - `POST /upload`: Validates the uploaded file, saves it temporarily, and dispatches a Celery task.
  - `GET /document/{id}`: Queries PostgreSQL for the current status of the document (`pending`, `completed`, `failed`).
  - `POST /ask`: Queries PostgreSQL via pgvector to find the top K most similar document chunks, constructs a grounded prompt, and calls the Gemini LLM for the final answer.

### 2.3 Redis (Message Broker)
- **Role:** Acts as the messaging queue between the FastAPI backend and the Celery workers.
- **Tech:** Redis 7 (Alpine).

### 2.4 Celery Worker (Asynchronous Processing)
- **Role:** Performs heavy background tasks (PDF chunking, embedding generation) to avoid blocking the main API thread.
- **Tech:** Celery, Python, LangChain, Google Generative AI Embeddings.
- **Processing Pipeline:**
  1. **Loading:** Uses `PyPDFLoader` to extract text from the PDF.
  2. **Chunking:** Uses `RecursiveCharacterTextSplitter` (chunk_size: 1000, overlap: 200).
  3. **Embedding:** Calls `models/gemini-embedding-2` to generate 3072-dimensional vector embeddings for each chunk.
  4. **Persistence:** Saves the chunks and their vectors to PostgreSQL. Note: The database session is safely isolated and disposed of after each run to prevent Celery event loop crashes.

### 2.5 PostgreSQL Database (Storage & Vector Search)
- **Role:** Stores document metadata and performs high-speed vector similarity searches.
- **Tech:** PostgreSQL 16, pgvector, SQLAlchemy (asyncpg).
- **Schema:**
  - `documents`: Stores document ID, title, and processing status.
  - `document_chunks`: Stores the chunk text and a `VECTOR(3072)` column for the embedding.
- **Search Strategy:** Uses exact k-NN (k-Nearest Neighbors) sequential scan using cosine similarity via the `vector_cosine_ops` operator. (Note: HNSW indexing is excluded due to pgvector's 2000-dimension limit for indexes).

## 3. Data Flow Diagrams

### Document Ingestion Flow
1. **User** uploads `document.pdf` via **Frontend**.
2. **Frontend** POSTs to **FastAPI** (`/upload`).
3. **FastAPI** inserts a `pending` record into **Postgres**.
4. **FastAPI** pushes a `process_document_task` to **Redis**.
5. **Celery Worker** picks up the task.
6. **Celery Worker** chunks the PDF and calls **Gemini** for embeddings.
7. **Celery Worker** saves vectors to **Postgres** and updates status to `completed`.
8. **Frontend** polls `/document/{id}` and sees `completed`.

### Query Retrieval Flow (RAG)
1. **User** types a question via **Frontend**.
2. **Frontend** POSTs to **FastAPI** (`/ask`).
3. **FastAPI** generates an embedding for the query string using **Gemini**.
4. **FastAPI** queries **Postgres** for the top 5 chunks with the highest cosine similarity to the query embedding.
5. **FastAPI** constructs a strict prompt using the retrieved chunks.
6. **FastAPI** calls **Gemini Flash LLM**.
7. **Gemini** generates an answer based strictly on the context.
8. **FastAPI** returns the answer and the source chunks (citations) to the **Frontend**.

## 4. Key Design Decisions & Trade-offs

1. **pgvector over Pinecone/Weaviate:** 
   By using PostgreSQL with the `pgvector` extension, we consolidate our relational data (document status, metadata) and our vector data into a single, ACID-compliant database. This heavily reduces infrastructure complexity and eliminates data synchronization issues.
2. **Celery for Asynchronous Tasks:** 
   PDF extraction and embedding generation can take anywhere from seconds to minutes depending on document size and rate limits. A synchronous API request would timeout. Offloading to Celery ensures high throughput and reliability.
3. **Exact k-NN vs Approximate Nearest Neighbors (ANN/HNSW):** 
   Because `gemini-embedding-2` outputs 3072 dimensions, it exceeds pgvector's HNSW limit of 2000 dimensions. For the scope of this project (which targets localized document querying rather than querying a million-document corpus), exact sequential scans are highly performant and perfectly acceptable.
