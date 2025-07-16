# Document View Enhancement Plan

## Introduction

This plan outlines the enhancements to the document detail view in RefServerLite. The goal is to provide a richer and more interactive experience for users when viewing processed documents, including page-by-page OCR text, PDF download, side-by-side page preview, and metadata editing.

## Goals

1.  **Page-by-Page OCR Text Display:** Store and display OCR text for each page individually.
2.  **PDF Download:** Provide a direct link to download the original uploaded PDF.
3.  **Page Preview & Side-by-Side Text:** Generate and display image previews of PDF pages alongside their extracted text.
4.  **Metadata Editing:** Allow users to edit the extracted bibliographic metadata.

## High-Level Plan

The implementation will proceed in the following phases:

1.  **Phase 1: Page-by-Page OCR Text Storage & Retrieval**
2.  **Phase 2: PDF Download Functionality**
3.  **Phase 3: PDF Page Preview Generation & Display**
4.  **Phase 4: Metadata Editing Functionality**
5.  **Phase 5: Testing and Verification**

## Detailed Steps

### Phase 1: Page-by-Page OCR Text Storage & Retrieval

**Objective:** Modify the database schema and processing pipeline to store OCR text on a per-page basis, and update the document view to display it accordingly.

**Files to Modify:**
*   `app/models.py`
*   `app/ocr.py`
*   `app/pipeline.py`
*   `app/main.py`
*   `app/templates/document.html`

**Specific Changes:**

*   **`app/models.py`**:
    *   Remove `ocr_text` field from `Paper` model.
    *   Add a new `PageText` model:
        ```python
        class PageText(BaseModel):
            paper = ForeignKeyField(Paper, backref='page_texts', on_delete='CASCADE')
            page_number = IntegerField()
            text = TextField()
            created_at = DateTimeField(default=datetime.datetime.now)

            class Meta:
                indexes = (
                    (('paper', 'page_number'), True), # Ensure unique page text per paper
                )
        ```
    *   Update `create_tables()` to include `PageText`.
*   **`app/ocr.py`**:
    *   Modify `extract_text_from_pdf` to return `List[str]` (list of texts, one per page) instead of a single concatenated string.
    *   Modify `process_pdf_ocr` to return `List[str]`.
*   **`app/pipeline.py`**:
    *   In `_process_ocr`:
        *   Call the modified `process_pdf_ocr` to get `texts_per_page`.
        *   Remove saving to `paper.ocr_text`.
        *   Store `texts_per_page` temporarily (e.g., as a new attribute on the `job` object, or pass it directly) for `_generate_embeddings` and for saving to `PageText` model.
    *   In `process_document` (or a new dedicated step):
        *   After OCR, iterate through `texts_per_page` and create `PageText` entries for each page, linking them to the `Paper` object.
*   **`app/main.py`**:
    *   In `admin_document_detail` endpoint:
        *   Fetch `PageText` objects associated with the `Paper` (e.g., `paper.page_texts.order_by(PageText.page_number)`).
        *   Pass the list of `PageText` objects to the `document.html` template.
    *   In `get_document` API endpoint:
        *   Modify the `text` field in the JSON response to return a list of page texts, or remove it if it's no longer needed for this API.
*   **`app/templates/document.html`**:
    *   Update the "Extracted Text" section to iterate over the `page_texts` passed from the backend.
    *   Display each page's text, possibly with a page number header.
    *   Remove the truncation logic for `paper.ocr_text`.

### Phase 2: PDF Download Functionality

**Objective:** Provide a direct link to download the original PDF file.

**Files to Modify:**
*   `app/main.py`
*   `app/templates/document.html`

**Specific Changes:**

*   **`app/main.py`**:
    *   Add a new FastAPI endpoint (e.g., `/download/pdf/{doc_id}`) that:
        *   Retrieves the `Paper` object using `doc_id`.
        *   Constructs the absolute path to the PDF file (`paper.file_path`).
        *   Returns a `FileResponse` for the PDF file.
        *   Implement proper error handling (e.g., 404 if file not found).
*   **`app/templates/document.html`**:
    *   Add a "Download PDF" button or link in the "Document Details" section, pointing to the new download endpoint.

