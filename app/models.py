from peewee import *
import datetime
import json
import warnings
from typing import List, Optional
from passlib.context import CryptContext

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
    is_admin = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.datetime.now)
    last_login = DateTimeField(null=True)
    
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

class Paper(BaseModel):
    doc_id = CharField(primary_key=True)
    filename = CharField()
    file_path = CharField()
    ocr_text = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)
    
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
    updated_at = DateTimeField(default=datetime.datetime.now) # <-- 이 줄 추가
    completed_at = DateTimeField(null=True)
    
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

def create_tables():
    """Create all database tables"""
    with db:
        db.create_tables([User, Paper, Metadata, ProcessingJob, PageText, SemanticChunk, ZoteroLink])

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