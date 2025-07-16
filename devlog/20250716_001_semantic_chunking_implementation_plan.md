# Semantic Chunking Implementation Plan

**Objective:** To introduce a semantic chunking pipeline alongside the existing page-level embedding process. This will enable more granular and accurate search results without disrupting the current functionality.

---

## Phase 1: Create the Chunking Module

A new, dedicated module for chunking logic will be created to ensure separation of concerns.

- **Action:** Create a new file `app/chunking.py`.
- **Contents:**
    - **`_extract_text_from_page(page)`:** An internal function that intelligently extracts text. It first attempts to get text directly from the PDF's text layer. If the text is absent or minimal (indicating a scanned page), it will trigger the OCR process for that page.
    - **`create_semantic_chunks(pdf_path: str, chunk_size: int, chunk_overlap: int)`:** The main function of the module. It will:
        1.  Iterate through each page of the PDF specified by `pdf_path`.
        2.  Use `_extract_text_from_page` to get the text for each page.
        3.  Apply a **Recursive Character Text Splitting** algorithm to the extracted text to break it down into smaller, semantically coherent chunks based on the provided `chunk_size` and `chunk_overlap`.
        4.  Return a list of structured dictionaries, with each dictionary representing a chunk and its metadata.

- **Example Chunk Structure:**
```python
{
    "text": "This is the content of the first chunk...",
    "page_number": 1,
    "chunk_index_on_page": 0 
}
```

---

## Phase 2: Update Database Schema

A new table is required to store the metadata for the semantic chunks.

- **Action:** Modify `app/models.py` to include a new `SemanticChunk` model.
- **Model Definition:**
```python
class SemanticChunk(BaseModel):
    document = peewee.ForeignKeyField(Document, backref='semantic_chunks', on_delete='CASCADE')
    text = peewee.TextField()
    page_number = peewee.IntegerField()
    embedding_id = peewee.CharField(unique=True) # Stores the corresponding ID from ChromaDB

    class Meta:
        table_name = 'semantic_chunk'
```

---

## Phase 3: Implement Embedding and Storage Logic

Functions to handle the embedding of the new chunks and storing their metadata need to be created.

- **Action 1:** Modify `app/embedding.py`.
    - **New Function:** `embed_and_store_chunks(document_id: int, chunks_with_metadata: list)`.
    - **Logic:** This function will loop through the list of chunks, perform embedding for each, store the vector in ChromaDB with appropriate metadata (`document_id`, `page_number`, `chunk_type: 'semantic'`), and then call a database function to persist the chunk's metadata in the new SQLite table.

- **Action 2:** Modify `app/db.py`.
    - **New Function:** `create_semantic_chunk(...)`.
    - **Logic:** This function will take the chunk's data and the `embedding_id` from ChromaDB and create a new record in the `semantic_chunk` table.

---

## Phase 4: Integrate into the Main Processing Pipeline

The new semantic chunking process will be added as a new step in the main document processing pipeline.

- **Action:** Modify the `run_processing_pipeline` function in `app/pipeline.py`.
- **Logic:**
    1.  The existing page-level embedding process will run first, as is.
    2.  Following the successful completion of the existing steps, a new `try...except` block will be added to execute the semantic chunking flow.
    3.  This new block will call `app.chunking.create_semantic_chunks()` to generate the chunks.
    4.  It will then pass the results to `app.embedding.embed_and_store_chunks()` to complete the process.
    5.  Errors in this new step will be logged but will not interrupt the success of the primary page-level processing.

---

## Phase 5: Database Migration

The database schema must be updated to reflect the new `SemanticChunk` model.

- **Action (User-driven):**
    1.  The user will run `python migrate.py` in the shell to generate the necessary migration script in the `migrations/` directory.
    2.  The application will automatically apply this migration upon the next startup (e.g., via `docker-compose up`).

---

## Phase 0: Text Extraction Enhancement (Prerequisites)

**Critical Issue Identified:** The current text extraction method in `app/ocr.py` does not preserve document structure, which will significantly impact the quality of semantic chunking.

### Current Problem

The existing `clean_extracted_text()` function removes paragraph boundaries:

```python
# Current approach destroys paragraph structure
text = page.get_text()  # Basic extraction without layout preservation
cleaned_text = clean_extracted_text(text)  # Removes all line breaks and paragraph boundaries
```

This results in text like: `"word1 word2 word3 word4..."` without natural paragraph breaks.

### Solution: Structure-Preserving Text Extraction

- **Action:** Enhance `app/ocr.py` with a new function `extract_text_with_structure()`.
- **Implementation:**

