
# Plan: Implementing an Advanced, Structure-Aware Chunking Strategy

**Objective:** To significantly enhance search accuracy by implementing a sophisticated, structure-aware semantic chunking pipeline. This will supplement the existing page-level embedding process, providing a more granular and contextually relevant search capability.

---

### Phase 0: Prerequisite - Structure-Preserving Text Extraction

**Problem:** The current text extraction method (`page.get_text()` followed by cleaning) discards critical document structure like paragraphs, leading to semantically incoherent chunks.

**Action:** Create a new, robust text extraction function that understands document layout.

1.  **Module:** This logic could be placed in a new `app/text_extraction.py` module or enhance the existing `app/ocr.py`.
2.  **Function:** `extract_structured_text(pdf_path: str) -> List[Dict]`
3.  **Implementation Details:**
    - Use `page.get_text("dict", sort=True)` to extract text blocks with layout metadata (bounding boxes, font info).
    - Process the blocks to identify and group paragraphs. A simple heuristic is to merge text blocks that are vertically close and treat larger vertical gaps as paragraph breaks.
    - For each page, return a list of structured blocks (e.g., `{'bbox': ..., 'text': ..., 'type': 'paragraph'}`).
    - **OCR Fallback:** If a page yields minimal text, trigger the existing OCR function. The OCR output will be treated as a single, unstructured block of text, ensuring compatibility.

---

### Phase 1: Implement Hierarchical Chunking Module

**Action:** Create a new `app/chunking.py` module to house the chunking logic.

1.  **Primary Function:** `create_semantic_chunks(page_structures: List[Dict], config: Dict) -> List[Dict]`
2.  **Configuration:** The `config` dictionary should contain parameters like `chunk_size`, `chunk_overlap`, etc., to avoid hardcoding.
3.  **Hierarchical Chunking Strategy:**
    -   **Strategy 1 (Paragraph-Level):** Iterate through the structured blocks from Phase 0. If a paragraph block is within the `chunk_size`, treat it as a single, perfect chunk.
    -   **Strategy 2 (Sentence-Level):** If a paragraph block exceeds `chunk_size`, split it into sentences. Group these sentences into chunks that respect the `chunk_size` limit. *Note: Use a simple regex-based sentence splitter for now, with a plan to potentially upgrade to NLTK or spaCy later for improved accuracy.*
    -   **Strategy 3 (Recursive Character Fallback):** For any remaining oversized chunks (e.g., a single long sentence) or for unstructured text from OCR, use a `RecursiveCharacterTextSplitter` as a final fallback.
4.  **Output:** The function will return a list of chunks, each with rich metadata.

- **Enhanced Chunk Metadata Structure:**
```python
{
    "text": "A semantically coherent chunk of text...",
    "page_number": 1,
    "chunk_type": "paragraph",  # or "sentence_group", "fallback_split"
    "bbox": [x0, y0, x1, y1]   # Bounding box of the chunk
}
```

---

### Phase 2: Update Database Schema

**Action:** Modify `app/models.py` to add a `SemanticChunk` table for storing chunk metadata.

- **Model Definition (`SemanticChunk`):**
```python
# In app/models.py
import datetime
import peewee

class SemanticChunk(BaseModel):
    # Sticking to 'Document' for consistency with existing models.
    paper = peewee.ForeignKeyField(Paper, backref='semantic_chunks', on_delete='CASCADE')
    text = peewee.TextField()
    page_number = peewee.IntegerField()
    chunk_type = peewee.CharField(default='paragraph') # Type of chunking strategy used
    embedding_id = peewee.CharField(unique=True) # ID from ChromaDB vector store
    created_at = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = 'semantic_chunk'
        # Ensures we don't store duplicate chunks for the same document
        indexes = (
            (('document', 'page_number', 'embedding_id'), True),
        )
```

---

### Phase 3: Implement Embedding and Storage Logic

**Action:** Update `app/embedding.py` and `app/db.py` to handle the new chunk type.

1.  **`app/embedding.py`:**
    -   Create `embed_and_store_semantic_chunks(document_id: int, chunks: List[Dict])`.
    -   This function will iterate through the chunks, generate a unique ID for each, create the vector embedding, and store it in ChromaDB with metadata (`document_id`, `page_number`, `chunk_type`).
2.  **`app/db.py`:**
    -   Create `create_semantic_chunk(...)` to save the chunk's text and metadata, including the ChromaDB embedding ID, into the new `semantic_chunk` table in SQLite.

---

### Phase 4: Integrate into Main Processing Pipeline

**Action:** Modify `app/pipeline.py` to incorporate the new workflow as a non-blocking step.

1.  **Modify `run_processing_pipeline`:**
    -   The existing page-level embedding process should complete as normal.
    -   Afterward, add a `try...except` block for the semantic chunking process.
    -   Inside the block, chain the new functions: `extract_structured_text()` -> `create_semantic_chunks()` -> `embed_and_store_semantic_chunks()`.
2.  **Logging:** Add detailed logs to record the number and type of chunks generated for each document. This is crucial for monitoring and debugging.
3.  **Resilience:** Failures in the semantic chunking step should be logged as errors but **must not** cause the entire document processing to fail.

---

### Phase 5: Database Migration

**Action:** The user will perform the database migration as per the established project workflow.

1.  **Generate Migration:** The user runs `python migrate.py` to create the new migration script in the `migrations/` directory.
2.  **Apply Migration:** The application automatically applies the migration on the next startup (`docker-compose up`).
