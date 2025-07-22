import pytest
import asyncio
import tempfile
import os
from playwright.async_api import async_playwright, expect
from unittest.mock import patch, MagicMock
import json
import uuid
from datetime import datetime

# Mock Zotero data for testing
MOCK_ZOTERO_COLLECTIONS = [
    {
        'key': 'COLL1234',
        'version': 1,
        'data': {
            'name': 'Test Collection',
            'parentCollection': None,
            'relations': {}
        }
    }
]

MOCK_ZOTERO_ITEMS = [
    {
        'key': 'ITEM1234',
        'version': 1,
        'data': {
            'itemType': 'journalArticle',
            'title': 'Test Article',
            'creators': [
                {'creatorType': 'author', 'firstName': 'John', 'lastName': 'Doe'}
            ],
            'publicationTitle': 'Test Journal',
            'date': '2023',
            'abstractNote': 'This is a test article',
            'DOI': '10.1234/test',
            'collections': ['COLL1234'],
            'tags': [{'tag': 'test'}],
            'dateAdded': '2023-01-01T00:00:00Z',
            'dateModified': '2023-01-01T00:00:00Z'
        }
    },
    {
        'key': 'ATTACH1234',
        'version': 1,
        'data': {
            'itemType': 'attachment',
            'parentItem': 'ITEM1234',
            'contentType': 'application/pdf',
            'filename': 'test_article.pdf',
            'linkMode': 'imported_file',
            'dateAdded': '2023-01-01T00:00:00Z',
            'dateModified': '2023-01-01T00:00:00Z'
        }
    }
]

MOCK_PDF_CONTENT = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF'


class MockZotero:
    """Mock Zotero API client for testing"""
    
    def __init__(self, library_id, library_type, api_key):
        self.library_id = library_id
        self.library_type = library_type
        self.api_key = api_key
    
    def collections(self):
        return MOCK_ZOTERO_COLLECTIONS
    
    def items(self, **params):
        return MOCK_ZOTERO_ITEMS
    
    def collection_items(self, collection_id, **params):
        return MOCK_ZOTERO_ITEMS
    
    def item(self, item_key):
        for item in MOCK_ZOTERO_ITEMS:
            if item['key'] == item_key:
                return item
        raise Exception(f"Item {item_key} not found")
    
    def file(self, item_key):
        if item_key == 'ATTACH1234':
            return MOCK_PDF_CONTENT
        return None


@pytest.fixture
async def browser():
    """Start browser for testing"""
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    yield browser
    await browser.close()
    await playwright.stop()


@pytest.fixture
async def page(browser):
    """Create a new page for testing"""
    context = await browser.new_context()
    page = await context.new_page()
    yield page
    await context.close()


@pytest.fixture
def mock_zotero():
    """Mock pyzotero.zotero.Zotero"""
    with patch('pyzotero.zotero.Zotero', MockZotero):
        yield MockZotero


@pytest.fixture
def test_server_url():
    """Test server URL - assumes server is running on localhost:8000"""
    return "http://localhost:8000"


