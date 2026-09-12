import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import io

from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@patch("main.AsyncSessionLocal")
@patch("main.process_document_task.delay")
def test_upload_document(mock_delay, mock_session):
    # Mock the database session
    mock_session_instance = AsyncMock()
    mock_session.return_value.__aenter__.return_value = mock_session_instance
    
    # Mock document id
    mock_doc = MagicMock()
    mock_doc.id = 1
    mock_session_instance.refresh = AsyncMock(return_value=None)
    
    # We need to simulate the SQLAlchemy object assignment since we mock the DB
    # The actual code creates `new_doc = Document(...)`, adds it, then refreshes.
    # It reads `new_doc.id`. Since we can't easily mock the exact SQLAlchemy behavior inline, 
    # we just let it create a real Document object and when it reads the ID, it might be None if not committed.
    # To avoid this, we'll patch `Document` as well, or just let it insert into a mocked session.
    # Actually, SQLAlchemy objects without DB commit have `id = None`. 
    # Let's mock the `Document` class in main to return our mock_doc.
    
    # Create a dummy PDF file
    dummy_pdf = io.BytesIO(b"%PDF-1.4\n%EOF")
    dummy_pdf.name = "test.pdf"

    with patch("main.Document", return_value=mock_doc):
        response = client.post("/upload", files={"file": ("test.pdf", dummy_pdf, "application/pdf")})
        
    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert response.json()["document_id"] == 1
    mock_delay.assert_called_once()

@patch("main.search_similar_chunks", new_callable=AsyncMock)
@patch("main.llm")
def test_ask_question(mock_llm, mock_search):
    # Mock retrieval
    mock_search.return_value = [
        {"chunk_id": 1, "document_id": 1, "text_content": "This is test context 1", "similarity_score": 0.9},
        {"chunk_id": 2, "document_id": 1, "text_content": "This is test context 2", "similarity_score": 0.8}
    ]
    
    # Mock LLM
    mock_response = MagicMock()
    mock_response.content = "This is the generated answer."
    mock_llm.invoke.return_value = mock_response

    payload = {
        "question": "What is the context?",
        "top_k": 2
    }

    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["answer"] == "This is the generated answer."
    assert data["citations"] == [1, 2]
    mock_search.assert_called_once_with("What is the context?", top_k=2)
    mock_llm.invoke.assert_called_once()
