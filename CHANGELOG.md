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