class TestZoteroE2E:
    """End-to-end tests for Zotero integration"""
    
    async def test_admin_login_and_zotero_setup(self, page, test_server_url, mock_zotero):
        """Test logging in as admin and setting up Zotero configuration"""
        # Navigate to login page
        await page.goto(f"{test_server_url}/login")
        
        # Login as admin
        await page.fill('input[name="username"]', 'admin')
        await page.fill('input[name="password"]', 'admin123')
        await page.click('button[type="submit"]')
        
        # Wait for redirect to main page
        await page.wait_for_url(f"{test_server_url}/")
        
        # Navigate to admin page
        await page.goto(f"{test_server_url}/admin")
        
        # Check if Zotero Settings button exists
        zotero_btn = page.locator('button:has-text("Zotero Settings")')
        await expect(zotero_btn).to_be_visible()
        
        # Click Zotero Settings button
        await zotero_btn.click()
        
        # Wait for modal to appear
        modal = page.locator('#zoteroModal')
        await expect(modal).to_be_visible()
        
        # Fill in Zotero configuration
        await page.fill('#zoteroLibraryId', 'test_library_123')
        await page.fill('#zoteroApiKey', 'test_api_key_456')
        
        # Save configuration
        await page.click('button:has-text("Save Configuration")')
        
        # Wait for success message
        await expect(page.locator('.alert-success')).to_be_visible()
        
        # Close modal
        await page.click('button:has-text("Close")')
        await expect(modal).not_to_be_visible()
    
    async def test_zotero_sync_workflow(self, page, test_server_url, mock_zotero):
        """Test complete Zotero synchronization workflow"""
        # Login and setup Zotero config (reuse from previous test)
        await self.test_admin_login_and_zotero_setup(page, test_server_url, mock_zotero)
        
        # Start Zotero sync
        await page.goto(f"{test_server_url}/admin")
        
        # Click sync button
        sync_btn = page.locator('button:has-text("Sync from Zotero")')
        await expect(sync_btn).to_be_visible()
        await sync_btn.click()
        
        # Wait for sync to start
        await expect(page.locator('.alert-info')).to_contain_text('sync started')
        
        # Wait for sync completion (with timeout)
        await page.wait_for_function(
            """() => {
                const alerts = document.querySelectorAll('.alert');
                for (let alert of alerts) {
                    if (alert.textContent.includes('sync completed')) {
                        return true;
                    }
                }
                return false;
            }""",
            timeout=30000
        )
        
        # Check that documents were imported
        await page.goto(f"{test_server_url}/")
        
        # Look for the imported document
        document_list = page.locator('.document-list')
        await expect(document_list).to_be_visible()
        
        # Check if test document appears
        test_doc = page.locator(':has-text("test_article.pdf")')
        await expect(test_doc).to_be_visible()
    
    async def test_document_view_with_zotero_metadata(self, page, test_server_url, mock_zotero):
        """Test viewing a document imported from Zotero"""
        # Complete sync first
        await self.test_zotero_sync_workflow(page, test_server_url, mock_zotero)
        
        # Click on the imported document
        await page.click(':has-text("test_article.pdf")')
        
        # Wait for document page to load
        await page.wait_for_load_state('networkidle')
        
        # Check metadata tab
        metadata_tab = page.locator('[data-bs-target="#metadata"]')
        await metadata_tab.click()
        
        # Verify Zotero metadata is displayed
        metadata_content = page.locator('#metadata')
        await expect(metadata_content).to_contain_text('Test Article')
        await expect(metadata_content).to_contain_text('John Doe')
        await expect(metadata_content).to_contain_text('Test Journal')
        await expect(metadata_content).to_contain_text('2023')
        await expect(metadata_content).to_contain_text('Source: zotero')
    
    async def test_search_zotero_documents(self, page, test_server_url, mock_zotero):
        """Test searching documents imported from Zotero"""
        # Complete sync first
        await self.test_zotero_sync_workflow(page, test_server_url, mock_zotero)
        
        # Go to admin page for advanced search
        await page.goto(f"{test_server_url}/admin")
        
        # Test keyword search
        search_input = page.locator('input[name="query"]')
        await search_input.fill('Test Article')
        
        search_btn = page.locator('button:has-text("Search")')
        await search_btn.click()
        
        # Wait for search results
        await page.wait_for_load_state('networkidle')
        
        # Check if results contain our document
        results = page.locator('#searchResults')
        await expect(results).to_contain_text('test_article.pdf')
        await expect(results).to_contain_text('Test Article')
    
    async def test_zotero_config_persistence(self, page, test_server_url, mock_zotero):
        """Test that Zotero configuration persists across sessions"""
        # Setup Zotero config
        await self.test_admin_login_and_zotero_setup(page, test_server_url, mock_zotero)
        
        # Logout
        await page.goto(f"{test_server_url}/logout")
        
        # Login again
        await page.goto(f"{test_server_url}/login")
        await page.fill('input[name="username"]', 'admin')
        await page.fill('input[name="password"]', 'admin123')
        await page.click('button[type="submit"]')
        
        # Go to admin page
        await page.goto(f"{test_server_url}/admin")
        
        # Open Zotero settings
        await page.click('button:has-text("Zotero Settings")')
        
        # Check if configuration is still there
        library_id = page.locator('#zoteroLibraryId')
        await expect(library_id).to_have_value('test_library_123')
        
        # API key should be masked but field should indicate it's set
        status = page.locator('#zoteroStatus')
        await expect(status).to_contain_text('configured')
    
    async def test_error_handling_invalid_credentials(self, page, test_server_url):
        """Test error handling for invalid Zotero credentials"""
        # Login as admin
        await page.goto(f"{test_server_url}/login")
        await page.fill('input[name="username"]', 'admin')
        await page.fill('input[name="password"]', 'admin123')
        await page.click('button[type="submit"]')
        
        # Go to admin page
        await page.goto(f"{test_server_url}/admin")
        
        # Open Zotero settings
        await page.click('button:has-text("Zotero Settings")')
        
        # Fill in invalid credentials
        await page.fill('#zoteroLibraryId', 'invalid_library')
        await page.fill('#zoteroApiKey', 'invalid_key')
        
        # Save configuration
        await page.click('button:has-text("Save Configuration")')
        
        # Try to sync (this should fail with real API, but might succeed with mock)
        await page.click('button:has-text("Close")')
        
        # For this test, we'd need to mock network failures
        # The UI should handle sync errors gracefully


if __name__ == "__main__":
    # Run tests with: pytest tests/test_zotero_e2e.py -v
    pass