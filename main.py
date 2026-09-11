import os
import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel

from models import AsyncSessionLocal, Document, engine, Base
from worker import process_document_task
from retrieval import search_similar_chunks
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

app = FastAPI(title="RAG Pipeline API")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

from sqlalchemy import select

# Pydantic model for the ask request
class AskRequest(BaseModel):
    question: str
    top_k: int = 5

# Initialize the Gemini Chat Model
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/documents/{document_id}")
async def get_document_status(document_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return {
            "id": document.id,
            "title": document.title,
            "status": document.status
        }

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    # Save the file to disk
    async with aiofiles.open(file_path, 'wb') as out_file:
        while content := await file.read(1024 * 1024):  # 1MB chunks
            await out_file.write(content)

    # Create the Document record with 'processing' status
    async with AsyncSessionLocal() as session:
        new_doc = Document(
            title=file.filename,
            source_url=file_path,
            status='processing'
        )
        session.add(new_doc)
        await session.commit()
        await session.refresh(new_doc)
        doc_id = new_doc.id

    # Dispatch Celery task
    process_document_task.delay(doc_id, file_path)

    return {
        "message": "File uploaded successfully and processing started.",
        "document_id": doc_id,
        "status": "processing"
    }

@app.post("/ask")
async def ask_question(request: AskRequest):
    # 1. Retrieve similar chunks
    retrieved_chunks = await search_similar_chunks(request.question, top_k=request.top_k)
    
    # 2. Extract chunk texts and IDs for context and citations
    context_texts = []
    chunk_ids = []
    for c in retrieved_chunks:
        context_texts.append(f"Chunk ID: {c['chunk_id']}\nContent: {c['text_content']}")
        chunk_ids.append(c['chunk_id'])
        
    context_block = "\n\n---\n\n".join(context_texts)

    # 3. Construct System Prompt
    system_prompt = (
        "You are an enterprise AI assistant. Answer the user's question based strictly on the provided context. "
        "If the answer is not in the context, say so.\n\n"
        f"Context:\n{context_block}"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=request.question)
    ]

    # 4. Invoke LLM
    response = llm.invoke(messages)

    return {
        "answer": response.content,
        "citations": chunk_ids
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
