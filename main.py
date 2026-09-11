import os
import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException
from contextlib import asynccontextmanager

from models import AsyncSessionLocal, Document, engine, Base
# Import the celery task (we will create worker.py shortly)
from worker import process_document_task

app = FastAPI(title="RAG Pipeline API")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
