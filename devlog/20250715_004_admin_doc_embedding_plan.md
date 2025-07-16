
# Devlog: Display Document Embedding in Admin Document List

**Date:** 2025-07-15
**Author:** Gemini

## Goal

Display the document embedding visualization in the admin document list view (`/admin`). This will provide a quick visual reference for each document's embedding.

## Plan

### 1. Modify `app/visualize.py`

- **File:** `app/visualize.py`
- **Function:** `visualize_embedding_heatmap`
- **Change:**
    - Add a new parameter `figsize` to the function to allow for custom image sizes.
    - Adjust the `dpi` to ensure the image is the correct size.

### 2. Modify `app/main.py`

- **File:** `app/main.py`
- **Endpoint:** `/admin`
- **Change:**
    - Retrieve the document embedding for each document.
- **Endpoint:** `/api/v1/document/{doc_id}/embedding_heatmap_mini`
- **Change:**
    - Create a new endpoint that generates a 32x32 image of the document embedding.

### 3. Modify `app/templates/admin.html`

- **File:** `app/templates/admin.html`
- **Change:**
    - Add a new column to the documents table for the embedding visualization.
    - Add an `<img>` tag to the new column that calls the new API endpoint to get the embedding visualization.

