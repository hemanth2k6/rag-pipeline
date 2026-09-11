import logging
from sqlalchemy import select
from models import AsyncSessionLocal, DocumentChunk
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Use the same Gemini model as the ingestion worker
embeddings_model = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

async def search_similar_chunks(query: str, top_k: int = 5):
    """
    Search for similar document chunks using cosine similarity against the pgvector HNSW index.
    """
    logger.info(f"Generating embedding for query: '{query}'")
    
    # Embed the search query
    query_embedding = embeddings_model.embed_query(query)

    async with AsyncSessionLocal() as session:
        # Use cosine distance (<=>) for similarity
        # Similarity score = 1 - cosine_distance
        distance_col = DocumentChunk.embedding.cosine_distance(query_embedding).label('distance')
        
        stmt = (
            select(DocumentChunk, distance_col)
            .order_by(distance_col)
            .limit(top_k)
        )
        
        result = await session.execute(stmt)
        rows = result.all()
        
        retrieved_results = []
        for row in rows:
            chunk = row.DocumentChunk
            distance = row.distance
            # 1 - distance gives us the cosine similarity score
            similarity_score = 1 - distance
            
            retrieved_results.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "text_content": chunk.text_content,
                "similarity_score": similarity_score
            })
            
            logger.info(f"Retrieved chunk {chunk.id} (Doc: {chunk.document_id}) with similarity {similarity_score:.4f}: {chunk.text_content[:100]}...")

        return retrieved_results

# For quick local testing
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    test_query = "What is the main topic of the uploaded document?"
    results = asyncio.run(search_similar_chunks(test_query))
    for res in results:
        print(f"--- Chunk {res['chunk_id']} (Score: {res['similarity_score']:.4f}) ---")
        print(res['text_content'])
        print()
