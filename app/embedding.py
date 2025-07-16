from sentence_transformers import SentenceTransformer
import numpy as np
import logging
from typing import List, Optional, Tuple
import torch

logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    """Generate embeddings using sentence-transformers"""
    
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        """Initialize the embedding model"""
        try:
            # Use local model path if available, otherwise fallback to download
            local_model_path = "/app/models/bge-m3-local"
            import os
            if os.path.exists(local_model_path):
                model_path = local_model_path
                print(f"🔥 Initializing local embedding model: {local_model_path}")
                logger.info(f"Using local embedding model: {local_model_path}")
            else:
                model_path = model_name
                print(f"🔥 Initializing embedding model: {model_name}")
                logger.info(f"Starting to load embedding model: {model_name}")
                logger.info("This may take a few minutes for first-time download...")
            
            print(f"📥 Loading SentenceTransformer model from: {model_path}")
            self.model = SentenceTransformer(model_path)
            print(f"✅ SentenceTransformer model loaded")
            
            self.model_name = model_name
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            print(f"📐 Embedding dimension: {self.embedding_dim}")
            
            # Set device
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            print(f"🖥️ Using device: {self.device}")
            self.model.to(self.device)
            print(f"✅ Model moved to device: {self.device}")
            
            logger.info(f"Successfully initialized embedding model: {model_name} on {self.device}")
            print(f"🎉 Embedding model fully initialized!")
        except Exception as e:
            print(f"❌ Failed to initialize embedding model: {str(e)}")
            logger.error(f"Failed to initialize embedding model: {str(e)}")
            raise
    
    def generate_embedding(self, text: str, max_length: Optional[int] = None) -> np.ndarray:
        """Generate embedding for a single text"""
        if not text or not text.strip():
            # Return zero vector for empty text
            return np.zeros(self.embedding_dim)
        
        # Truncate text if needed (be more aggressive)
        if max_length:
            text = text[:max_length]
        else:
            text = text[:2000]  # Default max length
        
        try:
            logger.info(f"Generating embedding for text of length: {len(text)}")
            
            # Generate embedding
            embedding = self.model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True  # Normalize for cosine similarity
            )
            
            logger.info("Successfully generated embedding")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            raise
    
    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 32) -> List[np.ndarray]:
        """Generate embeddings for multiple texts"""
        if not texts:
            return []
        
        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=True,
                normalize_embeddings=True
            )
            
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {str(e)}")
            raise
    
    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """
        Split text into overlapping chunks for embedding
        This helps with long documents that exceed model's max length
        """
        if not text:
            return []
        
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary
            if end < text_length:
                # Look for sentence end markers
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                
                # Use the latest sentence boundary found
                boundary = max(last_period, last_newline)
                if boundary > chunk_size * 0.8:  # Only if we're not losing too much text
                    chunk = chunk[:boundary + 1]
                    end = start + boundary + 1
            
            chunks.append(chunk.strip())
            
            # Move start position with overlap
            start = end - overlap if end < text_length else text_length
        
        return chunks
    
    def generate_document_embedding(self, text: str, strategy: str = "mean") -> np.ndarray:
        """
        Generate a single embedding for an entire document
        
        Strategies:
        - "mean": Average embeddings of all chunks
        - "first": Use only the first chunk (often contains summary/abstract)
        - "max": Max pooling across chunk embeddings
        """
        if not text or not text.strip():
            return np.zeros(self.embedding_dim)
        
        # For short texts, just encode directly
        if len(text) < 2000:
            return self.generate_embedding(text)
        
        # For longer texts, chunk and combine
        chunks = self.chunk_text(text, chunk_size=1000, overlap=200)
        
        if not chunks:
            return np.zeros(self.embedding_dim)
        
        # Generate embeddings for all chunks
        chunk_embeddings = self.generate_embeddings_batch(chunks)
        
        if strategy == "mean":
            # Average all chunk embeddings
            doc_embedding = np.mean(chunk_embeddings, axis=0)
        elif strategy == "first":
            # Use first chunk (often most representative)
            doc_embedding = chunk_embeddings[0]
        elif strategy == "max":
            # Max pooling
            doc_embedding = np.max(chunk_embeddings, axis=0)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        # Normalize the final embedding
        norm = np.linalg.norm(doc_embedding)
        if norm > 0:
            doc_embedding = doc_embedding / norm
        
        return doc_embedding
    
    def generate_embeddings_for_pages_and_document(self, page_texts: List[str]) -> Tuple[List[Tuple[int, np.ndarray]], np.ndarray, str]:
        """
        Generate both page-level and document-level embeddings
        
        Args:
            page_texts: List of text content for each page
            
        Returns:
            - List of (page_number, page_embedding) tuples (1-indexed page numbers)
            - document_level_embedding (mean of all page embeddings)
            - model_name
        """
        if not page_texts:
            return [], np.zeros(self.embedding_dim), self.model_name
        
        # Filter out pages with minimal content
        MIN_PAGE_CHARS = 50
        valid_pages = []
        page_embeddings = []
        
        print(f"📄 Processing {len(page_texts)} pages for embeddings...")
        
        for page_num, page_text in enumerate(page_texts, 1):
            if len(page_text.strip()) < MIN_PAGE_CHARS:
                print(f"⏭️ Skipping page {page_num} (too little content: {len(page_text.strip())} chars)")
                continue
                
            print(f"🔍 Generating embedding for page {page_num} ({len(page_text)} chars)")
            
            # Generate embedding for this page
            page_embedding = self.generate_embedding(page_text)
            
            valid_pages.append((page_num, page_embedding))
            page_embeddings.append(page_embedding)
        
        if not page_embeddings:
            print("⚠️ No valid pages found for embedding generation")
            return [], np.zeros(self.embedding_dim), self.model_name
        
        # Calculate document-level embedding as mean of page embeddings
        print(f"📊 Calculating document-level embedding from {len(page_embeddings)} page embeddings...")
        doc_embedding = np.mean(page_embeddings, axis=0)
        
        # Normalize the document embedding
        norm = np.linalg.norm(doc_embedding)
        if norm > 0:
            doc_embedding = doc_embedding / norm
        
        print(f"✅ Generated {len(valid_pages)} page embeddings and 1 document embedding")
        
        return valid_pages, doc_embedding, self.model_name

