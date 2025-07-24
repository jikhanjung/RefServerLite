// Admin Panel JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle functionality
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const sidebarToggleMobile = document.getElementById('sidebarToggleMobile');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const mainContent = document.querySelector('.main-content');
    
    // Mobile sidebar toggle
    if (sidebarToggleMobile) {
        sidebarToggleMobile.addEventListener('click', function() {
            sidebar.classList.toggle('show');
            sidebarOverlay.classList.toggle('show');
        });
    }
    
    // Desktop sidebar toggle
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('collapsed');
            if (mainContent) {
                mainContent.classList.toggle('sidebar-collapsed');
            }
            // Save state to localStorage
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        });
    }
    
    // Restore sidebar state from localStorage
    const sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (sidebarCollapsed && sidebar && mainContent) {
        sidebar.classList.add('collapsed');
        mainContent.classList.add('sidebar-collapsed');
    }
    
    // Close sidebar when clicking overlay
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', function() {
            sidebar.classList.remove('show');
            sidebarOverlay.classList.remove('show');
        });
    }
    
    // Close sidebar on window resize if mobile
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 768) {
            sidebar.classList.remove('show');
            sidebarOverlay.classList.remove('show');
        }
    });
    
    // Auto-hide alerts
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        if (alert.classList.contains('alert-success')) {
            setTimeout(() => {
                alert.style.opacity = '0';
                setTimeout(() => {
                    if (alert.parentNode) {
                        alert.parentNode.removeChild(alert);
                    }
                }, 300);
            }, 3000);
        }
    });
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
});

// Utility functions
function showAlert(message, type = 'info', containerId = null) {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    const container = containerId ? document.getElementById(containerId) : document.querySelector('.content');
    if (container) {
        container.insertAdjacentHTML('afterbegin', alertHtml);
    }
}

function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Loading state management
function setLoading(elementId, isLoading = true) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    if (isLoading) {
        element.disabled = true;
        const originalText = element.textContent;
        element.setAttribute('data-original-text', originalText);
        element.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading...';
    } else {
        element.disabled = false;
        const originalText = element.getAttribute('data-original-text');
        if (originalText) {
            element.textContent = originalText;
            element.removeAttribute('data-original-text');
        }
    }
}

// API helper functions
async function apiCall(url, options = {}) {
    const defaultOptions = {
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, mergedOptions);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        
        return { success: true, data };
    } catch (error) {
        console.error('API call failed:', error);
        return { success: false, error: error.message };
    }
}

// Admin-specific API helper function
async function fetchAdminData(url, options = {}) {
    const defaultOptions = {
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, mergedOptions);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }
        
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Admin API call failed:', error);
        throw error;
    }
}

// Table utilities
function updateTable(tableBodyId, data, renderRowFunction) {
    const tbody = document.getElementById(tableBodyId);
    if (!tbody) return;
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="100%" class="text-center text-muted">No data available</td></tr>';
        return;
    }
    
    tbody.innerHTML = data.map(renderRowFunction).join('');
}

// Pagination utilities
function updatePagination(paginationId, currentPage, totalPages, onPageChange) {
    const pagination = document.getElementById(paginationId);
    if (!pagination) return;
    
    if (totalPages <= 1) {
        pagination.style.display = 'none';
        return;
    }
    
    pagination.style.display = 'block';
    
    let html = '';
    
    // Previous button
    html += `
        <li class="page-item ${currentPage <= 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="${onPageChange}(${currentPage - 1}); return false;">Previous</a>
        </li>
    `;
    
    // Page numbers
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    if (startPage > 1) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="${onPageChange}(1); return false;">1</a></li>`;
        if (startPage > 2) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        html += `
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="${onPageChange}(${i}); return false;">${i}</a>
            </li>
        `;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        html += `<li class="page-item"><a class="page-link" href="#" onclick="${onPageChange}(${totalPages}); return false;">${totalPages}</a></li>`;
    }
    
    // Next button
    html += `
        <li class="page-item ${currentPage >= totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="${onPageChange}(${currentPage + 1}); return false;">Next</a>
        </li>
    `;
    
    const paginationList = pagination.querySelector('.pagination');
    if (paginationList) {
        paginationList.innerHTML = html;
    }
}

// Content display utilities
function showNotification(message, type = 'info', timeout = 5000) {
    const alertClass = `alert-${type}`;
    const iconMap = {
        'success': 'bi-check-circle',
        'error': 'bi-exclamation-triangle',
        'danger': 'bi-exclamation-triangle', 
        'warning': 'bi-exclamation-triangle',
        'info': 'bi-info-circle'
    };
    
    const icon = iconMap[type] || iconMap.info;
    
    const alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
            <i class="bi ${icon} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', alertHtml);
    
    // Auto-remove after timeout
    if (timeout > 0) {
        setTimeout(() => {
            const alerts = document.querySelectorAll('.alert');
            alerts.forEach(alert => {
                if (alert.innerHTML.includes(message)) {
                    alert.remove();
                }
            });
        }, timeout);
    }
}

function showEmpty(containerId, message = 'No data available', icon = 'bi-inbox') {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    container.innerHTML = `
        <div class="text-center py-5 text-muted">
            <i class="bi ${icon}" style="font-size: 3rem; opacity: 0.5;"></i>
            <p class="mt-3 mb-0">${message}</p>
        </div>
    `;
}

function showError(containerId, error, message = 'An error occurred') {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const errorMessage = error ? (error.message || error) : 'Unknown error';
    
    container.innerHTML = `
        <div class="text-center py-5">
            <div class="text-danger">
                <i class="bi bi-exclamation-triangle" style="font-size: 3rem;"></i>
                <h5 class="mt-3">${message}</h5>
                <p class="text-muted small">${errorMessage}</p>
            </div>
            <button class="btn btn-outline-primary btn-sm" onclick="location.reload()">
                <i class="bi bi-arrow-clockwise me-1"></i>
                Retry
            </button>
        </div>
    `;
}

function showLoading(containerId, message = 'Loading...') {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    container.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-3 text-muted">${message}</p>
        </div>
    `;
}