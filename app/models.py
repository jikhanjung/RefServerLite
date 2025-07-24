from peewee import *
import datetime
import json
import os
import warnings
from typing import List, Optional
from passlib.context import CryptContext
from cryptography.fernet import Fernet

# Suppress bcrypt warnings
warnings.filterwarnings("ignore", message=".*bcrypt.*", category=UserWarning)

db = SqliteDatabase(None)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(unique=True)
    password_hash = CharField()
    email = CharField(null=True)
    is_admin = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.datetime.now)
    last_login = DateTimeField(null=True)
    
    # Zotero integration fields
    zotero_library_id = CharField(null=True)
    zotero_library_type = CharField(null=True)  # 'user' or 'group'
    zotero_api_key_encrypted = CharField(null=True)
    zotero_last_sync = DateTimeField(null=True)
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.password_hash = pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(password, self.password_hash)
    
    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.datetime.now()
        self.save()
    
    def set_zotero_api_key(self, api_key: str):
        """Encrypt and set Zotero API key"""
        if not api_key:
            self.zotero_api_key_encrypted = None
            return
        
        encryption_key = self._get_encryption_key()
        cipher_suite = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        self.zotero_api_key_encrypted = cipher_suite.encrypt(api_key.encode()).decode()
    
    def get_zotero_api_key(self) -> Optional[str]:
        """Decrypt and get Zotero API key"""
        if not self.zotero_api_key_encrypted:
            return None
        
        try:
            encryption_key = self._get_encryption_key()
            cipher_suite = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            return cipher_suite.decrypt(self.zotero_api_key_encrypted.encode()).decode()
        except Exception:
            # If decryption fails, return None
            return None
    
    def has_zotero_config(self) -> bool:
        """Check if user has Zotero configuration"""
        return bool(self.zotero_library_id and self.zotero_api_key_encrypted)
    
    def clear_zotero_config(self):
        """Clear Zotero configuration"""
        self.zotero_library_id = None
        self.zotero_api_key_encrypted = None
        self.zotero_last_sync = None
    
    @staticmethod
    def _get_encryption_key() -> str:
        """Get or generate encryption key for Zotero API keys"""
        # First try environment variable
        encryption_key = os.getenv('ZOTERO_ENCRYPTION_KEY')
        if encryption_key:
            return encryption_key
        
        # Try to load from file
        key_file_path = os.path.join(os.getcwd(), 'refdata', 'encryption.key')
        if os.path.exists(key_file_path):
            try:
                with open(key_file_path, 'r') as f:
                    return f.read().strip()
            except Exception:
                pass
        
        # Generate new key and save to file
        new_key = Fernet.generate_key().decode()
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(key_file_path), exist_ok=True)
            with open(key_file_path, 'w') as f:
                f.write(new_key)
            # Set restrictive permissions
            os.chmod(key_file_path, 0o600)
            print(f"🔑 Generated new encryption key and saved to {key_file_path}")
        except Exception as e:
            print(f"⚠️ Could not save encryption key to file: {e}")
            # Fall back to environment variable for this session
            os.environ['ZOTERO_ENCRYPTION_KEY'] = new_key
        
        return new_key

class Paper(BaseModel):
    doc_id = CharField(primary_key=True)
    filename = CharField()
    file_path = CharField()
    ocr_text = TextField(null=True)
    uploaded_by = ForeignKeyField(User, backref='uploaded_papers', null=True, on_delete='SET NULL')
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)
    
    # File deduplication
    md5_hash = CharField(null=True, index=True)  # MD5 hash of PDF file for deduplication
    
    # Duplicate detection fields
    duplicate_check_completed = BooleanField(default=False)
    duplicate_checked_at = DateTimeField(null=True)
    has_potential_duplicates = BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.now()
        return super().save(*args, **kwargs)

class Metadata(BaseModel):
    paper = ForeignKeyField(Paper, backref='metadata', unique=True, on_delete='CASCADE')
    title = CharField(null=True)
    authors = TextField(null=True)  # Stored as JSON string
    journal = CharField(null=True)
    year = IntegerField(null=True)
    abstract = TextField(null=True)
    doi = CharField(null=True)
    source = CharField(default='extracted', index=True)  # 'extracted' or 'user_api'
    created_at = DateTimeField(default=datetime.datetime.now)
    
    def get_authors(self) -> List[str]:
        """Get authors as a list"""
        if self.authors:
            try:
                return json.loads(self.authors)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_authors(self, authors: List[str]):
        """Set authors from a list"""
        self.authors = json.dumps(authors)

