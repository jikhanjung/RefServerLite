import asyncio
import logging
from pathlib import Path
from typing import Optional
import numpy as np

from .models import Paper, Metadata, ProcessingJob, PageText
from .ocr import process_pdf_ocr, clean_extracted_text
from .metadata import extract_metadata_from_text
from .embedding import generate_embedding_for_document, generate_embeddings_for_pages
from .db import get_chromadb_client, get_or_create_collection, add_document_to_collection

logger = logging.getLogger(__name__)

class PDFProcessingPipeline:
    """Main pipeline for processing PDF documents"""
    
    def __init__(self):
        self.chroma_client = get_chromadb_client()
        self.chroma_collection = get_or_create_collection(self.chroma_client)
        # Temporary storage for page texts during processing
        self._page_texts_cache = {}
    
    async def process_document(self, job_id: str):
        """Process a single document through the entire pipeline"""
        try:
            print(f"🎯 Starting document processing for job {job_id}")
            
            # Get job from database
            job = ProcessingJob.get(ProcessingJob.job_id == job_id)
            paper = job.paper
            
            if not paper:
                raise ValueError("No paper associated with job")
            
            print(f"📄 Processing document: {paper.filename}")
            logger.info(f"Starting processing for job {job_id}, document {paper.doc_id}")
            
            # Update job status
            job.status = 'processing'
            job.progress_percentage = 15
            job.current_step = 'initializing'
            job.save()
            print(f"✅ Job status updated to processing")
            
            # Step 1: OCR Processing
            print(f"📖 Starting OCR processing...")
            await self._process_ocr(job, paper)
            print(f"✅ OCR processing completed")
            
            # Step 2: Metadata Extraction
            print(f"🔍 Starting metadata extraction...")
            await self._extract_metadata(job, paper)
            print(f"✅ Metadata extraction completed")
            
            # Step 3: Embedding Generation
            print(f"🧠 Starting embedding generation...")
            await self._generate_embeddings(job, paper)
            print(f"✅ Embedding generation completed")
            
            # Mark job as completed
            job.mark_completed()
            print(f"🎉 Completed processing for job {job_id}")
            logger.info(f"Completed processing for job {job_id}")
            
        except Exception as e:
            print(f"❌ Error processing job {job_id}: {str(e)}")
            logger.error(f"Error processing job {job_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            if 'job' in locals():
                job.mark_failed(str(e))
            raise
    
    async def _process_ocr(self, job: ProcessingJob, paper: Paper):
        """OCR processing step"""
        try:
            job.update_step_status('ocr', 'running')
            job.update_progress('ocr', 20)
            logger.info(f"Starting OCR for document {paper.doc_id}")
            
            # Extract text from PDF (now returns list of page texts)
            page_texts, ocr_used = process_pdf_ocr(paper.file_path)
            
            # Store page texts for embedding generation
            self._page_texts_cache[job.job_id] = page_texts
            
            # Store individual page texts in database
            print(f"💾 Storing {len(page_texts)} page texts in database...")
            for page_num, page_text in enumerate(page_texts, 1):
                PageText.create(
                    paper=paper,
                    page_number=page_num,
                    text=page_text
                )
            
            # For backward compatibility, also store concatenated text
            full_text = "\n\n".join(page_texts)
            cleaned_text = clean_extracted_text(full_text)
            paper.ocr_text = cleaned_text
            paper.save()
            
            job.update_step_status('ocr', 'completed')
            job.update_progress('ocr', 40)
            logger.info(f"OCR completed for document {paper.doc_id}, OCR used: {ocr_used}, {len(page_texts)} pages processed")
            
        except Exception as e:
            job.update_step_status('ocr', 'failed', str(e))
            logger.error(f"OCR failed for document {paper.doc_id}: {str(e)}")
            raise
    
    async def _extract_metadata(self, job: ProcessingJob, paper: Paper):
        """Metadata extraction step"""
        try:
            job.update_step_status('metadata', 'running')
            job.update_progress('metadata', 50)
            logger.info(f"Starting metadata extraction for document {paper.doc_id}")
            
            if not paper.ocr_text:
                logger.warning(f"No text available for metadata extraction in document {paper.doc_id}")
                job.update_step_status('metadata', 'completed')
                return
            
            # Extract metadata from text
            metadata_dict = extract_metadata_from_text(paper.ocr_text)
            
            # Create or update metadata record
            metadata, created = Metadata.get_or_create(
                paper=paper,
                defaults={
                    'title': metadata_dict.get('title'),
                    'journal': metadata_dict.get('journal'),
                    'year': metadata_dict.get('year'),
                    'abstract': metadata_dict.get('abstract'),
                    'doi': metadata_dict.get('doi')
                }
            )
            
            # Update authors separately
            if metadata_dict.get('authors'):
                metadata.set_authors(metadata_dict['authors'])
            
            # Update if not created
            if not created:
                metadata.title = metadata_dict.get('title') or metadata.title
                metadata.journal = metadata_dict.get('journal') or metadata.journal
                metadata.year = metadata_dict.get('year') or metadata.year
                metadata.abstract = metadata_dict.get('abstract') or metadata.abstract
                metadata.doi = metadata_dict.get('doi') or metadata.doi
            
            metadata.save()
            
            job.update_step_status('metadata', 'completed')
            job.update_progress('metadata', 70)
            logger.info(f"Metadata extraction completed for document {paper.doc_id}")
            
        except Exception as e:
            job.update_step_status('metadata', 'failed', str(e))
            logger.error(f"Metadata extraction failed for document {paper.doc_id}: {str(e)}")
            raise
    
    async def _generate_embeddings(self, job: ProcessingJob, paper: Paper):
        """Embedding generation step - now generates both page-level and document-level embeddings"""
        try:
            job.update_step_status('embedding', 'running')
            job.update_progress('embedding', 80)
            print(f"🧠 Starting page-level embedding generation for document {paper.doc_id}")
            logger.info(f"Starting embedding generation for document {paper.doc_id}")
            
            # Get page texts from cache
            page_texts = self._page_texts_cache.get(job.job_id)
            if not page_texts:
                print(f"⚠️ No page texts available for embedding generation")
                logger.warning(f"No page texts available for embedding generation in document {paper.doc_id}")
                job.update_step_status('embedding', 'completed')
                return
            
            print(f"📄 Processing {len(page_texts)} pages for embedding generation")
            
            # Generate page-level and document-level embeddings
            page_embeddings, doc_embedding, model_name = generate_embeddings_for_pages(page_texts)
            print(f"✅ Generated {len(page_embeddings)} page embeddings and 1 document embedding with model: {model_name}")
            
            # Prepare base metadata for ChromaDB
            base_metadata = {'filename': paper.filename}
            try:
                paper_metadata = paper.metadata.get()
                base_metadata.update({
                    'title': paper_metadata.title,
                    'authors': ', '.join(paper_metadata.get_authors()) if paper_metadata.get_authors() else None,
                    'journal': paper_metadata.journal,
                    'year': paper_metadata.year,
                    'doi': paper_metadata.doi
                })
            except Metadata.DoesNotExist:
                pass
            
            # Remove None values
            base_metadata = {k: v for k, v in base_metadata.items() if v is not None}
            
            # Add page-level embeddings to ChromaDB
            print(f"💾 Storing {len(page_embeddings)} page embeddings in ChromaDB...")
            for page_num, page_embedding in page_embeddings:
                page_metadata = base_metadata.copy()
                page_metadata.update({
                    'page_number': page_num,
                    'original_doc_id': paper.doc_id,
                    'is_document_level': False
                })
                
                # Get the page text (with bounds checking)
                page_text = page_texts[page_num - 1] if page_num <= len(page_texts) else ""
                
                add_document_to_collection(
                    self.chroma_collection,
                    doc_id=f"{paper.doc_id}_page_{page_num}",
                    text=page_text[:1000],  # Store first 1000 chars of page
                    embedding=page_embedding.tolist(),
                    metadata=page_metadata
                )
            
            # Add document-level embedding to ChromaDB
            print(f"💾 Storing document-level embedding in ChromaDB...")
            doc_metadata = base_metadata.copy()
            doc_metadata.update({
                'is_document_level': True,
                'total_pages': len(page_texts)
            })
            
            add_document_to_collection(
                self.chroma_collection,
                doc_id=paper.doc_id,
                text=paper.ocr_text[:1000] if paper.ocr_text else "",
                embedding=doc_embedding.tolist(),
                metadata=doc_metadata
            )
            
            # Clean up cache
            if job.job_id in self._page_texts_cache:
                del self._page_texts_cache[job.job_id]
            
            job.update_step_status('embedding', 'completed')
            job.update_progress('embedding', 95)
            logger.info(f"Embedding generation completed for document {paper.doc_id} - {len(page_embeddings)} pages + 1 document")
            
        except Exception as e:
            # Clean up cache on error
            if job.job_id in self._page_texts_cache:
                del self._page_texts_cache[job.job_id]
            job.update_step_status('embedding', 'failed', str(e))
            logger.error(f"Embedding generation failed for document {paper.doc_id}: {str(e)}")
            raise

# Background task processing
async def process_pending_jobs():
    """Process all pending jobs in the background"""
    print("🔄 Background job processor starting...")
    logger.info("Starting background job processor...")
    pipeline = PDFProcessingPipeline()
    
    while True:
        try:
            # Get pending jobs (both uploaded and processing status)
            pending_jobs = ProcessingJob.select().where(
                (ProcessingJob.status == 'uploaded') | 
                (ProcessingJob.status == 'processing')
            ).order_by(ProcessingJob.created_at)
            
            job_count = pending_jobs.count()
            
            if job_count > 0:
                print(f"📊 Found {job_count} pending jobs")
                logger.info(f"Found {job_count} pending jobs")
                
                for job in pending_jobs:
                    print(f"📝 Processing job {job.job_id} with status: {job.status}")
                    
                    if job.status == 'uploaded':
                        print(f"🚀 Starting processing for job {job.job_id}")
                        logger.info(f"Starting processing for job {job.job_id}")
                        job.status = 'processing'
                        job.progress_percentage = 10
                        job.current_step = 'starting'
                        job.save()
                    
                    if job.status == 'processing':
                        print(f"⚙️ Processing job {job.job_id}")
                        logger.info(f"Processing job {job.job_id}")
                        await pipeline.process_document(job.job_id)
                
                # Check again quickly if we processed jobs
                await asyncio.sleep(2)
            else:
                # No jobs found, wait longer before checking again
                await asyncio.sleep(15)
            
        except Exception as e:
            print(f"❌ Error in background job processor: {str(e)}")
            logger.error(f"Error in background job processor: {str(e)}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(10)  # Wait longer on error

def start_background_processor():
    """Start the background job processor"""
    import asyncio
    import threading
    
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_pending_jobs())
    
    # Start background processor in a separate thread to avoid blocking startup
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    logger.info("Background processor thread started")