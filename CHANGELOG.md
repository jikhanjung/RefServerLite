# Changelog

All notable changes to RefServerLite will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive unit test suite
- Performance optimization for large documents
- Production deployment guide
- Interactive 3D visualization with Plotly

### Changed
- Enhanced error handling and logging
- Improved UI/UX based on user feedback

## [0.1.4] - 2025-01-17

### Added
- **Zotero Integration System**: Complete integration with Zotero libraries
  - `scripts/import_from_zotero.py` - Interactive import script with batch processing
  - `POST /api/v1/papers/upload_with_metadata` - Upload PDF with Zotero metadata
  - `ZoteroLink` model for tracking paper-Zotero relationships
  - Configuration management with `config.yml` template
  - Collection resolution by name or ID
  - Progress tracking and resume capability
  - Comprehensive error handling and retry logic
  - Dry-run mode for preview before import

- **Background Job Monitoring Dashboard**: Real-time job monitoring system
  - `GET /api/v1/jobs` - List all processing jobs with filtering
  - `/admin/jobs` - Dedicated job monitoring page
  - Real-time updates with 5-second auto-refresh
  - Status filtering (All, Pending, Processing, Completed, Failed)
  - Progress bars with animations for active jobs
  - Error message display and document links
  - Pagination support for large job lists

- **Database Performance Optimization**: Resolved "database is locked" errors
  - SQLite WAL mode for improved concurrency
  - Bulk insert patterns for semantic chunks
  - Database configuration optimizations
  - Exponential backoff retry mechanisms
  - Performance improvement: 99% reduction in lock times (5-10s → 50-100ms)

- **Enhanced Metadata System**: 
  - `source` field in Metadata model (auto-extracted vs user-provided)
  - User-provided metadata prioritization in processing pipeline
  - Zotero metadata display in document detail view
  - Direct links to original Zotero items

### Changed
- **Admin Interface**: Separated job monitoring into dedicated page
- **Processing Pipeline**: Respects user-provided metadata from Zotero
- **Database Schema**: Added ZoteroLink model and metadata source tracking
- **Navigation**: Added Jobs link to navigation bar
- **Error Handling**: Improved database concurrency and retry logic

### Fixed
- **Database Concurrency**: "database is locked" errors during bulk operations
- **Semantic Chunking**: Bulk insert optimization for better performance
- **Authentication**: Fixed 401 errors in job monitoring API
- **Year Extraction**: Enhanced date parsing for various formats (01/2004, 2004-01-15)

### Technical Details
- **Dependencies Added**: `pyzotero==1.5.18`, `PyYAML==6.0.1`
- **Database Migrations**: 
  - `004_20250117_100757.py` - ZoteroLink model and metadata source field
  - `005_20250117_141855.py` - ProcessingJob updated_at field
- **Performance**: Database lock time reduced from 5-10 seconds to 50-100ms
- **Import Success Rate**: Improved from 12.5% to expected 90%+

### Security Enhancements
- Admin authentication for job monitoring APIs
- Bearer token authentication for metadata upload endpoint
- Secure credential handling in Zotero integration

### Development Infrastructure
- Comprehensive development logs in `/devlog/20250117_*`
- Zotero import script with interactive configuration
- Cache management for PDF downloads
- Progress tracking and error reporting

## [0.1.3] - 2025-07-16

### Added
- **Semantic Chunking System**: Hierarchical text segmentation for improved RAG performance
  - `chunking.py` module with paragraph-aware splitting
  - Structure-preserving text extraction from PDFs
  - Configurable chunk size (default: 500 characters)
  - Multiple chunk types: paragraph, sentence_group, fallback_split
  - Quality validation for generated chunks

- **Enhanced Database Models**:
  - `SemanticChunk` model with metadata and embedding references
  - `PageText` model for storing page-level text
  - Extended `ProcessingJob` with detailed step tracking
  - Chunking status fields and methods

- **Chunking Management APIs**:
  - `GET /api/v1/document/{doc_id}/chunks` - Retrieve semantic chunks
  - `POST /api/v1/admin/apply-chunking/{doc_id}` - Apply chunking to document
  - `POST /api/v1/admin/apply-chunking-all` - Apply chunking to all documents
  - `GET /api/v1/admin/chunking-status` - Check chunking status

- **Enhanced Search Capabilities**:
  - Chunk-level semantic search with `search_scope` parameter
  - Support for pages, chunks, documents, and all-levels search
  - Improved search result processing and ranking

- **Tabbed Document Interface**:
  - Pages tab: Original page preview and text view
  - Semantic Chunks tab: Interactive chunk browser
  - Page filtering and real-time status updates
  - Chunk statistics and type distribution

- **Embedding Visualizations**:
  - 2D heatmap fingerprints for documents, pages, and chunks
  - 3D visualization system with matplotlib
  - Bidirectional and unidirectional 3D bar charts
  - 3D surface plots for embedding analysis
  - Minimal mode for compact visualizations

- **Authentication System**:
  - User model with password hashing (bcrypt)
  - Admin-only access controls
  - Session-based authentication
  - Login/logout functionality

- **Development Infrastructure**:
  - Database migration system with peewee-migrate
  - Comprehensive development logs in `/devlog`
  - 3D visualization experiment documentation
  - Enhanced project documentation