class ProcessingJob(BaseModel):
    job_id = CharField(primary_key=True)
    paper = ForeignKeyField(Paper, backref='jobs', null=True, on_delete='SET NULL')
    filename = CharField()
    status = CharField(default='uploaded')  # uploaded, processing, completed, failed
    current_step = CharField(null=True)  # ocr, metadata, embedding
    progress_percentage = IntegerField(default=0)
    error_message = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)
    completed_at = DateTimeField(null=True)
    
    # Additional fields for different job types
    job_type = CharField(default='pdf_processing')  # pdf_processing, zotero_sync
    user_id = ForeignKeyField(User, backref='processing_jobs', null=True, on_delete='CASCADE')
    total_steps = IntegerField(default=4)  # Default for PDF processing
    parameters = TextField(null=True)  # JSON string for job-specific parameters
    result = TextField(null=True)  # JSON string for job results
    
    def save(self, *args, **kwargs): # <-- 이 save 메서드 추가
        self.updated_at = datetime.datetime.now()
        return super().save(*args, **kwargs)
    
    # Detailed step status tracking
    ocr_status = CharField(default='pending')  # pending, running, completed, failed
    ocr_error = TextField(null=True)
    ocr_completed_at = DateTimeField(null=True)
    
    metadata_status = CharField(default='pending')  # pending, running, completed, failed
    metadata_error = TextField(null=True)
    metadata_completed_at = DateTimeField(null=True)
    
    embedding_status = CharField(default='pending')  # pending, running, completed, failed
    embedding_error = TextField(null=True)
    embedding_completed_at = DateTimeField(null=True)
    
    chunking_status = CharField(default='pending')  # pending, running, completed, failed
    chunking_error = TextField(null=True)
    chunking_completed_at = DateTimeField(null=True)
    
    def update_progress(self, step: str, percentage: int):
        """Update job progress"""
        self.current_step = step
        self.progress_percentage = percentage
        self.save()
    
    def mark_completed(self):
        """Mark job as completed"""
        self.status = 'completed'
        self.progress_percentage = 100
        self.completed_at = datetime.datetime.now()
        self.save()
    
    def mark_failed(self, error_message: str):
        """Mark job as failed with error message"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = datetime.datetime.now()
        self.save()
    
    def update_step_status(self, step: str, status: str, error: str = None):
        """Update status for a specific step"""
        if step == 'ocr':
            self.ocr_status = status
            if error:
                self.ocr_error = error
            if status == 'completed':
                self.ocr_completed_at = datetime.datetime.now()
        elif step == 'metadata':
            self.metadata_status = status
            if error:
                self.metadata_error = error
            if status == 'completed':
                self.metadata_completed_at = datetime.datetime.now()
        elif step == 'embedding':
            self.embedding_status = status
            if error:
                self.embedding_error = error
            if status == 'completed':
                self.embedding_completed_at = datetime.datetime.now()
        elif step == 'chunking':
            self.chunking_status = status
            if error:
                self.chunking_error = error
            if status == 'completed':
                self.chunking_completed_at = datetime.datetime.now()
        self.save()
    
    def reset_step(self, step: str):
        """Reset a specific step to pending status"""
        if step == 'ocr':
            self.ocr_status = 'pending'
            self.ocr_error = None
            self.ocr_completed_at = None
        elif step == 'metadata':
            self.metadata_status = 'pending'
            self.metadata_error = None
            self.metadata_completed_at = None
        elif step == 'embedding':
            self.embedding_status = 'pending'
            self.embedding_error = None
            self.embedding_completed_at = None
        elif step == 'chunking':
            self.chunking_status = 'pending'
            self.chunking_error = None
            self.chunking_completed_at = None
        self.save()
    
    def get_step_info(self):
        """Get detailed step information"""
        return {
            'ocr': {
                'status': self.ocr_status,
                'error': self.ocr_error,
                'completed_at': self.ocr_completed_at.isoformat() if self.ocr_completed_at else None
            },
            'metadata': {
                'status': self.metadata_status,
                'error': self.metadata_error,
                'completed_at': self.metadata_completed_at.isoformat() if self.metadata_completed_at else None
            },
            'embedding': {
                'status': self.embedding_status,
                'error': self.embedding_error,
                'completed_at': self.embedding_completed_at.isoformat() if self.embedding_completed_at else None
            },
            'chunking': {
                'status': self.chunking_status,
                'error': self.chunking_error,
                'completed_at': self.chunking_completed_at.isoformat() if self.chunking_completed_at else None
            }
        }
    
    def get_parameters(self) -> dict:
        """Get parameters as dictionary"""
        if self.parameters:
            try:
                return json.loads(self.parameters)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_parameters(self, parameters: dict):
        """Set parameters from dictionary"""
        self.parameters = json.dumps(parameters) if parameters else None
    
    def get_result(self) -> dict:
        """Get result as dictionary"""
        if self.result:
            try:
                return json.loads(self.result)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_result(self, result: dict):
        """Set result from dictionary"""
        self.result = json.dumps(result) if result else None

class PageText(BaseModel):
    paper = ForeignKeyField(Paper, backref='page_texts', on_delete='CASCADE')
    page_number = IntegerField()
    text = TextField()
    created_at = DateTimeField(default=datetime.datetime.now)
    
    class Meta:
        indexes = (
            (('paper', 'page_number'), True),  # Ensure unique page text per paper
        )

class SemanticChunk(BaseModel):
    paper = ForeignKeyField(Paper, backref='semantic_chunks', on_delete='CASCADE')
    text = TextField()
    page_number = IntegerField()
    chunk_index_on_page = IntegerField()
    chunk_type = CharField(default='paragraph')  # 'paragraph', 'sentence_group', 'fallback_split'
    start_char = IntegerField(null=True)  # Position within page text
    end_char = IntegerField(null=True)    # End position within page text
    bbox_x0 = FloatField(null=True)       # Bounding box coordinates (if available)
    bbox_y0 = FloatField(null=True)
    bbox_x1 = FloatField(null=True)
    bbox_y1 = FloatField(null=True)
    embedding_id = CharField(unique=True) # Stores the corresponding ID from ChromaDB
    created_at = DateTimeField(default=datetime.datetime.now)
    
    def get_bbox(self):
        """Get bounding box as a list [x0, y0, x1, y1]"""
        if all(coord is not None for coord in [self.bbox_x0, self.bbox_y0, self.bbox_x1, self.bbox_y1]):
            return [self.bbox_x0, self.bbox_y0, self.bbox_x1, self.bbox_y1]
        return None
    
    def set_bbox(self, bbox):
        """Set bounding box from a list [x0, y0, x1, y1]"""
        if bbox and len(bbox) >= 4:
            self.bbox_x0, self.bbox_y0, self.bbox_x1, self.bbox_y1 = bbox[:4]
        else:
            self.bbox_x0 = self.bbox_y0 = self.bbox_x1 = self.bbox_y1 = None
    
    class Meta:
        indexes = (
            # Ensure unique chunk per page and position
            (('paper', 'page_number', 'chunk_index_on_page'), True),
            # Index for efficient querying by embedding_id
            (('embedding_id',), False),
            # Index for efficient querying by chunk type
            (('chunk_type',), False),
        )

class ZoteroLink(BaseModel):
    paper = ForeignKeyField(Paper, backref='zotero_link', unique=True, on_delete='CASCADE')
    zotero_key = CharField(unique=True, index=True)
    zotero_version = IntegerField()
    library_id = CharField()
    collection_keys = TextField(null=True)  # JSON array
    tags = TextField(null=True)  # JSON array
    imported_at = DateTimeField(default=datetime.datetime.now)
    
    def get_collection_keys(self) -> List[str]:
        """Get collection keys as a list"""
        if self.collection_keys:
            try:
                return json.loads(self.collection_keys)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_collection_keys(self, keys: List[str]):
        """Set collection keys from a list"""
        self.collection_keys = json.dumps(keys)
    
    def get_tags(self) -> List[str]:
        """Get tags as a list"""
        if self.tags:
            try:
                return json.loads(self.tags)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_tags(self, tags: List[str]):
        """Set tags from a list"""
        self.tags = json.dumps(tags)

class ZoteroItem(BaseModel):
    """Stores complete Zotero item metadata - includes all item types including attachments"""
    zotero_key = CharField(unique=True, index=True)
    library_id = CharField(index=True)
    item_type = CharField()  # journalArticle, book, webpage, note, attachment, etc.
    data = TextField()  # JSON - complete Zotero item data
    version = IntegerField()
    user = ForeignKeyField(User, backref='zotero_items')
    parent_key = CharField(null=True)  # For child items (notes, attachments)
    is_attachment = BooleanField(default=False)  # Flag for attachment items
    content_type = CharField(null=True)  # For attachments: application/pdf, text/html, etc.
    filename = CharField(null=True)  # For attachments
    link_mode = CharField(null=True)  # For attachments: linked_file, imported_file, linked_url
    url = CharField(null=True)  # For linked attachments
    created_date = DateTimeField(null=True)  # Zotero's dateAdded
    modified_date = DateTimeField(null=True)  # Zotero's dateModified
    synced_at = DateTimeField(default=datetime.datetime.now)
    
    # Search optimization fields
    title = CharField(null=True, index=True)
    authors_text = TextField(null=True)  # "Author1; Author2; Author3"
    journal = CharField(null=True, index=True)
    year = IntegerField(null=True, index=True)
    doi = CharField(null=True, index=True)
    abstract = TextField(null=True)
    
    def get_data(self) -> dict:
        """Get data as dictionary"""
        try:
            return json.loads(self.data)
        except json.JSONDecodeError:
            return {}
    
    def set_data(self, data: dict):
        """Set data from dictionary"""
        self.data = json.dumps(data)
    
    def is_pdf_attachment(self) -> bool:
        """Check if this is a PDF attachment"""
        return self.is_attachment and self.content_type == 'application/pdf'
    
    def get_authors_list(self) -> List[str]:
        """Get authors as a list"""
        if self.authors_text:
            return [author.strip() for author in self.authors_text.split(';') if author.strip()]
        return []
    
    def set_authors_from_creators(self, creators: List[dict]):
        """Set authors from Zotero creators data"""
        authors = []
        for creator in creators:
            if creator.get('creatorType') == 'author':
                name_parts = []
                if creator.get('firstName'):
                    name_parts.append(creator['firstName'])
                if creator.get('lastName'):
                    name_parts.append(creator['lastName'])
                if name_parts:
                    authors.append(' '.join(name_parts))
        self.authors_text = '; '.join(authors) if authors else None
    
    def extract_year_from_date(self, date_str: str) -> Optional[int]:
        """Extract year from Zotero date string"""
        if not date_str:
            return None
        # Zotero 날짜 형식: "2023-01-15", "2023", "01/2023" 등
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', str(date_str))
        return int(year_match.group()) if year_match else None
    
    class Meta:
        indexes = (
            (('library_id', 'zotero_key'), True),  # Unique per library
            (('user', 'item_type'), False),  # For filtering by type
            (('parent_key',), False),  # For finding child items
            (('is_attachment', 'content_type'), False),  # For finding attachments
        )

class ZoteroCollection(BaseModel):
    """Stores Zotero collection hierarchy"""
    collection_key = CharField(index=True)
    library_id = CharField(index=True)
    name = CharField()
    parent_key = CharField(null=True)  # For subcollections
    user = ForeignKeyField(User, backref='zotero_collections')
    data = TextField(null=True)  # JSON - additional collection data
    version = IntegerField()
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)
    
    class Meta:
        indexes = (
            (('collection_key', 'user'), True),  # Unique per user
        )
    
    def get_data(self) -> dict:
        """Get additional data as dictionary"""
        if self.data:
            try:
                return json.loads(self.data)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_data(self, data: dict):
        """Set additional data from dictionary"""
        self.data = json.dumps(data) if data else None

class ZoteroCollectionItem(BaseModel):
    """Many-to-many relationship between ZoteroCollections and ZoteroItems"""
    collection = ForeignKeyField(ZoteroCollection, backref='item_links')
    item = ForeignKeyField(ZoteroItem, backref='collection_links')
    created_at = DateTimeField(default=datetime.datetime.now)
    
    class Meta:
        indexes = (
            (('collection', 'item'), True),  # Unique relationship
        )

class ZoteroItemPaper(BaseModel):
    """Many-to-many relationship between Zotero items and Papers"""
    zotero_item = ForeignKeyField(ZoteroItem, backref='paper_links')
    paper = ForeignKeyField(Paper, backref='zotero_links')
    relationship_type = CharField(default='attachment')  # 'attachment', 'note', 'child'
    created_at = DateTimeField(default=datetime.datetime.now)
    
    class Meta:
        indexes = (
            (('zotero_item', 'paper'), True),  # Unique relationship
            (('paper', 'relationship_type'), False),  # For finding all Zotero items for a paper
        )

class PotentialDuplicate(BaseModel):
    """Stores potential duplicate relationships between papers"""
    paper1 = ForeignKeyField(Paper, backref='potential_duplicates_as_paper1')
    paper2 = ForeignKeyField(Paper, backref='potential_duplicates_as_paper2')
    similarity_score = FloatField()  # Cosine similarity score (0.0 to 1.0)
    detection_method = CharField(default='embedding')  # 'embedding', 'metadata', 'hybrid'
    status = CharField(default='pending')  # 'pending', 'resolved', 'ignored'
    resolved_by = ForeignKeyField(User, backref='resolved_duplicates', null=True)
    resolved_at = DateTimeField(null=True)
    resolution_action = CharField(null=True)  # 'merge', 'keep_both', 'delete_duplicate'
    created_at = DateTimeField(default=datetime.datetime.now)
    
    class Meta:
        indexes = (
            (('paper1', 'paper2'), True),  # Unique relationship
            (('status',), False),  # For filtering by status
            (('similarity_score',), False),  # For sorting by similarity
        )
    
    def get_other_paper(self, paper):
        """Get the other paper in this duplicate relationship"""
        if self.paper1 == paper:
            return self.paper2
        elif self.paper2 == paper:
            return self.paper1
        else:
            return None

class UserAuditLog(BaseModel):
    """Audit log for user management actions"""
    timestamp = DateTimeField(default=datetime.datetime.now)
    performing_user = ForeignKeyField(User, backref='performed_actions', on_delete='SET NULL', null=True)
    performing_username = CharField()  # Store username for cases where user is deleted
    affected_user = ForeignKeyField(User, backref='audit_logs', on_delete='SET NULL', null=True)
    affected_username = CharField()  # Store username for cases where user is deleted
    action = CharField()  # 'user_created', 'user_updated', 'user_deleted', 'password_changed', 'admin_status_changed'
    details = TextField(null=True)  # JSON blob for extra info
    ip_address = CharField(null=True)
    user_agent = CharField(null=True)
    
    class Meta:
        table_name = 'user_audit_log'
        indexes = [
            (('timestamp',), False),
            (('performing_user', 'timestamp'), False),
            (('affected_user', 'timestamp'), False),
            (('action', 'timestamp'), False),
        ]
    
    def get_details(self) -> dict:
        """Get details as dictionary"""
        if self.details:
            try:
                return json.loads(self.details)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_details(self, details: dict):
        """Set details from dictionary"""
        self.details = json.dumps(details)

def create_tables():
    """Create all database tables"""
    with db:
        db.create_tables([User, Paper, Metadata, ProcessingJob, PageText, SemanticChunk, ZoteroLink, ZoteroItem, ZoteroCollection, ZoteroCollectionItem, ZoteroItemPaper, PotentialDuplicate, UserAuditLog])

def create_admin_user():
    """Create default admin user if it doesn't exist"""
    try:
        User.get(User.username == 'admin')
    except User.DoesNotExist:
        admin_user = User(username='admin', is_admin=True)
        admin_user.set_password('admin123')
        admin_user.save()

