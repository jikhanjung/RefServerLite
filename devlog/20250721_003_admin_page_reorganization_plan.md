# Admin Page Reorganization Plan

**Objective:** Refactor the monolithic admin dashboard into a modern, sidebar-based layout with clear, category-based navigation to improve usability and scalability.

---

### Phase 1: Establish the New Layout Structure (HTML/CSS)

**Goal:** Create the foundational visual structure of the new admin interface, including the sidebar and main content area, without migrating all the features yet.

1.  **Create a Dedicated Admin Base Template:**
    *   **File:** `app/templates/admin_base.html` (New file)
    *   **Action:**
        *   Create a new `admin_base.html` file to serve as the master layout for all admin pages.
        *   This template will define the core structure: a fixed vertical sidebar, a top bar, and a main content area.
        *   The top bar will contain the app logo/name, the current user's name, and a "Logout" button.
        *   The sidebar will initially contain placeholder links for the navigation categories.

2.  **Apply Basic Styling:**
    *   **File:** `app/static/css/style.css`
    *   **Action:**
        *   Add CSS rules for the new layout.
        *   Style the sidebar to be fixed on the left, and ensure the main content area has appropriate padding to avoid being overlapped by the sidebar.
        *   Add styles for sidebar navigation links, including hover and active states.

3.  **Update Main Admin Page to Use New Base:**
    *   **File:** `app/templates/admin.html`
    *   **Action:**
        *   Modify the existing `admin.html` to extend the new `admin_base.html` (`{% extends "admin_base.html" %}`).
        *   For now, retain only the document list in the main content block and remove the old "Quick Links" section.

---

### Phase 2: Define Navigation Categories and Backend Routes

**Goal:** Define the new information architecture and create the necessary backend routes and empty pages for each navigation item.

1.  **Define Sidebar Navigation Structure:**
    *   The sidebar menu will be organized into logical categories:
        *   **Dashboard:** (Route: `/admin`) - System overview and latest documents (the role of the current `admin.html`).
        *   **Documents:** (Category Header)
            *   All Papers: (Route: `/admin/papers`) - Comprehensive list of papers with management tools.
            *   Duplicates: (Route: `/admin/duplicates`) - Interface for managing potential duplicates.
        *   **Zotero:** (Category Header)
            *   Configuration: (Route: `/admin/zotero/config`) - UI for setting Zotero API key and library ID.
            *   Sync: (Route: `/admin/zotero/sync`) - Interface to start synchronization and view status.
        *   **User Management:** (Category Header)
            *   Users: (Route: `/admin/users`) - View, create, edit, and delete users.
        *   **System:** (Category Header)
            *   Jobs: (Route: `/admin/system/jobs`) - Background job monitoring dashboard.
            *   Logs: (Route: `/admin/system/logs`) - Future placeholder for a system log viewer.

2.  **Create Backend Routes:**
    *   **File:** `app/main.py`
    *   **Action:**
        *   Create new FastAPI route functions for each new path (e.g., `/admin/users`, `/admin/zotero/config`).
        *   Protect all new routes with the `Depends(require_admin)` dependency.
        *   Each route should render a new, corresponding (and initially empty) template file.

3.  **Create Placeholder Template Files:**
    *   **Directory:** `app/templates/`
    *   **Action:**
        *   Create the necessary template files (e.g., `admin_users.html`, `admin_zotero_config.html`, `admin_system_jobs.html`).
        *   Each new template should extend `admin_base.html` and contain a simple heading (e.g., `<h1>User Management</h1>`) as a placeholder.

---

### Phase 3: Migrate and Integrate Existing Features

**Goal:** Move the functionality from the old pages and quick links into the newly created, dedicated sections.

1.  **Migrate User Management:**
    *   **Target:** `admin_users.html`
    *   **Action:** Move all UI elements and logic related to user creation and management into this template.

2.  **Migrate Job Monitoring:**
    *   **Target:** `admin_system_jobs.html`
    *   **Action:** Move the content from the old `jobs.html` into this new template and link it to the `/admin/system/jobs` route.

3.  **Migrate Zotero Features:**
    *   **Target:** `admin_zotero_config.html`, `admin_zotero_sync.html`
    *   **Action:** Decouple the Zotero configuration form and the sync status UI into their respective dedicated pages.

4.  **Implement Active State Highlighting:**
    *   **Files:** `app/main.py`, `app/templates/admin_base.html`
    *   **Action:**
        *   Modify the admin route functions in `app/main.py` to pass a context variable indicating the active page (e.g., `{"request": request, "active_page": "users"}`).
        *   In `admin_base.html`, use this variable with Jinja2 logic to conditionally add an `active` CSS class to the corresponding sidebar link, providing clear visual feedback to the user about their current location.
