
# RefServerLite: Project Overview

## 1. Introduction

RefServerLite is a streamlined, lightweight version of the original RefServer project. The goal is to create a simple, yet powerful, PDF repository service with a focus on core functionality and ease of use. This document outlines the project's architecture, features, and technical specifications.

## 2. Core Concepts

The system will allow users to upload PDF files, which will then be processed through a pipeline that includes:

*   **OCR (Optical Character Recognition):** To extract text from scanned documents.
*   **Metadata Extraction:** To identify key information like title, authors, and journal.
*   **Embedding Generation:** To create vector representations of the text for semantic search.

All processed data will be stored in a database and made available through a simple RESTful API and a web-based admin interface.

## 3. High-Level Architecture

The application will be built using a monolithic architecture, with a clear separation of concerns between the API, the processing pipeline, and the database.

```
+-----------------+      +------------------+      +-----------------+
|   Web Browser   | <--> |   FastAPI App    | <--> |   Database      |
+-----------------+      | (main.py)        |      | (SQLite)        |
                         +------------------+      +-----------------+
                               |
                               v
+--------------------------------------------------------------------+
|                        Processing Pipeline                         |
|                        (pipeline.py)                               |
|                                                                    |
|  +-------+     +-----------------+     +-----------+     +---------+  |
|  |  OCR  | --> | Metadata Extr.  | --> | Embedding | --> |  Save   |  |
|  +-------+     +-----------------+     +-----------+     +---------+  |
+--------------------------------------------------------------------+
```

## 4. Project Goals

*   **Simplicity:** Easy to understand, deploy, and maintain.
*   **Modularity:** Components should be loosely coupled and easy to replace or upgrade.
*   **Extensibility:** The system should be designed to allow for the addition of new features in the future.
*   **Focus on Core Functionality:** Prioritize the essential features of a PDF repository service.