```python
def extract_text_with_structure(pdf_path: str, use_ocr: bool = False) -> Tuple[List[Dict], bool]:
    """
    Enhanced text extraction that preserves document structure
    Returns: (list_of_page_structures, ocr_was_used)
    """
    try:
        doc = fitz.open(pdf_path)
        page_structures = []
        ocr_used = False
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            if use_ocr:
                # OCR processing (existing logic)
                # Note: OCR doesn't preserve structure, fallback to flat text
                ocr_text = perform_ocr_on_page(page)
                page_structures.append({
                    'page_num': page_num,
                    'text': ocr_text,
                    'structure': 'flat',
                    'blocks': []
                })
            else:
                # Extract with structure preservation using PyMuPDF's dict mode
                page_dict = page.get_text("dict", sort=True)
                
                # Process blocks to create structured text
                structured_blocks = []
                for block in page_dict["blocks"]:
                    if block["type"] == 0:  # Text block (paragraph)
                        block_text = ""
                        for line in block["lines"]:
                            line_text = ""
                            for span in line["spans"]:
                                line_text += span["text"]
                            block_text += line_text + "\n"
                        
                        structured_blocks.append({
                            'bbox': block["bbox"],
                            'text': block_text.strip(),
                            'type': 'paragraph'
                        })
                
                # Combine blocks with double newlines to preserve paragraph boundaries
                full_page_text = "\n\n".join([block['text'] for block in structured_blocks])
                
                page_structures.append({
                    'page_num': page_num,
                    'text': full_page_text,
                    'structure': 'preserved',
                    'blocks': structured_blocks
                })
        
        doc.close()
        return page_structures, ocr_used
        
    except Exception as e:
        logger.error(f"Error extracting structured text from {pdf_path}: {str(e)}")
        raise
```

### Enhanced Chunking Strategy

- **Action:** Modify the chunking approach in Phase 1 to be structure-aware.
- **Implementation:**

```python
def create_structure_aware_chunks(page_text: str, blocks: List[Dict], 
                                chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """
    Create chunks that respect document structure (paragraphs, sentences)
    """
    chunks = []
    
    # Strategy 1: Use paragraph boundaries as primary chunk boundaries
    for block in blocks:
        paragraph_text = block['text']
        
        # Strategy 2: If paragraph is too large, split by sentences
        if len(paragraph_text) > chunk_size:
            sentences = split_by_sentences(paragraph_text)
            sentence_chunks = group_sentences_into_chunks(sentences, chunk_size, chunk_overlap)
            chunks.extend(sentence_chunks)
        else:
            chunks.append(paragraph_text)
    
    # Strategy 3: Fallback to character-based splitting for edge cases
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > chunk_size * 1.5:  # Still too large
            # Use RecursiveCharacterTextSplitter as fallback
            splitter_chunks = recursive_character_split(chunk, chunk_size, chunk_overlap)
            final_chunks.extend(splitter_chunks)
        else:
            final_chunks.append(chunk)
    
    return final_chunks

def split_by_sentences(text: str) -> List[str]:
    """Split text into sentences using simple heuristics"""
    import re
    # Simple sentence splitting (can be enhanced with spaCy or NLTK)
    sentences = re.split(r'[.!?]+\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def group_sentences_into_chunks(sentences: List[str], max_size: int, overlap: int) -> List[str]:
    """Group sentences into chunks respecting size limits"""
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk + " " + sentence) <= max_size:
            current_chunk += " " + sentence if current_chunk else sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks
```

### Updated Phase 1 Requirements

- **Modify Phase 1:** Update `_extract_text_from_page()` to use the new structure-preserving extraction.
- **Enhanced Chunk Structure:**

```python
{
    "text": "This is a complete paragraph or semantic unit...",
    "page_number": 1,
    "chunk_index_on_page": 0,
    "chunk_type": "paragraph",  # or "sentence_group", "fallback_split"
    "start_char": 0,           # Position within page text
    "end_char": 500,           # End position within page text
    "bbox": [x0, y0, x1, y1]   # Optional: bounding box if available
}
```

### Benefits of This Approach

1. **Natural Boundaries:** Chunks respect paragraph and sentence boundaries
2. **Better Semantic Coherence:** Related content stays together
3. **Improved Search Quality:** More meaningful chunk-level search results
4. **Fallback Compatibility:** Still works with OCR'd documents (flat text)
5. **Metadata Extraction Enhancement:** Better title, author, and abstract detection

### Model Corrections

- **Phase 2 Correction:** Update the model reference to use the correct model name:

```python
class SemanticChunk(BaseModel):
    paper = peewee.ForeignKeyField(Paper, backref='semantic_chunks', on_delete='CASCADE')  # Changed from 'document' to 'paper'
    text = peewee.TextField()
    page_number = peewee.IntegerField()
    chunk_index_on_page = peewee.IntegerField()
    chunk_type = peewee.CharField(default='paragraph')  # 'paragraph', 'sentence_group', 'fallback_split'
    start_char = peewee.IntegerField(null=True)  # Position within page text
    end_char = peewee.IntegerField(null=True)    # End position within page text
    embedding_id = peewee.CharField(unique=True) # Stores the corresponding ID from ChromaDB
    created_at = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = 'semantic_chunk'
        indexes = (
            (('paper', 'page_number', 'chunk_index_on_page'), True),  # Ensure unique chunk per page
        )
```
