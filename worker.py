import os
import asyncio
import logging
from celery import Celery
from dotenv import load_dotenv

# LangChain imports
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Database imports
from sqlalchemy import select
from models import AsyncSessionLocal, Document, DocumentChunk

# Load environment variables
load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize Celery app
# Assuming Redis is running on localhost:6379 as per docker-compose
celery = Celery(
    'rag_worker',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

async def _process_document_async(doc_id: int, file_path: str):
    """
    Async implementation of the document processing pipeline.
    """
    try:
        logger.info(f"Starting processing for document {doc_id} at {file_path}")

        # 1. Load the PDF
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        logger.info(f"Loaded {len(docs)} pages from document {doc_id}")

        # 2. Chunk the text
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        chunks = text_splitter.split_documents(docs)
        logger.info(f"Split document {doc_id} into {len(chunks)} chunks")

        # 3. Generate embeddings
        # Ensure GOOGLE_API_KEY is present in the environment (.env)
        embeddings_model = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
        texts = [chunk.page_content for chunk in chunks]
        
        # Batch embed all chunks
        logger.info(f"Generating embeddings for {len(chunks)} chunks...")
        embeddings = embeddings_model.embed_documents(texts)

        # 4. Store in the database
        logger.info(f"Storing chunks and embeddings to database for document {doc_id}")
        async with AsyncSessionLocal() as session:
            # First, fetch the document to ensure it exists
            result = await session.execute(select(Document).where(Document.id == doc_id))
            document = result.scalar_one_or_none()
            
            if not document:
                logger.error(f"Document with ID {doc_id} not found in database!")
                return

            # Insert all chunks
            db_chunks = []
            for i, chunk in enumerate(chunks):
                db_chunks.append(
                    DocumentChunk(
                        document_id=doc_id,
                        text_content=chunk.page_content,
                        embedding=embeddings[i]
                    )
                )
            
            session.add_all(db_chunks)
            
            # Update document status
            document.status = 'completed'
            
            await session.commit()
            logger.info(f"Successfully finished processing document {doc_id}")

    except Exception as e:
        logger.error(f"Failed to process document {doc_id}: {str(e)}", exc_info=True)
        # Update status to failed
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Document).where(Document.id == doc_id))
                document = result.scalar_one_or_none()
                if document:
                    document.status = 'failed'
                    await session.commit()
        except Exception as db_e:
            logger.error(f"Failed to update document status to failed for {doc_id}: {str(db_e)}")


@celery.task(name='process_document_task')
def process_document_task(doc_id: int, file_path: str):
    """
    Celery task wrapper to run the async processing function.
    """
    asyncio.run(_process_document_async(doc_id, file_path))
