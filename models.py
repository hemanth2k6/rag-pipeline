import asyncio
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

# Connection string for asyncpg
DATABASE_URL = "postgresql+asyncpg://rag_user:rag_password@localhost:5433/rag_db"

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create async sessionmaker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    status = Column(String, default="pending")

    # Relationship to chunks
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text_content = Column(Text, nullable=False)
    
    # pgvector Vector column with dimension 768 (e.g. for Gemini models/text-embedding-004)
    embedding = Column(Vector(768))

    document = relationship("Document", back_populates="chunks")

# Create HNSW index for cosine distance
Index('hnsw_index_for_cosine', DocumentChunk.embedding,
      postgresql_using='hnsw',
      postgresql_with={'m': 16, 'ef_construction': 64},
      postgresql_ops={'embedding': 'vector_cosine_ops'})

async def run_migrations():
    """
    Initialize the database and run migrations (create tables).
    Assumes the pgvector extension is already created in the DB.
    """
    print("Running migrations...")
    async with engine.begin() as conn:
        # Drop all tables first since we are recreating schema in this greenfield project
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables defined in Base.metadata
        await conn.run_sync(Base.metadata.create_all)
    print("Migrations completed successfully.")

if __name__ == "__main__":
    # Execute the migration script if this file is run directly
    asyncio.run(run_migrations())
