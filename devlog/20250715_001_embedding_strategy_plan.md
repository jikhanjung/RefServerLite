# New Embedding Strategy: Page-level and Document-level Embeddings

## Introduction

This plan outlines a new embedding strategy for RefServerLite to enhance search granularity and accuracy. Currently, the system generates a single embedding for an entire document. The proposed change involves generating embeddings for each page of a PDF document, and then deriving a document-level embedding by averaging these page-level embeddings. This approach allows for more precise search results (pointing to specific pages) while retaining the ability to search across entire documents.

## Goals

1.  **Page-level Embeddings:** Generate a unique embedding vector for each page of a PDF document.
2.  **Document-level Embedding:** Create a single, comprehensive embedding for the entire document by averaging its page-level embeddings.
3.  **ChromaDB Storage:** Store both page-level and document-level embeddings in ChromaDB, with appropriate metadata to distinguish them (e.g., `page_number`, `is_document_level`).
4.  **Enhanced Search:** Update the search functionality to leverage page-level embeddings for more precise semantic search results, indicating the relevant page number.
5.  **Maintain Document Context:** Ensure that document-level search capabilities are preserved or improved.

## High-Level Plan

The implementation will proceed in the following phases:

1.  **Phase 1: Prepare OCR Output for Page-level Processing**
2.  **Phase 2: Update Embedding Generation Logic**
3.  **Phase 3: Adapt Processing Pipeline**
4.  **Phase 4: Modify Database Interaction (ChromaDB)**
5.  **Phase 5: Update API Endpoints and Search Logic**
6.  **Phase 6: Testing and Verification**

## Detailed Steps

### Phase 1: Prepare OCR Output for Page-level Processing

**Objective:** Modify the OCR module to return text content on a per-page basis.

**Files to Modify:** `app/ocr.py`

**Specific Changes:**

*   **`extract_text_from_pdf(pdf_path: str, use_ocr: bool = False) -> Tuple[List[str], bool]`**:
    *   Change the return type of this function from `Tuple[str, bool]` to `Tuple[List[str], bool]`.
    *   Instead of concatenating all page texts into a single string, collect each page's extracted text into a list.
    *   Ensure `clean_extracted_text` is applied to each page's text individually before returning the list.
*   **`process_pdf_ocr(pdf_path: str) -> Tuple[List[str], bool]`**:
    *   Update this function to call the modified `extract_text_from_pdf` and return the list of page texts.

### Phase 2: Update Embedding Generation Logic

**Objective:** Modify the embedding generator to handle a list of page texts and produce both page-level and document-level embeddings.

**Files to Modify:** `app/embedding.py`

**Specific Changes:**

*   **`generate_document_embedding(self, text: str, strategy: str = "mean") -> np.ndarray`**:
    *   Rename this function to something more generic, e.g., `generate_embeddings_for_pages_and_document`.
    *   Change its signature to accept a `List[str]` (representing page texts) instead of a single `str`.
    *   **For each page text in the input list:**
        *   Call `self.generate_embedding(page_text)` to get the page-level embedding.
        *   Store these page-level embeddings along with their original page index.
    *   **Calculate Document Embedding:**
        *   Take all generated page-level embeddings.
        *   Compute their mean (average) to get the single document-level embedding.
        *   Ensure this final document embedding is also normalized.
    *   **Return Value:** The function should return a tuple containing:
        *   A list of `(page_number, page_embedding)` tuples.
        *   The `document_level_embedding`.
        *   The `model_name` used.
*   **`generate_embedding_for_document(text: str) -> Tuple[np.ndarray, str]`**:
    *   This helper function will need to be updated to call the new `generate_embeddings_for_pages_and_document` and handle its new return type. It might be better to remove this helper and directly call the new function from the pipeline.

### Phase 3: Adapt Processing Pipeline

**Objective:** Integrate the new page-level OCR output and embedding generation into the document processing pipeline.

**Files to Modify:** `app/pipeline.py`

**Specific Changes:**

*   **`_process_ocr(self, job: ProcessingJob, paper: Paper)`**:
    *   Call the modified `process_pdf_ocr` to get `texts_per_page`.
    *   Instead of saving `paper.ocr_text` as a single string, consider:
        *   Saving the full concatenated text for backward compatibility or keyword search.
        *   Or, if `paper.ocr_text` is no longer needed as a single field, remove it or adapt its usage.
    *   **Crucially**, store `texts_per_page` temporarily (e.g., as a new attribute on the `job` object, or pass it directly) so it can be accessed by `_generate_embeddings`. (Note: Adding a new field to `ProcessingJob` model might be necessary if not passing directly).
