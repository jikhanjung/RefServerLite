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
    completed_at = DateTimeField(null=True)
    
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

def create_tables():
    """Create all database tables"""
    with db:
        db.create_tables([User, Paper, Metadata, ProcessingJob, PageText])

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
    
    # Run migrations
    try:
        run_migrations(database_path)
        print("✅ Database migrations completed successfully")
    except Exception as e:
        print(f"⚠️ Migration error (might be normal if tables already exist): {str(e)}")
        # Fallback to create_tables if migrations fail
        create_tables()
    
    create_admin_user()