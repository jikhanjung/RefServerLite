# Plan for Implementing User Creation Feature

This document outlines the plan to add a feature for creating new users. This functionality will be accessible only to administrators via the admin dashboard.

## Phase 1: Backend API Endpoint Development

The first step is to create the core server-side logic for user creation.

**File to Modify:** `app/main.py`

1.  **Add New API Endpoint:**
    *   Create a new API endpoint at `/api/v1/admin/users` that accepts `POST` requests.
    *   The endpoint will receive `username`, `password`, and `is_admin` (boolean) as form data.

2.  **Enforce Admin-Only Access:**
    *   Add `Depends(require_admin)` as a dependency to the endpoint to ensure only authenticated administrators can access it.

3.  **Implement User Creation Logic:**
    *   **Duplicate Check:** Verify if the provided `username` already exists in the `User` table. If it does, return a 409 Conflict HTTP status with an appropriate error message (e.g., "Username already exists").
    *   **Password Hashing:** Use the `set_password(password)` method from the `User` model to securely hash the incoming plaintext password before storage.
    *   **Database Insertion:** Create a new `User` record with the provided `username`, the hashed password, and the `is_admin` flag, and save it to the database.
    *   **Success Response:** Return a JSON response with a success message (e.g., "User created successfully").

## Phase 2: Frontend UI and Logic

Next, build the user interface for administrators to interact with this feature.

**File to Modify:** `app/templates/admin.html`

1.  **Add "Create User" Button and Modal:**
    *   Add a "Create New User" button to the admin dashboard.
    *   Create a Bootstrap modal that appears when the button is clicked. This modal will contain the user creation form.
    *   The form (`<form id="createUserForm">`) will include input fields for `username`, `password`, and a checkbox for "Is Admin?".

**File to Modify:** `app/static/js/script.js`

1.  **Implement Form Submission Logic (JavaScript):**
    *   Add a `submit` event listener to the `createUserForm`.
    *   Use the `fetch` API to send the form data asynchronously to the `/api/v1/admin/users` endpoint via a `POST` request.
    *   Handle the server's response:
        *   **On Success:** Display a success notification (e.g., "User 'username' created."), clear the form fields, and close the modal.
        *   **On Failure (e.g., duplicate username):** Display the error message returned by the server within the modal to inform the administrator.

## Phase 3: Testing and Verification

Finally, ensure the feature works correctly and securely.

1.  **Log in as an administrator** and navigate to the `/admin` page.
2.  Attempt to create a new **regular user** (Is Admin unchecked).
3.  Attempt to create a new **administrator user** (Is Admin checked).
4.  Attempt to create a user with an **existing username** to verify that the error handling works as expected.
5.  Log out and test logging in with each of the newly created accounts (both regular and admin) to confirm they are active. Verify that the regular user cannot access the `/admin` page.

## Additional Considerations

### Security Enhancements

1. **Password Complexity Requirements:**
   - Implement minimum password length (e.g., 8 characters)
   - Require at least one uppercase letter, one lowercase letter, one digit, and one special character
   - Add client-side validation with real-time feedback in the modal
   - Server-side validation to ensure requirements are met

2. **Email Field Addition:**
   - Add an optional email field to the User model for future features
   - Useful for password reset functionality
   - Can be used for user notifications
   - Add email format validation

### User Management Features

3. **User List View:**
   - Add a "View Users" section in the admin dashboard
   - Display a table with username, email, admin status, created date, and last login
   - Include action buttons for each user (Edit, Delete, Reset Password)
   - Implement pagination for large user lists

4. **User Edit/Delete Functionality:**
   - Add endpoints for updating user information (PUT /api/v1/admin/users/{user_id})
   - Add endpoint for deleting users (DELETE /api/v1/admin/users/{user_id})
   - Prevent deletion of the last admin user
   - Add confirmation dialog before deletion

### Audit and Monitoring

5. **Audit Logging:**
   - Log all user creation events with timestamp and creator's username
   - Store in a new `UserAuditLog` table
   - Track actions: created, updated, deleted, password_reset
   - Display audit history in the admin panel

6. **Activity Tracking:**
   - Add `last_login` field to User model
   - Track failed login attempts
   - Implement account lockout after N failed attempts

### Implementation Notes

7. **Script File Creation:**
   - If `app/static/js/script.js` doesn't exist, create it
   - Consider organizing JavaScript code into modules
   - Add proper error handling and loading states

8. **CSRF Protection:**
   - Implement CSRF token validation for all form submissions
   - Include token in all AJAX requests
   - Consider using FastAPI's built-in security features

9. **User Experience:**
   - Show password strength indicator in real-time
   - Add "Show/Hide Password" toggle
   - Implement proper form validation messages
   - Add loading spinners during API calls
