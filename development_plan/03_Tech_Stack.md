
# RefServerLite: Tech Stack

This document outlines the technology stack for the RefServerLite project.

## 1. Backend

*   **Framework:** FastAPI
*   **Language:** Python 3.10+
*   **Asynchronous Server:** Uvicorn
*   **Database ORM:** Peewee
*   **Schema Management:** peewee-migrate

## 2. Database

*   **Metadata Store:** SQLite
*   **Vector Store:** ChromaDB

## 3. Frontend

*   **Templating Engine:** Jinja2
*   **CSS Framework:** Bootstrap 5
*   **JavaScript:** Vanilla JavaScript (no framework)

## 4. PDF Processing

*   **OCR:** Tesseract
*   **PDF Handling:** PyMuPDF
*   **Embeddings:** bge-m3 (via Sentence-Transformers)

## 5. Deployment

*   **Containerization:** Docker
*   **Orchestration:** Docker Compose

## 6. Testing

*   **Testing Framework:** Pytest
*   **HTTP Client:** HTTPX
