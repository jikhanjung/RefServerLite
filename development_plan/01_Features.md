
# RefServerLite: Features

This document outlines the features that will be included in the initial version of RefServerLite.

## 1. Core Features

*   **PDF Upload:**
    *   A simple web form to upload one or more PDF files.
    *   Basic validation of file type (must be a PDF).
*   **Asynchronous Processing:**
    *   PDFs will be processed in the background to avoid blocking the user interface.
    *   A job queue will be used to manage the processing of multiple files.
*   **OCR (Optical Character Recognition):**
    *   Automatic detection of whether a PDF needs OCR.
    *   Use of Tesseract for OCR.
*   **Metadata Extraction:**
    *   Extraction of basic metadata (title, authors, journal, year) using rule-based methods.
*   **Embedding Generation:**
    *   Generation of vector embeddings for the full text of the PDF.
    *   Use of a lightweight, sentence-transformer-based model.
*   **Database Storage:**
    *   Storage of all processed data in a SQLite database.

## 2. Administrative Features

*   **Admin Dashboard:**
    *   A simple web interface to view and manage processed documents.
    *   A list of all processed documents with their metadata.
    *   A detail view for each document, showing the extracted text, metadata, and other information.
*   **Search:**
    *   Basic keyword search of the extracted text.
    *   Semantic search based on the generated embeddings.

## 3. API Features

*   **RESTful API:**
    *   A simple, well-documented RESTful API for interacting with the system.
    *   Endpoints for uploading files, checking the status of processing jobs, and retrieving processed data.

## 4. Future Features (Out of Scope for Initial Version)

*   **User Accounts:**
    *   User registration and authentication.
    *   Role-based access control.
*   **Advanced Search:**
    *   Faceted search.
    *   Filtering by metadata fields.
*   **Integration with External Services:**
    *   Integration with Zotero, Mendeley, and other reference managers.
