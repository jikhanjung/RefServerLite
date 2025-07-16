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

from .models import init_database, Paper, Metadata, ProcessingJob, User, PageText
from .db import get_chromadb_client, get_or_create_collection, get_embedding_from_chroma
from .pipeline import start_background_processor
from .auth import create_access_token, require_admin, check_session_auth
from .visualize import visualize_embedding_bar, visualize_embedding_heatmap, visualize_embedding_histogram

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

@app.get("/api/v1/job/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a processing job"""
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
    limit: Optional[int] = 10
):
    """Search for documents
    
    Search types:
    - keyword: Simple text search in documents
    - semantic: Page-level semantic search (default for semantic)
    - document: Document-level semantic search
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
        # Semantic search using ChromaDB - prioritize page-level results
        try:
            collection = app.state.chroma_collection
            
            # Search primarily in page-level embeddings
            search_results = collection.query(
                query_texts=[q],
                n_results=limit * 3,  # Get more results to filter and group
                where={"is_document_level": False}  # Only page-level embeddings
            )
            
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
        if step not in ['ocr', 'metadata', 'embedding']:
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
            "document_embedding": document_embedding
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
