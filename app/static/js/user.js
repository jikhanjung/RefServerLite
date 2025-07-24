// User Dashboard JavaScript

// Sidebar toggle functionality
document.addEventListener('DOMContentLoaded', function() {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarToggleMobile = document.getElementById('sidebarToggleMobile');
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.querySelector('.main-content');
    
    // Desktop sidebar toggle
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('collapsed');
            if (mainContent) {
                mainContent.classList.toggle('sidebar-collapsed');
            }
            // Save state to localStorage
            localStorage.setItem('userSidebarCollapsed', sidebar.classList.contains('collapsed'));
        });
    }
    
    // Mobile sidebar toggle
    if (sidebarToggleMobile && sidebar) {
        sidebarToggleMobile.addEventListener('click', function() {
            sidebar.classList.toggle('show');
        });
    }
    
    // Restore sidebar state from localStorage
    const sidebarCollapsed = localStorage.getItem('userSidebarCollapsed') === 'true';
    if (sidebarCollapsed && sidebar && mainContent) {
        sidebar.classList.add('collapsed');
        mainContent.classList.add('sidebar-collapsed');
    }
    
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(event) {
        if (window.innerWidth < 768) {
            if (!sidebar.contains(event.target) && !sidebarToggleMobile.contains(event.target)) {
                sidebar.classList.remove('show');
            }
        }
    });
    
    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 768) {
            sidebar.classList.remove('show');
        }
    });
});

// Utility functions for API calls
async function fetchUserData(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            credentials: 'include',
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// Show loading state
function showLoading(elementId, message = 'Loading...') {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2 text-muted">${message}</p>
            </div>
        `;
    }
}

// Show error state
function showError(elementId, message = 'An error occurred') {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${message}
            </div>
        `;
    }
}

// Show empty state
function showEmpty(elementId, icon = 'file-earmark', title = 'No items found', subtitle = 'There are no items to display.') {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="empty-state">
                <i class="bi bi-${icon}"></i>
                <h4>${title}</h4>
                <p>${subtitle}</p>
            </div>
        `;
    }
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Get status badge HTML
function getStatusBadge(status) {
    const statusMap = {
        'completed': { class: 'bg-success', text: 'Complete' },
        'processing': { class: 'bg-warning', text: 'Processing' },
        'failed': { class: 'bg-danger', text: 'Failed' },
        'pending': { class: 'bg-secondary', text: 'Pending' },
        'uploaded': { class: 'bg-info', text: 'Uploaded' }
    };
    
    const statusInfo = statusMap[status] || { class: 'bg-secondary', text: status };
    return `<span class="badge ${statusInfo.class}">${statusInfo.text}</span>`;
}

// Show notification
function showNotification(message, type = 'info', duration = 3000) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = `
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        max-width: 500px;
    `;
    
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to body
    document.body.appendChild(notification);
    
    // Auto remove after duration
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, duration);
}

// Refresh page data (used by multiple pages)
function refreshData() {
    // This will be overridden by specific pages
    console.log('Refreshing data...');
    window.location.reload();
}

// Auto-refresh functionality
let autoRefreshInterval;

function startAutoRefresh(intervalMs = 30000) {
    stopAutoRefresh(); // Clear any existing interval
    autoRefreshInterval = setInterval(refreshData, intervalMs);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// Clean up on page unload
window.addEventListener('beforeunload', stopAutoRefresh);

// Common form handling
function handleFormSubmit(formId, apiEndpoint, options = {}) {
    const form = document.getElementById(formId);
    if (!form) return;
    
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const submitButton = form.querySelector('button[type="submit"]');
        const originalText = submitButton.textContent;
        
        try {
            // Show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Submitting...';
            
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            
            const response = await fetchUserData(apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            
            // Success callback
            if (options.onSuccess) {
                options.onSuccess(response);
            } else {
                showNotification('Operation completed successfully!', 'success');
            }
            
            // Reset form if specified
            if (options.resetForm) {
                form.reset();
            }
            
        } catch (error) {
            console.error('Form submission error:', error);
            
            // Error callback
            if (options.onError) {
                options.onError(error);
            } else {
                showNotification('An error occurred. Please try again.', 'danger');
            }
        } finally {
            // Restore button
            submitButton.disabled = false;
            submitButton.textContent = originalText;
        }
    });
}

// Copy to clipboard functionality
function copyToClipboard(text, successMessage = 'Copied to clipboard!') {
    navigator.clipboard.writeText(text).then(() => {
        showNotification(successMessage, 'success', 2000);
    }).catch(() => {
        showNotification('Failed to copy to clipboard', 'danger');
    });
}

// Search functionality
function setupSearch(searchInputId, searchHandler) {
    const searchInput = document.getElementById(searchInputId);
    if (!searchInput) return;
    
    let searchTimeout;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim();
        
        // Debounce search
        searchTimeout = setTimeout(() => {
            searchHandler(query);
        }, 300);
    });
}

// Modal helpers
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
}

function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) {
            bsModal.hide();
        }
    }
}

// Confirm dialog
function showConfirm(message, callback) {
    if (confirm(message)) {
        callback();
    }
}