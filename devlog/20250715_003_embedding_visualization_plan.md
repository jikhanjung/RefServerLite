## On-Demand Embedding Visualization Plan

### Introduction

This plan outlines the integration of on-demand embedding visualization into RefServerLite. Instead of storing embedding visualization images in the database or filesystem during processing, these images will be generated dynamically when requested by the user. This approach optimizes storage and ensures visualizations are always up-to-date with the latest embedding data.

### Goals

1.  **Generate Visualizations On-Demand:** Create image files representing embedding vectors (page-level and document-level) only when a user requests to view them.
2.  **Serve Visualizations via API:** Provide dedicated API endpoints to serve these dynamically generated images.
3.  **Display in UI:** Integrate these API endpoints into the document detail page to display the visualizations.

### High-Level Plan

1.  **Phase 1: Implement Visualization Utility**
2.  **Phase 2: Create API Endpoints for On-Demand Visualization**
3.  **Phase 3: Update Document View to Request On-Demand Images**
4.  **Phase 4: Testing and Verification**

### Detailed Steps

### Phase 1: Implement Visualization Utility

**Objective:** Create a dedicated module for embedding visualization functions and ensure necessary dependencies are in place.

**Files to Modify:**
*   `app/visualize.py` (new file)
*   `requirements.txt`

**Specific Changes:**

*   **`app/visualize.py` (New File):**
    *   Create this file and add the `visualize_embedding_bar` function provided by the user.
    *   Add necessary imports: `import numpy as np`, `import matplotlib.pyplot as plt`.
    *   Ensure the function can save to a specified `save_path` (which will be a temporary file in Phase 2).
*   **`requirements.txt`:**
    *   Add `matplotlib` to the list of dependencies.
    *   Add `numpy` (if not already present).

### Phase 2: Create API Endpoints for On-Demand Visualization

**Objective:** Develop FastAPI endpoints that retrieve embedding data, generate the visualization image, and serve it.

**Files to Modify:**
*   `app/main.py`
*   `app/db.py` (potentially, to add helper for retrieving embeddings)

**Specific Changes:**

*   **`app/main.py`**:
    *   Add a new GET endpoint for document-level embedding visualization (e.g., `/api/v1/document/{doc_id}/embedding_viz`).
    *   Add a new GET endpoint for page-level embedding visualization (e.g., `/api/v1/document/{doc_id}/page/{page_number}/embedding_viz`).
    *   For each endpoint:
        1.  **Retrieve Embedding:**
            *   Access the `app.state.chroma_collection`.
            *   Query ChromaDB to retrieve the specific embedding vector.
                *   For document-level: Query with `ids=[doc_id]` and `where={"is_document_level": True}`.
                *   For page-level: Query with `ids=[f"{doc_id}_page_{page_number}"]` and `where={"is_document_level": False}`.
            *   Handle cases where the embedding is not found (e.g., return 404).
        2.  **Generate Image:**
            *   Convert the retrieved embedding (which will be a list from ChromaDB) back to a NumPy array.
            *   Call `visualize.visualize_embedding_bar()` with the embedding.
            *   Save the output to a temporary file (e.g., using Python's `tempfile` module to create a temporary PNG file).
        3.  **Serve Image:**
            *   Return the temporary image file using FastAPI's `FileResponse`.
            *   Ensure the temporary file is properly cleaned up after serving.
        4.  **Error Handling:** Implement robust error handling for database queries, image generation, and file operations.
*   **`app/db.py` (Optional but Recommended):**
    *   Add a helper function (e.g., `get_embedding_from_chroma(collection, doc_id, page_number=None, is_document_level=False)`) to encapsulate the logic for retrieving embeddings from ChromaDB. This would make the `main.py` endpoints cleaner.

### Phase 3: Update Document View to Request On-Demand Images

**Objective:** Modify the document detail page to display embedding visualizations by calling the new API endpoints.

**Files to Modify:**
*   `app/templates/document.html`

**Specific Changes:**

*   **`app/templates/document.html`**:
    *   In the document details section (or a new dedicated section), add an `<img>` tag for the document-level embedding visualization. The `src` attribute will point to the new API endpoint (e.g., `<img src="/api/v1/document/{{ paper.doc_id }}/embedding_viz" alt="Document Embedding Visualization">`).
    *   If displaying page-by-page text (assuming the "Page-by-Page OCR Text Storage & Retrieval" phase from the Document View Enhancement plan is completed), for each page, add an `<img>` tag for the page-level embedding visualization. The `src` attribute will point to the corresponding page-level API endpoint (e.g., `<img src="/api/v1/document/{{ paper.doc_id }}/page/{{ page.page_number }}/embedding_viz" alt="Page {{ page.page_number }} Embedding Visualization">`).

### Phase 4: Testing and Verification

**Objective:** Ensure the on-demand embedding visualization feature works correctly and efficiently.

**Specific Actions:**

*   **Unit Tests:**
    *   Add unit tests for `app/visualize.py` to ensure images are generated correctly from given NumPy arrays.
    *   Add unit tests for the new API endpoints in `app/main.py` to verify correct embedding retrieval, image generation, and `FileResponse` serving.
*   **Integration Tests:**
    *   Test the full flow: upload a PDF, navigate to the document detail page, and verify that both document-level and page-level embedding visualization images load successfully.
*   **Manual Testing:**
    *   Upload various PDF documents (single-page, multi-page) and manually check the document view for the presence and correctness of the embedding visualizations.
    *   Observe network requests to confirm images are fetched from the new API endpoints.
*   **Code Quality:**
    *   Run project linting and type checking.
    *   Verify `requirements.txt` is updated correctly with `matplotlib` and `numpy`.