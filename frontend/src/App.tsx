import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { UploadCloud, Send, FileText, Bot, User, CheckCircle2, Loader2 } from 'lucide-react';
import './index.css';

interface Message {
  role: 'user' | 'ai';
  content: string;
}

function App() {
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [docStatus, setDocStatus] = useState<string>('');
  const [isUploading, setIsUploading] = useState(false);
  
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Poll for document status if processing
  useEffect(() => {
    let interval: number;
    if (documentId && docStatus === 'processing') {
      interval = setInterval(async () => {
        try {
          const res = await axios.get(`http://localhost:8000/documents/${documentId}`);
          setDocStatus(res.data.status);
          if (res.data.status === 'completed' || res.data.status === 'failed') {
            clearInterval(interval);
          }
        } catch (e) {
          console.error('Error polling status', e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [documentId, docStatus]);

  // Auto scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    setIsUploading(true);
    setDocStatus('uploading...');
    try {
      const response = await axios.post('http://localhost:8000/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setDocumentId(response.data.document_id);
      setDocStatus('processing');
    } catch (error) {
      console.error('Upload failed', error);
      setDocStatus('failed');
    } finally {
      setIsUploading(false);
    }
  };

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isAsking) return;

    const query = inputMessage;
    setInputMessage('');
    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setIsAsking(true);

    try {
      const res = await axios.post('http://localhost:8000/ask', {
        question: query,
        top_k: 5
      });
      
      setMessages(prev => [...prev, { role: 'ai', content: res.data.answer }]);
    } catch (error) {
      setMessages(prev => [...prev, { role: 'ai', content: 'Sorry, I encountered an error answering your question.' }]);
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="app-container">
      <header>
        <h1>NeuralRAG</h1>
        <p>Enterprise-grade intelligent document querying</p>
      </header>

      {!documentId ? (
        <div className="upload-zone">
          <input 
            type="file" 
            accept=".pdf" 
            className="upload-input" 
            onChange={handleFileUpload} 
            disabled={isUploading}
          />
          <div className="upload-content">
            {isUploading ? (
              <Loader2 size={48} className="icon-upload animate-spin" />
            ) : (
              <UploadCloud size={48} className="icon-upload" />
            )}
            <h2>Upload Knowledge Base</h2>
            <p>Drag and drop a PDF file here or click to browse.</p>
          </div>
        </div>
      ) : (
        <div style={{textAlign: 'center'}}>
          <div className="status-badge" style={{ backgroundColor: docStatus === 'processing' ? 'rgba(59, 130, 246, 0.1)' : 'rgba(16, 185, 129, 0.1)', color: docStatus === 'processing' ? 'var(--accent-primary)' : 'var(--success)' }}>
            {docStatus === 'processing' ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
            Document {docStatus}
          </div>
        </div>
      )}

      {docStatus === 'completed' && (
        <div className="chat-container">
          <div className="chat-messages">
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', color: 'var(--text-secondary)', marginTop: '2rem' }}>
                <Bot size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
                <p>Knowledge base embedded successfully.<br/>Ask me anything about the document!</p>
              </div>
            )}
            
            {messages.map((msg, idx) => (
              <div key={idx} className={`message ${msg.role}`}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', opacity: 0.8, fontSize: '0.8rem' }}>
                  {msg.role === 'user' ? <User size={14}/> : <Bot size={14}/>}
                  {msg.role === 'user' ? 'You' : 'NeuralRAG'}
                </div>
                <div style={{ lineHeight: '1.5' }}>{msg.content}</div>
              </div>
            ))}
            
            {isAsking && (
              <div className="message ai" style={{ opacity: 0.7 }}>
                <Loader2 size={16} className="animate-spin" /> Generating response...
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={handleAsk} className="chat-input-area">
            <input 
              type="text" 
              placeholder="Ask a question about your document..." 
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              disabled={isAsking}
            />
            <button type="submit" className="btn" disabled={isAsking || !inputMessage.trim()}>
              <Send size={18} />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default App;