### Phase 3: PDF Page Preview Generation & Display

**Objective:** Generate image previews for each PDF page and display them side-by-side with their extracted text.

**Files to Modify:**
*   `app/ocr.py` (or a new utility module for image generation)
*   `app/pipeline.py`
*   `app/main.py`
*   `app/templates/document.html`
*   (Potentially add a new directory for storing image previews, e.g., `refdata/previews/`)

**Specific Changes:**

*   **`app/ocr.py` (or new module)**:
    *   Add a function (e.g., `generate_page_preview_image(pdf_path: str, page_number: int, output_dir: str) -> str`) that:
        *   Uses `PyMuPDF` (`fitz`) to open the PDF.
        *   Renders a specific page to a pixmap.
        *   Saves the pixmap as an image file (e.g., PNG or JPG) in a designated preview directory.
        *   Returns the path to the generated image.
*   **`app/pipeline.py`**:
    *   In `process_document` (or a new step after OCR):
        *   Iterate through each page of the PDF.
        *   Call the image generation function to create a preview for each page.
        *   Store the path to the generated image in the `PageText` model (add a `preview_image_path` field to `PageText`).
*   **`app/models.py`**:
    *   Add `preview_image_path = CharField(null=True)` to the `PageText` model.
*   **`app/main.py`**:
    *   Add a static route for the preview image directory (e.g., `/previews/`).
    *   In `admin_document_detail`:
        *   Ensure `preview_image_path` is fetched and passed with `PageText` objects to the template.
*   **`app/templates/document.html`**:
    *   Modify the page-by-page text display to include an `<img>` tag for the `preview_image_path` next to the text for each page.
    *   Use CSS to arrange them side-by-side.

### Phase 4: Metadata Editing Functionality

**Objective:** Allow users to edit the extracted bibliographic metadata directly from the document view.

**Files to Modify:**
*   `app/main.py`
*   `app/templates/document.html`
*   `app/static/js/script.js` (for frontend interaction)

**Specific Changes:**

*   **`app/main.py`**:
    *   Add a new FastAPI endpoint (e.g., `POST /api/v1/document/{doc_id}/metadata`) that:
        *   Accepts updated metadata fields (e.g., title, authors, journal, year, abstract, doi).
        *   Retrieves the `Metadata` object for the given `doc_id`.
        *   Updates the fields of the `Metadata` object.
        *   Saves the `Metadata` object.
        *   Returns a success/error JSON response.
        *   Implement proper validation and error handling.
*   **`app/templates/document.html`**:
    *   Convert the "Document Metadata" section into an editable form.
    *   Use `<input>` fields for text, authors (perhaps a textarea for comma-separated), journal, year, DOI.
    *   Use a `<textarea>` for the abstract.
    *   Add a "Save" button.
    *   Consider adding a "Cancel" or "Edit" button to toggle between view and edit modes.
*   **`app/static/js/script.js`**:
    *   Add JavaScript code to handle the form submission:
        *   Capture form data.
        *   Send an AJAX `POST` request to the new metadata update API endpoint.
        *   Handle the API response (e.g., display success message, error message).
        *   Update the displayed metadata on the page after successful save.

### Phase 5: Testing and Verification

**Objective:** Ensure all new features are correctly implemented and do not introduce regressions.

**Specific Actions:**

*   **Unit Tests:**
    *   Add/update unit tests for `app/models.py` (new `PageText` model).
    *   Add/update unit tests for `app/ocr.py` (page preview generation).
    *   Add/update unit tests for `app/main.py` (new download and metadata update endpoints).
*   **Integration Tests:**
    *   Test the full pipeline from PDF upload to viewing page-by-page text and previews.
    *   Test PDF download functionality.
    *   Test metadata editing: update fields, save, and verify changes persist.
*   **Manual Testing:**
    *   Upload various PDFs and check the document view for all new features.
    *   Verify page-by-page text accuracy.
    *   Check PDF download.
    *   Inspect page previews for correctness.
    *   Test metadata editing with valid and invalid inputs.
*   **Code Quality:**
    *   Run project linting and type checking.
    *   Review `requirements.txt` for any new dependencies (e.g., for image processing if not already covered by PyMuPDF).