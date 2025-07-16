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
│   ├── chunking.py     # Semantic chunking logic
│   ├── visualize.py    # 2D embedding visualization
│   ├── visualize_3d.py # 3D embedding visualization
│   ├── auth.py         # Authentication logic
│   └── db.py           # Database operations
├── /data
│   ├── /pdfs           # Uploaded PDF storage
│   └── refserver.db    # SQLite database
├── /devlog             # Development logs and experiments
├── /migrations         # Database migration files
└── /tests              # Pytest test suite
```

## Key Components

### 1. Database Models (models.py)
- **Paper**: Main document model (doc_id, filename, file_path, ocr_text)
- **Metadata**: Bibliographic info (title, authors, journal, year)
- **ProcessingJob**: Tracks async processing status with detailed step tracking
- **PageText**: Stores extracted text for each page
- **SemanticChunk**: Stores semantic chunks with metadata and embedding IDs
- **User**: User authentication and admin access
- **Note**: Embeddings stored in ChromaDB, not SQLite

### 2. API Endpoints (main.py)
- `POST /api/v1/upload` - Upload PDF for processing
- `GET /api/v1/job/{job_id}` - Check processing status
- `GET /api/v1/document/{doc_id}` - Retrieve processed document
- `GET /api/v1/search` - Search documents (keyword/semantic/chunks)
- `GET /api/v1/document/{doc_id}/chunks` - Get semantic chunks for document
- `POST /api/v1/admin/apply-chunking/{doc_id}` - Apply semantic chunking
- `GET /api/v1/admin/chunking-status` - Check chunking status
- **Visualization APIs**: 2D heatmaps and 3D visualizations for embeddings

### 3. Processing Pipeline (pipeline.py)
1. **OCR Detection & Processing** (ocr.py)
   - Auto-detect if OCR needed
   - Use Tesseract for text extraction
   - Structure-preserving text extraction for chunking
   
2. **Metadata Extraction** (metadata.py)
   - Extract title, authors, journal, year
   - Rule-based approach
   
3. **Embedding Generation** (embedding.py)
   - Generate vector embeddings using bge-m3
   - Store in ChromaDB collection
   - Enable semantic similarity search
   
4. **Semantic Chunking** (chunking.py)
   - Hierarchical chunking strategy
   - Preserve document structure (paragraphs, sentences)
   - Support for different chunk types and quality validation

### 4. Frontend Templates
- `base.html` - Base template with Bootstrap
- `index.html` - Upload form & document list
- `document.html` - Document detail view with tabbed interface
- `admin.html` - Admin dashboard with search and chunk management
- `login.html` - User authentication

## Implementation Status

### Phase 1: Foundation ✅
- [x] Set up project structure
- [x] Create database models with Peewee
- [x] Implement basic FastAPI app structure
- [x] Set up SQLite database connection
- [x] Initialize ChromaDB client and collection

### Phase 2: Core Processing ✅
- [x] Implement PDF upload endpoint
- [x] Create async processing job system
- [x] Implement OCR with Tesseract
- [x] Build metadata extraction logic
- [x] Add embedding generation with bge-m3

### Phase 3: API & Frontend ✅
- [x] Complete all API endpoints
- [x] Create web templates
- [x] Implement admin dashboard
- [x] Add keyword search (SQLite full-text)
- [x] Add semantic search (ChromaDB similarity)

### Phase 4: Advanced Features ✅
- [x] Semantic chunking implementation
- [x] Enhanced search with chunk support
- [x] Tabbed document interface
- [x] Embedding visualizations
- [x] Admin chunk management

### Phase 5: Testing & Deployment 🔄
- [x] Create Dockerfile
- [x] Set up docker-compose.yml
- [x] Database migrations
- [ ] Write comprehensive unit tests (pytest)
- [ ] Performance optimization
- [ ] Production deployment guide

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
matplotlib (for visualizations)
numpy
passlib (for authentication)
```

## Important Notes
- Use async/await for non-blocking operations
- ChromaDB handles vector storage and similarity search
- SQLite stores metadata and document info
- Authors stored as JSON string in metadata
- Job queue manages background processing
- Bootstrap 5 for responsive UI
- Basic user authentication with admin access
- Semantic chunking supports hierarchical text splitting
- 2D heatmap visualizations for embedding fingerprints
- 3D visualizations available via API but not used in production UI