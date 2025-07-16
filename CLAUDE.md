# RefServerLite Implementation Guide

## Project Overview
RefServerLite is a streamlined PDF repository service with OCR, metadata extraction, and semantic search capabilities.

## Core Architecture
- **Framework**: FastAPI with Uvicorn
- **Database**: SQLite with Peewee ORM (metadata)
- **Vector Store**: ChromaDB (embeddings & semantic search)
- **Frontend**: Jinja2 templates + Bootstrap 5
- **Processing**: Asynchronous pipeline with job queue

## Directory Structure
```
/RefServerLite
├── /app
│   ├── /static         # CSS/JS assets
│   ├── /templates      # Jinja2 templates
│   ├── main.py         # FastAPI app & endpoints
│   ├── pipeline.py     # PDF processing pipeline
│   ├── models.py       # Peewee database models
│   ├── ocr.py          # OCR logic (Tesseract)
│   ├── metadata.py     # Metadata extraction
│   ├── embedding.py    # Vector embeddings (bge-m3)
│   └── db.py           # Database operations
├── /data
│   ├── /pdfs           # Uploaded PDF storage
│   └── refserver.db    # SQLite database
└── /tests              # Pytest test suite
```

## Key Components

### 1. Database Models (models.py)
- **Paper**: Main document model (doc_id, filename, file_path, ocr_text)
- **Metadata**: Bibliographic info (title, authors, journal, year)
- **ProcessingJob**: Tracks async processing status
- **Note**: Embeddings stored in ChromaDB, not SQLite

### 2. API Endpoints (main.py)
- `POST /api/v1/upload` - Upload PDF for processing
- `GET /api/v1/job/{job_id}` - Check processing status
- `GET /api/v1/document/{doc_id}` - Retrieve processed document
- `GET /api/v1/search` - Search documents (keyword/semantic)

### 3. Processing Pipeline (pipeline.py)
1. **OCR Detection & Processing** (ocr.py)
   - Auto-detect if OCR needed
   - Use Tesseract for text extraction
   
2. **Metadata Extraction** (metadata.py)
   - Extract title, authors, journal, year
   - Rule-based approach
   
3. **Embedding Generation** (embedding.py)
   - Generate vector embeddings using bge-m3
   - Store in ChromaDB collection
   - Enable semantic similarity search

### 4. Frontend Templates
- `base.html` - Base template with Bootstrap
- `index.html` - Upload form & document list
- `document.html` - Document detail view

## Implementation Checklist

### Phase 1: Foundation
- [ ] Set up project structure
- [ ] Create database models with Peewee
- [ ] Implement basic FastAPI app structure
- [ ] Set up SQLite database connection
- [ ] Initialize ChromaDB client and collection

### Phase 2: Core Processing
- [ ] Implement PDF upload endpoint
- [ ] Create async processing job system
- [ ] Implement OCR with Tesseract
- [ ] Build metadata extraction logic
- [ ] Add embedding generation with bge-m3

### Phase 3: API & Frontend
- [ ] Complete all API endpoints
- [ ] Create web templates
- [ ] Implement admin dashboard
- [ ] Add keyword search (SQLite full-text)
- [ ] Add semantic search (ChromaDB similarity)

### Phase 4: Testing & Deployment
- [ ] Write unit tests (pytest)
- [ ] Create Dockerfile
- [ ] Set up docker-compose.yml
- [ ] Add documentation

## Key Libraries
```
fastapi
uvicorn
peewee
peewee-migrate
chromadb
tesseract (via pytesseract)
PyMuPDF
sentence-transformers
jinja2
httpx (for testing)
pytest
```

## Important Notes
- Use async/await for non-blocking operations
- ChromaDB handles vector storage and similarity search
- SQLite stores metadata and document info
- Authors stored as JSON string in metadata
- Job queue manages background processing
- Bootstrap 5 for responsive UI
- No user authentication in initial version