*   **`_generate_embeddings(self, job: ProcessingJob, paper: Paper)`**:
    *   Retrieve the `texts_per_page` from the previous step.
    *   Call the modified embedding generator function (from `app/embedding.py`) with `texts_per_page`.
    *   **Loop through the returned `(page_number, page_embedding)` tuples:**
        *   For each, call `add_document_to_collection` (from `app/db.py`).
        *   Use a unique `doc_id` for each page (e.g., `f"{paper.doc_id}_page_{page_number}"`).
        *   Include `page_number` and `original_doc_id: paper.doc_id` in the `metadata`.
        *   Store the page's text (e.g., first 1000 chars) as the `document` in ChromaDB.
    *   **Add Document-level Embedding:**
        *   Call `add_document_to_collection` again for the `document_level_embedding`.
        *   Use the original `paper.doc_id` as the `doc_id`.
        *   Include `is_document_level: true` in the `metadata`.
        *   Store the full document text (or a summary) as the `document` in ChromaDB.

### Phase 4: Modify Database Interaction (ChromaDB)

**Objective:** Ensure ChromaDB interactions correctly handle and store the new page-level and document-level embeddings with appropriate metadata.

**Files to Modify:** `app/db.py`

**Specific Changes:**

*   **`add_document_to_collection(collection, doc_id: str, text: str, embedding=None, metadata=None)`**:
    *   No direct changes needed to the function signature, but ensure the `metadata` dictionary passed from `pipeline.py` correctly contains `page_number`, `original_doc_id`, and `is_document_level` flags as needed.
    *   The `doc_id` parameter will now be used for both `paper.doc_id` (for document-level) and `f"{paper.doc_id}_page_{page_number}"` (for page-level).

### Phase 5: Update API Endpoints and Search Logic

**Objective:** Adapt the search API to leverage page-level embeddings for more precise results.

**Files to Modify:** `app/main.py`

**Specific Changes:**

*   **`search_documents(q: str, type: Optional[str] = "keyword", limit: Optional[int] = 10)`**:
    *   **Semantic Search (`type == "semantic"`):**
        *   When querying ChromaDB, filter results to primarily search against **page-level embeddings**. This can be done by adding a `where` clause to the ChromaDB query (e.g., `where={"is_document_level": False}`).
        *   The returned `doc_ids` from ChromaDB will now be in the format `f"{original_doc_id}_page_{page_number}"`. Parse these to extract the `original_doc_id` and `page_number`.
        *   The search results returned to the user should include `page_number` for each relevant result.
        *   Consider how to group results by document if multiple pages from the same document are highly relevant.
    *   **Keyword Search (`type == "keyword"`):**
        *   This can remain largely unchanged, as it operates on the `Paper.ocr_text` field (which would still contain the full document text if preserved).
    *   **Admin Dashboard (`/admin`, `/admin/document/{doc_id}`):**
        *   Review these endpoints to ensure they display document information correctly, even with the underlying change to page-level embeddings in ChromaDB. They primarily rely on the SQLite `Paper` and `Metadata` models, so minimal changes are expected here.

### Phase 6: Testing and Verification

**Objective:** Ensure the new embedding strategy is correctly implemented and does not introduce regressions.

**Specific Actions:**

*   **Unit Tests:**
    *   Add/update unit tests for `app/ocr.py` to verify correct page-level text extraction.
    *   Add/update unit tests for `app/embedding.py` to verify correct page-level and document-level embedding generation.
    *   Add unit tests for `app/pipeline.py` to ensure the processing flow correctly handles and stores both types of embeddings.
*   **Integration Tests:**
    *   Write integration tests for the full document upload and processing flow, verifying that both page-level and document-level embeddings are created in ChromaDB.
    *   Write integration tests for the semantic search API, verifying that queries return correct page numbers and that document-level search (if still exposed) works as expected.
*   **Manual Testing:**
    *   Upload various PDF documents (single-page, multi-page, text-heavy, image-heavy) and observe the processing status.
    *   Perform semantic searches and verify the relevance and page numbers of the results.
*   **Code Quality:**
    *   Run project linting (`ruff check .`) and type checking (`mypy .` if configured) to ensure code quality and consistency.
    *   Review `requirements.txt` for any new dependencies or version updates.

## Considerations / Open Questions

*   **Storage Impact:** The number of embeddings stored in ChromaDB will increase significantly. Monitor storage usage.
*   **Performance Impact:** Generating more embeddings will increase processing time. Monitor job completion times.
*   **UI/UX for Search Results:** How will the frontend display search results that include page numbers? This will require frontend changes not covered in this plan.
*   **Handling Blank/Sparse Pages:** How should pages with very little or no text be handled? Should they still get an embedding, or be skipped? (Current `generate_embedding` returns a zero vector for empty text, which is a reasonable default).
*   **Document-level Search Strategy:** Should the `/api/v1/search` endpoint offer a distinct option for document-level semantic search (querying only `is_document_level: true` embeddings), or should it always prioritize page-level results? The current plan prioritizes page-level.
*   **Error Handling:** Ensure robust error handling for all new logic, especially during file processing and database interactions.
