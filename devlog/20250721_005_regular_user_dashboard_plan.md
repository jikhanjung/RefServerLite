# Plan for Regular User Dashboard & Features

**Objective:** Create a dedicated user dashboard for regular (non-admin) users, providing personal Zotero integration and a view of their uploaded documents.

---

#### Phase 1: Backend Data Model & API Enhancements

**Goal:** Modify existing data models and create new API endpoints to support user-specific data and interactions.

1.  **Link `Paper` to `User`:**
    *   **File:** `app/models.py`
    *   **Action:**
        *   Add a `ForeignKeyField` named `uploaded_by` to the `Paper` model, linking it to the `User` model. This will allow tracking which user uploaded which paper.
        *   **Crucial:** This change requires a database migration. The user will need to run `python migrate.py` after this change.

2.  **Update Upload APIs to Associate Papers with Users:**
    *   **File:** `app/main.py`
    *   **Action:**
        *   Modify the `POST /api/v1/upload` endpoint: When a user uploads a PDF, associate the created `Paper` record with the `current_user` (obtained via `Depends(get_current_user)`).
        *   Modify the `POST /api/v1/papers/upload_with_metadata` endpoint: Similarly, associate the created `Paper` record with the `current_user`.

3.  **API Endpoint for User's Uploaded Papers:**
    *   **File:** `app/main.py`
    *   **Action:**
        *   Create a new `GET /api/v1/users/me/papers` endpoint.
        *   This endpoint should return a list of `Paper` records where `uploaded_by` matches the `current_user`.
        *   Implement pagination and filtering (e.g., by filename, status) as needed.

4.  **API Endpoints for User's Zotero Collections and Items:**
    *   **File:** `app/main.py`
    *   **Action:**
        *   Create a new `GET /api/v1/users/me/zotero/collections` endpoint. This should return the `ZoteroCollection` records associated with the `current_user`.
        *   Create a new `GET /api/v1/users/me/zotero/items` endpoint. This should return the `ZoteroItem` records associated with the `current_user`, potentially with filtering by collection or item type.
        *   (Note: The `POST /api/v1/users/me/zotero_config` and `GET /api/v1/users/me/zotero_config` endpoints already exist and are suitable for managing user-specific Zotero API keys.)

---

#### Phase 2: Frontend UI for Regular Users

**Goal:** Develop the user-facing dashboard, navigation, and specific feature pages.

1.  **New User Dashboard Base Template:**
    *   **File:** `app/templates/user_base.html` (New file)
    *   **Action:**
        *   Create a new base template for the user dashboard, similar to `admin_base.html` but tailored for regular users.
        *   Include a top bar with app name, user name, and logout.
        *   Include a sidebar for user-specific navigation (e.g., "My Papers", "Zotero Settings", "Zotero Library").

2.  **User Dashboard Landing Page:**
    *   **File:** `app/main.py` (New route), `app/templates/user_dashboard.html` (New file)
    *   **Action:**
        *   Create a `GET /dashboard` route that redirects authenticated regular users to their main dashboard.
        *   Create `user_dashboard.html` extending `user_base.html`, which will serve as the landing page.

3.  **Zotero Account Settings Page:**
    *   **File:** `app/main.py` (New route), `app/templates/user_zotero_config.html` (New file)
    *   **Action:**
        *   Create a `GET /dashboard/zotero/config` route.
        *   Create `user_zotero_config.html` to display the Zotero API key input form (using the existing `/api/v1/users/me/zotero_config` API).
        *   Include a "Start Sync" button that calls the `/api/v1/users/me/zotero_sync` API.

4.  **Zotero Library View Page:**
    *   **File:** `app/main.py` (New route), `app/templates/user_zotero_library.html` (New file)
    *   **Action:**
        *   Create a `GET /dashboard/zotero/library` route.
        *   Create `user_zotero_library.html` to display the user's Zotero collections and items, fetched from the new `/api/v1/users/me/zotero/collections` and `/api/v1/users/me/zotero/items` APIs. This will likely involve JavaScript to dynamically load and display the hierarchical data.

5.  **User's Uploaded Files List Page:**
    *   **File:** `app/main.py` (New route), `app/templates/user_my_papers.html` (New file)
    *   **Action:**
        *   Create a `GET /dashboard/my-papers` route.
        *   Create `user_my_papers.html` to display a table of papers uploaded by the current user, fetched from the new `/api/v1/users/me/papers` API.

6.  **Update Authentication Redirect:**
    *   **File:** `app/main.py`
    *   **Action:** Modify the `POST /login` endpoint to redirect regular users (`is_admin=False`) to `/dashboard` instead of `/admin`.

---

#### Phase 3: Testing and Refinement

**Goal:** Ensure all new features function correctly and provide a good user experience.

1.  **User Creation:** Create a new regular user account (via the admin panel).
2.  **Login & Redirection:** Log in as the new regular user and verify redirection to `/dashboard`.
3.  **Zotero Configuration:** Test setting/updating Zotero API key and library ID.
4.  **Zotero Sync:** Initiate a Zotero sync and verify that collections and items appear in the "Zotero Library" view.
5.  **File Upload:** Test uploading a PDF file as a regular user and verify it appears in "My Papers".
6.  **Data Isolation:** Ensure that a regular user can only see their own Zotero data and uploaded papers, not those of other users or admin-uploaded papers.
7.  **UI/UX Review:** Check responsiveness, navigation, and overall user experience.