### Changed
- **Processing Pipeline**: Added semantic chunking as optional 4th step
- **OCR Module**: Enhanced with structure-preserving text extraction
- **Database Schema**: Extended with new models and fields
- **Admin Interface**: Redesigned with chunking controls and status indicators
- **Search API**: Extended with chunk-level search capabilities
- **Document Detail View**: Upgraded to tabbed interface with chunk browser

### Fixed
- **Database Constraints**: Resolved UNIQUE constraint errors in PageText
- **Text Extraction**: Fixed paragraph boundary preservation for chunking
- **Background Processing**: Improved error handling and status tracking
- **UI Responsiveness**: Enhanced loading states and error messages

### Technical Details
- **Chunking Strategy**: Hierarchical approach (paragraph → sentence → character)
- **Embedding Storage**: ChromaDB for vectors, SQLite for metadata
- **Chunk Size**: 500 characters (optimal for RAG applications)
- **Visualization**: 32x32 grid representation of 1024-dimensional embeddings
- **Authentication**: Passlib with bcrypt for secure password hashing

### Experimental Features
- **3D Visualizations**: Available via API for research purposes
- **Interactive Chunk Analysis**: Advanced chunk quality metrics
- **Batch Processing**: Concurrent chunking for multiple documents

### Performance Improvements
- **Non-blocking Chunking**: Semantic chunking runs as optional background step
- **Efficient Embedding**: Batch processing of chunk embeddings
- **Caching**: 1-hour cache for visualization endpoints
- **Database Optimization**: Proper indexing for chunk queries

## [0.1.2] - 2025-07-15

### Added
- **Enhanced Processing Pipeline**: Multi-step processing with detailed status tracking
- **Page-level Embeddings**: Individual page embedding generation and storage
- **Embedding Visualizations**: 2D heatmap and histogram visualizations
- **Admin Dashboard**: Comprehensive document management interface
- **Advanced Search**: Semantic search with ChromaDB integration
- **Background Processing**: Async job queue with real-time status updates

### Changed
- **Database Schema**: Extended models with detailed processing status
- **API Structure**: Reorganized endpoints with better error handling
- **Frontend**: Bootstrap-based responsive design
- **Processing Logic**: Improved OCR detection and metadata extraction

### Fixed
- **Memory Usage**: Optimized embedding generation for large documents
- **Error Handling**: Better error recovery and user feedback
- **Performance**: Improved search response times

## [0.1.0] - 2025-07-14

### Added
- **Initial Release**: Basic PDF repository functionality
- **PDF Upload**: File upload with automatic processing
- **OCR Processing**: Tesseract-based text extraction
- **Metadata Extraction**: Rule-based bibliographic information extraction
- **Basic Search**: Keyword search capabilities
- **Web Interface**: Simple upload and document listing
- **Docker Support**: Containerized deployment with docker-compose

### Technical Stack
- **Backend**: FastAPI with Uvicorn
- **Database**: SQLite with Peewee ORM
- **Vector Store**: ChromaDB for embeddings
- **Frontend**: Jinja2 templates with Bootstrap
- **Processing**: PyMuPDF for PDF handling
- **Embeddings**: BGE-M3 model with sentence-transformers

---

## Development Notes

### 3D Visualization Experiment Results
*Date: 2025-07-16*

**Key Finding**: Static 3D visualizations provide limited advantage over 2D heatmaps for embedding fingerprints. Benefits of 3D visualization are only realized with interactive manipulation (rotation, zoom).

**Decision**: Reverted to 2D heatmaps for production UI while maintaining 3D API endpoints for research purposes.

### Semantic Chunking Implementation
*Date: 2025-07-16*

**Strategy**: Hierarchical chunking with document structure preservation
- **Chunk Size**: 500 characters (optimal for RAG applications)
- **Overlap**: 50 characters between chunks
- **Quality Validation**: Minimum length and content requirements
- **Non-blocking**: Optional step that doesn't fail main pipeline

**Result**: Successful implementation with comprehensive UI integration and management tools.

### Database Migration Strategy
*Date: 2025-07-16*

**Approach**: Peewee-migrate for schema evolution
- **New Models**: SemanticChunk, enhanced ProcessingJob
- **Backward Compatibility**: Graceful handling of existing data
- **Migration Files**: Versioned schema changes in `/migrations`

---

## Future Roadmap

### Version 0.1.4 (Planned)
- **Interactive 3D Visualizations**: Plotly-based interactive embedding analysis
- **Advanced Analytics**: Document similarity analysis and clustering
- **API Enhancements**: GraphQL support and rate limiting
- **Performance Optimization**: Caching and concurrent processing improvements

### Version 0.1.5 (Planned)
- **Multi-user Support**: User management and document permissions
- **Advanced Search**: Faceted search and filters
- **Document Comparison**: Side-by-side document analysis
- **Export Features**: PDF annotations and search result exports

### Version 0.2.0 (Planned)
- **Production Ready**: Comprehensive testing and security audit
- **Scalability**: Support for large document collections
- **Enterprise Features**: SSO integration and advanced admin controls
- **Documentation**: Complete API documentation and user guides