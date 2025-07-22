# Admin Dashboard: Zotero Management Enhancement Plan (Revised)

**Date:** 2025-07-22

## 1. Overview

This plan details the necessary changes to enhance the Zotero integration management features within the admin dashboard. The goal is to separate system-wide Zotero configuration from individual user Zotero settings and to provide administrators with the ability to view, manage, and test users' Zotero configurations.

This revised plan is based on a detailed analysis of the existing codebase.

## 2. Analysis of Current Implementation

*   **`app/models.py`**: The `User` model already contains `zotero_library_id` and `zotero_api_key_encrypted` fields. An encryption/decryption mechanism for the API key is also in place. This means minimal database changes are required.
*   **`app/main.py`**: An admin route `/admin/zotero/config` exists but its corresponding template (`admin_zotero_config.html`) fetches user-specific data (`/api/v1/users/me/zotero_config`), creating ambiguity. The user management page (`/admin/users`) relies on a yet-to-be-implemented API endpoint (`/api/v1/admin/users`) for dynamic content loading.
*   **Templates**: `admin_users.html` has existing JavaScript for fetching and displaying user data, which can be extended. `admin_zotero_config.html` needs to be repurposed for system-wide settings.

## 3. Detailed Execution Plan

### Phase 1: Database Model Update (Minimal)

1.  **Modify `User` Model (`app/models.py`):**
    *   Add a single new field to the `User` model to store the library type.
        *   `zotero_library_type = CharField(null=True)` (This will store 'user' or 'group').

2.  **Generate Database Migration:**
    *   The user will be instructed to run the following command in the terminal to generate the migration script:
        ```bash
        python migrate.py "add zotero_library_type to user"
        ```

### Phase 2: Backend API Implementation and Refactoring

1.  **Refactor System Zotero Configuration (`app/main.py`):**
    *   **Rename Route:** Change the existing route from `/admin/zotero/config` to `/admin/system-zotero-config`.
    *   **Rename Handler Function:** Rename the `admin_zotero_config` function to `admin_system_zotero_config`.
    *   **Clarify Logic:** For now, the "system" configuration will continue to be the settings of the primary `admin` user, but the UI and endpoint paths will be distinct to avoid confusion.

2.  **Implement User Management APIs (`app/main.py`):**
    *   **Create `GET /api/v1/admin/users`:**
        *   Implement this new API endpoint to be called by the JavaScript on the `admin_users.html` page.
        *   It should support pagination via `page` and `per_page` query parameters.
        *   For each user, the API will return a JSON object including: `id`, `username`, `email`, `is_admin`, `created_at`, `last_login`, and a new boolean field `zotero_configured` (derived from `user.has_zotero_config()`).
    *   **Create `GET /admin/users/{user_id}/zotero`:**
        *   Create a new route and handler function that renders a detailed Zotero management page for a specific user.
        *   It will fetch the `User` object by `user_id` and pass it to a new template, `admin_user_zotero_details.html`.
    *   **Create `POST /api/v1/admin/users/{user_id}/zotero/test`:**
        *   Create a new API endpoint for testing a user's Zotero connection.
        *   The handler will:
            1.  Fetch the user by `user_id`.
            2.  Decrypt the user's Zotero API key.
            3.  Use `pyzotero` to attempt a simple, authenticated API call (e.g., `zot.collections(limit=1)`).
            4.  Return a JSON response indicating success or failure (e.g., `{"status": "success"}` or `{"status": "error", "message": "Invalid API key"}`).
    *   **Create `POST /api/v1/admin/users/{user_id}/zotero`:**
        *   Create an endpoint to save the updated Zotero details for a user from the new management page.

### Phase 3: Frontend UI/UX Changes

1.  **Update Admin Base Template (`app/templates/admin_base.html`):**
    *   In the sidebar navigation, find the "Zotero" section.
    *   Change the link text from "Configuration" to "System Config".
    *   Update the `href` attribute to point to the new `/admin/system-zotero-config` route.

2.  **Repurpose Zotero Config Template:**
    *   Rename `app/templates/admin_zotero_config.html` to `app/templates/admin_system_zotero_config.html`.
    *   Update the title and description on this page to reflect that it manages **system-wide** Zotero settings.
    *   Update the JavaScript `fetch` calls to point to a new system-level API endpoint (e.g., `/api/v1/system/zotero_config`), which will need to be created in the backend.

3.  **Update Users Page (`app/templates/admin_users.html`):**
    *   In the table header (`<thead>`), add two new columns: `<th>Zotero Status</th>` and `<th>Zotero Actions</th>`.
    *   Modify the `displayUsersList` JavaScript function:
        *   For each user row, check the `user.zotero_configured` flag.
        *   In the "Zotero Status" cell, display a badge: `<span class="badge bg-success">Configured</span>` or `<span class="badge bg-secondary">Not Configured</span>`.
        *   In the "Zotero Actions" cell, add a management link: `<a href="/admin/users/${user.id}/zotero" class="btn btn-sm btn-outline-info">Manage</a>`.

4.  **Create New User Zotero Details Template (`app/templates/admin_user_zotero_details.html`):**
    *   Create this new file, extending `admin_base.html`.
    *   The page will feature a form for managing a specific user's Zotero settings.
    *   The form will display the user's `zotero_library_id` and `zotero_library_type`.
    *   The API key field will be a password input, showing `******************` by default, allowing a new key to be entered.
    *   The form will include:
        *   A "Test Connection" button that triggers a `fetch` call to the `POST /api/v1/admin/users/{user_id}/zotero/test` endpoint and displays the result dynamically.
        *   A "Save Changes" button that submits the form to the `POST /api/v1/admin/users/{user_id}/zotero` endpoint.

## 4. File Changes Summary

*   **Modified:**
    *   `app/models.py` (Add one field)
    *   `app/main.py` (Refactor routes, add new API endpoints)
    *   `app/templates/admin_base.html` (Update sidebar link)
    *   `app/templates/admin_users.html` (Update table and JavaScript)
*   **Renamed:**
    *   `app/templates/admin_zotero_config.html` -> `app/templates/admin_system_zotero_config.html`
*   **Created:**
    *   `app/templates/admin_user_zotero_details.html`
*   **To be Generated:**
    *   A new migration file in the `migrations/` directory.
