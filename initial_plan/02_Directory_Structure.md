
# RefServerLite: Directory Structure

This document outlines the planned directory structure for the RefServerLite project.

```
/RefServerLite
|-- /app
|   |-- /static
|   |   |-- /css
|   |   |   `-- style.css
|   |   `-- /js
|   |       `-- script.js
|   |-- /templates
|   |   |-- base.html
|   |   |-- index.html
|   |   `-- document.html
|   |-- __init__.py
|   |-- main.py             # FastAPI application, API endpoints
|   |-- pipeline.py         # PDF processing pipeline
|   |-- models.py           # Peewee database models
|   |-- ocr.py              # OCR processing logic
|   |-- metadata.py         # Metadata extraction logic
|   |-- embedding.py        # Embedding generation logic
|   `-- db.py               # Database interaction logic
|-- /data
|   |-- /pdfs
|   |   `-- (uploaded PDF files)
|   `-- refserver.db      # SQLite database
|-- /tests
|   |-- __init__.py
|   |-- test_api.py
|   `-- test_pipeline.py
|-- .gitignore
|-- Dockerfile
|-- docker-compose.yml
|-- README.md
`-- requirements.txt
```

## Directory Descriptions

*   **/app:** The main application directory.
    *   **/static:** Static files (CSS, JavaScript) for the web interface.
    *   **/templates:** HTML templates for the web interface.
    *   **main.py:** The main FastAPI application file, containing the API endpoints.
    *   **pipeline.py:** The PDF processing pipeline.
    *   **models.py:** The Peewee database models.
    *   **ocr.py:** OCR processing logic.
    *   **metadata.py:** Metadata extraction logic.
    *   **embedding.py:** Embedding generation logic.
    *   **db.py:** Database interaction logic.
*   **/data:** Data storage directory.
    *   **/pdfs:** Storage for the uploaded PDF files.
    *   **refserver.db:** The SQLite database file.
*   **/tests:** Unit and integration tests.
*   **.gitignore:** A list of files and directories to ignore in Git.
*   **Dockerfile:** A file for building the Docker image.
*   **docker-compose.yml:** A file for running the application with Docker Compose.
*   **README.md:** The main project README file.
*   **requirements.txt:** A list of the Python dependencies.