# Global instance
_embedding_generator = None

def get_embedding_generator() -> EmbeddingGenerator:
    """Get or create the global embedding generator instance"""
    global _embedding_generator
    if _embedding_generator is None:
        print(f"🚀 Creating new embedding generator...")
        _embedding_generator = EmbeddingGenerator()
        print(f"✅ Embedding generator created successfully")
    else:
        print(f"♻️ Using existing embedding generator")
    return _embedding_generator

def generate_embedding_for_document(text: str) -> Tuple[np.ndarray, str]:
    """
    Generate embedding for a document (legacy function for backward compatibility)
    Returns: (embedding, model_name)
    """
    print(f"🔧 Getting embedding generator...")
    generator = get_embedding_generator()
    print(f"✅ Got embedding generator, model: {generator.model_name}")
    print(f"📊 Generating document embedding...")
    embedding = generator.generate_document_embedding(text)
    print(f"✅ Document embedding generated successfully")
    return embedding, generator.model_name

def generate_embeddings_for_pages(page_texts: List[str]) -> Tuple[List[Tuple[int, np.ndarray]], np.ndarray, str]:
    """
    Generate both page-level and document-level embeddings from page texts
    
    Args:
        page_texts: List of text content for each page
        
    Returns:
        - List of (page_number, page_embedding) tuples (1-indexed page numbers)
        - document_level_embedding (mean of all page embeddings)
        - model_name
    """
    print(f"🔧 Getting embedding generator for page-level processing...")
    generator = get_embedding_generator()
    print(f"✅ Got embedding generator, model: {generator.model_name}")
    
    page_embeddings, doc_embedding, model_name = generator.generate_embeddings_for_pages_and_document(page_texts)
    
    return page_embeddings, doc_embedding, model_name