import re
import logging
from typing import List, Dict, Tuple, Optional
from .ocr import validate_chunk_quality

logger = logging.getLogger(__name__)

# Default chunking configuration
DEFAULT_CHUNKING_CONFIG = {
    "chunk_size": 500,
    "chunk_overlap": 50,
    "min_chunk_length": 50,
    "sentence_split_pattern": r'[.!?]+\s+',
    "max_sentences_per_chunk": 10,
    "paragraph_priority": True  # Prefer paragraph boundaries over sentence boundaries
}

def create_semantic_chunks(page_structures: List[Dict], config: Optional[Dict] = None) -> List[Dict]:
    """
    Create semantic chunks from structured page data using hierarchical strategy
    
    Args:
        page_structures: List of page structures from extract_structured_text()
        config: Chunking configuration dictionary
        
    Returns:
        List of chunk dictionaries with metadata
    """
    if config is None:
        config = DEFAULT_CHUNKING_CONFIG.copy()
    
    all_chunks = []
    
    for page_structure in page_structures:
        page_num = page_structure['page_num']
        structure_type = page_structure['structure']
        
        logger.debug(f"Processing page {page_num + 1} with structure type: {structure_type}")
        
        if structure_type == 'preserved':
            # Use structure-aware chunking for pages with preserved structure
            page_chunks = _create_structure_aware_chunks(page_structure, config)
        else:
            # Use fallback chunking for flat text (OCR results)
            page_chunks = _create_fallback_chunks(page_structure, config)
        
        # Add page-level metadata to each chunk
        for i, chunk in enumerate(page_chunks):
            chunk['page_number'] = page_num
            chunk['chunk_index_on_page'] = i
            chunk['doc_chunk_id'] = f"page_{page_num}_chunk_{i}"
        
        all_chunks.extend(page_chunks)
        logger.debug(f"Created {len(page_chunks)} chunks from page {page_num + 1}")
    
    logger.info(f"Total chunks created: {len(all_chunks)}")
    return all_chunks

def _create_structure_aware_chunks(page_structure: Dict, config: Dict) -> List[Dict]:
    """
    Create chunks using document structure (paragraphs, blocks)
    """
    chunks = []
    blocks = page_structure['blocks']
    chunk_size = config['chunk_size']
    chunk_overlap = config['chunk_overlap']
    
    for block in blocks:
        block_text = block['text']
        block_bbox = block.get('bbox', [0, 0, 0, 0])
        
        # Strategy 1: If paragraph fits within chunk size, use as-is
        if len(block_text) <= chunk_size:
            if validate_chunk_quality(block_text):
                chunks.append({
                    'text': block_text,
                    'chunk_type': 'paragraph',
                    'bbox': block_bbox,
                    'start_char': 0,
                    'end_char': len(block_text)
                })
        else:
            # Strategy 2: Split large paragraphs by sentences
            paragraph_chunks = _split_paragraph_by_sentences(
                block_text, block_bbox, config
            )
            
            # Strategy 3: If sentences are still too large, use recursive splitting
            final_chunks = []
            for chunk in paragraph_chunks:
                if len(chunk['text']) > chunk_size * 1.5:
                    # Use character-based splitting as last resort
                    char_chunks = _recursive_character_split(
                        chunk['text'], chunk_size, chunk_overlap
                    )
                    for i, char_chunk_text in enumerate(char_chunks):
                        if validate_chunk_quality(char_chunk_text):
                            final_chunks.append({
                                'text': char_chunk_text,
                                'chunk_type': 'fallback_split',
                                'bbox': chunk['bbox'],
                                'start_char': 0,  # Approximate for char splits
                                'end_char': len(char_chunk_text)
                            })
                else:
                    if validate_chunk_quality(chunk['text']):
                        final_chunks.append(chunk)
            
            chunks.extend(final_chunks)
    
    return chunks