def run_migrations(database_path: str):
    """Run database migrations"""
    from peewee_migrate import Router
    router = Router(db, migrate_dir='migrations')
    router.run()

def init_database(database_path: str):
    """Initialize database connection"""
    db.init(database_path)
    
    # Configure SQLite for better concurrency and performance
    try:
        print("🔧 Configuring SQLite for optimal performance...")
        db.execute_sql('PRAGMA journal_mode=WAL;')        # Enable WAL mode for better concurrency
        db.execute_sql('PRAGMA synchronous=NORMAL;')      # Balanced durability vs performance
        db.execute_sql('PRAGMA cache_size=1000;')         # 1MB cache
        db.execute_sql('PRAGMA temp_store=memory;')       # Store temp tables in memory
        db.execute_sql('PRAGMA busy_timeout=30000;')      # 30 second timeout for locks
        print("✅ SQLite configuration applied successfully")
    except Exception as e:
        print(f"⚠️ Failed to configure SQLite settings: {str(e)}")
    
    # Run migrations
    try:
        run_migrations(database_path)
        print("✅ Database migrations completed successfully")
    except Exception as e:
        print(f"⚠️ Migration error (might be normal if tables already exist): {str(e)}")
        # Fallback to create_tables if migrations fail
        create_tables()
    
    create_admin_user()