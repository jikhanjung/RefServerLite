
# RefServerLite: API Endpoints

This document outlines the planned API endpoints for the RefServerLite project.

## 1. Base URL

`/api/v1`

## 2. Endpoints

### 2.1. PDF Upload

*   **Endpoint:** `POST /upload`
*   **Description:** Upload a PDF file for processing.
*   **Request Body:** `multipart/form-data` with a `file` field containing the PDF file.
*   **Response:**
    ```json
    {
      "job_id": "<job_id>",
      "filename": "<filename>",
      "message": "File uploaded successfully. Processing started in background.",
      "status": "processing"
    }
    ```

### 2.2. Job Status

*   **Endpoint:** `GET /job/{job_id}`
*   **Description:** Get the status of a processing job.
*   **Response:**
    ```json
    {
      "job_id": "<job_id>",
      "filename": "<filename>",
      "status": "<status>",
      "current_step": "<current_step>",
      "progress_percentage": <progress_percentage>,
      "result": {
        "doc_id": "<doc_id>"
      }
    }
    ```

### 2.3. Document

*   **Endpoint:** `GET /document/{doc_id}`
*   **Description:** Get the processed data for a document.
*   **Response:**
    ```json
    {
      "doc_id": "<doc_id>",
      "filename": "<filename>",
      "metadata": {
        "title": "<title>",
        "authors": [
          "<author1>",
          "<author2>"
        ],
        "journal": "<journal>",
        "year": <year>
      },
      "text": "<extracted_text>"
    }
    ```

### 2.4. Search

*   **Endpoint:** `GET /search`
*   **Description:** Search for documents.
*   **Query Parameters:**
    *   `q`: The search query.
    *   `type`: The search type (`keyword` or `semantic`).
*   **Response:**
    ```json
    {
      "query": "<query>",
      "results": [
        {
          "doc_id": "<doc_id>",
          "filename": "<filename>",
          "metadata": {
            "title": "<title>",
            "authors": [
              "<author1>",
              "<author2>"
            ],
            "journal": "<journal>",
            "year": <year>
          },
          "score": <score>
        }
      ]
    }
    ```