def _create_fallback_chunks(page_structure: Dict, config: Dict) -> List[Dict]:
    """
    Create chunks from flat text using character-based splitting
    """
    page_text = page_structure['text']
    chunk_size = config['chunk_size']
    chunk_overlap = config['chunk_overlap']
    
    # First try to split by paragraphs (double newlines)
    paragraphs = page_text.split('\n\n')
    
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # If adding this paragraph would exceed chunk size
        if current_chunk and len(current_chunk + "\n\n" + paragraph) > chunk_size:
            # Save current chunk
            if validate_chunk_quality(current_chunk):
                chunks.append({
                    'text': current_chunk.strip(),
                    'chunk_type': 'paragraph_group',
                    'bbox': [0, 0, 0, 0],  # No bbox info for flat text
                    'start_char': 0,
                    'end_char': len(current_chunk)
                })
            current_chunk = paragraph
        else:
            # Add to current chunk
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
    
    # Don't forget the last chunk
    if current_chunk and validate_chunk_quality(current_chunk):
        chunks.append({
            'text': current_chunk.strip(),
            'chunk_type': 'paragraph_group',
            'bbox': [0, 0, 0, 0],
            'start_char': 0,
            'end_char': len(current_chunk)
        })
    
    # If chunks are still too large, apply recursive splitting
    final_chunks = []
    for chunk in chunks:
        if len(chunk['text']) > chunk_size * 1.5:
            char_chunks = _recursive_character_split(
                chunk['text'], chunk_size, chunk_overlap
            )
            for char_chunk_text in char_chunks:
                if validate_chunk_quality(char_chunk_text):
                    final_chunks.append({
                        'text': char_chunk_text,
                        'chunk_type': 'fallback_split',
                        'bbox': [0, 0, 0, 0],
                        'start_char': 0,
                        'end_char': len(char_chunk_text)
                    })
        else:
            final_chunks.append(chunk)
    
    return final_chunks

def _split_paragraph_by_sentences(paragraph_text: str, bbox: List[float], config: Dict) -> List[Dict]:
    """
    Split a paragraph into sentence-based chunks
    """
    sentences = _split_by_sentences(paragraph_text, config['sentence_split_pattern'])
    chunk_size = config['chunk_size']
    max_sentences = config['max_sentences_per_chunk']
    
    chunks = []
    current_chunk_sentences = []
    current_chunk_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # Check if adding this sentence would exceed limits
        new_length = current_chunk_length + len(sentence) + 1  # +1 for space
        
        if (current_chunk_sentences and 
            (new_length > chunk_size or len(current_chunk_sentences) >= max_sentences)):
            # Save current chunk
            chunk_text = " ".join(current_chunk_sentences)
            if validate_chunk_quality(chunk_text):
                chunks.append({
                    'text': chunk_text,
                    'chunk_type': 'sentence_group',
                    'bbox': bbox,
                    'start_char': 0,  # Approximate for sentence groups
                    'end_char': len(chunk_text)
                })
            
            # Start new chunk
            current_chunk_sentences = [sentence]
            current_chunk_length = len(sentence)
        else:
            # Add to current chunk
            current_chunk_sentences.append(sentence)
            current_chunk_length = new_length
    
    # Don't forget the last chunk
    if current_chunk_sentences:
        chunk_text = " ".join(current_chunk_sentences)
        if validate_chunk_quality(chunk_text):
            chunks.append({
                'text': chunk_text,
                'chunk_type': 'sentence_group',
                'bbox': bbox,
                'start_char': 0,
                'end_char': len(chunk_text)
            })
    
    return chunks

def _split_by_sentences(text: str, pattern: str = r'[.!?]+\s+') -> List[str]:
    """
    Split text into sentences using regex pattern
    """
    # Enhanced sentence splitting that handles common academic text patterns
    sentences = re.split(pattern, text)
    
    # Clean and filter sentences
    cleaned_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        
        # Skip very short fragments that are likely splitting artifacts
        if len(sentence) >= 20:  # Minimum sentence length
            cleaned_sentences.append(sentence)
    
    return cleaned_sentences

def _recursive_character_split(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    Recursively split text by characters with overlap, respecting word boundaries
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        # Calculate end position
        end = min(start + chunk_size, len(text))
        
        # If we're not at the end of text, try to break at word boundary
        if end < len(text):
            # Look backward for a space to break on word boundary
            space_pos = text.rfind(' ', start, end)
            if space_pos != -1 and space_pos > start + chunk_size // 2:
                end = space_pos
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start position with overlap
        if end < len(text):
            # For next chunk, start with overlap
            start = max(start + 1, end - chunk_overlap)
        else:
            break
    
    return chunks

def get_chunking_stats(chunks: List[Dict]) -> Dict:
    """
    Calculate statistics about the chunking results
    """
    if not chunks:
        return {}
    
    chunk_types = {}
    lengths = []
    
    for chunk in chunks:
        chunk_type = chunk.get('chunk_type', 'unknown')
        chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
        lengths.append(len(chunk['text']))
    
    return {
        'total_chunks': len(chunks),
        'chunk_types': chunk_types,
        'avg_chunk_length': sum(lengths) / len(lengths) if lengths else 0,
        'min_chunk_length': min(lengths) if lengths else 0,
        'max_chunk_length': max(lengths) if lengths else 0,
        'quality_score': sum(1 for chunk in chunks if validate_chunk_quality(chunk['text'])) / len(chunks)
    }