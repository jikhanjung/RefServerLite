from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from typing import Optional, List
import os
import uuid
from pathlib import Path
from datetime import timedelta
import numpy as np

from .models import init_database, Paper, Metadata, ProcessingJob, User, PageText, SemanticChunk, ZoteroLink
from .db import get_chromadb_client, get_or_create_collection, get_embedding_from_chroma
from .pipeline import start_background_processor
from .auth import create_access_token, require_admin, check_session_auth, get_current_user
from .visualize import visualize_embedding_bar, visualize_embedding_heatmap, visualize_embedding_histogram
from .visualize_3d import visualize_embedding_3d_bidirectional, visualize_embedding_3d_unidirectional, visualize_embedding_3d_surface

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
    return templates.TemplateResponse("index.html", {"request": request})

# Authentication endpoints
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page"""
    # Redirect to admin if already logged in
    user = check_session_auth(request)
    if user and user.is_admin:
        return RedirectResponse(url="/admin", status_code=302)
    
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login form submission"""
    try:
        user = User.get(User.username == username)
        if user.verify_password(password) and user.is_admin:
            # Set session
            request.session["username"] = username
            user.update_last_login()
            return RedirectResponse(url="/admin", status_code=302)
        else:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Invalid credentials or insufficient privileges"
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
async def upload_pdf(file: UploadFile = File(...)):
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
            file_path=str(file_path)
        )
        
        # Create ProcessingJob entry
        job = ProcessingJob.create(
            job_id=job_id,
            paper=paper,
            filename=file.filename,
            status='uploaded'
        )
        
        # Start processing immediately
        job.status = 'processing'
        job.save()
        
        return {
            "job_id": job_id,
            "filename": file.filename,
            "message": "File uploaded successfully. Processing started in background.",
            "status": "processing"
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
            file_path=str(file_path)
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
            status='uploaded'
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
            status='uploaded'
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
                    status='uploaded'
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
        "documents": documents
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
            "created_at": job.created_at,
            "updated_at": job.updated_at,
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
            collection = app.state.chroma_collection
            
            # Get document-level embedding
            try:
                doc_result = collection.get(ids=[doc_id], include=['embeddings'])
                if doc_result['embeddings'] and len(doc_result['embeddings']) > 0:
                    # Get first 10 values from document embedding vector
                    document_embedding = doc_result['embeddings'][0][:10]
            except Exception as e:
                # Skip if document embedding not found
                pass
            
            # Get page embeddings
            for page_text in page_texts:
                page_doc_id = f"{doc_id}_page_{page_text.page_number}"
                try:
                    result = collection.get(ids=[page_doc_id], include=['embeddings'])
                    if result['embeddings'] and len(result['embeddings']) > 0:
                        # Get first 10 values from embedding vector
                        embedding = result['embeddings'][0][:10]
                        page_embeddings[page_text.page_number] = embedding
                except Exception as e:
                    # Skip if embedding not found for this page
                    continue
        except Exception as e:
            # If ChromaDB is not available, continue without embeddings
            pass
        
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
