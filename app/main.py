from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form, Depends, Body
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from typing import Optional, List
import os
import uuid
from pathlib import Path
import datetime
from datetime import timedelta
import numpy as np
import logging
import asyncio

from .models import init_database, Paper, Metadata, ProcessingJob, User, PageText, SemanticChunk, ZoteroLink, PotentialDuplicate, UserAuditLog, ZoteroItem, ZoteroCollection, ZoteroCollectionItem, ZoteroItemPaper, db
from .db import get_chromadb_client, get_or_create_collection, get_embedding_from_chroma
from .pipeline import start_background_processor, PDFProcessingPipeline
from .auth import create_access_token, require_admin, check_session_auth, get_current_user, require_session_user, require_session_admin
from .visualize import visualize_embedding_bar, visualize_embedding_heatmap, visualize_embedding_histogram
from .visualize_3d import visualize_embedding_3d_bidirectional, visualize_embedding_3d_unidirectional, visualize_embedding_3d_surface

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="RefServerLite", version="1.0.0")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-in-production")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="app/templates")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    print("🚀 Starting RefServerLite startup process...")
    
    try:
        print("📁 Initializing SQLite database...")
        # Initialize SQLite database
        db_path = Path("refdata/refserver.db")
        db_path.parent.mkdir(exist_ok=True)
        init_database(str(db_path))
        print("✅ SQLite database initialized successfully")
        
        print("🔗 Initializing ChromaDB...")
        # Initialize ChromaDB
        client = get_chromadb_client()
        print("✅ ChromaDB client created")
        
        collection = get_or_create_collection(client)
        print("✅ ChromaDB collection ready")
        
        app.state.chroma_client = client
        app.state.chroma_collection = collection
        
        print("🎉 RefServerLite startup completed successfully!")
        
        # Start background processor after startup completes
        print("⚙️ Starting background processor...")
        start_background_processor()
        print("✅ Background processor started")
        
    except Exception as e:
        print(f"❌ Startup failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

# Root endpoint - display upload page
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Landing page"""
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Upload page"""
    user = check_session_auth(request)
    return templates.TemplateResponse("upload.html", {
        "request": request, 
        "current_user": user
    })

@app.get("/document/{doc_id}", response_class=HTMLResponse)
async def document_view(request: Request, doc_id: str):
    """Document view page (accessible to any authenticated user)"""
    user = check_session_auth(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        # Get the document
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Check if user can access this document (admins can see all, users can see their own)
        if not user.is_admin and paper.uploaded_by != user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get metadata if available
        metadata = None
        try:
            metadata = Metadata.get(Metadata.paper == paper)
        except Metadata.DoesNotExist:
            pass
        
        # Get page texts
        page_texts = list(PageText.select().where(PageText.paper == paper).order_by(PageText.page_number))
        
        # Get processing jobs for this paper
        jobs = list(ProcessingJob.select().where(ProcessingJob.paper == paper).order_by(ProcessingJob.created_at.desc()))
        
        # Get semantic chunks
        chunks = SemanticChunk.select().where(SemanticChunk.paper == paper).order_by(
            SemanticChunk.page_number, 
            SemanticChunk.chunk_index_on_page
        )
        
        # Get ZoteroLink if exists
        zotero_link = None
        try:
            zotero_link = ZoteroLink.get(ZoteroLink.paper == paper)
        except ZoteroLink.DoesNotExist:
            pass
        
        # Get page embeddings and document embedding from ChromaDB
        page_embeddings = {}
        document_embedding = None
        try:
            logger.info(f"Attempting to get ChromaDB collection for document {doc_id}")
            collection = app.state.chroma_collection
            logger.info(f"Successfully got ChromaDB collection: {collection}")
            
            if not collection:
                logger.warning("ChromaDB collection is None")
                raise Exception("ChromaDB collection is None")
            
            # Get document-level embedding
            try:
                doc_result = collection.get(ids=[doc_id], include=['embeddings'])
                if doc_result['embeddings'] is not None and len(doc_result['embeddings']) > 0:
                    # Get first 10 values from document embedding vector and convert to list
                    document_embedding = doc_result['embeddings'][0][:10].tolist()
            except Exception as e:
                # Skip if document embedding not found
                pass
            
            # Get page embeddings
            for page_text in page_texts:
                page_doc_id = f"{doc_id}_page_{page_text.page_number}"
                try:
                    result = collection.get(ids=[page_doc_id], include=['embeddings'])
                    if result['embeddings'] is not None and len(result['embeddings']) > 0:
                        # Get first 10 values from embedding vector and convert to list
                        embedding = result['embeddings'][0][:10].tolist()
                        page_embeddings[page_text.page_number] = embedding
                        logger.info(f"Found page embedding for page {page_text.page_number}: {len(embedding)} values")
                    else:
                        logger.warning(f"No embedding found for page_doc_id: {page_doc_id}")
                except Exception as e:
                    # Skip if embedding not found for this page
                    logger.error(f"Error getting page embedding for {page_doc_id}: {str(e)}")
                    continue
        except Exception as e:
            # If ChromaDB is not available, continue without embeddings
            logger.error(f"ChromaDB error when getting embeddings: {str(e)}")
            pass
        
        logger.info(f"Rendering document template with {len(page_embeddings)} page embeddings")
        for page_num, embedding in page_embeddings.items():
            logger.info(f"  Page {page_num}: {len(embedding)} embedding values")
        
        return templates.TemplateResponse("document.html", {
            "request": request,
            "current_user": user,
            "paper": paper,
            "metadata": metadata,
            "jobs": jobs,
            "page_texts": page_texts,
            "page_embeddings": page_embeddings,
            "document_embedding": document_embedding,
            "chunks": list(chunks),
            "zotero_link": zotero_link
        })
        
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")

# Authentication endpoints
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page"""
    # Redirect based on user role if already logged in
    user = check_session_auth(request)
    if user:
        if user.is_admin:
            return RedirectResponse(url="/admin", status_code=302)
        else:
            return RedirectResponse(url="/dashboard", status_code=302)
    
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login form submission"""
    try:
        user = User.get(User.username == username)
        if user.verify_password(password):
            # Set session
            request.session["username"] = username
            user.update_last_login()
            
            # Redirect based on user role
            if user.is_admin:
                return RedirectResponse(url="/admin", status_code=302)
            else:
                return RedirectResponse(url="/dashboard", status_code=302)
        else:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Invalid credentials"
            })
    except User.DoesNotExist:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid credentials"
        })

@app.post("/logout")
async def logout(request: Request):
    """Handle logout"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

# API Authentication
@app.post("/api/v1/auth/login")
async def api_login(username: str = Form(...), password: str = Form(...)):
    """API login endpoint"""
    try:
        user = User.get(User.username == username)
        if user.verify_password(password) and user.is_admin:
            access_token_expires = timedelta(minutes=480)
            access_token = create_access_token(
                data={"sub": user.username}, expires_delta=access_token_expires
            )
            user.update_last_login()
            return {"access_token": access_token, "token_type": "bearer"}
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except User.DoesNotExist:
        raise HTTPException(status_code=401, detail="Invalid credentials")

# API endpoints
@app.post("/api/v1/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a PDF file for processing"""
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Generate unique job ID and document ID
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    
    # Save uploaded file
    upload_dir = Path("refdata/pdfs")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{doc_id}_{file.filename}"
    
    try:
        contents = await file.read()
        with open(file_path, 'wb') as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Create database entries
    try:
        # Create Paper entry
        paper = Paper.create(
            doc_id=doc_id,
            filename=file.filename,
            file_path=str(file_path),
            uploaded_by=current_user
        )
        
        # Create ProcessingJob entry
        job = ProcessingJob.create(
            job_id=job_id,
            paper=paper,
            filename=file.filename,
            status='uploaded',
            user_id=current_user
        )
        
        # Let the background processor handle this job (started on server startup)
        # Background processor will pick this up automatically
        
        return {
            "job_id": job_id,
            "filename": file.filename,
            "message": "File uploaded successfully. Processing started in background.",
            "status": "pending"
        }
    except Exception as e:
        # Clean up file if database entry fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/v1/papers/upload_with_metadata")
async def upload_with_metadata(
    file: UploadFile = File(...),
    title: str = Form(...),
    authors: str = Form(...),  # JSON string
    year: Optional[int] = Form(None),
    zotero_key: Optional[str] = Form(None),
    zotero_library_id: Optional[str] = Form(None),
    zotero_version: Optional[int] = Form(None),
    collection_keys: Optional[str] = Form(None),  # JSON string
    tags: Optional[str] = Form(None),  # JSON string
    current_user: User = Depends(get_current_user)
):
    """Upload a PDF file with metadata (requires authentication)"""
    # Check admin permission
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Check for duplicate Zotero key if provided
    if zotero_key:
        existing_link = ZoteroLink.select().where(ZoteroLink.zotero_key == zotero_key).first()
        if existing_link:
            raise HTTPException(
                status_code=409, 
                detail=f"Document with Zotero key '{zotero_key}' already exists (doc_id: {existing_link.paper.doc_id})"
            )
    
    # Generate unique IDs
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    
    # Save uploaded file
    upload_dir = Path("refdata/pdfs")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{doc_id}_{file.filename}"
    
    try:
        contents = await file.read()
        with open(file_path, 'wb') as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    try:
        # Create Paper entry
        paper = Paper.create(
            doc_id=doc_id,
            filename=file.filename,
            file_path=str(file_path),
            uploaded_by=current_user
        )
        
        # Create Metadata entry with user-provided data
        metadata = Metadata.create(
            paper=paper,
            title=title,
            authors=authors,  # Already JSON string
            year=year,
            source='user_api'  # Mark as user-provided
        )
        
        # Create ZoteroLink if Zotero data provided
        if zotero_key and zotero_library_id:
            zotero_link = ZoteroLink.create(
                paper=paper,
                zotero_key=zotero_key,
                library_id=zotero_library_id,
                zotero_version=zotero_version or 0,
                collection_keys=collection_keys,
                tags=tags
            )
        
        # Create ProcessingJob entry
        job = ProcessingJob.create(
            job_id=job_id,
            paper=paper,
            filename=file.filename,
            status='uploaded',
            user_id=current_user
        )
        
        # Start processing
        job.status = 'processing'
        job.save()
        
        return {
            "job_id": job_id,
            "doc_id": doc_id,
            "filename": file.filename,
            "message": "File uploaded successfully with metadata. Processing started.",
            "status": "processing"
        }
        
    except Exception as e:
        # Clean up file if database entry fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/v1/job/{job_id}")
async def get_job_status(job_id: str, current_user: User = Depends(get_current_user)):
    """Get the status of a processing job (admin only)"""
    # Require admin access
    require_admin(current_user)
    try:
        job = ProcessingJob.get(ProcessingJob.job_id == job_id)
        response = {
            "job_id": job.job_id,
            "filename": job.filename,
            "status": job.status,
            "current_step": job.current_step,
            "progress_percentage": job.progress_percentage
        }
        
        if job.status == 'completed' and job.paper:
            response["result"] = {"doc_id": job.paper.doc_id}
        elif job.status == 'failed':
            response["error"] = job.error_message
            
        return response
    except ProcessingJob.DoesNotExist:
        raise HTTPException(status_code=404, detail="Job not found")

@app.post("/api/v1/job/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: User = Depends(require_admin)):
    """Cancel a running job (admin only)"""
    try:
        job = ProcessingJob.get(ProcessingJob.job_id == job_id)
        
        # Check if job can be cancelled
        if job.status not in ['pending', 'processing']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{job.status}'. Only pending or processing jobs can be cancelled."
            )
        
        # Update job status to cancelled
        job.status = 'cancelled'
        job.current_step = 'cancelled'
        job.error_message = f"Job cancelled by admin {current_user.username}"
        job.completed_at = datetime.datetime.now()
        job.save()
        
        return {
            "success": True,
            "message": f"Job {job_id} has been cancelled successfully",
            "job_id": job_id,
            "status": job.status
        }
        
    except ProcessingJob.DoesNotExist:
        raise HTTPException(status_code=404, detail="Job not found")
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel job")

@app.post("/api/v1/jobs/cancel-all")
async def cancel_all_jobs(
    job_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    current_user: User = Depends(require_admin)
):
    """Cancel all jobs or jobs of specific type/status (admin only)"""
    import datetime
    try:
        # Build query for jobs to cancel
        query = ProcessingJob.select()
        
        # Filter by job type if specified
        if job_type:
            query = query.where(ProcessingJob.job_type == job_type)
        
        # Filter by status if specified, otherwise default to pending/processing
        if status_filter:
            if status_filter in ['pending', 'processing', 'cancelled', 'completed', 'failed']:
                query = query.where(ProcessingJob.status == status_filter)
        else:
            # Default: only cancel pending/processing jobs
            query = query.where(ProcessingJob.status.in_(['pending', 'processing']))
        
        jobs_to_cancel = list(query)
        cancelled_count = 0
        
        if not jobs_to_cancel:
            return {
                "success": True,
                "message": "No jobs found to cancel",
                "cancelled_count": 0,
                "jobs": []
            }
        
        cancelled_jobs = []
        
        for job in jobs_to_cancel:
            # Skip already completed/cancelled jobs unless explicitly requested
            if job.status not in ['pending', 'processing'] and not status_filter:
                continue
                
            # Update job status
            job.status = 'cancelled'
            job.current_step = 'cancelled'
            job.error_message = f"Bulk cancelled by admin {current_user.username}"
            job.completed_at = datetime.datetime.now()
            job.save()
            
            cancelled_count += 1
            cancelled_jobs.append({
                "job_id": job.job_id,
                "job_type": job.job_type,
                "filename": job.filename,
                "previous_status": job.status,
                "cancelled_at": job.completed_at.isoformat()
            })
        
        logger.info(f"Admin {current_user.username} cancelled {cancelled_count} jobs")
        
        return {
            "success": True,
            "message": f"Successfully cancelled {cancelled_count} job{'s' if cancelled_count != 1 else ''}",
            "cancelled_count": cancelled_count,
            "jobs": cancelled_jobs
        }
        
    except Exception as e:
        logger.error(f"Error cancelling all jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel jobs")

@app.post("/api/v1/admin/database/reset")
async def reset_database(
    confirmation: str = Form(...),
    current_user: User = Depends(require_admin)
):
    """Reset the entire database (admin only) - DANGER ZONE"""
    import os
    import shutil
    import datetime
    
    # Security check: require explicit confirmation
    if confirmation != "RESET_ALL_DATA":
        raise HTTPException(
            status_code=400, 
            detail="Invalid confirmation. Must provide confirmation='RESET_ALL_DATA'"
        )
    
    try:
        logger.warning(f"🚨 DANGER: Admin {current_user.username} is resetting the entire database!")
        
        # Get database path
        database_path = db.database
        chromadb_path = "/app/refdata/chromadb"
        pdfs_path = "/app/refdata/pdfs"
        
        deleted_items = {
            "database": False,
            "chromadb": False,
            "pdfs": False,
            "admin_recreated": False
        }
        
        # 1. Cancel all running jobs first
        try:
            running_jobs = ProcessingJob.select().where(ProcessingJob.status.in_(['pending', 'processing']))
            for job in running_jobs:
                job.status = 'cancelled'
                job.error_message = 'Cancelled due to database reset'
                job.completed_at = datetime.datetime.now()
                job.save()
            logger.info(f"✅ Cancelled {running_jobs.count()} running jobs")
        except Exception as e:
            logger.warning(f"⚠️ Could not cancel jobs: {e}")
        
        # 2. Close ChromaDB client connections (if possible)
        try:
            # Force garbage collection to close any open connections
            import gc
            gc.collect()
            logger.info("✅ Triggered garbage collection")
        except Exception as e:
            logger.warning(f"⚠️ Garbage collection warning: {e}")
        
        # 3. Close database connection
        try:
            if not db.is_closed():
                db.close()
            logger.info("✅ Closed database connection")
        except Exception as e:
            logger.warning(f"⚠️ Database close warning: {e}")
        
        # 4. Delete SQLite database file with retry
        for attempt in range(3):
            try:
                if os.path.exists(database_path):
                    os.remove(database_path)
                    deleted_items["database"] = True
                    logger.info("✅ Deleted SQLite database")
                break
            except Exception as e:
                if attempt == 2:
                    logger.error(f"❌ Failed to delete database after 3 attempts: {e}")
                    raise
                logger.warning(f"⚠️ Database delete attempt {attempt + 1} failed, retrying: {e}")
                import time
                time.sleep(1)
        
        # 5. Delete ChromaDB data with retry
        for attempt in range(3):
            try:
                if os.path.exists(chromadb_path):
                    shutil.rmtree(chromadb_path, ignore_errors=True)
                    deleted_items["chromadb"] = True
                    logger.info("✅ Deleted ChromaDB data")
                break
            except Exception as e:
                if attempt == 2:
                    logger.error(f"❌ Failed to delete ChromaDB after 3 attempts: {e}")
                    # Continue anyway, not critical
                logger.warning(f"⚠️ ChromaDB delete attempt {attempt + 1} failed, retrying: {e}")
                import time
                time.sleep(1)
        
        # 6. Delete PDF files with retry
        for attempt in range(3):
            try:
                if os.path.exists(pdfs_path):
                    shutil.rmtree(pdfs_path, ignore_errors=True)
                    os.makedirs(pdfs_path, exist_ok=True)
                    deleted_items["pdfs"] = True
                    logger.info("✅ Deleted PDF files")
                break
            except Exception as e:
                if attempt == 2:
                    logger.error(f"❌ Failed to delete PDFs after 3 attempts: {e}")
                    # Continue anyway, not critical
                logger.warning(f"⚠️ PDFs delete attempt {attempt + 1} failed, retrying: {e}")
                import time
                time.sleep(1)
        
        # 5. Reinitialize database and recreate admin user
        try:
            # Reinitialize the database with fresh schema
            from app.models import init_database
            init_database(database_path)
            logger.info("✅ Database reinitialized with fresh schema")
            
            # Recreate database connection
            db.init(database_path)
            
            # Create new admin user with same username/email as current user
            try:
                admin_user = User.create(
                    username=current_user.username,
                    email=current_user.email or '',
                    is_admin=True
                )
                admin_user.set_password('admin123')  # Default password, user should change
                admin_user.save()
                deleted_items["admin_recreated"] = True
                logger.info(f"✅ Recreated admin user: {current_user.username}")
            except Exception as user_error:
                # Fallback to default admin
                logger.warning(f"⚠️ Could not recreate current admin user ({user_error}), creating default admin")
                admin_user = User.create(username='admin', email='', is_admin=True)
                admin_user.set_password('admin123')
                admin_user.save()
                deleted_items["admin_recreated"] = True
                logger.info("✅ Created default admin user")
                
        except Exception as e:
            logger.error(f"❌ Failed to reinitialize database: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to reinitialize database: {e}")
        
        # 6. Reinitialize ChromaDB
        try:
            from app.embedding import get_chroma_client
            client = get_chroma_client()
            # ChromaDB will be recreated on first use
            logger.info("✅ ChromaDB client reinitialized")
        except Exception as e:
            logger.warning(f"ChromaDB reinit warning: {e}")
        
        logger.warning(f"🔥 DATABASE RESET COMPLETE by admin {current_user.username}")
        
        return {
            "success": True,
            "message": "Database has been completely reset",
            "reset_by": current_user.username,
            "reset_at": datetime.datetime.now().isoformat(),
            "deleted_items": deleted_items,
            "warning": "All data has been permanently deleted. Admin password reset to 'admin123'."
        }
        
    except Exception as e:
        logger.error(f"❌ Error resetting database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset database: {str(e)}")

