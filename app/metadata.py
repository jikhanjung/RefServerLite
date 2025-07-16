import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MetadataExtractor:
    """Extract bibliographic metadata from text using rule-based methods"""
    
    def __init__(self):
        # Common patterns for metadata extraction
        self.title_indicators = ['title:', 'title :', '^#', '^##']
        self.author_patterns = [
            r'(?:by|authors?|written by)[:\s]+([^\n]+)',
            r'([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+)(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+)*',
        ]
        self.year_pattern = r'\b(19[5-9]\d|20[0-2]\d)\b'
        self.doi_pattern = r'(?:doi:|DOI:|https?://doi\.org/|10\.)\s*([0-9]+\.[0-9]+/[^\s]+)'
        self.journal_indicators = ['journal', 'published in', 'in:', 'journal:']
        
    def extract_metadata(self, text: str) -> Dict[str, Any]:
        """Extract all metadata from text"""
        # Get first 2000 characters for metadata extraction (usually in beginning)
        sample_text = text[:2000]
        
        metadata = {
            'title': self._extract_title(sample_text, text),
            'authors': self._extract_authors(sample_text),
            'journal': self._extract_journal(sample_text),
            'year': self._extract_year(sample_text),
            'doi': self._extract_doi(sample_text),
            'abstract': self._extract_abstract(text)
        }
        
        return metadata
    
    def _extract_title(self, sample_text: str, full_text: str) -> Optional[str]:
        """Extract paper title"""
        lines = sample_text.split('\n')
        
        # Strategy 1: Look for explicit title markers
        for line in lines[:20]:  # Check first 20 lines
            line_lower = line.lower().strip()
            for indicator in self.title_indicators:
                if line_lower.startswith(indicator):
                    title = line.replace(indicator, '', 1).strip()
                    if len(title) > 10:  # Reasonable title length
                        return self._clean_title(title)
        
        # Strategy 2: First substantial line that looks like a title
        for line in lines:
            line = line.strip()
            if (len(line) > 20 and len(line) < 200 and 
                not line.startswith('(') and 
                not re.search(r'^\d+\.', line) and  # Not a numbered item
                line[0].isupper()):  # Starts with capital
                return self._clean_title(line)
        
        # Strategy 3: Look for title in full text between specific markers
        title_match = re.search(r'(?:Title|TITLE)[:\s]+([^\n]+)', full_text[:1000], re.IGNORECASE)
        if title_match:
            return self._clean_title(title_match.group(1))
        
        return None
    
    def _extract_authors(self, text: str) -> List[str]:
        """Extract author names"""
        authors = []
        
        # Look for explicit author section
        author_match = re.search(r'(?:Authors?|by)[:\s]+([^\n]+)', text, re.IGNORECASE)
        if author_match:
            author_text = author_match.group(1)
            # Split by common separators
            potential_authors = re.split(r'[,;&]|\band\b', author_text)
            
            for author in potential_authors:
                author = author.strip()
                # Basic validation - should have at least first and last name
                if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+', author):
                    authors.append(author)
        
        # If no authors found, try to find name patterns in first 500 chars
        if not authors:
            # Look for patterns like "John Doe, Jane Smith"
            name_matches = re.findall(
                r'([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+)',
                text[:500]
            )
            
            # Filter out common false positives
            exclude_words = {'The', 'This', 'These', 'That', 'What', 'Where', 'When', 'Abstract', 'Introduction'}
            for name in name_matches[:5]:  # Limit to first 5 matches
                if name not in exclude_words and len(name.split()) >= 2:
                    authors.append(name)
        
        return list(dict.fromkeys(authors))  # Remove duplicates while preserving order
    
    def _extract_journal(self, text: str) -> Optional[str]:
        """Extract journal name"""
        # Look for journal indicators
        for indicator in self.journal_indicators:
            pattern = rf'{indicator}[:\s]+([^\n,]+)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                journal = match.group(1).strip()
                # Clean up journal name
                journal = re.sub(r'\s*\d{4}\s*$', '', journal)  # Remove trailing year
                journal = re.sub(r'[,\.]$', '', journal)  # Remove trailing punctuation
                if len(journal) > 5:  # Reasonable journal name length
                    return journal
        
        # Look for common journal patterns
        journal_match = re.search(r'(?:Proceedings of|Journal of|Conference on)\s+([^\n,]+)', text)
        if journal_match:
            return journal_match.group(0).strip()
        
        return None
    
    def _extract_year(self, text: str) -> Optional[int]:
        """Extract publication year"""
        # Find all 4-digit years in reasonable range
        years = re.findall(self.year_pattern, text)
        
        if years:
            # Return the most recent year found (likely publication year)
            years_int = [int(y) for y in years]
            current_year = datetime.now().year
            
            # Filter out future years
            valid_years = [y for y in years_int if y <= current_year]
            
            if valid_years:
                return max(valid_years)
        
        return None
    
    def _extract_doi(self, text: str) -> Optional[str]:
        """Extract DOI"""
        doi_match = re.search(self.doi_pattern, text)
        if doi_match:
            doi = doi_match.group(1) if '10.' not in doi_match.group(0) else doi_match.group(0)
            # Clean up DOI
            doi = re.sub(r'^(?:doi:|DOI:|https?://doi\.org/)', '', doi).strip()
            if not doi.startswith('10.'):
                doi = '10.' + doi
            return doi
        
        return None
    
    def _extract_abstract(self, text: str) -> Optional[str]:
        """Extract abstract"""
        # Look for abstract section
        abstract_patterns = [
            r'(?:Abstract|ABSTRACT)[:\s]*\n+(.*?)(?:\n\n|\n(?:Introduction|Keywords|1\.|I\.))',
            r'(?:Summary|SUMMARY)[:\s]*\n+(.*?)(?:\n\n|\n(?:Introduction|Keywords|1\.|I\.))',
        ]
        
        for pattern in abstract_patterns:
            match = re.search(pattern, text[:3000], re.IGNORECASE | re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                # Clean up abstract
                abstract = re.sub(r'\s+', ' ', abstract)  # Normalize whitespace
                if len(abstract) > 50:  # Reasonable abstract length
                    return abstract
        
        return None
    
    def _clean_title(self, title: str) -> str:
        """Clean and normalize title"""
        # Remove common artifacts
        title = re.sub(r'^[\d\.\-\s]+', '', title)  # Remove leading numbers/punctuation
        title = re.sub(r'\s+', ' ', title)  # Normalize whitespace
        title = title.strip()
        
        # Remove quotes if they surround the entire title
        if title.startswith('"') and title.endswith('"'):
            title = title[1:-1]
        
        return title

def extract_metadata_from_text(text: str) -> Dict[str, Any]:
    """Main function to extract metadata from text"""
    extractor = MetadataExtractor()
    metadata = extractor.extract_metadata(text)
    
    # Log what was extracted
    logger.info(f"Extracted metadata: {metadata}")
    
    return metadata