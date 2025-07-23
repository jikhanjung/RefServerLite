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
├── /scripts            # Utility scripts & development tools
│   ├── import_from_zotero.py  # Zotero import script
│   ├── config.yml.example     # Configuration template
│   ├── config.yml            # Active configuration
│   ├── setup_dev.sh          # Development environment setup
│   ├── run_server.sh         # Native server execution
│   ├── stop_server.sh        # Server shutdown
│   └── check_server.sh       # Server status check
├── /logs               # Server logs and debug output
├── /devlog             # Development logs and experiments
├── /migrations         # Database migration files
└── /tests              # Pytest test suite
```

## Key Components

### 1. Database Models (models.py)
- **Paper**: Main document model (doc_id, filename, file_path, ocr_text)
- **Metadata**: Bibliographic info (title, authors, journal, year, source)
- **ProcessingJob**: Tracks async processing status with detailed step tracking
- **PageText**: Stores extracted text for each page
- **SemanticChunk**: Stores semantic chunks with metadata and embedding IDs
- **User**: User authentication and admin access
- **ZoteroLink**: Links papers to Zotero items (zotero_key, library_id)
- **Note**: Embeddings stored in ChromaDB, not SQLite

### 2. API Endpoints (main.py)
- `POST /api/v1/upload` - Upload PDF for processing
- `POST /api/v1/papers/upload_with_metadata` - Upload PDF with Zotero metadata
- `GET /api/v1/job/{job_id}` - Check processing status
- `GET /api/v1/jobs` - List all processing jobs (admin)
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
- `jobs.html` - Background job monitoring dashboard
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

### Phase 5: Zotero Integration ✅
- [x] Zotero API integration with pyzotero
- [x] Interactive import script with batch processing
- [x] Configuration management system
- [x] Collection resolution and preview
- [x] Progress tracking and resume capability
- [x] Metadata upload endpoint
- [x] Database schema extensions

### Phase 6: Job Monitoring ✅
- [x] Background job monitoring dashboard
- [x] Real-time job status updates
- [x] Dedicated job monitoring page
- [x] Admin authentication for job APIs
- [x] Job filtering and pagination

### Phase 7: Performance Optimization ✅
- [x] Database concurrency improvements
- [x] SQLite WAL mode implementation
- [x] Bulk insert optimization
- [x] Retry mechanisms for database locks
- [x] Performance monitoring and metrics

### Phase 8: Development Environment & Bug Fixes ✅
- [x] Native development scripts (setup_dev.sh, run_server.sh, etc.)
- [x] Docker-free development environment (10-20x faster)
- [x] Document embedding display fixes
- [x] Zotero sync optimization with batch processing
- [x] ChromaDB NumPy array handling improvements
- [x] Collection item count accuracy fixes

### Phase 9: Testing & Deployment 🔄
- [x] Create Dockerfile
- [x] Set up docker-compose.yml
- [x] Database migrations
- [ ] Write comprehensive unit tests (pytest)
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
pyzotero (for Zotero integration)
PyYAML (for configuration)
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
- 2D heatmap visualizations for embedding fingerprints (64px size)
- 3D visualizations available via API but not used in production UI
- Zotero integration with batch processing and caching
- Database performance optimized with WAL mode and bulk operations
- Real-time job monitoring with dedicated admin dashboard
- Metadata source tracking (auto-extracted vs user-provided)
- Date parsing supports various formats (01/2004, 2004-01-15, etc.)

## Development Environment
- **Native Scripts**: Use `scripts/run_server.sh` for Docker-free development
- **Performance**: Native development is 10-20x faster than Docker builds
- **Requirements**: tesseract-ocr, build-essential, python3-dev
- **Data Sharing**: Both Docker and Native use `./refdata/` directory
- **Logs**: Stored in `./logs/server.log` for debugging

## Critical Patterns
- **ChromaDB Queries**: Always check `if result['embeddings'] is not None and len(result['embeddings']) > 0`
- **Template Data**: Convert NumPy arrays to lists with `.tolist()` before passing to Jinja2
- **Zotero API**: Add 2-second delays between requests to prevent rate limiting
- **Batch Processing**: Use 20-item batches with 1-second delays for UI responsiveness