@app.post("/api/v1/admin/database/soft-reset")
async def soft_reset_database(
    confirmation: str = Form(...),
    current_user: User = Depends(require_admin)
):
    """Soft reset: Clear documents and data but preserve users and settings (admin only)"""
    import os
    import shutil
    import datetime
    
    # Security check: require explicit confirmation
    if confirmation != "SOFT_RESET_DATA":
        raise HTTPException(
            status_code=400, 
            detail="Invalid confirmation. Must provide confirmation='SOFT_RESET_DATA'"
        )
    
    try:
        logger.warning(f"🔄 Admin {current_user.username} is performing soft database reset (preserving users)")
        
        chromadb_path = "/app/refdata/chromadb"
        pdfs_path = "/app/refdata/pdfs"
        
        deleted_items = {
            "papers": 0,
            "metadata": 0,
            "processing_jobs": 0,
            "page_texts": 0,
            "semantic_chunks": 0,
            "zotero_items": 0,
            "zotero_collections": 0,
            "zotero_item_papers": 0,
            "potential_duplicates": 0,
            "chromadb": False,
            "pdfs": False
        }
        
        # 1. Cancel all running jobs first
        try:
            running_jobs = ProcessingJob.select().where(ProcessingJob.status.in_(['pending', 'processing']))
            for job in running_jobs:
                job.status = 'cancelled'
                job.error_message = 'Cancelled due to soft database reset'
                job.completed_at = datetime.datetime.now()
                job.save()
            logger.info(f"✅ Cancelled {running_jobs.count()} running jobs")
        except Exception as e:
            logger.warning(f"⚠️ Could not cancel jobs: {e}")
        
        # 2. Delete document-related table data (preserve users and settings)
        try:
            # Delete in reverse dependency order
            deleted_items["potential_duplicates"] = PotentialDuplicate.delete().execute()
            deleted_items["zotero_item_papers"] = ZoteroItemPaper.delete().execute()
            deleted_items["semantic_chunks"] = SemanticChunk.delete().execute()
            deleted_items["page_texts"] = PageText.delete().execute()
            deleted_items["processing_jobs"] = ProcessingJob.delete().execute()
            deleted_items["metadata"] = Metadata.delete().execute()
            deleted_items["papers"] = Paper.delete().execute()
            deleted_items["zotero_items"] = ZoteroItem.delete().execute()
            deleted_items["zotero_collections"] = ZoteroCollection.delete().execute()
            
            logger.info("✅ Deleted document-related table data")
            for table, count in deleted_items.items():
                if isinstance(count, int) and count > 0:
                    logger.info(f"  - {table}: {count} records deleted")
        except Exception as e:
            logger.error(f"❌ Error deleting table data: {e}")
            raise
        
        # 3. Clear ChromaDB data
        try:
            if os.path.exists(chromadb_path):
                shutil.rmtree(chromadb_path, ignore_errors=True)
                deleted_items["chromadb"] = True
                logger.info("✅ Deleted ChromaDB data")
        except Exception as e:
            logger.warning(f"⚠️ Could not delete ChromaDB: {e}")
        
        # 4. Clear PDF files
        try:
            if os.path.exists(pdfs_path):
                shutil.rmtree(pdfs_path, ignore_errors=True)
                os.makedirs(pdfs_path, exist_ok=True)
                deleted_items["pdfs"] = True
                logger.info("✅ Deleted PDF files")
        except Exception as e:
            logger.warning(f"⚠️ Could not delete PDFs: {e}")
        
        # 5. Reset users' last sync times
        try:
            User.update(zotero_last_sync=None).execute()
            logger.info("✅ Reset all users' last sync times")
        except Exception as e:
            logger.warning(f"⚠️ Could not reset sync times: {e}")
        
        total_records = sum(count for count in deleted_items.values() if isinstance(count, int))
        
        return {
            "success": True,
            "message": f"Soft database reset completed. Deleted {total_records} records while preserving users and settings.",
            "details": deleted_items,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error in soft database reset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to perform soft reset: {str(e)}")

@app.get("/api/v1/jobs")
async def get_jobs(
    request: Request,
    status: Optional[str] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0,
    order_by: Optional[str] = "created_at",
    current_user: User = Depends(get_current_user)
):
    """Get list of processing jobs (admin only)"""
    # Require admin access
    require_admin(current_user)
    
    try:
        # Build query
        query = ProcessingJob.select()
        
        # Apply status filter if provided
        if status:
            query = query.where(ProcessingJob.status == status)
        
        # Apply ordering
        if order_by == "created_at":
            query = query.order_by(ProcessingJob.created_at.desc())
        elif order_by == "status":
            query = query.order_by(ProcessingJob.status)
        else:
            query = query.order_by(ProcessingJob.created_at.desc())
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        
        # Execute query and format response
        jobs = []
        for job in query:
            job_data = {
                "job_id": job.job_id,
                "filename": job.filename,
                "status": job.status,
                "current_step": job.current_step,
                "progress_percentage": job.progress_percentage,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None
            }
            
            # Add result or error info
            if job.status == 'completed' and job.paper:
                job_data["result"] = {"doc_id": job.paper.doc_id}
            elif job.status == 'failed' and job.error_message:
                job_data["error"] = job.error_message
                
            jobs.append(job_data)
        
        # Get total count for pagination info
        total_query = ProcessingJob.select()
        if status:
            total_query = total_query.where(ProcessingJob.status == status)
        total_count = total_query.count()
        
        return {
            "jobs": jobs,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve jobs: {str(e)}")

@app.get("/api/v1/document/{doc_id}")
async def get_document(doc_id: str):
    """Get the processed data for a document"""
    try:
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Get metadata if exists
        metadata_dict = {}
        try:
            metadata = paper.metadata.get()
            metadata_dict = {
                "title": metadata.title,
                "authors": metadata.get_authors(),
                "journal": metadata.journal,
                "year": metadata.year,
                "abstract": metadata.abstract,
                "doi": metadata.doi
            }
        except Metadata.DoesNotExist:
            pass
        
        return {
            "doc_id": paper.doc_id,
            "filename": paper.filename,
            "metadata": metadata_dict,
            "text": paper.ocr_text or "",
            "created_at": paper.created_at.isoformat()
        }
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")

@app.get("/download/pdf/{doc_id}")
async def download_pdf(doc_id: str):
    """Download the original PDF file"""
    try:
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Check if file exists
        file_path = Path(paper.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found on server")
        
        # Return file with proper headers
        return FileResponse(
            path=str(file_path),
            media_type="application/pdf",
            filename=paper.filename,
            headers={
                "Content-Disposition": f"attachment; filename=\"{paper.filename}\"",
                "Cache-Control": "no-cache"
            }
        )
        
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")

@app.get("/preview/{doc_id}/{page_num}")
async def get_page_preview(doc_id: str, page_num: int):
    """Generate and serve page preview image on-demand"""
    try:
        # Check if paper exists
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Define preview file path
        preview_dir = Path("refdata/previews")
        preview_dir.mkdir(exist_ok=True)
        preview_path = preview_dir / f"{doc_id}_page_{page_num}.png"
        
        # Generate if doesn't exist
        if not preview_path.exists():
            generate_page_preview(paper.file_path, page_num, preview_path)
        
        return FileResponse(
            preview_path,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=86400",  # Cache for 1 day
                "ETag": f'"{doc_id}-{page_num}"'   # Enable conditional requests
            }
        )
        
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {str(e)}")

def generate_page_preview(pdf_path: str, page_num: int, output_path: Path):
    """Generate preview image for a specific PDF page"""
    import fitz  # PyMuPDF
    
    doc = fitz.open(pdf_path)
    
    if page_num < 1 or page_num > len(doc):
        doc.close()
        raise ValueError(f"Page {page_num} not found in document (total pages: {len(doc)})")
    
    try:
        page = doc[page_num - 1]  # Convert to 0-indexed
        
        # Generate image with good quality/size balance
        mat = fitz.Matrix(1.5, 1.5)  # 1.5x zoom for good quality
        pix = page.get_pixmap(matrix=mat)
        
        # Save as PNG
        pix.save(str(output_path))
        
    finally:
        doc.close()

@app.get("/api/v1/search")
async def search_documents(
    q: str,
    type: Optional[str] = "keyword",
    search_scope: Optional[str] = "pages",
    limit: Optional[int] = 10
):
    """Search for documents
    
    Search types:
    - keyword: Simple text search in documents
    - semantic: Semantic search using embeddings
    - document: Document-level semantic search
    
    Search scopes (for semantic search):
    - pages: Page-level search (default)
    - chunks: Semantic chunk-level search
    - documents: Document-level search
    - all: Search all levels and merge results
    """
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    
    results = []
    
    if type == "keyword":
        # Simple keyword search in SQLite
        papers = Paper.select().where(
            Paper.ocr_text.contains(q) | 
            Paper.filename.contains(q)
        ).limit(limit)
        
        for paper in papers:
            # Get metadata
            metadata_dict = {}
            try:
                metadata = paper.metadata.get()
                metadata_dict = {
                    "title": metadata.title,
                    "authors": metadata.get_authors(),
                    "journal": metadata.journal,
                    "year": metadata.year
                }
            except Metadata.DoesNotExist:
                pass
            
            results.append({
                "doc_id": paper.doc_id,
                "filename": paper.filename,
                "metadata": metadata_dict,
                "score": 1.0  # Simple presence score
            })
    
    elif type == "semantic":
        # Semantic search using ChromaDB
        try:
            collection = app.state.chroma_collection
            
            if search_scope == "chunks":
                # Search in semantic chunks
                search_results = collection.query(
                    query_texts=[q],
                    n_results=limit * 2,
                    where={"paper_id": {"$ne": None}}  # Only chunk-level embeddings
                )
                results = await _process_chunk_search_results(search_results, limit)
                
            elif search_scope == "documents":
                # Search in document-level embeddings
                search_results = collection.query(
                    query_texts=[q],
                    n_results=limit,
                    where={"is_document_level": True}  # Only document-level embeddings
                )
                results = await _process_document_search_results(search_results, limit)
                
            elif search_scope == "all":
                # Search across all levels and merge
                results = await _search_all_levels(collection, q, limit)
                
            else:  # search_scope == "pages" (default)
                # Search primarily in page-level embeddings
                search_results = collection.query(
                    query_texts=[q],
                    n_results=limit * 3,  # Get more results to filter and group
                    where={"is_document_level": False}  # Only page-level embeddings
                )
                results = await _process_page_search_results(search_results, limit)
            
            if search_results['ids'] and len(search_results['ids'][0]) > 0:
                doc_ids = search_results['ids'][0]
                distances = search_results['distances'][0]
                metadatas = search_results['metadatas'][0] if search_results['metadatas'] else []
                documents = search_results['documents'][0] if search_results['documents'] else []
                
                # Group results by document and collect page information
                doc_results = {}
                
                for idx, doc_id in enumerate(doc_ids):
                    try:
                        # Parse page-level doc_id to get original doc_id and page number
                        if "_page_" in doc_id:
                            original_doc_id, page_part = doc_id.split("_page_")
                            page_number = int(page_part)
                        else:
                            continue  # Skip if not a page-level result
                        
                        # Get paper metadata
                        paper = Paper.get(Paper.doc_id == original_doc_id)
                        
                        score = 1.0 - distances[idx]  # Convert distance to similarity score
                        snippet = documents[idx][:200] + "..." if len(documents[idx]) > 200 else documents[idx]
                        
                        if original_doc_id not in doc_results:
                            # Get document metadata
                            metadata_dict = {}
                            try:
                                metadata = paper.metadata.get()
                                metadata_dict = {
                                    "title": metadata.title,
                                    "authors": metadata.get_authors(),
                                    "journal": metadata.journal,
                                    "year": metadata.year
                                }
                            except Metadata.DoesNotExist:
                                pass
                            
                            doc_results[original_doc_id] = {
                                "doc_id": original_doc_id,
                                "filename": paper.filename,
                                "metadata": metadata_dict,
                                "pages": [],
                                "best_score": score,
                                "search_type": "page"
                            }
                        
                        # Add page result
                        doc_results[original_doc_id]["pages"].append({
                            "page": page_number,
                            "score": score,
                            "snippet": snippet
                        })
                        
                        # Update best score if this page has higher score
                        if score > doc_results[original_doc_id]["best_score"]:
                            doc_results[original_doc_id]["best_score"] = score
                        
                    except (Paper.DoesNotExist, ValueError):
                        continue
                
                # Sort pages within each document by score
                for doc_result in doc_results.values():
                    doc_result["pages"].sort(key=lambda x: x["score"], reverse=True)
                
                # Convert to list and sort by best score
                results = list(doc_results.values())
                results.sort(key=lambda x: x["best_score"], reverse=True)
                
                # Limit results
                results = results[:limit]
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")
    
    elif type == "document":
        # Document-level semantic search using ChromaDB
        try:
            collection = app.state.chroma_collection
            
            # Search only in document-level embeddings
            search_results = collection.query(
                query_texts=[q],
                n_results=limit,
                where={"is_document_level": True}  # Only document-level embeddings
            )
            
            if search_results['ids'] and len(search_results['ids'][0]) > 0:
                doc_ids = search_results['ids'][0]
                distances = search_results['distances'][0]
                
                for idx, doc_id in enumerate(doc_ids):
                    try:
                        paper = Paper.get(Paper.doc_id == doc_id)
                        
                        # Get metadata
                        metadata_dict = {}
                        try:
                            metadata = paper.metadata.get()
                            metadata_dict = {
                                "title": metadata.title,
                                "authors": metadata.get_authors(),
                                "journal": metadata.journal,
                                "year": metadata.year
                            }
                        except Metadata.DoesNotExist:
                            pass
                        
                        results.append({
                            "doc_id": paper.doc_id,
                            "filename": paper.filename,
                            "metadata": metadata_dict,
                            "score": 1.0 - distances[idx],  # Convert distance to similarity score
                            "search_type": "document"
                        })
                    except Paper.DoesNotExist:
                        continue
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")
    
    return {
        "query": q,
        "type": type,
        "results": results
    }

@app.get("/api/v1/admin/progress")
async def get_processing_progress():
    """Get processing progress for all documents"""
    papers = Paper.select().order_by(Paper.created_at.desc()).limit(50)
    
    progress_data = []
    for paper in papers:
        try:
            latest_job = paper.jobs.order_by(ProcessingJob.created_at.desc()).get()
            progress_data.append({
                "doc_id": paper.doc_id,
                "job_id": latest_job.job_id,
                "status": latest_job.status,
                "current_step": latest_job.current_step,
                "progress_percentage": latest_job.progress_percentage,
                "error_message": latest_job.error_message,
                "steps": latest_job.get_step_info()
            })
        except ProcessingJob.DoesNotExist:
            progress_data.append({
                "doc_id": paper.doc_id,
                "job_id": None,
                "status": "unknown",
                "current_step": None,
                "progress_percentage": 0,
                "error_message": None,
                "steps": {
                    "ocr": {"status": "pending", "error": None, "completed_at": None},
                    "metadata": {"status": "pending", "error": None, "completed_at": None},
                    "embedding": {"status": "pending", "error": None, "completed_at": None}
                }
            })
    
    return {"documents": progress_data}

@app.post("/api/v1/admin/rerun-step/{job_id}/{step}")
async def rerun_processing_step(job_id: str, step: str):
    """Re-run a specific processing step for a job"""
    try:
        job = ProcessingJob.get(ProcessingJob.job_id == job_id)
        
        # Validate step
        if step not in ['ocr', 'metadata', 'embedding', 'chunking']:
            raise HTTPException(status_code=400, detail="Invalid step name")
        
        # Reset the step status
        job.reset_step(step)
        
        # If re-running OCR, also reset subsequent steps
        if step == 'ocr':
            job.reset_step('metadata')
            job.reset_step('embedding')
        # If re-running metadata, also reset embedding
        elif step == 'metadata':
            job.reset_step('embedding')
        
        # Set job status back to processing if it was failed/completed
        if job.status in ['failed', 'completed']:
            job.status = 'processing'
            job.save()
        
        return {
            "message": f"Step '{step}' has been reset and will be re-processed",
            "job_id": job_id,
            "step": step
        }
        
    except ProcessingJob.DoesNotExist:
        raise HTTPException(status_code=404, detail="Job not found")

@app.post("/api/v1/admin/apply-chunking/{doc_id}")
async def apply_semantic_chunking(doc_id: str, force: bool = False):
    """Apply semantic chunking to an existing document"""
    try:
        # Get paper
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Check if chunking already exists
        existing_chunks = SemanticChunk.select().where(SemanticChunk.paper == paper).count()
        
        if existing_chunks > 0 and not force:
            return {
                "doc_id": doc_id,
                "message": f"Document already has {existing_chunks} semantic chunks. Use force=true to recreate.",
                "existing_chunks": existing_chunks,
                "status": "skipped"
            }
        
        # If force=true, delete existing chunks first
        if force and existing_chunks > 0:
            from .embedding import delete_semantic_chunks_for_paper
            collection = app.state.chroma_collection
            deleted_count = delete_semantic_chunks_for_paper(doc_id, collection)
            print(f"🗑️ Deleted {deleted_count} existing chunks for {doc_id}")
        
        # Create a new processing job for chunking
        job_id = str(uuid.uuid4())
        job = ProcessingJob.create(
            job_id=job_id,
            paper=paper,
            filename=paper.filename,
            status='uploaded',
            user_id=paper.uploaded_by
        )
        
        # Mark the job as chunking-only by setting earlier steps as completed
        job.update_step_status('ocr', 'completed')
        job.update_step_status('metadata', 'completed') 
        job.update_step_status('embedding', 'completed')
        job.status = 'processing'
        job.current_step = 'chunking'
        job.save()
        
        return {
            "doc_id": doc_id,
            "job_id": job_id,
            "message": "Semantic chunking started in background",
            "status": "processing",
            "existing_chunks_deleted": deleted_count if force else 0
        }
        
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting chunking: {str(e)}")

@app.post("/api/v1/admin/apply-chunking-all")
async def apply_semantic_chunking_all(force: bool = False):
    """Apply semantic chunking to all existing documents"""
    try:
        # Get all papers
        papers = Paper.select()
        
        results = []
        processed_count = 0
        skipped_count = 0
        
        for paper in papers:
            try:
                # Check if chunking already exists
                existing_chunks = SemanticChunk.select().where(SemanticChunk.paper == paper).count()
                
                if existing_chunks > 0 and not force:
                    results.append({
                        "doc_id": paper.doc_id,
                        "filename": paper.filename,
                        "status": "skipped",
                        "existing_chunks": existing_chunks,
                        "message": "Already has chunks"
                    })
                    skipped_count += 1
                    continue
                
                # If force=true, delete existing chunks first
                if force and existing_chunks > 0:
                    from .embedding import delete_semantic_chunks_for_paper
                    collection = app.state.chroma_collection
                    deleted_count = delete_semantic_chunks_for_paper(paper.doc_id, collection)
                    print(f"🗑️ Deleted {deleted_count} existing chunks for {paper.doc_id}")
                
                # Create a new processing job for chunking
                job_id = str(uuid.uuid4())
                job = ProcessingJob.create(
                    job_id=job_id,
                    paper=paper,
                    filename=paper.filename,
                    status='uploaded',
                    user_id=paper.uploaded_by
                )
                
                # Mark the job as chunking-only
                job.update_step_status('ocr', 'completed')
                job.update_step_status('metadata', 'completed')
                job.update_step_status('embedding', 'completed')
                job.status = 'processing'
                job.current_step = 'chunking'
                job.save()
                
                results.append({
                    "doc_id": paper.doc_id,
                    "filename": paper.filename,
                    "job_id": job_id,
                    "status": "processing",
                    "message": "Chunking started"
                })
                processed_count += 1
                
            except Exception as e:
                results.append({
                    "doc_id": paper.doc_id,
                    "filename": paper.filename,
                    "status": "error",
                    "message": str(e)
                })
        
        return {
            "message": f"Semantic chunking initiated for {processed_count} documents, {skipped_count} skipped",
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "total_count": len(results),
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing documents: {str(e)}")

@app.get("/api/v1/admin/chunking-status")
async def get_chunking_status():
    """Get semantic chunking status for all documents"""
    try:
        papers = Paper.select()
        
        status_data = []
        for paper in papers:
            # Count existing chunks
            chunk_count = SemanticChunk.select().where(SemanticChunk.paper == paper).count()
            
            # Get chunk types if chunks exist
            chunk_types = {}
            if chunk_count > 0:
                chunks = SemanticChunk.select().where(SemanticChunk.paper == paper)
                for chunk in chunks:
                    chunk_type = chunk.chunk_type
                    chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
            
            # Get latest job info
            latest_job = None
            try:
                latest_job = paper.jobs.order_by(ProcessingJob.created_at.desc()).get()
            except ProcessingJob.DoesNotExist:
                pass
            
            status_data.append({
                "doc_id": paper.doc_id,
                "filename": paper.filename,
                "chunk_count": chunk_count,
                "chunk_types": chunk_types,
                "has_chunks": chunk_count > 0,
                "latest_job_status": latest_job.status if latest_job else "unknown",
                "created_at": paper.created_at.isoformat()
            })
        
        # Summary statistics
        total_docs = len(status_data)
        docs_with_chunks = sum(1 for doc in status_data if doc["has_chunks"])
        total_chunks = sum(doc["chunk_count"] for doc in status_data)
        
        return {
            "summary": {
                "total_documents": total_docs,
                "documents_with_chunks": docs_with_chunks,
                "documents_without_chunks": total_docs - docs_with_chunks,
                "total_chunks": total_chunks
            },
            "documents": status_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting chunking status: {str(e)}")

# Helper function for session authentication
def require_session_admin_redirect(request: Request):
    """Require admin session, redirect to login if not authenticated"""
    user = check_session_auth(request)
    if not user or not user.is_admin:
        return RedirectResponse(url="/login", status_code=302)
    return user

# Admin endpoints
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Display admin dashboard with list of documents"""
    # Check authentication
    auth_result = require_session_admin_redirect(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    current_user = auth_result  # Get the authenticated user
    papers = Paper.select().order_by(Paper.created_at.desc()).limit(50)
    
    documents = []
    for paper in papers:
        # Get latest job status
        job_status = "unknown"
        current_step = None
        progress_percentage = 0
        job_id = None
        try:
            latest_job = paper.jobs.order_by(ProcessingJob.created_at.desc()).get()
            job_status = latest_job.status
            current_step = latest_job.current_step
            progress_percentage = latest_job.progress_percentage
            job_id = latest_job.job_id
        except ProcessingJob.DoesNotExist:
            pass
        
        # Get metadata
        metadata = {}
        try:
            meta = paper.metadata.get()
            metadata = {
                "title": meta.title,
                "authors": ", ".join(meta.get_authors()) if meta.get_authors() else None,
                "year": meta.year
            }
        except Metadata.DoesNotExist:
            pass
        
        documents.append({
            "doc_id": paper.doc_id,
            "filename": paper.filename,
            "created_at": paper.created_at,
            "status": job_status,
            "current_step": current_step,
            "progress_percentage": progress_percentage,
            "job_id": job_id,
            "metadata": metadata
        })
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "documents": documents,
        "active_page": "dashboard",
        "current_user": current_user
    })

@app.get("/admin/jobs", response_class=HTMLResponse)
async def admin_jobs_dashboard(request: Request):
    """Display admin jobs dashboard showing processing jobs"""
    # Check authentication
    auth_result = require_session_admin_redirect(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    
    # Get all jobs with pagination
    page = int(request.query_params.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page
    
    # Get jobs ordered by creation date
    total_jobs = ProcessingJob.select().count()
    jobs_query = ProcessingJob.select().order_by(ProcessingJob.created_at.desc()).offset(offset).limit(per_page)
    
    jobs = []
    for job in jobs_query:
        job_data = {
            "job_id": job.job_id,
            "filename": job.filename,
            "status": job.status,
            "current_step": job.current_step,
            "progress_percentage": job.progress_percentage,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "error_message": job.error_message,
            "doc_id": job.paper.doc_id if job.paper else None,
            "steps": job.get_step_info()
        }
        jobs.append(job_data)
    
    # Calculate pagination info
    total_pages = (total_jobs + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get status summary
    status_counts = {}
    for status in ['uploaded', 'processing', 'completed', 'failed']:
        count = ProcessingJob.select().where(ProcessingJob.status == status).count()
        status_counts[status] = count
    
    return templates.TemplateResponse("jobs.html", {
        "request": request,
        "jobs": jobs,
        "current_page": page,
        "total_pages": total_pages,
        "total_jobs": total_jobs,
        "has_prev": has_prev,
        "has_next": has_next,
        "status_counts": status_counts
    })

# User Dashboard Routes
@app.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request):
    """User dashboard landing page"""
    # Check authentication
    auth_result = require_session_user(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    current_user = auth_result
    
    # Get user's recent papers
    user_papers = Paper.select().where(Paper.uploaded_by == current_user).order_by(Paper.created_at.desc()).limit(10)
    
    papers = []
    for paper in user_papers:
        # Get latest job status
        job_status = "unknown"
        progress_percentage = 0
        try:
            latest_job = paper.jobs.order_by(ProcessingJob.created_at.desc()).get()
            job_status = latest_job.status
            progress_percentage = latest_job.progress_percentage
        except ProcessingJob.DoesNotExist:
            pass
        
        # Get metadata
        metadata = {}
        try:
            meta = paper.metadata.get()
            metadata = {
                "title": meta.title,
                "authors": ", ".join(meta.get_authors()) if hasattr(meta, 'get_authors') else [],
            }
        except Metadata.DoesNotExist:
            pass
        
        papers.append({
            "doc_id": paper.doc_id,
            "filename": paper.filename,
            "status": job_status,
            "progress_percentage": progress_percentage,
            "metadata": type('obj', (object,), metadata),
            "created_at": paper.created_at
        })
    
    # Get user stats
    total_papers = Paper.select().where(Paper.uploaded_by == current_user).count()
    processing_papers = 0
    completed_papers = 0
    
    for paper in Paper.select().where(Paper.uploaded_by == current_user):
        try:
            latest_job = paper.jobs.order_by(ProcessingJob.created_at.desc()).get()
            if latest_job.status == 'processing':
                processing_papers += 1
            elif latest_job.status == 'completed':
                completed_papers += 1
        except ProcessingJob.DoesNotExist:
            pass
    
    # Get Zotero status
    zotero_configured = current_user.has_zotero_config()
    zotero_items_count = current_user.zotero_items.count()
    
    return templates.TemplateResponse("user_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "dashboard",
        "papers": papers,
        "stats": {
            "total_papers": total_papers,
            "processing_papers": processing_papers,
            "completed_papers": completed_papers,
            "zotero_configured": zotero_configured,
            "zotero_items_count": zotero_items_count
        }
    })

@app.get("/dashboard/my-papers", response_class=HTMLResponse)
async def user_my_papers(request: Request):
    """User's uploaded papers page"""
    # Check authentication
    auth_result = require_session_user(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    current_user = auth_result
    
    return templates.TemplateResponse("user_my_papers.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "my-papers"
    })

@app.get("/dashboard/zotero/config", response_class=HTMLResponse)
async def user_zotero_config(request: Request):
    """User's Zotero configuration page"""
    # Check authentication
    auth_result = require_session_user(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    current_user = auth_result
    
    return templates.TemplateResponse("user_zotero_config.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "zotero-config"
    })

@app.get("/dashboard/zotero/library", response_class=HTMLResponse)
async def user_zotero_library(request: Request):
    """User's Zotero library page"""
    # Check authentication
    auth_result = require_session_user(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    current_user = auth_result
    
    return templates.TemplateResponse("user_zotero_library.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "zotero-library"
    })

@app.get("/dashboard/zotero/item/{item_key}", response_class=HTMLResponse)
async def user_zotero_item_detail(request: Request, item_key: str):
    """Zotero item detail page"""
    # Check authentication
    auth_result = require_session_user(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    current_user = auth_result
    
    # Get the Zotero item
    try:
        zotero_item = (ZoteroItem
                      .select()
                      .where(
                          ZoteroItem.zotero_key == item_key,
                          ZoteroItem.user == current_user
                      )
                      .first())
        
        if not zotero_item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Get item data
        item_data = zotero_item.get_data()
        
        # Get associated PDF if exists
        paper = None
        try:
            zotero_paper = ZoteroItemPaper.select().where(ZoteroItemPaper.zotero_item == zotero_item).first()
            if zotero_paper:
                paper = zotero_paper.paper
        except:
            pass
        
        # Get collections this item belongs to
        collections = []
        for ci in ZoteroCollectionItem.select().where(ZoteroCollectionItem.item == zotero_item):
            collections.append({
                'key': ci.collection.collection_key,
                'name': ci.collection.name
            })
        
        return templates.TemplateResponse("user_zotero_item_detail.html", {
            "request": request,
            "current_user": current_user,
            "active_page": "zotero-library",
            "item": zotero_item,
            "item_data": item_data,
            "paper": paper,
            "collections": collections
        })
        
    except Exception as e:
        logger.error(f"Error loading Zotero item {item_key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# New Admin Routes
@app.get("/admin/papers", response_class=HTMLResponse)
async def admin_papers(request: Request, current_user: User = Depends(require_admin)):
    """All Papers management page"""
    papers = Paper.select().order_by(Paper.created_at.desc()).limit(100)
    
    documents = []
    for paper in papers:
        # Get latest job status
        job_status = "unknown"
        current_step = None
        progress_percentage = 0
        job_id = None
        try:
            latest_job = paper.jobs.order_by(ProcessingJob.created_at.desc()).get()
            job_status = latest_job.status
            current_step = latest_job.current_step
            progress_percentage = latest_job.progress_percentage
            job_id = latest_job.job_id
        except ProcessingJob.DoesNotExist:
            pass
        
        # Get metadata
        metadata = {}
        try:
            meta = paper.metadata.get()
            metadata = {
                "title": meta.title,
                "authors": ", ".join(meta.get_authors()) if meta.get_authors() else None,
                "journal": meta.journal,
                "year": meta.year
            }
        except Metadata.DoesNotExist:
            pass
        
        documents.append({
            "doc_id": paper.doc_id,
            "filename": paper.filename,
            "created_at": paper.created_at,
            "status": job_status,
            "current_step": current_step,
            "progress_percentage": progress_percentage,
            "job_id": job_id,
            "metadata": type('obj', (object,), metadata)
        })
    
    return templates.TemplateResponse("admin_papers.html", {
        "request": request,
        "active_page": "papers",
        "current_user": current_user,
        "documents": documents
    })

@app.get("/admin/duplicates", response_class=HTMLResponse)
async def admin_duplicates(request: Request, current_user: User = Depends(require_admin)):
    """Duplicates management page"""
    return templates.TemplateResponse("admin_duplicates.html", {
        "request": request,
        "active_page": "duplicates",
        "current_user": current_user
    })

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, current_user: User = Depends(require_admin)):
    """User management page"""
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "active_page": "users",
        "current_user": current_user
    })

@app.get("/admin/users/{user_id}/zotero", response_class=HTMLResponse)
async def admin_user_zotero_details(request: Request, user_id: int, current_user: User = Depends(require_admin)):
    """Zotero management page for a specific user"""
    try:
        target_user = User.get_by_id(user_id)
        return templates.TemplateResponse("admin_user_zotero_details.html", {
            "request": request,
            "active_page": "users",
            "current_user": current_user,
            "target_user": target_user
        })
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")

@app.get("/admin/audit-logs", response_class=HTMLResponse)
async def admin_audit_logs(request: Request, current_user: User = Depends(require_admin)):
    """Audit logs page"""
    return templates.TemplateResponse("admin_audit_logs.html", {
        "request": request,
        "active_page": "audit-logs",
        "current_user": current_user
    })

@app.get("/admin/system-zotero-config", response_class=HTMLResponse)
async def admin_system_zotero_config(request: Request, current_user: User = Depends(require_admin)):
    """System-wide Zotero configuration page"""
    return templates.TemplateResponse("admin_system_zotero_config.html", {
        "request": request,
        "active_page": "zotero-config",
        "current_user": current_user
    })

@app.get("/admin/zotero/sync", response_class=HTMLResponse)
async def admin_zotero_sync(request: Request, current_user: User = Depends(require_admin)):
    """Zotero sync status page"""
    return templates.TemplateResponse("admin_zotero_sync.html", {
        "request": request,
        "active_page": "zotero-sync",
        "current_user": current_user
    })

@app.get("/admin/zotero/library", response_class=HTMLResponse)
async def admin_zotero_library(request: Request, current_user: User = Depends(require_admin)):
    """Admin Zotero library browser"""
    return templates.TemplateResponse("admin_zotero_library.html", {
        "request": request,
        "active_page": "zotero-library",
        "current_user": current_user
    })

@app.get("/admin/system/jobs", response_class=HTMLResponse)
async def admin_system_jobs(request: Request, current_user: User = Depends(require_admin)):
    """System jobs page"""
    # Get all jobs with pagination
    page = int(request.query_params.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page
    
    # Get jobs ordered by creation date
    total_jobs = ProcessingJob.select().count()
    jobs_query = ProcessingJob.select().order_by(ProcessingJob.created_at.desc()).offset(offset).limit(per_page)
    
    jobs = []
    for job in jobs_query:
        job_data = {
            "job_id": job.job_id,
            "filename": job.filename,
            "status": job.status,
            "current_step": job.current_step,
            "progress_percentage": job.progress_percentage,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message,
            "doc_id": job.paper.doc_id if job.paper else None
        }
        jobs.append(job_data)
    
    # Calculate pagination
    total_pages = (total_jobs + per_page - 1) // per_page
    
    # Get status counts
    status_counts = {}
    for status in ['pending', 'processing', 'completed', 'failed']:
        status_counts[status] = ProcessingJob.select().where(ProcessingJob.status == status).count()
    
    return templates.TemplateResponse("admin_system_jobs.html", {
        "request": request,
        "active_page": "system-jobs",
        "current_user": current_user,
        "jobs": jobs,
        "page": page,
        "per_page": per_page,
        "total_jobs": total_jobs,
        "total_pages": total_pages,
        "status_counts": status_counts
    })

@app.get("/admin/system/settings", response_class=HTMLResponse)
async def admin_system_settings(request: Request, current_user: User = Depends(require_admin)):
    """System settings page"""
    return templates.TemplateResponse("admin_system_settings.html", {
        "request": request,
        "active_page": "system-settings",
        "current_user": current_user
    })

@app.get("/admin/system/database", response_class=HTMLResponse)
async def admin_system_database(request: Request, current_user: User = Depends(require_admin)):
    """Database reset page"""
    return templates.TemplateResponse("admin_system_database.html", {
        "request": request,
        "active_page": "system-database",
        "current_user": current_user
    })

@app.get("/admin/document/{doc_id}", response_class=HTMLResponse)
async def admin_document_detail(request: Request, doc_id: str):
    """Display detailed view of a document"""
    # Check authentication
    auth_result = require_session_admin_redirect(request)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    try:
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Get metadata
        metadata = None
        try:
            metadata = paper.metadata.get()
        except Metadata.DoesNotExist:
            pass
        
        # Get processing jobs
        jobs = list(paper.jobs.order_by(ProcessingJob.created_at.desc()))
        
        # Get page texts
        page_texts = list(paper.page_texts.order_by(PageText.page_number))
        
        # Get Zotero link if exists
        zotero_link = None
        try:
            zotero_link = ZoteroLink.get(ZoteroLink.paper == paper)
        except ZoteroLink.DoesNotExist:
            pass
        
        # Get page embeddings and document embedding from ChromaDB
        page_embeddings = {}
        document_embedding = None
        try:
            logger.info(f"Attempting to get ChromaDB collection for document {doc_id}")
            collection = app.state.chroma_collection
            logger.info(f"Successfully got ChromaDB collection: {collection}")
            
            if not collection:
                logger.warning("ChromaDB collection is None")
                raise Exception("ChromaDB collection is None")
            
            # Get document-level embedding
            try:
                doc_result = collection.get(ids=[doc_id], include=['embeddings'])
                if doc_result['embeddings'] is not None and len(doc_result['embeddings']) > 0:
                    # Get first 10 values from document embedding vector and convert to list
                    document_embedding = doc_result['embeddings'][0][:10].tolist()
            except Exception as e:
                # Skip if document embedding not found
                pass
            
            # Get page embeddings
            for page_text in page_texts:
                page_doc_id = f"{doc_id}_page_{page_text.page_number}"
                try:
                    result = collection.get(ids=[page_doc_id], include=['embeddings'])
                    if result['embeddings'] is not None and len(result['embeddings']) > 0:
                        # Get first 10 values from embedding vector and convert to list
                        embedding = result['embeddings'][0][:10].tolist()
                        page_embeddings[page_text.page_number] = embedding
                        logger.info(f"Found page embedding for page {page_text.page_number}: {len(embedding)} values")
                    else:
                        logger.warning(f"No embedding found for page_doc_id: {page_doc_id}")
                except Exception as e:
                    # Skip if embedding not found for this page
                    logger.error(f"Error getting page embedding for {page_doc_id}: {str(e)}")
                    continue
        except Exception as e:
            # If ChromaDB is not available, continue without embeddings
            logger.error(f"ChromaDB error when getting embeddings: {str(e)}")
            pass
        
        logger.info(f"Rendering document template with {len(page_embeddings)} page embeddings")
        for page_num, embedding in page_embeddings.items():
            logger.info(f"  Page {page_num}: {len(embedding)} embedding values")
        
        return templates.TemplateResponse("document.html", {
            "request": request,
            "paper": paper,
            "metadata": metadata,
            "jobs": jobs,
            "page_texts": page_texts,
            "page_embeddings": page_embeddings,
            "document_embedding": document_embedding,
            "zotero_link": zotero_link
        })
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")

@app.post("/api/v1/document/{doc_id}/metadata")
async def update_document_metadata(
    doc_id: str,
    title: Optional[str] = Form(None),
    authors: Optional[str] = Form(None),  # Comma-separated string
    journal: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    abstract: Optional[str] = Form(None),
    doi: Optional[str] = Form(None)
):
    """Update document metadata"""
    try:
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Get or create metadata
        try:
            metadata = paper.metadata.get()
        except Metadata.DoesNotExist:
            metadata = Metadata.create(paper=paper)
        
        # Update fields if provided
        if title is not None:
            metadata.title = title.strip() if title.strip() else None
        
        if authors is not None:
            # Parse comma-separated authors
            authors_list = [author.strip() for author in authors.split(',') if author.strip()]
            metadata.set_authors(authors_list)
        
        if journal is not None:
            metadata.journal = journal.strip() if journal.strip() else None
        
        if year is not None:
            metadata.year = year
        
        if abstract is not None:
            metadata.abstract = abstract.strip() if abstract.strip() else None
        
        if doi is not None:
            metadata.doi = doi.strip() if doi.strip() else None
        
        metadata.save()
        
        return {
            "status": "success",
            "message": "Metadata updated successfully",
            "metadata": {
                "title": metadata.title,
                "authors": metadata.get_authors(),
                "journal": metadata.journal,
                "year": metadata.year,
                "abstract": metadata.abstract,
                "doi": metadata.doi
            }
        }
        
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update metadata: {str(e)}")

# Embedding visualization endpoints
@app.get("/api/v1/document/{doc_id}/embedding_viz")
async def get_document_embedding_visualization(
    doc_id: str,
    viz_type: str = "bar",  # bar, heatmap, histogram
    max_values: int = 50
):
    """Generate and serve document-level embedding visualization"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(collection, doc_id, is_document_level=True)
        
        if embedding is None:
            raise HTTPException(status_code=404, detail="Document embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate visualization based on type
        title = f"Document Embedding - {paper.filename}"
        
        if viz_type == "bar":
            image_data = visualize_embedding_bar(
                embedding_array, 
                title=title,
                max_values=max_values
            )
        elif viz_type == "heatmap":
            image_data = visualize_embedding_heatmap(
                embedding_array,
                title=title
            )
        elif viz_type == "histogram":
            image_data = visualize_embedding_histogram(
                embedding_array,
                title=title
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid visualization type. Use 'bar', 'heatmap', or 'histogram'")
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        # Return image as response
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f"inline; filename=\"{doc_id}_embedding_{viz_type}.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/page/{page_number}/embedding_viz")
async def get_page_embedding_visualization(
    doc_id: str,
    page_number: int,
    viz_type: str = "bar",  # bar, heatmap, histogram
    max_values: int = 50
):
    """Generate and serve page-level embedding visualization"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Verify page exists
        try:
            page_text = PageText.get(
                (PageText.paper == paper) & 
                (PageText.page_number == page_number)
            )
        except PageText.DoesNotExist:
            raise HTTPException(status_code=404, detail=f"Page {page_number} not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(
            collection, 
            doc_id, 
            page_number=page_number, 
            is_document_level=False
        )
        
        if embedding is None:
            raise HTTPException(status_code=404, detail=f"Page {page_number} embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate visualization based on type
        title = f"Page {page_number} Embedding - {paper.filename}"
        
        if viz_type == "bar":
            image_data = visualize_embedding_bar(
                embedding_array, 
                title=title,
                max_values=max_values
            )
        elif viz_type == "heatmap":
            image_data = visualize_embedding_heatmap(
                embedding_array,
                title=title
            )
        elif viz_type == "histogram":
            image_data = visualize_embedding_histogram(
                embedding_array,
                title=title
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid visualization type. Use 'bar', 'heatmap', or 'histogram'")
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        # Return image as response
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f"inline; filename=\"{doc_id}_page_{page_number}_embedding_{viz_type}.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/embedding_heatmap_mini")
async def get_document_embedding_heatmap_mini(doc_id: str):
    """Generate and serve minimal document-level embedding heatmap (64x64px)"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(collection, doc_id, is_document_level=True)
        
        if embedding is None:
            raise HTTPException(status_code=404, detail="Document embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate minimal heatmap (64x64 pixels)
        image_data = visualize_embedding_heatmap(
            embedding_array,
            minimal=True,
            figsize=(0.64, 0.64)
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        # Return image as response
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f"inline; filename=\"{doc_id}_embedding_mini.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/page/{page_number}/embedding_heatmap_mini")
async def get_page_embedding_heatmap_mini(doc_id: str, page_number: int):
    """Generate and serve minimal page-level embedding heatmap (64x64px)"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Verify page exists
        try:
            page_text = PageText.get(
                (PageText.paper == paper) & 
                (PageText.page_number == page_number)
            )
        except PageText.DoesNotExist:
            raise HTTPException(status_code=404, detail=f"Page {page_number} not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(
            collection, 
            doc_id, 
            page_number=page_number, 
            is_document_level=False
        )
        
        if embedding is None:
            raise HTTPException(status_code=404, detail=f"Page {page_number} embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate minimal heatmap (64x64 pixels)
        image_data = visualize_embedding_heatmap(
            embedding_array,
            minimal=True,
            figsize=(0.64, 0.64)
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        # Return image as response
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f"inline; filename=\"{doc_id}_page_{page_number}_embedding_mini.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/chunks")
async def get_document_chunks(doc_id: str, page: Optional[int] = None):
    """Get semantic chunks for a document with optional page filtering"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Build query
        query = SemanticChunk.select().where(SemanticChunk.paper == paper)
        
        # Filter by page if specified
        if page is not None:
            query = query.where(SemanticChunk.page_number == page)
        
        # Order by page and chunk index
        chunks = list(query.order_by(SemanticChunk.page_number, SemanticChunk.chunk_index_on_page))
        
        # Prepare response data
        chunk_data = []
        for chunk in chunks:
            chunk_data.append({
                "id": chunk.id,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "chunk_index_on_page": chunk.chunk_index_on_page,
                "chunk_type": chunk.chunk_type,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "bbox": chunk.get_bbox(),
                "embedding_id": chunk.embedding_id,
                "created_at": chunk.created_at.isoformat()
            })
        
        # Generate statistics
        stats = {}
        if chunks:
            stats = {
                "total_chunks": len(chunks),
                "pages_with_chunks": len(set(c.page_number for c in chunks)),
                "chunk_types": {},
                "avg_chunk_length": sum(len(c.text) for c in chunks) // len(chunks)
            }
            
            # Count by chunk type
            for chunk in chunks:
                chunk_type = chunk.chunk_type
                if chunk_type not in stats["chunk_types"]:
                    stats["chunk_types"][chunk_type] = 0
                stats["chunk_types"][chunk_type] += 1
        
        return {
            "doc_id": doc_id,
            "filename": paper.filename,
            "chunks": chunk_data,
            "statistics": stats,
            "filtered_by_page": page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving chunks: {str(e)}")

@app.get("/api/v1/document/{doc_id}/chunk/{chunk_id}/embedding_heatmap_mini")
async def get_chunk_embedding_heatmap_mini(doc_id: str, chunk_id: int):
    """Generate and serve minimal chunk-level embedding heatmap"""
    try:
        # Verify document and chunk exist
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
            chunk = SemanticChunk.get(
                (SemanticChunk.id == chunk_id) & 
                (SemanticChunk.paper == paper)
            )
        except (Paper.DoesNotExist, SemanticChunk.DoesNotExist):
            raise HTTPException(status_code=404, detail="Document or chunk not found")
        
        # Get embedding from ChromaDB using embedding_id
        collection = app.state.chroma_collection
        
        try:
            result = collection.get(ids=[chunk.embedding_id], include=['embeddings'])
            if not result['embeddings'] or not result['embeddings'][0]:
                raise HTTPException(status_code=404, detail="Chunk embedding not found")
            
            embedding = result['embeddings'][0]
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Chunk embedding not found: {str(e)}")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate minimal heatmap (64x64 pixels)
        image_data = visualize_embedding_heatmap(
            embedding_array,
            minimal=True,
            figsize=(0.64, 0.64)
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        # Return image as response
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f"inline; filename=\"{doc_id}_chunk_{chunk_id}_embedding_mini.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/embedding_3d_bidirectional")
async def get_document_embedding_3d_bidirectional(doc_id: str, minimal: bool = False):
    """Generate 3D bidirectional bar chart for document embedding"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(collection, doc_id, is_document_level=True)
        
        if embedding is None:
            raise HTTPException(status_code=404, detail="Document embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate 3D bidirectional visualization
        image_data = visualize_embedding_3d_bidirectional(
            embedding_array,
            title=f"3D Bidirectional: {paper.filename}",
            reshape_dims=(32, 32),
            minimal=minimal
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",
                "Content-Disposition": f"inline; filename=\"{doc_id}_3d_bidirectional.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/embedding_3d_unidirectional")
async def get_document_embedding_3d_unidirectional(doc_id: str, minimal: bool = False):
    """Generate 3D unidirectional bar chart for document embedding"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(collection, doc_id, is_document_level=True)
        
        if embedding is None:
            raise HTTPException(status_code=404, detail="Document embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate 3D unidirectional visualization
        image_data = visualize_embedding_3d_unidirectional(
            embedding_array,
            title=f"3D Unidirectional: {paper.filename}",
            reshape_dims=(32, 32),
            minimal=minimal
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",
                "Content-Disposition": f"inline; filename=\"{doc_id}_3d_unidirectional.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/embedding_3d_surface")
async def get_document_embedding_3d_surface(doc_id: str, minimal: bool = False):
    """Generate 3D surface plot for document embedding"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(collection, doc_id, is_document_level=True)
        
        if embedding is None:
            raise HTTPException(status_code=404, detail="Document embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate 3D surface visualization
        image_data = visualize_embedding_3d_surface(
            embedding_array,
            title=f"3D Surface: {paper.filename}",
            reshape_dims=(32, 32),
            minimal=minimal
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",
                "Content-Disposition": f"inline; filename=\"{doc_id}_3d_surface.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/chunk/{chunk_id}/embedding_3d_bidirectional")
async def get_chunk_embedding_3d_bidirectional(doc_id: str, chunk_id: int, minimal: bool = False):
    """Generate 3D bidirectional bar chart for chunk embedding"""
    try:
        # Verify document and chunk exist
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
            chunk = SemanticChunk.get(
                (SemanticChunk.id == chunk_id) & 
                (SemanticChunk.paper == paper)
            )
        except (Paper.DoesNotExist, SemanticChunk.DoesNotExist):
            raise HTTPException(status_code=404, detail="Document or chunk not found")
        
        # Get embedding from ChromaDB using embedding_id
        collection = app.state.chroma_collection
        
        try:
            result = collection.get(ids=[chunk.embedding_id], include=['embeddings'])
            if not result['embeddings'] or not result['embeddings'][0]:
                raise HTTPException(status_code=404, detail="Chunk embedding not found")
            
            embedding = result['embeddings'][0]
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Chunk embedding not found: {str(e)}")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate 3D bidirectional visualization
        image_data = visualize_embedding_3d_bidirectional(
            embedding_array,
            title=f"3D Bidirectional: Chunk {chunk_id}",
            reshape_dims=(32, 32),
            minimal=minimal
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",
                "Content-Disposition": f"inline; filename=\"{doc_id}_chunk_{chunk_id}_3d_bidirectional.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/chunk/{chunk_id}/embedding_3d_unidirectional")
async def get_chunk_embedding_3d_unidirectional(doc_id: str, chunk_id: int, minimal: bool = False):
    """Generate 3D unidirectional bar chart for chunk embedding"""
    try:
        # Verify document and chunk exist
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
            chunk = SemanticChunk.get(
                (SemanticChunk.id == chunk_id) & 
                (SemanticChunk.paper == paper)
            )
        except (Paper.DoesNotExist, SemanticChunk.DoesNotExist):
            raise HTTPException(status_code=404, detail="Document or chunk not found")
        
        # Get embedding from ChromaDB using embedding_id
        collection = app.state.chroma_collection
        
        try:
            result = collection.get(ids=[chunk.embedding_id], include=['embeddings'])
            if not result['embeddings'] or not result['embeddings'][0]:
                raise HTTPException(status_code=404, detail="Chunk embedding not found")
            
            embedding = result['embeddings'][0]
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Chunk embedding not found: {str(e)}")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate 3D unidirectional visualization
        image_data = visualize_embedding_3d_unidirectional(
            embedding_array,
            title=f"3D Unidirectional: Chunk {chunk_id}",
            reshape_dims=(32, 32),
            minimal=minimal
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",
                "Content-Disposition": f"inline; filename=\"{doc_id}_chunk_{chunk_id}_3d_unidirectional.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/page/{page_number}/embedding_3d_bidirectional")
async def get_page_embedding_3d_bidirectional(doc_id: str, page_number: int, minimal: bool = False):
    """Generate 3D bidirectional bar chart for page embedding"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Verify page exists
        try:
            page_text = PageText.get(
                (PageText.paper == paper) & 
                (PageText.page_number == page_number)
            )
        except PageText.DoesNotExist:
            raise HTTPException(status_code=404, detail=f"Page {page_number} not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(
            collection, 
            doc_id, 
            page_number=page_number, 
            is_document_level=False
        )
        
        if embedding is None:
            raise HTTPException(status_code=404, detail=f"Page {page_number} embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate 3D bidirectional visualization
        image_data = visualize_embedding_3d_bidirectional(
            embedding_array,
            title=f"3D Bidirectional: Page {page_number}",
            reshape_dims=(32, 32),
            minimal=minimal
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",
                "Content-Disposition": f"inline; filename=\"{doc_id}_page_{page_number}_3d_bidirectional.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

@app.get("/api/v1/document/{doc_id}/page/{page_number}/embedding_3d_unidirectional")
async def get_page_embedding_3d_unidirectional(doc_id: str, page_number: int, minimal: bool = False):
    """Generate 3D unidirectional bar chart for page embedding"""
    try:
        # Verify document exists
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
        except Paper.DoesNotExist:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Verify page exists
        try:
            page_text = PageText.get(
                (PageText.paper == paper) & 
                (PageText.page_number == page_number)
            )
        except PageText.DoesNotExist:
            raise HTTPException(status_code=404, detail=f"Page {page_number} not found")
        
        # Get embedding from ChromaDB
        collection = app.state.chroma_collection
        embedding = get_embedding_from_chroma(
            collection, 
            doc_id, 
            page_number=page_number, 
            is_document_level=False
        )
        
        if embedding is None:
            raise HTTPException(status_code=404, detail=f"Page {page_number} embedding not found")
        
        # Convert to numpy array
        embedding_array = np.array(embedding)
        
        # Generate 3D unidirectional visualization
        image_data = visualize_embedding_3d_unidirectional(
            embedding_array,
            title=f"3D Unidirectional: Page {page_number}",
            reshape_dims=(32, 32),
            minimal=minimal
        )
        
        if image_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate visualization")
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "max-age=3600",
                "Content-Disposition": f"inline; filename=\"{doc_id}_page_{page_number}_3d_unidirectional.png\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization generation failed: {str(e)}")

# Search helper functions
async def _process_chunk_search_results(search_results, limit: int):
    """Process semantic chunk search results"""
    results = []
    
    if not search_results['ids'] or not search_results['ids'][0]:
        return results
    
    doc_ids = search_results['ids'][0]
    distances = search_results['distances'][0]
    metadatas = search_results['metadatas'][0] if search_results['metadatas'] else []
    documents = search_results['documents'][0] if search_results['documents'] else []
    
    # Group results by document
    doc_results = {}
    
    for idx, chunk_id in enumerate(doc_ids):
        try:
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            paper_id = metadata.get('paper_id')
            
            if not paper_id:
                continue
                
            # Get paper
            paper = Paper.get(Paper.doc_id == paper_id)
            score = 1.0 - distances[idx]
            
            # Get chunk details from database
            try:
                chunk = SemanticChunk.get(SemanticChunk.embedding_id == chunk_id)
                chunk_text = chunk.text[:300] + "..." if len(chunk.text) > 300 else chunk.text
                
                chunk_info = {
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index_on_page,
                    "chunk_type": chunk.chunk_type,
                    "score": score,
                    "text": chunk_text
                }
            except SemanticChunk.DoesNotExist:
                # Fallback to document text if chunk not found
                chunk_text = documents[idx][:300] + "..." if len(documents[idx]) > 300 else documents[idx]
                chunk_info = {
                    "page_number": metadata.get('page_number', 0),
                    "chunk_index": metadata.get('chunk_index_on_page', 0),
                    "chunk_type": metadata.get('chunk_type', 'unknown'),
                    "score": score,
                    "text": chunk_text
                }
            
            if paper_id not in doc_results:
                # Get document metadata
                metadata_dict = {}
                try:
                    doc_metadata = paper.metadata.get()
                    metadata_dict = {
                        "title": doc_metadata.title,
                        "authors": doc_metadata.get_authors(),
                        "journal": doc_metadata.journal,
                        "year": doc_metadata.year
                    }
                except Metadata.DoesNotExist:
                    pass
                
                doc_results[paper_id] = {
                    "doc_id": paper_id,
                    "filename": paper.filename,
                    "metadata": metadata_dict,
                    "score": score,
                    "chunks": [],
                    "search_type": "chunk"
                }
            
            # Update best score
            if score > doc_results[paper_id]["score"]:
                doc_results[paper_id]["score"] = score
            
            doc_results[paper_id]["chunks"].append(chunk_info)
            
        except Paper.DoesNotExist:
            continue
        except Exception as e:
            logger.error(f"Error processing chunk result: {str(e)}")
            continue
    
    # Convert to list and sort by score
    results = list(doc_results.values())
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Sort chunks within each document by score
    for result in results:
        result["chunks"].sort(key=lambda x: x["score"], reverse=True)
        result["chunks"] = result["chunks"][:5]  # Limit chunks per document
    
    return results[:limit]

async def _process_page_search_results(search_results, limit: int):
    """Process page-level search results"""
    results = []
    
    if not search_results['ids'] or not search_results['ids'][0]:
        return results
    
    doc_ids = search_results['ids'][0]
    distances = search_results['distances'][0]
    documents = search_results['documents'][0] if search_results['documents'] else []
    
    # Group results by document
    doc_results = {}
    
    for idx, doc_id in enumerate(doc_ids):
        try:
            # Parse page-level doc_id
            if "_page_" in doc_id:
                paper_id, page_part = doc_id.split("_page_")
                page_number = int(page_part)
            else:
                continue
            
            paper = Paper.get(Paper.doc_id == paper_id)
            score = 1.0 - distances[idx]
            snippet = documents[idx][:200] + "..." if len(documents[idx]) > 200 else documents[idx]
            
            if paper_id not in doc_results:
                # Get document metadata
                metadata_dict = {}
                try:
                    metadata = paper.metadata.get()
                    metadata_dict = {
                        "title": metadata.title,
                        "authors": metadata.get_authors(),
                        "journal": metadata.journal,
                        "year": metadata.year
                    }
                except Metadata.DoesNotExist:
                    pass
                
                doc_results[paper_id] = {
                    "doc_id": paper_id,
                    "filename": paper.filename,
                    "metadata": metadata_dict,
                    "score": score,
                    "pages": [],
                    "search_type": "page"
                }
            
            # Update best score
            if score > doc_results[paper_id]["score"]:
                doc_results[paper_id]["score"] = score
            
            doc_results[paper_id]["pages"].append({
                "page_number": page_number,
                "score": score,
                "snippet": snippet
            })
            
        except (Paper.DoesNotExist, ValueError):
            continue
    
    # Convert to list and sort by score
    results = list(doc_results.values())
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Sort pages within each document by score
    for result in results:
        result["pages"].sort(key=lambda x: x["score"], reverse=True)
        result["pages"] = result["pages"][:3]  # Limit pages per document
    
    return results[:limit]

async def _process_document_search_results(search_results, limit: int):
    """Process document-level search results"""
    results = []
    
    if not search_results['ids'] or not search_results['ids'][0]:
        return results
    
    doc_ids = search_results['ids'][0]
    distances = search_results['distances'][0]
    
    for idx, doc_id in enumerate(doc_ids):
        try:
            paper = Paper.get(Paper.doc_id == doc_id)
            
            # Get metadata
            metadata_dict = {}
            try:
                metadata = paper.metadata.get()
                metadata_dict = {
                    "title": metadata.title,
                    "authors": metadata.get_authors(),
                    "journal": metadata.journal,
                    "year": metadata.year
                }
            except Metadata.DoesNotExist:
                pass
            
            results.append({
                "doc_id": paper.doc_id,
                "filename": paper.filename,
                "metadata": metadata_dict,
                "score": 1.0 - distances[idx],
                "search_type": "document"
            })
        except Paper.DoesNotExist:
            continue
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]

async def _search_all_levels(collection, query: str, limit: int):
    """Search across all levels and merge results"""
    all_results = []
    
    # Search chunks
    chunk_results = collection.query(
        query_texts=[query],
        n_results=limit,
        where={"paper_id": {"$ne": None}}
    )
    chunk_processed = await _process_chunk_search_results(chunk_results, limit // 2)
    all_results.extend(chunk_processed)
    
    # Search pages
    page_results = collection.query(
        query_texts=[query],
        n_results=limit,
        where={"is_document_level": False}
    )
    page_processed = await _process_page_search_results(page_results, limit // 2)
    all_results.extend(page_processed)
    
    # Merge results by document ID and take the best score
    merged_results = {}
    for result in all_results:
        doc_id = result["doc_id"]
        
        if doc_id not in merged_results:
            merged_results[doc_id] = result
        else:
            # Keep the result with the higher score
            if result["score"] > merged_results[doc_id]["score"]:
                merged_results[doc_id] = result
    
    final_results = list(merged_results.values())
    final_results.sort(key=lambda x: x["score"], reverse=True)
    return final_results[:limit]

# Zotero Integration APIs
from pydantic import BaseModel, validator

class ZoteroConfigRequest(BaseModel):
    user_id: str  # Zotero user ID
    library_type: str  # 'user' or 'group'
    library_id: Optional[str] = None  # Group library ID (only for groups)
    api_key: str

class ZoteroConfigResponse(BaseModel):
    success: bool
    message: str
    has_config: bool
    library_id: Optional[str] = None
    library_type: Optional[str] = None
    user_id: Optional[str] = None  # Zotero user ID
    last_sync: Optional[str] = None
    configured: Optional[bool] = None  # Alias for has_config for backward compatibility

@app.post("/api/v1/users/me/zotero_config", response_model=ZoteroConfigResponse)
async def set_zotero_config(
    request: ZoteroConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Set Zotero configuration for current user"""
    try:
        # Validate required fields
        if not request.user_id or not request.api_key:
            raise HTTPException(
                status_code=400,
                detail="Both user_id and api_key are required"
            )
        
        # For group libraries, library_id is required
        if request.library_type == 'group' and not request.library_id:
            raise HTTPException(
                status_code=400,
                detail="library_id is required for group libraries"
            )
        
        # Determine the library ID to use
        library_id = request.library_id if request.library_type == 'group' else request.user_id
        
        # Test Zotero connection
        try:
            from pyzotero import zotero
            zot = zotero.Zotero(library_id, request.library_type, request.api_key)
            # Test connection by getting a small number of items
            zot.items(limit=1)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to connect to Zotero: {str(e)}"
            )
        
        # Save configuration
        current_user.zotero_library_id = library_id
        current_user.zotero_library_type = request.library_type
        current_user.set_zotero_api_key(request.api_key)
        current_user.save()
        
        return ZoteroConfigResponse(
            success=True,
            message="Zotero configuration saved successfully",
            has_config=True,
            library_id=request.library_id,
            last_sync=current_user.zotero_last_sync.isoformat() if current_user.zotero_last_sync else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving Zotero config: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@app.post("/api/v1/users/me/zotero/test")
async def test_user_zotero_connection(current_user: User = Depends(get_current_user)):
    """Test Zotero connection for current user"""
    try:
        if not current_user.has_zotero_config():
            raise HTTPException(
                status_code=400,
                detail="No Zotero configuration found. Please configure Zotero settings first."
            )
        
        api_key = current_user.get_zotero_api_key()
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Failed to decrypt Zotero API key. Please reconfigure your Zotero settings."
            )
        
        # Test connection
        try:
            from pyzotero import zotero
            library_type = current_user.zotero_library_type or 'user'
            zot = zotero.Zotero(current_user.zotero_library_id, library_type, api_key)
            
            # Test by fetching user info and a small number of items
            user_info = zot.key_info()
            items = zot.items(limit=1)
            
            return {
                'success': True,
                'message': 'Zotero connection successful',
                'library_id': current_user.zotero_library_id,
                'library_type': library_type,
                'user_info': {
                    'username': user_info.get('username', 'Unknown'),
                    'displayName': user_info.get('displayName', 'Unknown'),
                    'userID': user_info.get('userID', 'Unknown')
                }
            }
            
        except Exception as e:
            logger.error(f"Zotero connection test failed for user {current_user.username}: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to connect to Zotero: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing Zotero connection for user {current_user.username}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while testing connection"
        )

class ZoteroTestRequest(BaseModel):
    user_id: str
    library_type: str = 'user'
    library_id: Optional[str] = None
    api_key: str

@app.post("/api/v1/users/me/zotero/test-config")
async def test_user_zotero_config(
    config: ZoteroTestRequest, 
    current_user: User = Depends(get_current_user)
):
    """Test Zotero connection with provided configuration values"""
    try:
        # Use the library_id from config, or user_id for user libraries
        library_id = config.library_id if config.library_type == 'group' else config.user_id
        
        # Test connection with provided values
        try:
            from pyzotero import zotero
            zot = zotero.Zotero(library_id, config.library_type, config.api_key)
            
            # Test by fetching user info and a small number of items
            user_info = zot.key_info()
            items = zot.items(limit=1)
            
            return {
                'success': True,
                'message': 'Zotero connection successful',
                'library_id': library_id,
                'library_type': config.library_type,
                'user_info': {
                    'username': user_info.get('username', 'Unknown'),
                    'displayName': user_info.get('displayName', 'Unknown'),
                    'userID': user_info.get('userID', 'Unknown')
                }
            }
            
        except Exception as e:
            logger.error(f"Zotero connection test failed for user {current_user.username}: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to connect to Zotero: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing Zotero connection for user {current_user.username}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while testing connection"
        )

class ZoteroSyncRequest(BaseModel):
    collection_id: Optional[str] = None
    limit: Optional[int] = None
    force_full_sync: bool = False
    
    class Config:
        # Enable extra validation
        extra = "forbid"  # Reject any extra fields
    
    @validator('limit')
    def validate_limit(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError('limit must be greater than 0')
            if v > 10000:
                raise ValueError('limit cannot exceed 10000 items for performance reasons')
        return v
    
    @validator('collection_id')
    def validate_collection_id(cls, v):
        if v is not None:
            # Basic validation - Zotero collection IDs are typically 8-character alphanumeric strings
            if not v.strip():
                raise ValueError('collection_id cannot be empty string')
            if len(v) > 100:  # Reasonable upper bound
                raise ValueError('collection_id is too long')
        return v

class ZoteroSyncResponse(BaseModel):
    success: bool
    message: str
    job_id: Optional[str] = None

@app.post("/api/v1/users/me/zotero/sync", response_model=ZoteroSyncResponse)
async def start_user_zotero_sync(
    request: ZoteroSyncRequest = Body(None),
    current_user: User = Depends(get_current_user)
):
    """Start Zotero synchronization for current user (alternative URL)"""
    try:
        logger.info(f"User {current_user.username} requesting Zotero sync with request: {request}")
        # Use the same implementation as the original endpoint for consistency
        return await start_zotero_sync(request, current_user)
    except Exception as e:
        logger.error(f"Error in start_user_zotero_sync: {e}")
        raise

@app.get("/api/v1/users/me/zotero_config", response_model=ZoteroConfigResponse)
async def get_zotero_config(current_user: User = Depends(get_current_user)):
    """Get Zotero configuration for current user"""
    try:
        has_config = current_user.has_zotero_config()
        
        # For personal libraries, user_id is the same as library_id
        user_id = None
        if has_config and current_user.zotero_library_type == 'user':
            user_id = current_user.zotero_library_id
        
        return ZoteroConfigResponse(
            success=True,
            message="Zotero configuration retrieved successfully",
            has_config=has_config,
            configured=has_config,  # Backward compatibility
            library_id=current_user.zotero_library_id if has_config else None,
            library_type=current_user.zotero_library_type if has_config else None,
            user_id=user_id,
            last_sync=current_user.zotero_last_sync.isoformat() if current_user.zotero_last_sync else None
        )
        
    except Exception as e:
        logger.error(f"Error getting Zotero config: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@app.delete("/api/v1/users/me/zotero_config")
async def delete_zotero_config(current_user: User = Depends(get_current_user)):
    """Delete Zotero configuration for current user"""
    try:
        current_user.clear_zotero_config()
        current_user.save()
        
        return {"success": True, "message": "Zotero configuration deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting Zotero config: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@app.delete("/api/v1/users/me/zotero/library")
async def clear_user_zotero_library(current_user: User = Depends(get_current_user)):
    """Clear all Zotero library data for current user"""
    try:
        logger.info(f"User {current_user.username} requesting to clear Zotero library")
        # Check if user has any running Zotero sync jobs
        running_job = (ProcessingJob
                      .select()
                      .where(
                          ProcessingJob.user_id == current_user.id,
                          ProcessingJob.job_type == 'zotero_sync',
                          ProcessingJob.status.in_(['pending', 'processing'])
                      )
                      .first())
        
        if running_job:
            logger.warning(f"User {current_user.username} has running sync job {running_job.job_id}")
            raise HTTPException(
                status_code=400,
                detail="Cannot clear library while sync is in progress. Please cancel the running sync job first."
            )
        
        # Count existing data before deletion
        zotero_items_count = ZoteroItem.select().where(ZoteroItem.user == current_user).count()
        zotero_collections_count = ZoteroCollection.select().where(ZoteroCollection.user == current_user).count()
        logger.info(f"User {current_user.username} has {zotero_items_count} items and {zotero_collections_count} collections to delete")
        
        # Delete all Zotero-related data for this user
        from .models import ZoteroItemPaper
        
        # 1. Delete ZoteroItemPaper relationships
        zotero_item_papers = (ZoteroItemPaper
                             .select()
                             .join(ZoteroItem)
                             .where(ZoteroItem.user == current_user))
        for zip_rel in zotero_item_papers:
            zip_rel.delete_instance()
        
        # Note: ZoteroLink is legacy - not deleting as it may be used elsewhere
        
        # 2. Delete Papers that were created from Zotero sync (optional - commented out for safety)
        # If you want to delete papers created from Zotero sync, uncomment below:
        # zotero_papers = (Paper
        #                 .select()
        #                 .join(ZoteroItemPaper)
        #                 .join(ZoteroItem)
        #                 .where(ZoteroItem.user == current_user))
        # for paper in zotero_papers:
        #     paper.delete_instance()
        
        # 3. Delete ZoteroItems
        zotero_items = ZoteroItem.select().where(ZoteroItem.user == current_user)
        for item in zotero_items:
            item.delete_instance()
        
        # 4. Delete ZoteroCollections
        zotero_collections = ZoteroCollection.select().where(ZoteroCollection.user == current_user)
        for collection in zotero_collections:
            collection.delete_instance()
        
        # 5. Reset last sync time
        current_user.zotero_last_sync = None
        current_user.save()
        
        logger.info(f"Cleared Zotero library for user {current_user.username}: {zotero_items_count} items, {zotero_collections_count} collections")
        
        return {
            "success": True, 
            "message": f"Successfully cleared Zotero library: {zotero_items_count} items and {zotero_collections_count} collections deleted",
            "items_deleted": zotero_items_count,
            "collections_deleted": zotero_collections_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error clearing Zotero library for user {current_user.username}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while clearing library"
        )

@app.post("/api/v1/users/me/zotero_sync", response_model=ZoteroSyncResponse)
async def start_zotero_sync(
    request: ZoteroSyncRequest = Body(None),
    current_user: User = Depends(get_current_user)
):
    """Start Zotero synchronization for current user"""
    try:
        # Validate request parameters if provided
        if request is not None:
            # Pydantic will automatically validate the request based on our model
            # Additional custom validation can be added here if needed
            pass
        
        # Check if user has Zotero configuration
        if not current_user.has_zotero_config():
            raise HTTPException(
                status_code=400,
                detail="Zotero configuration not found. Please configure Zotero first."
            )
        
        # Check if there's already a running sync job for this user
        existing_job = (ProcessingJob
                       .select()
                       .where(
                           ProcessingJob.user_id == current_user.id,
                           ProcessingJob.job_type == 'zotero_sync',
                           ProcessingJob.status.in_(['pending', 'processing'])
                       )
                       .first())
        
        if existing_job:
            # Check if the job is stuck (created more than 30 minutes ago)
            import datetime
            job_age = datetime.datetime.now() - existing_job.created_at
            if job_age.total_seconds() > 1800:  # 30 minutes
                logger.warning(f"Found stuck Zotero sync job {existing_job.job_id}, marking as failed")
                existing_job.mark_failed("Job timed out - automatically cancelled after 30 minutes")
            else:
                # Check if job is actually cancelled
                if check_job_cancelled(existing_job.job_id):
                    logger.info(f"Found cancelled Zotero sync job {existing_job.job_id}, marking as cancelled")
                    existing_job.status = 'cancelled'
                    existing_job.save()
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Zotero sync is already in progress (Job ID: {existing_job.job_id}). Please wait for it to complete or cancel it from the jobs page."
                    )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Create new sync job
        job = ProcessingJob.create(
            job_id=job_id,
            job_type='zotero_sync',
            user_id=current_user,
            status='pending',
            filename=f"zotero_sync_{current_user.username}",
            current_step='initializing',
            total_steps=5,
            progress_percentage=0
        )
        
        # Set parameters using helper method
        job.set_parameters({
            'collection_id': request.collection_id if request else None,
            'limit': request.limit if request else None,
            'force_full_sync': request.force_full_sync if request else False,
            'user_id': current_user.id
        })
        job.save()
        
        # Start background processing
        asyncio.create_task(process_zotero_sync_job(job.job_id))
        
        return ZoteroSyncResponse(
            success=True,
            message="Zotero synchronization started successfully",
            job_id=job.job_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting Zotero sync: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

# Audit logging helper
def create_audit_log(
    performing_user: User,
    affected_user: User,
    action: str,
    details: dict = None,
    request = None
):
    """Create an audit log entry"""
    try:
        # Extract IP and user agent from request if available
        ip_address = None
        user_agent = None
        if request:
            ip_address = request.client.host if hasattr(request, 'client') else None
            user_agent = request.headers.get('user-agent', '')[:500]  # Truncate long user agents
        
        audit_log = UserAuditLog(
            performing_user=performing_user,
            performing_username=performing_user.username,
            affected_user=affected_user,
            affected_username=affected_user.username,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if details:
            audit_log.set_details(details)
        
        audit_log.save()
        return audit_log
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        return None

# Password validation
def validate_password_complexity(password: str) -> List[str]:
    """Validate password complexity and return list of errors"""
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        errors.append("Password must contain at least one special character")
    
    return errors

# User Management Endpoints
class CreateUserRequest(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    is_admin: bool = False

class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    is_admin: bool
    created_at: datetime.datetime
    last_login: Optional[datetime.datetime]
    zotero_configured: bool = False

@app.post("/api/v1/admin/users", response_model=UserResponse)
async def create_user(
    user_request: CreateUserRequest,
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Create a new user (admin only)"""
    try:
        # Check if username already exists
        existing_user = User.select().where(User.username == user_request.username).first()
        if existing_user:
            raise HTTPException(
                status_code=409,
                detail="Username already exists"
            )
        
        # Validate password complexity
        password_errors = validate_password_complexity(user_request.password)
        if password_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": "Password does not meet complexity requirements",
                    "details": {
                        "field": "password",
                        "requirements": password_errors
                    }
                }
            )
        
        # Create new user
        new_user = User(
            username=user_request.username,
            email=user_request.email,
            is_admin=user_request.is_admin
        )
        new_user.set_password(user_request.password)
        new_user.save()
        
        # Create audit log
        create_audit_log(
            performing_user=current_user,
            affected_user=new_user,
            action='user_created',
            details={
                'created_user_id': new_user.id,
                'is_admin': new_user.is_admin,
                'has_email': bool(new_user.email)
            },
            request=request
        )
        
        logger.info(f"User '{new_user.username}' created by admin '{current_user.username}'")
        
        return UserResponse(
            id=new_user.id,
            username=new_user.username,
            email=new_user.email,
            is_admin=new_user.is_admin,
            created_at=new_user.created_at,
            last_login=new_user.last_login,
            zotero_configured=new_user.has_zotero_config()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create user"
        )

class UserListResponse(BaseModel):
    total_count: int
    page: int
    per_page: int
    total_pages: int
    items: List[UserResponse]

@app.get("/api/v1/admin/users", response_model=UserListResponse)
async def list_users(
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(require_admin)
):
    """List all users with pagination (admin only)"""
    try:
        # Get total count
        total_count = User.select().count()
        
        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page
        
        # Get users for current page
        users = User.select().order_by(User.created_at.desc()).offset(offset).limit(per_page)
        
        # Convert to response format
        items = []
        for user in users:
            items.append(UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                is_admin=user.is_admin,
                created_at=user.created_at,
                last_login=user.last_login,
                zotero_configured=user.has_zotero_config()
            ))
        
        return UserListResponse(
            total_count=total_count,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            items=items
        )
        
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list users"
        )

class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    is_admin: Optional[bool] = None
    password: Optional[str] = None

@app.put("/api/v1/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_request: UpdateUserRequest,
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Update user details (admin only)"""
    try:
        # Get user to update
        user = User.get_or_none(User.id == user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Track changes for audit log
        changes = {}
        original_email = user.email
        original_is_admin = user.is_admin
        
        # Update fields if provided
        if update_request.email is not None:
            if user.email != update_request.email:
                changes['email'] = {'old': user.email, 'new': update_request.email}
            user.email = update_request.email
            
        if update_request.is_admin is not None:
            # Prevent removing admin status from the last admin
            if user.is_admin and not update_request.is_admin:
                admin_count = User.select().where(User.is_admin == True).count()
                if admin_count <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot remove admin status from the last administrator"
                    )
            if user.is_admin != update_request.is_admin:
                changes['is_admin'] = {'old': user.is_admin, 'new': update_request.is_admin}
            user.is_admin = update_request.is_admin
            
        if update_request.password is not None:
            # Validate password complexity
            password_errors = validate_password_complexity(update_request.password)
            if password_errors:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "validation_error",
                        "message": "Password does not meet complexity requirements",
                        "details": {
                            "field": "password",
                            "requirements": password_errors
                        }
                    }
                )
            user.set_password(update_request.password)
            changes['password'] = 'changed'
        
        user.save()
        
        # Create audit log if there were changes
        if changes:
            action = 'user_updated'
            if 'password' in changes:
                action = 'password_changed'
            elif 'is_admin' in changes:
                action = 'admin_status_changed'
            
            create_audit_log(
                performing_user=current_user,
                affected_user=user,
                action=action,
                details={
                    'user_id': user.id,
                    'changes': changes
                },
                request=request
            )
        
        logger.info(f"User '{user.username}' updated by admin '{current_user.username}'")
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_admin=user.is_admin,
            created_at=user.created_at,
            last_login=user.last_login,
            zotero_configured=user.has_zotero_config()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update user"
        )

@app.delete("/api/v1/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Delete a user (admin only)"""
    try:
        # Get user to delete
        user = User.get_or_none(User.id == user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Prevent deleting the current user
        if user.id == current_user.id:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete your own account"
            )
        
        # Prevent deleting the last admin
        if user.is_admin:
            admin_count = User.select().where(User.is_admin == True).count()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete the last administrator account"
                )
        
        username = user.username
        user_data = {
            'deleted_user_id': user.id,
            'deleted_username': user.username,
            'was_admin': user.is_admin,
            'had_email': bool(user.email)
        }
        
        # Create audit log before deletion
        create_audit_log(
            performing_user=current_user,
            affected_user=user,
            action='user_deleted',
            details=user_data,
            request=request
        )
        
        user.delete_instance()
        
        logger.info(f"User '{username}' deleted by admin '{current_user.username}'")
        
        return {"success": True, "message": f"User '{username}' deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete user"
        )

@app.post("/api/v1/admin/users/{user_id}/zotero/test")
async def test_user_zotero_connection(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Test a user's Zotero connection (admin only)"""
    try:
        # Get user
        user = User.get_or_none(User.id == user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if user has Zotero config
        if not user.has_zotero_config():
            raise HTTPException(
                status_code=400,
                detail="User does not have Zotero configuration"
            )
        
        # Decrypt API key
        api_key = user.get_zotero_api_key()
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Failed to decrypt API key"
            )
        
        # Test connection
        try:
            from pyzotero import zotero
            library_type = user.zotero_library_type or 'user'  # Default to 'user' if not set
            zot = zotero.Zotero(user.zotero_library_id, library_type, api_key)
            # Test by getting one collection
            collections = zot.collections(limit=1)
            
            # Create audit log
            create_audit_log(
                performing_user=current_user,
                affected_user=user,
                action='zotero_test',
                details={
                    'library_id': user.zotero_library_id,
                    'library_type': library_type,
                    'success': True
                },
                request=request
            )
            
            return {
                "status": "success",
                "message": "Zotero connection successful",
                "library_id": user.zotero_library_id,
                "library_type": library_type
            }
            
        except Exception as e:
            # Create audit log for failed test
            create_audit_log(
                performing_user=current_user,
                affected_user=user,
                action='zotero_test',
                details={
                    'library_id': user.zotero_library_id,
                    'library_type': user.zotero_library_type,
                    'success': False,
                    'error': str(e)
                },
                request=request
            )
            
            return {
                "status": "error",
                "message": f"Zotero connection failed: {str(e)}"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing Zotero connection: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to test Zotero connection"
        )

class UpdateUserZoteroRequest(BaseModel):
    library_id: str
    library_type: str
    api_key: Optional[str] = None  # Only provided if being changed

@app.post("/api/v1/admin/users/{user_id}/zotero")
async def update_user_zotero_config(
    user_id: int,
    zotero_request: UpdateUserZoteroRequest,
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Update a user's Zotero configuration (admin only)"""
    try:
        # Get user
        user = User.get_or_none(User.id == user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update Zotero config
        user.zotero_library_id = zotero_request.library_id
        user.zotero_library_type = zotero_request.library_type
        
        # Update API key if provided
        if zotero_request.api_key:
            user.set_zotero_api_key(zotero_request.api_key)
        
        user.save()
        
        # Create audit log
        create_audit_log(
            performing_user=current_user,
            affected_user=user,
            action='zotero_config_updated',
            details={
                'library_id': zotero_request.library_id,
                'library_type': zotero_request.library_type,
                'api_key_updated': bool(zotero_request.api_key)
            },
            request=request
        )
        
        return {
            "success": True,
            "message": "Zotero configuration updated successfully",
            "has_config": user.has_zotero_config()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating Zotero config: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update Zotero configuration"
        )

# ============================================================================
# Admin Zotero Library APIs
# ============================================================================

@app.get("/api/v1/admin/users/{user_id}/zotero/collections")
async def get_admin_user_zotero_collections(
    user_id: int,
    current_user: User = Depends(require_admin)
):
    """Get Zotero collections for a specific user (admin only)"""
    try:
        user = User.get(User.id == user_id)
        collections = []
        
        for collection in user.zotero_collections.order_by(ZoteroCollection.name):
            # Count items in this collection
            item_count = (ZoteroCollectionItem
                         .select()
                         .where(ZoteroCollectionItem.collection == collection)
                         .count())
            
            collections.append({
                'key': collection.collection_key,
                'name': collection.name,
                'parent_key': collection.parent_key,
                'version': collection.version,
                'numItems': item_count  # Add actual item count
            })
        
        return {'collections': collections}
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        logger.error(f"Error fetching collections for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch collections")

@app.get("/api/v1/admin/users/{user_id}/zotero/items")
async def get_admin_user_zotero_items(
    user_id: int,
    page: int = 1,
    per_page: int = 20,
    collection: Optional[str] = None,
    search: Optional[str] = None,
    item_type: Optional[str] = None,
    current_user: User = Depends(require_admin)
):
    """Get Zotero items for a specific user (admin only)"""
    try:
        user = User.get(User.id == user_id)
        
        # Build query using ZoteroItemPaper relationships to get items with actual papers
        zotero_papers_query = ZoteroItemPaper.select().join(ZoteroItem).where(ZoteroItem.user == user)
        
        if search:
            # Search in Paper metadata
            zotero_papers_query = zotero_papers_query.join(Paper).join(Metadata).where(
                (Metadata.title.contains(search)) | 
                (Metadata.authors.contains(search))
            )
        
        # Get total count
        total = zotero_papers_query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        zotero_papers = zotero_papers_query.offset(offset).limit(per_page)
        
        items = []
        for zp in zotero_papers:
            item = zp.zotero_item
            paper = zp.paper
            
            try:
                metadata = paper.metadata.get()
                title = metadata.title or 'Untitled'
                authors = metadata.get_authors()
                abstract = metadata.abstract or ''
                date = str(metadata.year) if metadata.year else ''
            except:
                # Fallback to ZoteroItem data if no metadata
                data = item.get_data()
                title = data.get('title', 'Untitled')
                creators = data.get('creators', [])
                authors = [f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() for c in creators] if isinstance(creators, list) else []
                abstract = data.get('abstractNote', '')
                date = data.get('date', '')
            
            items.append({
                'key': item.zotero_key,
                'itemType': item.item_type,
                'title': title,
                'creators': [{'name': author} for author in authors] if authors else [],
                'date': date,
                'publicationTitle': '',  # Could be added from metadata if needed
                'abstractNote': abstract,
                'attachments': [],
                'version': item.version,
                'paper_id': paper.doc_id
            })
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
        
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        logger.error(f"Error fetching items for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch items")

@app.delete("/api/v1/admin/users/{user_id}/zotero/library")
async def admin_clear_user_zotero_library(
    user_id: int,
    current_user: User = Depends(require_admin)
):
    """Clear all Zotero library data for a specific user (admin only)"""
    try:
        user = User.get(User.id == user_id)
        
        # Check if user has any running Zotero sync jobs
        running_job = (ProcessingJob
                      .select()
                      .where(
                          ProcessingJob.user_id == user.id,
                          ProcessingJob.job_type == 'zotero_sync',
                          ProcessingJob.status.in_(['pending', 'processing'])
                      )
                      .first())
        
        if running_job:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot clear library for user {user.username} while sync is in progress. Please cancel the running sync job first."
            )
        
        # Count existing data before deletion
        zotero_items_count = ZoteroItem.select().where(ZoteroItem.user == user).count()
        zotero_collections_count = ZoteroCollection.select().where(ZoteroCollection.user == user).count()
        
        # Delete all Zotero-related data for this user
        from .models import ZoteroItemPaper
        
        # 1. Delete ZoteroItemPaper relationships
        zotero_item_papers = (ZoteroItemPaper
                             .select()
                             .join(ZoteroItem)
                             .where(ZoteroItem.user == user))
        for zip_rel in zotero_item_papers:
            zip_rel.delete_instance()
        
        # Note: ZoteroLink is legacy - not deleting as it may be used elsewhere
        
        # 2. Delete Papers that were created from Zotero sync (optional - commented out for safety)
        # If you want to delete papers created from Zotero sync, uncomment below:
        # zotero_papers = (Paper
        #                 .select()
        #                 .join(ZoteroItemPaper)
        #                 .join(ZoteroItem)
        #                 .where(ZoteroItem.user == current_user))
        # for paper in zotero_papers:
        #     paper.delete_instance()
        
        # 3. Delete ZoteroItems
        zotero_items = ZoteroItem.select().where(ZoteroItem.user == user)
        for item in zotero_items:
            item.delete_instance()
        
        # 4. Delete ZoteroCollections
        zotero_collections = ZoteroCollection.select().where(ZoteroCollection.user == user)
        for collection in zotero_collections:
            collection.delete_instance()
        
        # 5. Reset last sync time
        user.zotero_last_sync = None
        user.save()
        
        # Log admin action
        logger.info(f"Admin {current_user.username} cleared Zotero library for user {user.username}: {zotero_items_count} items, {zotero_collections_count} collections")
        
        # Create audit log
        create_audit_log(
            performing_user=current_user,
            affected_user=user,
            action="clear_zotero_library",
            details={
                "items_deleted": zotero_items_count,
                "collections_deleted": zotero_collections_count
            }
        )
        
        return {
            "success": True, 
            "message": f"Successfully cleared Zotero library for user {user.username}: {zotero_items_count} items and {zotero_collections_count} collections deleted",
            "user_id": user_id,
            "username": user.username,
            "items_deleted": zotero_items_count,
            "collections_deleted": zotero_collections_count
        }
        
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing Zotero library for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while clearing library"
        )

@app.post("/api/v1/admin/users/{user_id}/zotero/sync")
async def admin_sync_user_zotero(
    user_id: int,
    request: ZoteroSyncRequest = Body(None),
    current_user: User = Depends(require_admin)
):
    """Start Zotero sync for a specific user (admin only)"""
    try:
        # Validate request parameters if provided
        if request is not None:
            # Pydantic will automatically validate the request based on our model
            pass
        
        user = User.get(User.id == user_id)
        
        if not user.has_zotero_config():
            raise HTTPException(
                status_code=400,
                detail="User does not have Zotero configuration"
            )
        
        # Create Zotero sync job
        job_id = str(uuid.uuid4())
        job = ProcessingJob.create(
            job_id=job_id,
            filename=f"zotero_sync_admin_{user.username}",
            status='pending',
            job_type='zotero_sync',
            user_id=user,
            total_steps=5
        )
        job.set_parameters({
            'user_id': user.id,
            'collection_id': request.collection_id if request else None,
            'limit': request.limit if request else None,
            'force_full_sync': request.force_full_sync if request else False,
            'started_by_admin': True,
            'admin_user_id': current_user.id
        })
        job.save()
        
        # Start background processing
        asyncio.create_task(process_zotero_sync_job(job_id))
        
        return {
            'success': True,
            'message': 'Zotero sync started successfully',
            'job_id': job_id
        }
        
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        logger.error(f"Error starting Zotero sync for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start sync")

# ============================================================================
# Audit Logs
# ============================================================================

class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime.datetime
    performing_username: str
    affected_username: str
    action: str
    details: Optional[dict]
    ip_address: Optional[str]

class AuditLogListResponse(BaseModel):
    total_count: int
    page: int
    per_page: int
    total_pages: int
    items: List[AuditLogResponse]

@app.get("/api/v1/admin/audit_logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = 1,
    per_page: int = 50,
    action: Optional[str] = None,
    affected_user: Optional[str] = None,
    current_user: User = Depends(require_admin)
):
    """Get audit logs with pagination and filtering (admin only)"""
    try:
        # Build query
        query = UserAuditLog.select()
        
        # Apply filters
        if action:
            query = query.where(UserAuditLog.action == action)
        if affected_user:
            query = query.where(UserAuditLog.affected_username.contains(affected_user))
        
        # Get total count
        total_count = query.count()
        
        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page
        
        # Get logs for current page
        logs = query.order_by(UserAuditLog.timestamp.desc()).offset(offset).limit(per_page)
        
        # Convert to response format
        items = []
        for log in logs:
            items.append(AuditLogResponse(
                id=log.id,
                timestamp=log.timestamp,
                performing_username=log.performing_username,
                affected_username=log.affected_username,
                action=log.action,
                details=log.get_details(),
                ip_address=log.ip_address
            ))
        
        return AuditLogListResponse(
            total_count=total_count,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            items=items
        )
        
    except Exception as e:
        logger.error(f"Error getting audit logs: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get audit logs"
        )

def check_job_cancelled(job_id: str) -> bool:
    """Check if job has been cancelled"""
    try:
        job = ProcessingJob.get(ProcessingJob.job_id == job_id)
        return job.status == 'cancelled'
    except ProcessingJob.DoesNotExist:
        return True  # If job doesn't exist, consider it cancelled

async def process_zotero_sync_job(job_id: str):
    """Process Zotero synchronization job with new models"""
    import asyncio
    from pyzotero import zotero
    import datetime
    
    job = ProcessingJob.get(ProcessingJob.job_id == job_id)
    
    try:
        # Update job status
        job.status = 'processing'
        job.current_step = 'connecting_to_zotero'
        job.progress_percentage = 5
        job.save()
        
        # Check if job was cancelled
        if check_job_cancelled(job_id):
            logger.info(f"Zotero sync job {job_id} was cancelled")
            return
        
        # Get user and Zotero config
        user = User.get(User.id == job.get_parameters()['user_id'])
        api_key = user.get_zotero_api_key()
        
        if not api_key:
            raise Exception("Failed to decrypt Zotero API key. Please reconfigure your Zotero settings in the dashboard.")
        
        # Connect to Zotero
        library_type = user.zotero_library_type or 'user'
        zot = zotero.Zotero(user.zotero_library_id, library_type, api_key)
        
        # Check if job was cancelled
        if check_job_cancelled(job_id):
            logger.info(f"Zotero sync job {job_id} was cancelled")
            return
        
        # Update progress - sync collections first
        job.current_step = 'syncing_collections'
        job.progress_percentage = 10
        job.save()
        
        # Sync collections
        collections_synced = await sync_zotero_collections(user, zot)
        logger.info(f"Synced {collections_synced} collections")
        
        # Check if job was cancelled
        if check_job_cancelled(job_id):
            logger.info(f"Zotero sync job {job_id} was cancelled")
            return
        
        # Update progress - fetch items
        job.current_step = 'fetching_items'
        job.progress_percentage = 20
        job.save()
        
        # Determine sync parameters
        job_params = job.get_parameters()
        params = {}
        if job_params.get('limit'):
            params['limit'] = job_params['limit']
        
        # Incremental sync unless force_full_sync is True
        if not job_params.get('force_full_sync') and user.zotero_last_sync:
            # Use last sync time for incremental sync (Zotero expects Unix timestamp)
            import time
            since_timestamp = int(user.zotero_last_sync.timestamp())
            params['since'] = since_timestamp
            logger.info(f"🔄 Incremental sync: fetching items since {user.zotero_last_sync} (timestamp: {since_timestamp})")
        else:
            logger.info("🔄 Full sync: fetching all items")
        
        logger.info(f"📋 Sync parameters: {params}")
        
        # Fetch all items (exclude attachments to get only parent items) - similar to collections
        if job_params.get('collection_id'):
            logger.info(f"📁 Fetching parent items from collection: {job_params['collection_id']}")
            # For collection-specific sync, still use params with limits if specified
            params['itemType'] = '-attachment'  # Exclude attachments
            items = zot.collection_items(job_params['collection_id'], **params)
        else:
            logger.info("📚 Fetching all parent items using everything() method (similar to collections)")
            # Use everything() method to get all items without pagination limits
            try:
                # Get all items (excluding attachments) using everything method
                items = zot.everything(zot.items(itemType='-attachment'))
                logger.info(f"📊 Retrieved {len(items)} parent items using everything(items()) method")
                
                # Add delay after fetching to be gentle on Zotero API
                if len(items) > 0:
                    await asyncio.sleep(2.0)  # 2 second pause after fetching items
                    logger.info("⏸️ Added 2 second pause after fetching items from Zotero API")
                    
            except Exception as e:
                logger.warning(f"Failed to use everything() method: {e}, falling back to items() method")
                params['itemType'] = '-attachment'  # Exclude attachments
                items = zot.items(**params)
                
                # Add delay after fallback fetch too
                if len(items) > 0:
                    await asyncio.sleep(2.0)  # 2 second pause after fallback fetch
                    logger.info("⏸️ Added 2 second pause after fallback fetch from Zotero API")
        
        logger.info(f"📊 Fetched {len(items)} items for processing")
        
        # Test: Try fetching with different methods if no items found
        if len(items) == 0:
            logger.info("🔍 No items found, testing different approaches...")
            
            # Test 1: Force full sync of parent items only
            test_items_1 = zot.items(limit=10, itemType='-attachment')
            logger.info(f"Test 1 - items(limit=10, itemType='-attachment'): {len(test_items_1)} items")
            
            # Test 2: Try without any filters
            try:
                test_items_2 = zot.items(limit=5)
                logger.info(f"Test 2 - items(limit=5) [all types]: {len(test_items_2)} items")
                if len(test_items_2) > 0:
                    # Show item types for debugging
                    item_types = [item.get('data', {}).get('itemType', 'unknown') for item in test_items_2]
                    logger.info(f"Item types found: {item_types}")
            except Exception as e:
                logger.info(f"Test 2 failed: {e}")
            
            # Test 3: Check user's last sync time
            logger.info(f"User's last sync time: {user.zotero_last_sync}")
            
            # Use the working method if available
            if len(test_items_1) > 0:
                logger.info("🎯 Using parent items only")
                items = test_items_1  # For testing, use small subset
        
        # Check if job was cancelled
        if check_job_cancelled(job_id):
            logger.info(f"Zotero sync job {job_id} was cancelled")
            return
        
        # Update progress - process items
        job.current_step = 'processing_items'
        job.progress_percentage = 30
        job.total_steps = len(items) + 10
        job.save()
        
        processed_count = 0
        success_count = 0
        error_count = 0
        pdf_count = 0
        
        # Process items in batches to reduce memory usage and allow better concurrency
        batch_size = 20  # Process 20 items at a time
        total_items = len(items)
        
        for i in range(0, total_items, batch_size):
            batch = items[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(total_items + batch_size - 1)//batch_size} ({len(batch)} items)")
            
            for item in batch:
                # Check if job was cancelled every 10 items
                if processed_count % 10 == 0 and check_job_cancelled(job_id):
                    logger.info(f"Zotero sync job {job_id} was cancelled during item processing")
                    return
                
                # Add more frequent delays to reduce CPU load and allow other requests
                if processed_count % 2 == 0:  # Every 2 items instead of 5
                    await asyncio.sleep(0.2)  # 200ms pause instead of 100ms
                
                try:
                    # Process each item (including attachments)
                    result = await process_zotero_item(user, zot, item, job_params.get('force_full_sync', False))
                    
                    if result['processed']:
                        success_count += 1
                        if result['pdf_created']:
                            pdf_count += 1
                    elif result['skipped']:
                        # Item already exists and not force sync
                        pass
                    else:
                        error_count += 1
                    
                    processed_count += 1
                    
                    # Update progress less frequently to reduce database load
                    if processed_count % 10 == 0:  # Update every 10 items instead of every item
                        progress = 30 + (processed_count / len(items)) * 60
                        job.progress_percentage = int(progress)
                        job.save()
                        
                except Exception as e:
                    logger.error(f"Error processing item {item['key']}: {e}")
                    error_count += 1
                    processed_count += 1
                    continue
            
            # Add longer pause between batches to allow other requests
            if i + batch_size < total_items:  # Not the last batch
                logger.info(f"Batch completed, taking 1-second break to allow other requests...")
                await asyncio.sleep(1.0)  # 1 second pause between batches
        
        # Update last sync time
        user.zotero_last_sync = datetime.datetime.now()
        user.save()
        
        # Complete job
        job.status = 'completed'
        job.current_step = 'completed'
        job.progress_percentage = 100
        job.completed_at = datetime.datetime.now()
        job.set_result({
            'processed_items': processed_count,
            'success_count': success_count,
            'error_count': error_count,
            'pdf_count': pdf_count,
            'collections_synced': collections_synced,
            'total_items': len(items)
        })
        job.save()
        
        logger.info(f"Zotero sync completed for user {user.username}: {success_count} items, {pdf_count} PDFs, {error_count} errors")
        
    except Exception as e:
        logger.error(f"Zotero sync job failed: {e}")
        job.status = 'failed'
        job.error = str(e)
        job.save()

async def sync_zotero_collections(user: User, zot_instance) -> int:
    """Sync Zotero collections"""
    import json
    import datetime
    try:
        # Use all_collections() method to get all collections
        collections = zot_instance.all_collections()
        logger.info(f"📊 Retrieved {len(collections)} collections using all_collections() method")
        synced_count = 0
        
        for collection in collections:
            collection_data = collection['data']
            
            # Create or update collection (unique per user)
            zotero_collection, created = ZoteroCollection.get_or_create(
                collection_key=collection['key'],
                user=user,
                defaults={
                    'library_id': user.zotero_library_id,
                    'name': collection_data['name'],
                    'parent_key': collection_data.get('parentCollection'),
                    'version': collection['version'],
                    'data': json.dumps(collection_data)
                }
            )
            
            if not created:
                # Update existing collection if version is newer
                if collection['version'] > zotero_collection.version:
                    zotero_collection.name = collection_data['name']
                    zotero_collection.parent_key = collection_data.get('parentCollection')
                    zotero_collection.version = collection['version']
                    zotero_collection.data = json.dumps(collection_data)
                    zotero_collection.updated_at = datetime.datetime.now()
                    zotero_collection.save()
            
            synced_count += 1
        
        return synced_count
        
    except Exception as e:
        logger.error(f"Error syncing collections: {e}")
        return 0

async def process_zotero_item(user: User, zot_instance, item: dict, force_sync: bool = False) -> dict:
    """Process a single Zotero item with new model structure"""
    result = {
        'processed': False,
        'skipped': False,
        'pdf_created': False,
        'error': None
    }
    
    try:
        item_data = item['data']
        item_key = item['key']
        
        # Check if item already exists
        existing_item = (ZoteroItem
                        .select()
                        .where(
                            ZoteroItem.zotero_key == item_key,
                            ZoteroItem.library_id == user.zotero_library_id
                        )
                        .first())
        
        if existing_item and not force_sync:
            # Skip if already exists and not force sync
            result['skipped'] = True
            return result
        
        # Create or update ZoteroItem
        if existing_item:
            zotero_item = existing_item
            zotero_item.version = item['version']
            zotero_item.modified_date = datetime.datetime.fromisoformat(item_data.get('dateModified', '').replace('Z', '+00:00')) if item_data.get('dateModified') else None
        else:
            zotero_item = ZoteroItem(
                zotero_key=item_key,
                library_id=user.zotero_library_id,
                user=user,
                version=item['version']
            )
        
        # Set item data
        zotero_item.item_type = item_data.get('itemType', 'unknown')
        zotero_item.parent_key = item_data.get('parentItem')
        zotero_item.is_attachment = (item_data.get('itemType') == 'attachment')
        zotero_item.set_data(item_data)
        zotero_item.synced_at = datetime.datetime.now()
        
        # Handle attachment-specific fields
        if zotero_item.is_attachment:
            zotero_item.content_type = item_data.get('contentType')
            zotero_item.filename = item_data.get('filename')
            zotero_item.link_mode = item_data.get('linkMode')
            zotero_item.url = item_data.get('url')
        
        # Handle dates
        if item_data.get('dateAdded'):
            try:
                zotero_item.created_date = datetime.datetime.fromisoformat(item_data['dateAdded'].replace('Z', '+00:00'))
            except:
                pass
        
        if item_data.get('dateModified'):
            try:
                zotero_item.modified_date = datetime.datetime.fromisoformat(item_data['dateModified'].replace('Z', '+00:00'))
            except:
                pass
        
        # Populate search optimization fields
        zotero_item.title = item_data.get('title')
        zotero_item.journal = (item_data.get('publicationTitle') or 
                              item_data.get('journalAbbreviation'))
        zotero_item.doi = item_data.get('DOI')
        zotero_item.abstract = item_data.get('abstractNote')
        zotero_item.year = zotero_item.extract_year_from_date(item_data.get('date'))
        
        # Set authors from creators
        creators = item_data.get('creators', [])
        zotero_item.set_authors_from_creators(creators)
        
        zotero_item.save()
        
        # Save collection relationships
        collections = item_data.get('collections', [])
        if collections and not zotero_item.is_attachment:
            # Only save collection relationships for non-attachment items
            for collection_key in collections:
                try:
                    # Find the collection
                    collection = (ZoteroCollection
                                .select()
                                .where(
                                    ZoteroCollection.collection_key == collection_key,
                                    ZoteroCollection.library_id == user.zotero_library_id,
                                    ZoteroCollection.user == user
                                )
                                .first())
                    
                    if collection:
                        # Create or update the relationship
                        ZoteroCollectionItem.get_or_create(
                            collection=collection,
                            item=zotero_item
                        )
                        logger.debug(f"Linked item {item_key} to collection {collection_key}")
                    else:
                        logger.warning(f"Collection {collection_key} not found for item {item_key}")
                        
                except Exception as e:
                    logger.error(f"Error linking item {item_key} to collection {collection_key}: {e}")
        
        # Skip PDF processing for now - just sync metadata
        # TODO: Implement separate PDF attachment processing
        if zotero_item.is_pdf_attachment():
            logger.info(f"📎 Skipping PDF processing for attachment {item_key} (metadata-only sync)")
            # Don't set pdf_created = True for attachments in this phase
        
        result['processed'] = True
        return result
        
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"Error processing Zotero item {item.get('key', 'unknown')}: {e}")
        return result

async def upload_from_zotero_sync(user: User, item: dict, pdf_content: bytes, attachment: dict):
    """Upload PDF from Zotero sync to RefServerLite"""
    try:
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
            date_str = str(data['date'])
            import re
            matches = re.findall(r'\b\d{4}\b', date_str)
            current_year = datetime.datetime.now().year
            
            for potential_year_str in matches:
                try:
                    potential_year = int(potential_year_str)
                    if 1500 <= potential_year <= current_year + 1:
                        year = potential_year
                        break
                except ValueError:
                    pass
        
        # Create document
        doc_id = f"zotero_{item['key']}"
        filename = attachment['data'].get('filename', f"{item['key']}.pdf")
        
        # Save PDF file
        pdf_path = f"refdata/pdfs/{doc_id}.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(pdf_content)
        
        # Create Paper record
        paper = Paper.create(
            doc_id=doc_id,
            filename=filename,
            file_path=pdf_path,
            uploaded_by=user.id
        )
        
        # Create Metadata record
        Metadata.create(
            paper=paper,
            title=data.get('title', 'Untitled'),
            authors=json.dumps(authors),
            journal=data.get('publicationTitle', ''),
            year=year,
            source='zotero'
        )
        
        # Create ZoteroLink record
        ZoteroLink.create(
            paper=paper,
            zotero_key=item['key'],
            library_id=user.zotero_library_id,
            zotero_version=item['version'],
            collection_keys=json.dumps(data.get('collections', [])),
            tags=json.dumps([tag['tag'] for tag in data.get('tags', [])])
        )
        
        # Start background processing for this document
        processing_job = ProcessingJob.create(
            job_id=str(uuid.uuid4()),
            job_type='process_pdf',
            user_id=user,
            status='pending',
            filename=filename,
            current_step='initializing',
            total_steps=4,
            progress_percentage=0
        )
        
        # Set parameters using helper method
        processing_job.set_parameters({'doc_id': doc_id, 'from_zotero': True})
        processing_job.save()
        
        # Let the background processor handle this job
        # Background processor will pick this up automatically
        
        logger.info(f"Successfully uploaded {filename} from Zotero")
        
    except Exception as e:
        logger.error(f"Error uploading from Zotero: {e}")
        raise

async def create_paper_from_zotero_attachment(user: User, zotero_item: 'ZoteroItem', zot_instance, pdf_content: bytes) -> Optional['Paper']:
    """Create a Paper record from a Zotero PDF attachment using new model structure"""
    try:
        import uuid
        import os
        import json
        
        # Get parent item metadata if this is an attachment
        parent_item = None
        if zotero_item.parent_key:
            # Try to get parent from our database first
            parent_zotero_item = (ZoteroItem
                                .select()
                                .where(
                                    ZoteroItem.zotero_key == zotero_item.parent_key,
                                    ZoteroItem.library_id == zotero_item.library_id
                                )
                                .first())
            
            if parent_zotero_item:
                parent_item = parent_zotero_item.get_data()
            else:
                # Fetch parent from Zotero API
                try:
                    parent_item_response = zot_instance.item(zotero_item.parent_key)
                    parent_item = parent_item_response['data']
                except:
                    logger.warning(f"Could not fetch parent item {zotero_item.parent_key}")
        
        # Generate unique doc_id and use consistent filename format (like regular upload)
        doc_id = str(uuid.uuid4())
        original_filename = zotero_item.filename or f"zotero_{zotero_item.zotero_key}.pdf"
        
        # Ensure filename is safe
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in "._-")
        if not safe_filename.endswith('.pdf'):
            safe_filename += '.pdf'
        
        # Save PDF file with consistent naming like regular upload: {doc_id}_{filename}
        pdf_dir = "refdata/pdfs"
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{doc_id}_{safe_filename}")
        
        with open(pdf_path, 'wb') as f:
            f.write(pdf_content)
        
        # Create Paper record (consistent with regular upload)
        paper = Paper.create(
            doc_id=doc_id,
            filename=original_filename,  # Use original filename like regular upload
            file_path=pdf_path,
            uploaded_by=user  # Set the user who imported this PDF
        )
        
        # Store Zotero metadata for later use by background processing
        # Don't create Metadata record here - let background processing handle it consistently
        
        # Create ProcessingJob (consistent with regular upload)
        job_id = str(uuid.uuid4())
        logger.info(f"Creating ProcessingJob {job_id} for Zotero attachment {zotero_item.zotero_key}")
        processing_job = ProcessingJob.create(
            job_id=job_id,
            paper=paper,
            filename=paper.filename,
            status='uploaded',  # Same as regular upload
            user_id=user
        )
        logger.info(f"Successfully created ProcessingJob {job_id} for paper {paper.doc_id}")
        
        # Let the background processor handle this job
        # Don't start processing immediately to avoid duplicate processing
        
        logger.info(f"Successfully created Paper {doc_id} from Zotero attachment {zotero_item.zotero_key}")
        return paper
        
    except Exception as e:
        logger.error(f"Error creating Paper from Zotero attachment {zotero_item.zotero_key}: {e}")
        return None

# DEPRECATED: This function is no longer used - background processor handles all jobs
# async def process_document_job(job_id: str):
#     """Process a document job using the pipeline processor"""
#     try:
#         # Create processor instance and process the document
#         processor = PDFProcessingPipeline()
#         await processor.process_document(job_id)
#     except Exception as e:
#         logger.error(f"Error processing document job {job_id}: {e}")
#         # Mark job as failed
#         try:
#             job = ProcessingJob.get(ProcessingJob.job_id == job_id)
#             job.mark_failed(str(e))
#         except:
#             pass

# ============================================================================
# User-specific APIs
# ============================================================================

@app.get("/api/v1/users/me/papers")
async def get_user_papers(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get papers uploaded by the current user"""
    try:
        # Build query for user's papers
        query = Paper.select().where(Paper.uploaded_by == current_user)
        
        # Filter by processing status if provided
        if status:
            # Join with ProcessingJob to filter by status
            query = query.join(ProcessingJob).where(ProcessingJob.status == status)
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        papers_query = query.order_by(Paper.created_at.desc()).offset(offset).limit(per_page)
        
        papers = []
        for paper in papers_query:
            # Get latest job status
            job_status = "unknown"
            progress_percentage = 0
            job_id = None
            try:
                latest_job = paper.jobs.order_by(ProcessingJob.created_at.desc()).get()
                job_status = latest_job.status
                progress_percentage = latest_job.progress_percentage
                job_id = latest_job.job_id
            except ProcessingJob.DoesNotExist:
                pass
            
            # Get metadata
            metadata = {}
            try:
                meta = paper.metadata.get()
                metadata = {
                    "title": meta.title,
                    "authors": meta.get_authors() if hasattr(meta, 'get_authors') else [],
                    "journal": meta.journal,
                    "year": meta.year,
                    "source": meta.source
                }
            except Metadata.DoesNotExist:
                pass
            
            papers.append({
                "doc_id": paper.doc_id,
                "filename": paper.filename,
                "status": job_status,
                "progress_percentage": progress_percentage,
                "job_id": job_id,
                "metadata": metadata,
                "created_at": paper.created_at.isoformat(),
                "updated_at": paper.updated_at.isoformat()
            })
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        
        return {
            "papers": papers,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_count,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching user papers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/users/me/zotero/collections")
async def get_user_zotero_collections(current_user: User = Depends(get_current_user)):
    """Get Zotero collections for the current user"""
    import json
    try:
        collections = []
        for collection in current_user.zotero_collections.order_by(ZoteroCollection.name):
            data = json.loads(collection.data) if collection.data else {}
            
            # Count items in this collection
            item_count = (ZoteroCollectionItem
                         .select()
                         .where(ZoteroCollectionItem.collection == collection)
                         .count())
            
            collections.append({
                "collection_key": collection.collection_key,
                "name": collection.name,
                "parent_key": collection.parent_key,
                "library_id": collection.library_id,
                "version": collection.version,
                "data": data,
                "numItems": item_count,  # Add item count
                "created_at": collection.created_at.isoformat(),
                "updated_at": collection.updated_at.isoformat()
            })
        
        return {"collections": collections}
        
    except Exception as e:
        logger.error(f"Error fetching user Zotero collections: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/users/me/zotero/items")
async def get_user_zotero_items(
    page: int = 1,
    per_page: int = 50,
    collection: Optional[str] = None,
    collection_key: Optional[str] = None,  # Keep for backward compatibility
    item_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get Zotero items for the current user"""
    import json
    try:
        # Build query for ZoteroItems directly (not requiring PDF attachments)
        zotero_items_query = ZoteroItem.select().where(ZoteroItem.user == current_user)
        
        # Use collection if collection_key is not provided (for backward compatibility)
        filter_collection = collection_key or collection
        
        logger.info(f"Getting items for user {current_user.username}, collection={collection}, collection_key={collection_key}, filter_collection={filter_collection}")
        
        # Filter by collection if provided
        if filter_collection and filter_collection != 'all':
            # Use ZoteroCollectionItem table for efficient filtering
            try:
                collection_obj = (ZoteroCollection
                            .select()
                            .where(
                                ZoteroCollection.collection_key == filter_collection,
                                ZoteroCollection.user == current_user
                            )
                            .first())
                
                if collection_obj:
                    # Join with ZoteroCollectionItem to get items in this collection
                    zotero_items_query = (ZoteroItem
                                        .select()
                                        .join(ZoteroCollectionItem)
                                        .where(
                                            ZoteroCollectionItem.collection == collection_obj,
                                            ZoteroItem.user == current_user
                                        ))
                else:
                    logger.warning(f"Collection {filter_collection} not found for user {current_user.username}")
                    # Return empty result if collection not found
                    return {
                        "items": [],
                        "total": 0,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": 0
                    }
            except Exception as e:
                logger.error(f"Error filtering by collection: {e}")
                # Fall back to no filtering
        
        # Filter by item type if provided
        if item_type:
            zotero_items_query = zotero_items_query.where(ZoteroItem.item_type == item_type)
        
        # Get total count and apply pagination
        total_count = zotero_items_query.count()
        offset = (page - 1) * per_page
        zotero_items = zotero_items_query.offset(offset).limit(per_page)
        
        items = []
        for item in zotero_items:
            # Use ZoteroItem data directly
            data = item.get_data()
            title = data.get('title', 'Untitled')
            creators = data.get('creators', [])
            authors = [f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() for c in creators] if isinstance(creators, list) else []
            abstract = data.get('abstractNote', '')
            date = data.get('date', '')
            publication_title = data.get('publicationTitle', '')
            
            # Check if this item has an associated PDF
            paper_id = None
            try:
                zotero_paper = ZoteroItemPaper.select().where(ZoteroItemPaper.zotero_item == item).get()
                paper_id = zotero_paper.paper.doc_id
            except ZoteroItemPaper.DoesNotExist:
                pass  # No PDF attachment
            
            items.append({
                'key': item.zotero_key,
                'itemType': item.item_type,
                'title': title,
                'creators': [{'name': author} for author in authors] if authors else [],
                'date': date,
                'publicationTitle': publication_title,
                'abstractNote': abstract,
                'attachments': [],
                'version': item.version,
                'paper_id': paper_id,  # None if no PDF attached
                'has_pdf': paper_id is not None
            })
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        
        return {
            "items": items,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }
        
    except Exception as e:
        logger.error(f"Error fetching user Zotero items: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/api/v1/users/me/zotero/sync_item/{item_key}")
async def sync_single_zotero_item(
    item_key: str,
    current_user: User = Depends(get_current_user)
):
    """Sync a single Zotero item from the library"""
    try:
        # Check if user has Zotero configured
        if not current_user.has_zotero_config():
            raise HTTPException(status_code=400, detail="Zotero not configured")
        
        # Get Zotero instance
        from pyzotero import zotero as pyzotero
        zot = pyzotero.Zotero(
            current_user.zotero_library_id,
            current_user.zotero_library_type,
            current_user.get_zotero_api_key()
        )
        
        # Fetch the specific item
        try:
            item = zot.item(item_key)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found in Zotero")
        except Exception as e:
            logger.error(f"Error fetching item {item_key} from Zotero: {e}")
            raise HTTPException(status_code=404, detail="Item not found in Zotero")
        
        # Process the item
        result = await process_zotero_item(current_user, zot, item, force_sync=True)
        
        if result['processed']:
            return {
                "success": True,
                "message": "Item synced successfully"
            }
        else:
            return {
                "success": False,
                "message": "Item sync failed",
                "error": result.get('error')
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing Zotero item {item_key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/users/me/zotero/import/{item_key}")
async def import_zotero_item_pdfs(
    item_key: str,
    current_user: User = Depends(get_current_user)
):
    """Import PDF attachments for a specific Zotero item"""
    try:
        # Check if user has Zotero configured
        if not current_user.has_zotero_config():
            raise HTTPException(status_code=400, detail="Zotero not configured")
        
        # Get the Zotero item
        zotero_item = (ZoteroItem
                      .select()
                      .where(
                          ZoteroItem.zotero_key == item_key,
                          ZoteroItem.user == current_user
                      )
                      .first())
        
        if not zotero_item:
            raise HTTPException(status_code=404, detail="Item not found in local database")
        
        # Get Zotero instance
        from pyzotero import zotero as pyzotero
        zot = pyzotero.Zotero(
            current_user.zotero_library_id,
            current_user.zotero_library_type,
            current_user.get_zotero_api_key()
        )
        
        # Find PDF attachments
        children = zot.children(item_key)
        pdf_attachments = [
            child for child in children 
            if child['data'].get('itemType') == 'attachment' 
            and child['data'].get('contentType') == 'application/pdf'
        ]
        
        if not pdf_attachments:
            return {
                "success": True,
                "message": "No PDF attachments found",
                "imported_count": 0
            }
        
        imported_count = 0
        for attachment in pdf_attachments:
            try:
                # Download PDF content
                pdf_content = zot.file(attachment['key'])
                
                if pdf_content:
                    # First sync the attachment as ZoteroItem
                    attachment_result = await process_zotero_item(current_user, zot, attachment, force_sync=True)
                    
                    # Get the attachment ZoteroItem
                    attachment_item = (ZoteroItem
                                     .select()
                                     .where(
                                         ZoteroItem.zotero_key == attachment['key'],
                                         ZoteroItem.user == current_user
                                     )
                                     .first())
                    
                    if attachment_item:
                        # Create Paper from the attachment
                        paper = await create_paper_from_zotero_attachment(
                            current_user,
                            attachment_item,
                            zot,
                            pdf_content
                        )
                        
                        if paper:
                            # Create ZoteroItemPaper relationship
                            try:
                                ZoteroItemPaper.create(
                                    zotero_item=zotero_item,  # Parent item
                                    paper=paper,
                                    relationship_type='attachment'
                                )
                                logger.info(f"Created ZoteroItemPaper relationship for {item_key} -> {paper.doc_id}")
                            except Exception as e:
                                logger.error(f"Error creating ZoteroItemPaper relationship: {e}")
                            
                            imported_count += 1
                            logger.info(f"Imported PDF attachment {attachment['key']} for item {item_key}")
                    
            except Exception as e:
                logger.error(f"Error importing attachment {attachment['key']}: {e}")
                continue
        
        return {
            "success": True,
            "message": f"Imported {imported_count} PDF(s)",
            "imported_count": imported_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing PDFs for item {item_key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Duplicate Detection APIs
# ============================================================================

@app.post("/api/v1/documents/{doc_id}/check_duplicates")
async def check_document_duplicates(doc_id: str, current_user: User = Depends(get_current_user)):
    """Check for potential duplicates of a specific document"""
    try:
        # Get the paper
        paper = Paper.get(Paper.doc_id == doc_id)
        
        # Run duplicate detection
        duplicates_found = await detect_duplicates_for_paper(paper)
        
        # Update paper status
        paper.duplicate_check_completed = True
        paper.duplicate_checked_at = datetime.datetime.now()
        paper.has_potential_duplicates = duplicates_found > 0
        paper.save()
        
        return {
            "doc_id": doc_id,
            "duplicates_found": duplicates_found,
            "message": f"Found {duplicates_found} potential duplicates"
        }
        
    except Paper.DoesNotExist:
        raise HTTPException(status_code=404, detail="Document not found")
    except Exception as e:
        logger.error(f"Error checking duplicates for {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/check_all_duplicates")
async def check_all_duplicates(current_user: User = Depends(require_admin)):
    """Run duplicate detection for all documents (admin only)"""
    try:
        # Get all papers that haven't been checked yet
        papers = Paper.select().where(Paper.duplicate_check_completed == False)
        
        total_papers = papers.count()
        processed = 0
        total_duplicates = 0
        
        for paper in papers:
            try:
                duplicates_found = await detect_duplicates_for_paper(paper)
                
                # Update paper status
                paper.duplicate_check_completed = True
                paper.duplicate_checked_at = datetime.datetime.now()
                paper.has_potential_duplicates = duplicates_found > 0
                paper.save()
                
                total_duplicates += duplicates_found
                processed += 1
                
                # Log progress every 10 papers
                if processed % 10 == 0:
                    logger.info(f"Processed {processed}/{total_papers} papers for duplicate detection")
                    
            except Exception as e:
                logger.error(f"Error processing paper {paper.doc_id}: {e}")
                processed += 1
                continue
        
        return {
            "total_papers": total_papers,
            "processed": processed,
            "total_duplicates": total_duplicates,
            "message": f"Processed {processed} papers, found {total_duplicates} potential duplicates"
        }
        
    except Exception as e:
        logger.error(f"Error in batch duplicate check: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/potential_duplicates")
async def get_potential_duplicates(
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_admin)
):
    """Get list of potential duplicate pairs (admin only)"""
    try:
        # Query potential duplicates
        query = (PotentialDuplicate
                .select()
                .where(PotentialDuplicate.status == status)
                .order_by(PotentialDuplicate.similarity_score.desc())
                .limit(limit)
                .offset(offset))
        
        duplicates = []
        for dup in query:
            # Get paper metadata
            paper1_metadata = {}
            paper2_metadata = {}
            
            try:
                metadata1 = dup.paper1.metadata.get()
                paper1_metadata = {
                    "title": metadata1.title,
                    "authors": metadata1.get_authors(),
                    "journal": metadata1.journal,
                    "year": metadata1.year
                }
            except:
                pass
            
            try:
                metadata2 = dup.paper2.metadata.get()
                paper2_metadata = {
                    "title": metadata2.title,
                    "authors": metadata2.get_authors(),
                    "journal": metadata2.journal,
                    "year": metadata2.year
                }
            except:
                pass
            
            duplicates.append({
                "id": dup.id,
                "paper1": {
                    "doc_id": dup.paper1.doc_id,
                    "filename": dup.paper1.filename,
                    "metadata": paper1_metadata
                },
                "paper2": {
                    "doc_id": dup.paper2.doc_id,
                    "filename": dup.paper2.filename,
                    "metadata": paper2_metadata
                },
                "similarity_score": dup.similarity_score,
                "detection_method": dup.detection_method,
                "status": dup.status,
                "created_at": dup.created_at.isoformat()
            })
        
        # Get total count
        total_count = (PotentialDuplicate
                      .select()
                      .where(PotentialDuplicate.status == status)
                      .count())
        
        return {
            "duplicates": duplicates,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Error getting potential duplicates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/resolve_duplicate")
async def resolve_duplicate(
    duplicate_id: int,
    action: str,  # 'merge', 'keep_both', 'delete_duplicate'
    keep_doc_id: str = None,  # Which document to keep (for merge/delete actions)
    current_user: User = Depends(require_admin)
):
    """Resolve a potential duplicate pair (admin only)"""
    try:
        # Get the duplicate record
        duplicate = PotentialDuplicate.get(PotentialDuplicate.id == duplicate_id)
        
        if action == "keep_both":
            # Mark as resolved, keep both documents
            duplicate.status = "resolved"
            duplicate.resolved_by = current_user
            duplicate.resolved_at = datetime.datetime.now()
            duplicate.resolution_action = "keep_both"
            duplicate.save()
            
            return {"message": "Marked as resolved - keeping both documents"}
            
        elif action == "ignore":
            # Mark as ignored
            duplicate.status = "ignored"
            duplicate.resolved_by = current_user
            duplicate.resolved_at = datetime.datetime.now()
            duplicate.resolution_action = "ignore"
            duplicate.save()
            
            return {"message": "Duplicate marked as ignored"}
            
        elif action == "delete_duplicate":
            if not keep_doc_id:
                raise HTTPException(status_code=400, detail="keep_doc_id is required for delete action")
            
            # Determine which document to delete
            if keep_doc_id == duplicate.paper1.doc_id:
                paper_to_delete = duplicate.paper2
                paper_to_keep = duplicate.paper1
            elif keep_doc_id == duplicate.paper2.doc_id:
                paper_to_delete = duplicate.paper1
                paper_to_keep = duplicate.paper2
            else:
                raise HTTPException(status_code=400, detail="keep_doc_id must be one of the duplicate pair")
            
            # Delete the duplicate paper and its associated data
            await delete_paper_and_data(paper_to_delete)
            
            # Mark duplicate as resolved
            duplicate.status = "resolved"
            duplicate.resolved_by = current_user
            duplicate.resolved_at = datetime.datetime.now()
            duplicate.resolution_action = "delete_duplicate"
            duplicate.save()
            
            return {
                "message": f"Deleted duplicate document {paper_to_delete.doc_id}, kept {paper_to_keep.doc_id}"
            }
            
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use 'keep_both', 'ignore', or 'delete_duplicate'")
            
    except PotentialDuplicate.DoesNotExist:
        raise HTTPException(status_code=404, detail="Duplicate record not found")
    except Exception as e:
        logger.error(f"Error resolving duplicate {duplicate_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def detect_duplicates_for_paper(paper: Paper, similarity_threshold: float = 0.85) -> int:
    """
    Detect potential duplicates for a given paper using embedding similarity
    Returns the number of duplicates found
    """
    try:
        collection = app.state.chroma_collection
        
        # Get the paper's document-level embedding
        doc_embedding_result = collection.get(
            ids=[paper.doc_id],
            where={"is_document_level": True}
        )
        
        if not doc_embedding_result['embeddings']:
            logger.warning(f"No embedding found for paper {paper.doc_id}")
            return 0
        
        paper_embedding = doc_embedding_result['embeddings'][0]
        
        # Search for similar embeddings
        similar_results = collection.query(
            query_embeddings=[paper_embedding],
            n_results=100,  # Get top 100 similar documents
            where={"is_document_level": True}
        )
        
        duplicates_found = 0
        
        for i, similar_doc_id in enumerate(similar_results['ids'][0]):
            similarity_score = 1.0 - similar_results['distances'][0][i]  # Convert distance to similarity
            
            # Skip self-comparison
            if similar_doc_id == paper.doc_id:
                continue
                
            # Only consider high similarity scores
            if similarity_score < similarity_threshold:
                continue
            
            try:
                # Get the other paper
                other_paper = Paper.get(Paper.doc_id == similar_doc_id)
                
                # Check if this duplicate relationship already exists
                existing_duplicate = (PotentialDuplicate
                                    .select()
                                    .where(
                                        ((PotentialDuplicate.paper1 == paper) & (PotentialDuplicate.paper2 == other_paper)) |
                                        ((PotentialDuplicate.paper1 == other_paper) & (PotentialDuplicate.paper2 == paper))
                                    )
                                    .first())
                
                if existing_duplicate:
                    # Update similarity score if it's higher
                    if similarity_score > existing_duplicate.similarity_score:
                        existing_duplicate.similarity_score = similarity_score
                        existing_duplicate.save()
                else:
                    # Create new duplicate relationship
                    PotentialDuplicate.create(
                        paper1=paper,
                        paper2=other_paper,
                        similarity_score=similarity_score,
                        detection_method='embedding',
                        status='pending'
                    )
                    duplicates_found += 1
                    
            except Paper.DoesNotExist:
                logger.warning(f"Paper {similar_doc_id} not found in database")
                continue
                
        return duplicates_found
        
    except Exception as e:
        logger.error(f"Error detecting duplicates for paper {paper.doc_id}: {e}")
        return 0

async def delete_paper_and_data(paper: Paper):
    """Delete a paper and all its associated data"""
    try:
        # Delete from ChromaDB
        collection = app.state.chroma_collection
        
        # Delete document-level embedding
        try:
            collection.delete(ids=[paper.doc_id])
        except:
            pass
        
        # Delete page-level embeddings
        try:
            page_ids = [f"{paper.doc_id}_page_{i}" for i in range(1, 100)]  # Assume max 100 pages
            collection.delete(ids=page_ids)
        except:
            pass
        
        # Delete chunk embeddings
        try:
            chunks = paper.semantic_chunks
            chunk_ids = [chunk.embedding_id for chunk in chunks]
            if chunk_ids:
                collection.delete(ids=chunk_ids)
        except:
            pass
        
        # Delete PDF file
        try:
            if paper.file_path and os.path.exists(paper.file_path):
                os.remove(paper.file_path)
        except:
            pass
        
        # Delete database records (cascading deletes will handle related records)
        paper.delete_instance()
        
        logger.info(f"Successfully deleted paper {paper.doc_id} and all associated data")
        
    except Exception as e:
        logger.error(f"Error deleting paper {paper.doc_id}: {e}")
        raise
