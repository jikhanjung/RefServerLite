import pytesseract
import fitz  # PyMuPDF
from PIL import Image
import io
import logging
from pathlib import Path
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

def check_if_ocr_needed(pdf_path: str) -> bool:
    """
    Check if a PDF needs OCR by examining if it contains extractable text
    """
    try:
        doc = fitz.open(pdf_path)
        
        # Check first few pages for text
        pages_to_check = min(3, len(doc))
        total_text_length = 0
        
        for page_num in range(pages_to_check):
            page = doc[page_num]
            text = page.get_text()
            total_text_length += len(text.strip())
        
        doc.close()
        
        # If very little text found, OCR is likely needed
        # Threshold: less than 100 characters per page on average
        avg_text_per_page = total_text_length / pages_to_check if pages_to_check > 0 else 0
        return avg_text_per_page < 100
        
    except Exception as e:
        logger.error(f"Error checking if OCR needed for {pdf_path}: {str(e)}")
        return True  # Default to needing OCR if error

def extract_text_from_pdf(pdf_path: str, use_ocr: bool = False) -> Tuple[List[str], bool]:
    """
    Extract text from PDF, optionally using OCR
    Returns: (list_of_page_texts, ocr_was_used)
    """
    try:
        doc = fitz.open(pdf_path)
        page_texts = []
        ocr_used = False
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            if use_ocr:
                # Convert page to image and perform OCR
                mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR quality
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                
                # Perform OCR
                try:
                    text = pytesseract.image_to_string(img)
                    # Clean the text for this page
                    cleaned_text = clean_extracted_text(text)
                    page_texts.append(cleaned_text)
                    ocr_used = True
                except Exception as e:
                    logger.error(f"OCR failed for page {page_num + 1}: {str(e)}")
                    # Fall back to regular text extraction
                    text = page.get_text()
                    cleaned_text = clean_extracted_text(text)
                    page_texts.append(cleaned_text)
            else:
                # Regular text extraction
                text = page.get_text()
                cleaned_text = clean_extracted_text(text)
                page_texts.append(cleaned_text)
        
        doc.close()
        
        return page_texts, ocr_used
        
    except Exception as e:
        logger.error(f"Error extracting text from {pdf_path}: {str(e)}")
        raise

def process_pdf_ocr(pdf_path: str) -> Tuple[List[str], bool]:
    """
    Main function to process a PDF with automatic OCR detection
    Returns: (list_of_page_texts, ocr_was_used)
    """
    # First, check if OCR is needed
    needs_ocr = check_if_ocr_needed(pdf_path)
    
    logger.info(f"Processing PDF: {pdf_path}, OCR needed: {needs_ocr}")
    
    # Extract text with or without OCR
    page_texts, ocr_used = extract_text_from_pdf(pdf_path, use_ocr=needs_ocr)
    
    # If very little text was extracted, try one more time with OCR
    total_text_length = sum(len(text.strip()) for text in page_texts)
    if total_text_length < 100 and not ocr_used:
        logger.warning(f"Very little text extracted, forcing OCR for {pdf_path}")
        page_texts, ocr_used = extract_text_from_pdf(pdf_path, use_ocr=True)
    
    return page_texts, ocr_used

def clean_extracted_text(text: str) -> str:
    """
    Clean and normalize extracted text
    """
    # Remove excessive whitespace
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line:  # Keep non-empty lines
            cleaned_lines.append(line)
    
    # Join with single newlines
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Remove multiple consecutive newlines
    while '\n\n\n' in cleaned_text:
        cleaned_text = cleaned_text.replace('\n\n\n', '\n\n')
    
    return cleaned_text.strip()

