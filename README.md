# RefServerLite

A streamlined, lightweight PDF repository service with OCR, metadata extraction, and semantic search capabilities.

## Features

- **PDF Upload & Processing**: Upload PDF files with automatic background processing
- **OCR**: Automatic text extraction using Tesseract OCR for scanned documents
- **Metadata Extraction**: Rule-based extraction of title, authors, journal, year, and DOI
- **Semantic Search**: Vector embeddings using BGE-M3 model with ChromaDB
- **Admin Dashboard**: Web interface for document management and search
- **RESTful API**: Complete API for integration with other services

## Tech Stack

- **Backend**: FastAPI with Uvicorn
- **Database**: SQLite (metadata) + ChromaDB (vector store)
- **Frontend**: Jinja2 templates with Bootstrap 5
- **OCR**: Tesseract
- **PDF Processing**: PyMuPDF
- **Embeddings**: Sentence Transformers (BGE-M3)

## Installation

### Prerequisites

- Python 3.10+
- Tesseract OCR installed on your system

#### Install Tesseract

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**macOS:**
```bash
brew install tesseract
```

**Windows:**
Download and install from [GitHub Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd RefServerLite
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create data directories:
```bash
mkdir -p refdata/pdfs
```

## Usage

### Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at `http://localhost:8000`

### API Endpoints

- `POST /api/v1/upload` - Upload PDF file
- `GET /api/v1/job/{job_id}` - Check processing status
- `GET /api/v1/document/{doc_id}` - Get document details
- `GET /api/v1/search` - Search documents (keyword/semantic)

### Web Interface

- `/` - Upload page
- `/admin` - Admin dashboard with document list and search
- `/admin/document/{doc_id}` - Document detail view

## Processing Pipeline

1. **Upload**: PDF file is uploaded and saved
2. **OCR**: Text extraction with automatic OCR detection
3. **Metadata**: Rule-based extraction of bibliographic information
4. **Embeddings**: Vector generation and storage in ChromaDB

## Docker Deployment

### Build and Run

```bash
docker-compose up --build
```

This will start the application on port 8000.

### Environment Variables

- `DEBUG`: Enable debug mode (default: False)
- `LOG_LEVEL`: Logging level (default: INFO)

## API Examples

### Upload a PDF

```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -F "file=@document.pdf"
```

### Check Job Status

```bash
curl "http://localhost:8000/api/v1/job/job-id-here"
```

### Search Documents

```bash
# Keyword search
curl "http://localhost:8000/api/v1/search?q=machine+learning&type=keyword"

# Semantic search
curl "http://localhost:8000/api/v1/search?q=neural+networks&type=semantic"
```

## Development

### Project Structure

```
RefServerLite/
├── app/
│   ├── main.py           # FastAPI application
│   ├── models.py         # Database models
│   ├── pipeline.py       # Processing pipeline
│   ├── ocr.py           # OCR processing
│   ├── metadata.py      # Metadata extraction
│   ├── embedding.py     # Embedding generation
│   ├── db.py            # Database connections
│   ├── static/          # CSS/JS files
│   └── templates/       # HTML templates
├── refdata/
│   ├── pdfs/            # Uploaded PDF files
│   ├── refserver.db     # SQLite database
│   └── chromadb/        # ChromaDB data
├── tests/               # Test files
└── requirements.txt
```

### Running Tests

```bash
pytest tests/
```

### Adding New Features

1. Update `CLAUDE.md` with implementation details
2. Add tests for new functionality
3. Update API documentation
4. Follow existing code patterns

## Troubleshooting

### Common Issues

1. **Tesseract not found**: Ensure Tesseract is installed and in PATH
2. **CUDA issues**: Set `CUDA_VISIBLE_DEVICES=""` to force CPU usage
3. **Memory issues**: Large PDFs may require more RAM for processing
4. **Port conflicts**: Change port in uvicorn command if 8000 is busy

### Logs

Check application logs for detailed error information:
```bash
tail -f logs/app.log
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

MIT License - see LICENSE file for details