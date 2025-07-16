
# RefServerLite: Database Schema

This document outlines the planned database schema for the **SQLite metadata store**, using Peewee as the ORM. Vector embeddings will be stored and managed in **ChromaDB**.

## 1. SQLite Models

### 1.1. `Paper`

This is the main model for storing information about the PDF files.

```python
from peewee import *
import datetime

class Paper(BaseModel):
    doc_id = CharField(primary_key=True) # This ID will be used as the primary key in ChromaDB as well.
    filename = CharField()
    file_path = CharField()
    ocr_text = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
```

### 1.2. `Metadata`

This model stores the bibliographic metadata for each paper.

```python
class Metadata(BaseModel):
    paper = ForeignKeyField(Paper, backref='metadata', unique=True)
    title = CharField(null=True)
    authors = TextField(null=True)  # Stored as a JSON string
    journal = CharField(null=True)
    year = IntegerField(null=True)
```

### 1.3. `ProcessingJob`

This model tracks the status of each processing job.

```python
class ProcessingJob(BaseModel):
    job_id = CharField(primary_key=True)
    paper = ForeignKeyField(Paper, backref='jobs', null=True)
    filename = CharField()
    status = CharField(default='uploaded')
    current_step = CharField(null=True)
    progress_percentage = IntegerField(default=0)
    error_message = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
```

## 2. ChromaDB Collection

A single ChromaDB collection will be used to store the embeddings.

*   **Collection Name:** `papers`
*   **Document ID:** The `doc_id` from the `Paper` table.
*   **Embedding Vector:** The `bge-m3` embedding.
*   **Metadata:** A copy of the metadata (title, authors, year, etc.) will be stored with the embedding in ChromaDB to allow for efficient filtering during similarity searches.

## 3. Relationships

*   A `Paper` record in SQLite corresponds to one document in ChromaDB, linked by `doc_id`.
*   A `Paper` can have one `Metadata` record.
*   A `Paper` can have multiple `ProcessingJob` records (although typically only one).
