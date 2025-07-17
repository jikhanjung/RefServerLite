#!/usr/bin/env python3
"""
Import PDF documents from Zotero library to RefServerLite
"""
import argparse
import json
import logging
import os
import sys
import time
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import tempfile
import getpass

import requests
import yaml
from pyzotero import zotero

# For retry logic
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    logger.warning("tenacity not available, using simple retry logic")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global interactive mode flag
INTERACTIVE_MODE = True

class ZoteroCache:
    """Zotero PDF and metadata cache management"""
    
    def __init__(self, cache_dir: str = "zotero_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pdfs_dir = self.cache_dir / "pdfs"
        self.metadata_dir = self.cache_dir / "metadata"
        self.pdfs_dir.mkdir(exist_ok=True)
        self.metadata_dir.mkdir(exist_ok=True)
        
        logger.info(f"Zotero cache initialized at: {self.cache_dir}")
    
    def _get_pdf_path(self, zotero_key: str) -> Path:
        """Get PDF file path for a Zotero key"""
        return self.pdfs_dir / f"{zotero_key}.pdf"
    
    def _get_metadata_path(self, zotero_key: str) -> Path:
        """Get metadata file path for a Zotero key"""
        return self.metadata_dir / f"{zotero_key}.json"
    
    def cache_pdf(self, zotero_key: str, pdf_content: bytes, filename: str = None) -> bool:
        """Cache PDF content to disk"""
        try:
            pdf_path = self._get_pdf_path(zotero_key)
            
            # Write PDF content
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            
            # Store additional info
            info = {
                'cached_at': datetime.now().isoformat(),
                'original_filename': filename,
                'file_size': len(pdf_content),
                'checksum': hashlib.md5(pdf_content).hexdigest()
            }
            
            info_path = pdf_path.with_suffix('.pdf.info')
            with open(info_path, 'w') as f:
                json.dump(info, f, indent=2)
            
            logger.debug(f"Cached PDF for {zotero_key}: {len(pdf_content)} bytes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache PDF for {zotero_key}: {e}")
            return False
    
    def cache_metadata(self, zotero_key: str, item_data: Dict, processed_metadata: Dict = None) -> bool:
        """Cache Zotero item metadata"""
        try:
            metadata_path = self._get_metadata_path(zotero_key)
            
            cache_data = {
                'cached_at': datetime.now().isoformat(),
                'zotero_key': zotero_key,
                'zotero_data': item_data,  # Raw Zotero item data
                'processed_metadata': processed_metadata or {},  # Processed for RefServerLite
                'version': item_data.get('version'),
                'library_id': item_data.get('library', {}).get('id')
            }
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Cached metadata for {zotero_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache metadata for {zotero_key}: {e}")
            return False
    
    def get_cached_pdf(self, zotero_key: str) -> Optional[bytes]:
        """Get cached PDF content"""
        try:
            pdf_path = self._get_pdf_path(zotero_key)
            if not pdf_path.exists():
                return None
            
            with open(pdf_path, 'rb') as f:
                content = f.read()
            
            # Verify integrity if info file exists
            info_path = pdf_path.with_suffix('.pdf.info')
            if info_path.exists():
                with open(info_path, 'r') as f:
                    info = json.load(f)
                
                # Check checksum
                if hashlib.md5(content).hexdigest() != info.get('checksum'):
                    logger.warning(f"Cached PDF checksum mismatch for {zotero_key}")
                    return None
            
            logger.debug(f"Retrieved cached PDF for {zotero_key}: {len(content)} bytes")
            return content
            
        except Exception as e:
            logger.error(f"Failed to get cached PDF for {zotero_key}: {e}")
            return None
    
    def get_cached_metadata(self, zotero_key: str) -> Optional[Dict]:
        """Get cached metadata"""
        try:
            metadata_path = self._get_metadata_path(zotero_key)
            if not metadata_path.exists():
                return None
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            logger.debug(f"Retrieved cached metadata for {zotero_key}")
            return cache_data
            
        except Exception as e:
            logger.error(f"Failed to get cached metadata for {zotero_key}: {e}")
            return None
    
    def is_cached(self, zotero_key: str, check_pdf: bool = True, check_metadata: bool = True) -> Dict[str, bool]:
        """Check what's cached for a Zotero key"""
        result = {'pdf': False, 'metadata': False}
        
        if check_pdf:
            result['pdf'] = self._get_pdf_path(zotero_key).exists()
        
        if check_metadata:
            result['metadata'] = self._get_metadata_path(zotero_key).exists()
        
        return result
    
    def get_cached_pdf_info(self, zotero_key: str) -> Optional[Dict]:
        """Get cached PDF info (filename, size, etc.)"""
        try:
            pdf_path = self._get_pdf_path(zotero_key)
            info_path = pdf_path.with_suffix('.pdf.info')
            
            if not info_path.exists():
                return None
            
            with open(info_path, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Failed to get PDF info for {zotero_key}: {e}")
            return None
    
    def invalidate_cache(self, zotero_key: str):
        """Remove cached files for a Zotero key"""
        try:
            pdf_path = self._get_pdf_path(zotero_key)
            metadata_path = self._get_metadata_path(zotero_key)
            info_path = pdf_path.with_suffix('.pdf.info')
            
            for path in [pdf_path, metadata_path, info_path]:
                if path.exists():
                    path.unlink()
                    logger.debug(f"Removed cached file: {path}")
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache for {zotero_key}: {e}")
    
    def cleanup_cache(self, max_age_days: int = 30):
        """Clean up old cache files"""
        try:
            cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
            removed_count = 0
            
            for file_path in self.cache_dir.rglob("*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    removed_count += 1
            
            logger.info(f"Cleaned up {removed_count} old cache files (older than {max_age_days} days)")
            return removed_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {e}")
            return 0
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        try:
            pdf_files = list(self.pdfs_dir.glob("*.pdf"))
            metadata_files = list(self.metadata_dir.glob("*.json"))
            
            total_pdf_size = sum(f.stat().st_size for f in pdf_files)
            
            return {
                'pdf_count': len(pdf_files),
                'metadata_count': len(metadata_files),
                'total_pdf_size_mb': round(total_pdf_size / (1024 * 1024), 2),
                'cache_dir': str(self.cache_dir)
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}

def prompt_user_confirmation(message: str, default_yes: bool = False) -> bool:
    """Prompt user for yes/no confirmation"""
    if not INTERACTIVE_MODE:
        return default_yes
    
    suffix = " [Y/n]" if default_yes else " [y/N]"
    while True:
        response = input(f"{message}{suffix}: ").strip().lower()
        if not response:
            return default_yes
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")

def prompt_user_input(message: str, default: str = None, required: bool = True, 
                     secret: bool = False) -> str:
    """Prompt user for input with optional default and validation"""
    if not INTERACTIVE_MODE:
        if default:
            return default
        elif required:
            raise Exception(f"Required field '{message}' not provided in non-interactive mode")
        else:
            return ""
    
    suffix = f" [default: {default}]" if default else ""
    full_message = f"{message}{suffix}: "
    
    while True:
        if secret:
            value = getpass.getpass(full_message)
        else:
            value = input(full_message).strip()
        
        if not value and default:
            return default
        elif not value and required:
            print("This field is required. Please enter a value.")
        else:
            return value

def create_config_interactively() -> dict:
    """Create configuration interactively by prompting user"""
    print("\n🔧 Setting up Zotero import configuration...")
    print("You can find your Zotero credentials at: https://www.zotero.org/settings/keys")
    print()
    
    config = {
        'zotero': {},
        'refserver': {},
        'import_options': {}
    }
    
    # Zotero configuration
    config['zotero']['library_id'] = prompt_user_input(
        "Enter your Zotero Library ID (found in Settings > Feeds/API)"
    )
    config['zotero']['api_key'] = prompt_user_input(
        "Enter your Zotero API Key", secret=True
    )
    
    # RefServerLite configuration
    config['refserver']['api_url'] = prompt_user_input(
        "Enter RefServerLite API URL", default="http://localhost:8000"
    )
    config['refserver']['username'] = prompt_user_input(
        "Enter RefServerLite admin username", default="admin"
    )
    config['refserver']['password'] = prompt_user_input(
        "Enter RefServerLite admin password", secret=True
    )
    
    # Import options
    config['import_options']['batch_size'] = int(prompt_user_input(
        "Enter batch size (items to process at once)", default="5"
    ))
    config['import_options']['delay_seconds'] = float(prompt_user_input(
        "Enter delay between batches (seconds)", default="3.0"
    ))
    
    # Save configuration
    if prompt_user_confirmation("Save this configuration to config.yml?", default_yes=True):
        with open('config.yml', 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        print("✅ Configuration saved to config.yml")
    
    return config

class ImportProgress:
    """Track import progress for resume capability"""
    def __init__(self, progress_file: str = "zotero_import_progress.json"):
        self.progress_file = progress_file
        self.processed_keys = self.load_progress()
    
    def load_progress(self) -> Set[str]:
        """Load previously processed keys"""
        try:
            with open(self.progress_file, 'r') as f:
                data = json.load(f)
                return set(data.get("processed", []))
        except FileNotFoundError:
            return set()
    
    def save_progress(self):
        """Save current progress"""
        with open(self.progress_file, 'w') as f:
            json.dump({"processed": list(self.processed_keys)}, f)
    
    def mark_processed(self, zotero_key: str):
        """Mark an item as processed"""
        self.processed_keys.add(zotero_key)
        self.save_progress()
    
    def is_processed(self, zotero_key: str) -> bool:
        """Check if an item has been processed"""
        return zotero_key in self.processed_keys

class ZoteroImporter:
    def __init__(self, config_path: str):
        """Initialize the importer with configuration"""
        self.config = self._load_config(config_path)
        self.progress = ImportProgress()
        self.auth_token = None
        self.results = []
        self.cache = ZoteroCache()
        
        # Show cache statistics
        cache_stats = self.cache.get_cache_stats()
        if cache_stats.get('pdf_count', 0) > 0:
            logger.info(f"🗄️ Cache contains {cache_stats['pdf_count']} PDFs ({cache_stats['total_pdf_size_mb']} MB)")
        else:
            logger.info("🗄️ Cache is empty")
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file or create interactively"""
        if not Path(config_path).exists():
            print(f"❌ Configuration file '{config_path}' not found.")
            if prompt_user_confirmation("Would you like to create it interactively?", default_yes=True):
                return create_config_interactively()
            else:
                print("Please create the configuration file and try again.")
                sys.exit(1)
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                
            # Validate required fields
            required_fields = [
                ('zotero', 'library_id'),
                ('zotero', 'api_key'),
                ('refserver', 'api_url'),
                ('refserver', 'username'),
                ('refserver', 'password')
            ]
            
            missing_fields = []
            for section, field in required_fields:
                if section not in config or field not in config[section] or not config[section][field]:
                    missing_fields.append(f"{section}.{field}")
            
            if missing_fields:
                print(f"❌ Missing required configuration fields: {', '.join(missing_fields)}")
                if prompt_user_confirmation("Would you like to fill in the missing values interactively?", default_yes=True):
                    return self._complete_config_interactively(config, missing_fields)
                else:
                    print("Please update the configuration file and try again.")
                    sys.exit(1)
            
            return config
            
        except Exception as e:
            print(f"❌ Error reading configuration file: {e}")
            if prompt_user_confirmation("Would you like to create a new configuration?", default_yes=True):
                return create_config_interactively()
            else:
                sys.exit(1)
    
    def _complete_config_interactively(self, config: dict, missing_fields: List[str]) -> dict:
        """Fill in missing configuration fields interactively"""
        print(f"\n🔧 Completing missing configuration fields...")
        
        for field_path in missing_fields:
            section, field = field_path.split('.')
            
            if section not in config:
                config[section] = {}
            
            if field == 'api_key' or field == 'password':
                config[section][field] = prompt_user_input(f"Enter {field_path}", secret=True)
            elif field == 'api_url':
                config[section][field] = prompt_user_input(f"Enter {field_path}", default="http://localhost:8000")
            elif field == 'username':
                config[section][field] = prompt_user_input(f"Enter {field_path}", default="admin")
            else:
                config[section][field] = prompt_user_input(f"Enter {field_path}")
        
        # Save updated configuration
        if prompt_user_confirmation("Save updated configuration?", default_yes=True):
            with open('config.yml', 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            print("✅ Configuration updated and saved")
        
        return config
    
    def authenticate(self):
        """Authenticate with RefServerLite API"""
        login_url = f"{self.config['refserver']['api_url']}/api/v1/auth/login"
        
        try:
            response = requests.post(
                login_url,
                data={
                    "username": self.config['refserver']['username'],
                    "password": self.config['refserver']['password']
                }
            )
            response.raise_for_status()
            
            auth_data = response.json()
            self.auth_token = auth_data['access_token']
            logger.info("Successfully authenticated with RefServerLite")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to authenticate: {e}")
            raise
    
    def get_zotero_items(self, collection: Optional[str] = None, 
                        since_version: Optional[int] = None,
                        limit: Optional[int] = None) -> List[Dict]:
        """Fetch items from Zotero library"""
        zot = zotero.Zotero(
            self.config['zotero']['library_id'],
            'user',
            self.config['zotero']['api_key']
        )
        
        # Build query parameters
        params = {}
        if since_version:
            params['since'] = since_version
        if limit:
            params['limit'] = limit
            
        # Fetch items
        if collection:
            # Try to resolve collection name to ID if needed
            print(f"🔍 Resolving collection: {collection}")
            collection_id = self._resolve_collection_id(zot, collection)
            if collection_id:
                print(f"✅ Using collection ID: {collection_id}")
                items = zot.collection_items(collection_id, **params)
            else:
                logger.error(f"❌ Collection '{collection}' not found")
                print("💡 Available collections:")
                try:
                    collections = zot.collections()
                    for coll in collections[:10]:  # Show first 10
                        print(f"   - {coll['data']['name']} (ID: {coll['key']})")
                    if len(collections) > 10:
                        print(f"   ... and {len(collections) - 10} more")
                except:
                    print("   (Unable to fetch collection list)")
                return []
        else:
            items = zot.items(**params)
        
        # Filter for items with PDF attachments
        items_with_pdfs = []
        for item in items:
            if item['data'].get('itemType') in ['journalArticle', 'book', 'report', 'thesis']:
                # Get attachments
                attachments = zot.children(item['key'])
                pdf_attachments = [
                    att for att in attachments 
                    if att['data'].get('contentType') == 'application/pdf'
                ]
                if pdf_attachments:
                    item['pdf_attachments'] = pdf_attachments
                    items_with_pdfs.append(item)
        
        return items_with_pdfs
    
    def _resolve_collection_id(self, zot_instance, collection_input: str) -> Optional[str]:
        """
        Resolve collection name or ID to collection ID
        
        Args:
            zot_instance: Zotero API instance
            collection_input: Either collection name or collection ID
            
        Returns:
            Collection ID if found, None otherwise
        """
        # First, check if it's already a valid collection ID (8 characters, alphanumeric)
        if len(collection_input) == 8 and collection_input.isalnum():
            # Verify it exists
            try:
                zot_instance.collection(collection_input)
                logger.info(f"Using collection ID: {collection_input}")
                return collection_input
            except Exception:
                logger.warning(f"Collection ID {collection_input} not found, trying as name...")
        
        # Try to find by name
        try:
            collections = zot_instance.collections()
            for collection in collections:
                if collection['data']['name'].lower() == collection_input.lower():
                    collection_id = collection['key']
                    logger.info(f"Found collection '{collection_input}' with ID: {collection_id}")
                    return collection_id
            
            # Also check subcollections
            for collection in collections:
                if 'collections' in collection['data']:
                    subcollections = zot_instance.collections_sub(collection['key'])
                    for subcoll in subcollections:
                        if subcoll['data']['name'].lower() == collection_input.lower():
                            collection_id = subcoll['key']
                            logger.info(f"Found subcollection '{collection_input}' with ID: {collection_id}")
                            return collection_id
                            
        except Exception as e:
            logger.error(f"Error searching for collection: {e}")
        
        return None
    
    def check_existing_in_refserver(self) -> Set[str]:
        """Get existing Zotero keys from RefServerLite"""
        # This would require an API endpoint to list existing Zotero keys
        # For now, return empty set
        return set()
    
    def download_pdf(self, zot_instance, attachment_key: str, filename: str = None) -> Optional[bytes]:
        """Download PDF content from Zotero with caching"""
        # Check cache first (unless disabled)
        if self.cache:
            cached_pdf = self.cache.get_cached_pdf(attachment_key)
            if cached_pdf:
                logger.info(f"📁 Using cached PDF for {attachment_key}")
                return cached_pdf
        
        # Download from Zotero
        try:
            logger.info(f"⬇️ Downloading PDF from Zotero: {attachment_key}")
            pdf_content = zot_instance.file(attachment_key)
            
            # Cache the downloaded PDF (unless disabled)
            if pdf_content and self.cache:
                self.cache.cache_pdf(attachment_key, pdf_content, filename)
                logger.debug(f"💾 Cached PDF for {attachment_key}")
            
            return pdf_content
            
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return None
    
    def upload_to_refserver_with_retry(self, item: Dict, pdf_content: bytes, 
                                     attachment_filename: str, max_retries: int = 3) -> Dict:
        """Upload with retry logic for database lock errors"""
        for attempt in range(max_retries):
            try:
                return self._upload_to_refserver_single_attempt(item, pdf_content, attachment_filename)
            except requests.exceptions.HTTPError as e:
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 500 and 'database is locked' in e.response.text:
                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) + 2  # Exponential backoff: 3, 6, 10 seconds
                            logger.warning(f"Database locked (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"All retry attempts failed due to database lock")
                            raise
                    else:
                        # Other HTTP errors, don't retry
                        raise
                else:
                    # Network errors, don't retry
                    raise
        
        # Should not reach here, but just in case
        raise Exception("Maximum retry attempts exceeded")
    
    def _upload_to_refserver_single_attempt(self, item: Dict, pdf_content: bytes, 
                                          attachment_filename: str) -> Dict:
        """Upload PDF and metadata to RefServerLite"""
        url = f"{self.config['refserver']['api_url']}/api/v1/papers/upload_with_metadata"
        
        # Extract metadata
        data = item['data']
        
        # Format authors
        authors = []
        for creator in data.get('creators', []):
            if creator.get('creatorType') == 'author':
                if 'name' in creator:
                    authors.append(creator['name'])
                else:
                    name = f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
                    if name:
                        authors.append(name)
        
        # Extract year from date
        year = None
        if data.get('date'):
            date_str = str(data['date']) # Ensure it's a string
            import re
            from datetime import datetime

            # Regex to find any four-digit number that could be a year
            # It looks for a word boundary, followed by four digits, and another word boundary.
            # This is more general than (19|20) and allows for earlier centuries.
            matches = re.findall(r'\b\d{4}\b', date_str)
            
            current_year = datetime.now().year
            
            for potential_year_str in matches:
                try:
                    potential_year = int(potential_year_str)
                    # Check if the year is within a plausible range (e.g., 1500 to current year + 1)
                    if 1500 <= potential_year <= current_year + 1:
                        year = potential_year
                        break # Found a plausible year, stop searching
                except ValueError:
                    pass # Not a valid integer, skip
            
            # Fallback to original logic if no plausible year found by regex
            if year is None:
                try:
                    if len(date_str) >= 4:
                        year = int(date_str[:4])
                except ValueError:
                    pass
        
        # Prepare form data
        form_data = {
            'title': data.get('title', 'Untitled'),
            'authors': json.dumps(authors),
            'year': year,
            'zotero_key': item['key'],
            'zotero_library_id': str(self.config['zotero']['library_id']),
            'zotero_version': item['version'],
        }
        
        # Add collection keys if present
        if item.get('data', {}).get('collections'):
            form_data['collection_keys'] = json.dumps(item['data']['collections'])
        
        # Add tags if present
        if item.get('data', {}).get('tags'):
            tags = [tag['tag'] for tag in item['data']['tags']]
            form_data['tags'] = json.dumps(tags)
        
        # Create temporary file for upload
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_file.write(pdf_content)
            tmp_file_path = tmp_file.name
        
        try:
            with open(tmp_file_path, 'rb') as f:
                files = {'file': (attachment_filename, f, 'application/pdf')}
                
                response = requests.post(
                    url,
                    data=form_data,
                    files=files,
                    headers={'Authorization': f'Bearer {self.auth_token}'}
                )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 409:
                    logger.info(f"Item {item['key']} already exists in RefServerLite")
                    return {'status': 'skipped', 'reason': 'duplicate'}
                else:
                    logger.error(f"Upload failed: {e.response.text}")
            else:
                logger.error(f"Upload failed: {e}")
            raise
        finally:
            # Clean up temp file
            os.unlink(tmp_file_path)
    
    def process_item(self, item: Dict, zot_instance) -> Dict:
        """Process a single Zotero item with caching"""
        result = {
            'zotero_key': item['key'],
            'title': item['data'].get('title', 'Untitled'),
            'success': False,
            'skipped': False,
            'error': None
        }
        
        try:
            # Cache metadata first (if cache is enabled)
            if self.cache:
                self.cache.cache_metadata(item['key'], item['data'])
            
            # Check if already processed
            if self.progress.is_processed(item['key']):
                logger.info(f"⏭️ Skipping already processed item: {item['key']}")
                result['skipped'] = True
                result['success'] = True
                return result
            
            # Check cache status
            cache_info = ""
            if self.cache:
                cache_status = self.cache.is_cached(item['key'])
                if cache_status['pdf']:
                    cache_info = " (using cached PDF)"
            
            # Process each PDF attachment
            for attachment in item.get('pdf_attachments', []):
                att_key = attachment['key']
                att_filename = attachment['data'].get('filename', f"{item['key']}.pdf")
                
                logger.info(f"📄 Processing PDF for '{result['title']}'{cache_info}")
                pdf_content = self.download_pdf(zot_instance, att_key, att_filename)
                
                if not pdf_content:
                    result['error'] = "Failed to download PDF"
                    continue
                
                logger.info(f"📤 Uploading to RefServerLite...")
                upload_result = self.upload_to_refserver_with_retry(item, pdf_content, att_filename)
                
                if upload_result.get('status') == 'skipped':
                    result['skipped'] = True
                    result['success'] = True
                else:
                    result['success'] = True
                    result['job_id'] = upload_result.get('job_id')
                    result['doc_id'] = upload_result.get('doc_id')
                
                # Mark as processed only after successful upload
                self.progress.mark_processed(item['key'])
                break  # Process only the first PDF
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Failed to process item {item['key']}: {e}")
            
            # On failure, the cache is preserved for retry
            logger.info(f"🗄️ PDF and metadata cached for retry: {item['key']}")
        
        return result
    
    def run_import(self, dry_run: bool = False, collection: Optional[str] = None,
                   since_version: Optional[int] = None, limit: Optional[int] = None):
        """Run the import process"""
        # Authenticate first
        if not dry_run:
            self.authenticate()
        
        # Initialize Zotero
        zot = zotero.Zotero(
            self.config['zotero']['library_id'],
            'user',
            self.config['zotero']['api_key']
        )
        
        # Get items
        if collection:
            logger.info(f"Fetching items from collection: {collection}")
        else:
            logger.info("Fetching items from entire Zotero library...")
        
        items = self.get_zotero_items(collection, since_version, limit)
        logger.info(f"Found {len(items)} items with PDF attachments")
        
        # Show collection contents preview if collection is specified
        if collection and items:
            self._show_collection_preview(items)
        
        if dry_run:
            # Dry run - collection preview already shown above, just confirm
            print("\n🔍 DRY RUN MODE - No actual import will be performed")
            print(f"📋 Would process {len(items)} items from the collection")
            return
        
        # Confirm before proceeding with actual import
        if not prompt_user_confirmation(f"\nProceed with importing {len(items)} items?", default_yes=True):
            print("❌ Import cancelled by user")
            return
        
        # Process items in batches
        batch_size = self.config.get('import_options', {}).get('batch_size', 20)
        delay = self.config.get('import_options', {}).get('delay_seconds', 1.0)
        
        total_batches = (len(items) + batch_size - 1) // batch_size
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_num = i//batch_size + 1
            
            # Show batch confirmation (except for first batch which was already confirmed)
            if batch_num > 1:
                print(f"\n📦 Starting batch {batch_num}/{total_batches} ({len(batch)} items)")
                if not prompt_user_confirmation("Continue with this batch?", default_yes=True):
                    print(f"❌ Import stopped at batch {batch_num}")
                    break
            else:
                print(f"\n📦 Starting batch {batch_num}/{total_batches} ({len(batch)} items)")
            
            logger.info(f"Processing batch {batch_num} ({len(batch)} items)...")
            
            batch_results = []
            for item in batch:
                result = self.process_item(item, zot)
                self.results.append(result)
                batch_results.append(result)
                
                if result['success'] and not result['skipped']:
                    logger.info(f"✓ Successfully imported: {result['title']}")
                elif result['skipped']:
                    logger.info(f"⚬ Skipped (already exists): {result['title']}")
                else:
                    logger.error(f"✗ Failed: {result['title']} - {result['error']}")
            
            # Show batch summary
            successful = sum(1 for r in batch_results if r['success'] and not r.get('skipped'))
            skipped = sum(1 for r in batch_results if r.get('skipped'))
            failed = sum(1 for r in batch_results if not r['success'])
            
            print(f"📊 Batch {batch_num} completed: {successful} successful, {skipped} skipped, {failed} failed")
            
            # Delay between batches
            if i + batch_size < len(items):
                print(f"⏱️ Waiting {delay} seconds before next batch...")
                time.sleep(delay)
    
    def _show_collection_preview(self, items: List[Dict]):
        """Show preview of collection contents"""
        print(f"\n{'='*60}")
        print(f"📚 COLLECTION CONTENTS PREVIEW ({len(items)} items)")
        print(f"{'='*60}")
        
        for i, item in enumerate(items, 1):
            data = item['data']
            
            # Extract basic info
            title = data.get('title', 'Untitled')
            if len(title) > 60:
                title = title[:57] + "..."
            
            # Extract authors
            authors = []
            for creator in data.get('creators', []):
                if creator.get('creatorType') == 'author':
                    if 'name' in creator:
                        authors.append(creator['name'])
                    else:
                        name = f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
                        if name:
                            authors.append(name)
            
            author_str = ", ".join(authors[:2])  # Show first 2 authors
            if len(authors) > 2:
                author_str += f" et al."
            if not author_str:
                author_str = "Unknown authors"
            
            # Extract year
            year = "Unknown"
            if data.get('date'):
                try:
                    year = str(int(data['date'][:4]))
                except:
                    year = data['date'][:10] if len(data['date']) >= 10 else data['date']
            
            # Extract journal/publication
            publication = data.get('publicationTitle') or data.get('bookTitle') or data.get('university') or "Unknown"
            if len(publication) > 30:
                publication = publication[:27] + "..."
            
            # Count PDF attachments
            pdf_count = len(item.get('pdf_attachments', []))
            
            print(f"{i:2d}. {title}")
            print(f"    📝 Authors: {author_str}")
            print(f"    📅 Year: {year} | 📖 Publication: {publication}")
            print(f"    📎 PDF attachments: {pdf_count}")
            print()
        
        print(f"{'='*60}")
        print(f"✅ Ready to import {len(items)} items from this collection")
        print(f"{'='*60}\n")
    
    def generate_report(self):
        """Generate import report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_items": len(self.results),
            "successful": sum(1 for r in self.results if r["success"]),
            "failed": sum(1 for r in self.results if not r["success"]),
            "skipped": sum(1 for r in self.results if r.get("skipped")),
            "errors": [r for r in self.results if not r["success"] and not r.get("skipped")]
        }
        
        report_filename = f"import_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n=== Import Summary ===")
        print(f"Total items: {report['total_items']}")
        print(f"Successful: {report['successful']}")
        print(f"Failed: {report['failed']}")
        print(f"Skipped: {report['skipped']}")
        print(f"\nDetailed report saved to: {report_filename}")

def main():
    parser = argparse.ArgumentParser(description='Import PDFs from Zotero to RefServerLite')
    parser.add_argument('--config', default='config.yml', help='Path to configuration file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be imported without actually importing')
    parser.add_argument('--collection', help='Import only from specific collection (ID or name)')
    parser.add_argument('--since-version', type=int, help='Import items modified since this Zotero library version')
    parser.add_argument('--limit', type=int, help='Limit number of items to import')
    parser.add_argument('--non-interactive', action='store_true', help='Run without user prompts (use with caution)')
    
    # Cache management options
    parser.add_argument('--cache-stats', action='store_true', help='Show cache statistics and exit')
    parser.add_argument('--cache-cleanup', type=int, metavar='DAYS', help='Clean up cache files older than DAYS')
    parser.add_argument('--cache-invalidate', help='Invalidate cache for specific Zotero key')
    parser.add_argument('--no-cache', action='store_true', help='Disable cache usage (force download)')
    
    args = parser.parse_args()
    
    # Set global interactive mode
    global INTERACTIVE_MODE
    INTERACTIVE_MODE = not args.non_interactive
    
    # Handle cache management commands first
    if args.cache_stats or args.cache_cleanup is not None or args.cache_invalidate:
        cache = ZoteroCache()
        
        if args.cache_stats:
            stats = cache.get_cache_stats()
            print(f"\n📊 Cache Statistics:")
            print(f"   Cache directory: {stats['cache_dir']}")
            print(f"   PDF files: {stats['pdf_count']}")
            print(f"   Metadata files: {stats['metadata_count']}")
            print(f"   Total PDF size: {stats['total_pdf_size_mb']} MB")
            
            if stats['pdf_count'] > 0:
                print(f"\n📁 Recent cached files:")
                for pdf_file in list(cache.pdfs_dir.glob("*.pdf"))[:5]:
                    key = pdf_file.stem
                    info = cache.get_cached_pdf_info(key)
                    if info:
                        print(f"   {key}: {info.get('original_filename', 'unknown')} ({info.get('file_size', 0)} bytes)")
            sys.exit(0)
        
        if args.cache_cleanup is not None:
            removed = cache.cleanup_cache(args.cache_cleanup)
            print(f"🧹 Cleaned up {removed} cache files older than {args.cache_cleanup} days")
            sys.exit(0)
        
        if args.cache_invalidate:
            cache.invalidate_cache(args.cache_invalidate)
            print(f"🗑️ Invalidated cache for: {args.cache_invalidate}")
            sys.exit(0)
    
    # Check config file exists for import operations
    if not Path(args.config).exists():
        logger.error(f"Configuration file not found: {args.config}")
        sys.exit(1)
    
    # Run import
    importer = ZoteroImporter(args.config)
    
    # Disable cache if requested
    if args.no_cache:
        logger.info("🚫 Cache disabled - forcing fresh downloads")
        importer.cache = None
    
    try:
        importer.run_import(
            dry_run=args.dry_run,
            collection=args.collection,
            since_version=args.since_version,
            limit=args.limit
        )
        
        if not args.dry_run:
            importer.generate_report()
            
    except Exception as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
