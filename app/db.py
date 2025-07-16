import chromadb
from chromadb.config import Settings
from pathlib import Path
import os
import logging

# Disable ChromaDB telemetry
os.environ["CHROMA_TELEMETRY_DISABLED"] = "1"
os.environ["ANONYMIZED_TELEMETRY"] = "false"

# Suppress ChromaDB telemetry error logs
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

def get_chromadb_client():
    """Initialize and return ChromaDB client"""
    # Create data directory if it doesn't exist
    data_dir = Path("refdata/chromadb")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize ChromaDB with persistent storage
    client = chromadb.PersistentClient(
        path=str(data_dir),
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    
    return client

def get_or_create_collection(client, collection_name="refserver_docs"):
    """Get or create ChromaDB collection for document embeddings"""
    try:
        # Try to get existing collection
        collection = client.get_collection(name=collection_name)
    except:
        # Create new collection if it doesn't exist
        collection = client.create_collection(
            name=collection_name,
            metadata={"description": "RefServerLite document embeddings"}
        )
    
    return collection

def add_document_to_collection(collection, doc_id: str, text: str, embedding=None, metadata=None):
    """Add a document to the ChromaDB collection"""
    # Prepare metadata
    if metadata is None:
        metadata = {}
    metadata["doc_id"] = doc_id
    
    # Add to collection
    if embedding is not None:
        # Add with pre-computed embedding
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata]
        )
    else:
        # Let ChromaDB compute the embedding
        collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata]
        )

def update_document_in_collection(collection, doc_id: str, text: str, embedding=None, metadata=None):
    """Update a document in the ChromaDB collection"""
    # Prepare metadata
    if metadata is None:
        metadata = {}
    metadata["doc_id"] = doc_id
    
    # Update in collection
    if embedding is not None:
        collection.update(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata]
        )
    else:
        collection.update(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata]
        )

def delete_document_from_collection(collection, doc_id: str):
    """Delete a document from the ChromaDB collection"""
    collection.delete(ids=[doc_id])

def search_similar_documents(collection, query_text: str, n_results: int = 10):
    """Search for similar documents using semantic search"""
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    return results

def get_embedding_from_chroma(collection, doc_id: str, page_number: int = None, is_document_level: bool = False):
    """
    Helper function to retrieve embeddings from ChromaDB
    
    Args:
        collection: ChromaDB collection
        doc_id: Document ID
        page_number: Page number for page-level embeddings (None for document-level)
        is_document_level: Whether to get document-level embedding
    
    Returns:
        numpy array of embedding values or None if not found
    """
    try:
        if is_document_level:
            # Document-level embedding
            query_id = doc_id
            where_clause = {"is_document_level": True}
        else:
            # Page-level embedding
            if page_number is None:
                raise ValueError("page_number is required for page-level embeddings")
            query_id = f"{doc_id}_page_{page_number}"
            where_clause = {"is_document_level": False}
        
        # Query ChromaDB
        result = collection.get(
            ids=[query_id],
            include=['embeddings'],
            where=where_clause
        )
        
        if result['embeddings'] and len(result['embeddings']) > 0:
            return result['embeddings'][0]
        else:
            return None
            
    except Exception as e:
        print(f"Error retrieving embedding: {str(e)}")
        return None