def extract_structured_text(pdf_path: str) -> Tuple[List[dict], bool]:
    """
    Extract text from PDF while preserving document structure (paragraphs, blocks)
    Returns: (list_of_page_structures, ocr_was_used)
    
    Each page structure contains:
    {
        'page_num': int,
        'text': str,           # Full page text with preserved paragraph boundaries
        'structure': str,      # 'preserved' or 'flat' (for OCR)
        'blocks': List[dict]   # Individual text blocks/paragraphs
    }
    """
    try:
        doc = fitz.open(pdf_path)
        page_structures = []
        ocr_used = False
        
        # First check if OCR is needed for the entire document
        needs_ocr = check_if_ocr_needed(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            if needs_ocr:
                # Use OCR - structure cannot be preserved
                try:
                    mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR quality
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    
                    # Perform OCR
                    ocr_text = pytesseract.image_to_string(img)
                    cleaned_text = clean_extracted_text(ocr_text)
                    
                    page_structures.append({
                        'page_num': page_num,
                        'text': cleaned_text,
                        'structure': 'flat',  # OCR doesn't preserve structure
                        'blocks': []  # No structural blocks available from OCR
                    })
                    ocr_used = True
                    
                except Exception as e:
                    logger.error(f"OCR failed for page {page_num + 1}: {str(e)}")
                    # Fallback to regular text extraction
                    text = page.get_text()
                    cleaned_text = clean_extracted_text(text)
                    page_structures.append({
                        'page_num': page_num,
                        'text': cleaned_text,
                        'structure': 'flat',
                        'blocks': []
                    })
            else:
                # Extract with structure preservation using PyMuPDF's dict mode
                page_dict = page.get_text("dict", sort=True)
                
                # Process blocks to create structured text
                structured_blocks = []
                full_page_text_parts = []
                
                for block in page_dict["blocks"]:
                    if block["type"] == 0:  # Text block (not image)
                        block_text_lines = []
                        
                        # Extract text from all lines in the block
                        for line in block["lines"]:
                            line_text = ""
                            for span in line["spans"]:
                                line_text += span["text"]
                            if line_text.strip():  # Only add non-empty lines
                                block_text_lines.append(line_text.strip())
                        
                        # Join lines within block and clean
                        if block_text_lines:
                            block_text = "\n".join(block_text_lines)
                            
                            # Filter out very short or meaningless blocks
                            if len(block_text.strip()) >= 10:  # Minimum block length
                                structured_blocks.append({
                                    'bbox': block["bbox"],
                                    'text': block_text.strip(),
                                    'type': 'paragraph',
                                    'block_num': len(structured_blocks)
                                })
                                full_page_text_parts.append(block_text.strip())
                
                # Combine all blocks with double newlines to preserve paragraph boundaries
                full_page_text = "\n\n".join(full_page_text_parts)
                
                # If very little structured text was extracted, fallback to basic extraction
                if len(full_page_text.strip()) < 50:
                    logger.warning(f"Little structured text found on page {page_num + 1}, using basic extraction")
                    text = page.get_text()
                    cleaned_text = clean_extracted_text(text)
                    
                    page_structures.append({
                        'page_num': page_num,
                        'text': cleaned_text,
                        'structure': 'flat',
                        'blocks': []
                    })
                else:
                    page_structures.append({
                        'page_num': page_num,
                        'text': full_page_text,
                        'structure': 'preserved',
                        'blocks': structured_blocks
                    })
        
        doc.close()
        logger.info(f"Extracted structured text from {len(page_structures)} pages, OCR used: {ocr_used}")
        
        return page_structures, ocr_used
        
    except Exception as e:
        logger.error(f"Error extracting structured text from {pdf_path}: {str(e)}")
        raise

def validate_chunk_quality(chunk_text: str) -> bool:
    """
    Validate if a chunk meets minimum quality criteria
    """
    text = chunk_text.strip()
    
    # Filter out chunks that are too short
    if len(text) < 50:
        return False
    
    # Filter out chunks with too few words
    word_count = len(text.split())
    if word_count < 8:
        return False
    
    # Filter out chunks that are mostly numbers or symbols
    alpha_ratio = sum(c.isalpha() for c in text) / len(text)
    if alpha_ratio < 0.5:
        return False
    
    # Filter out chunks that are mostly uppercase (likely headers/titles that got split)
    if len(text) > 20 and text.isupper():
        return False
    
    return True