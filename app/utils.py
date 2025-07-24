"""
Utility functions for RefServerLite
"""
import hashlib
import os
from typing import Optional


def calculate_file_md5(file_path: str) -> Optional[str]:
    """
    Calculate MD5 hash of a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        MD5 hash as hex string, or None if file doesn't exist or error occurs
    """
    if not os.path.exists(file_path):
        return None
    
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Error calculating MD5 for {file_path}: {e}")
        return None


def calculate_bytes_md5(file_bytes: bytes) -> str:
    """
    Calculate MD5 hash of bytes data
    
    Args:
        file_bytes: File content as bytes
        
    Returns:
        MD5 hash as hex string
    """
    hash_md5 = hashlib.md5()
    hash_md5.update(file_bytes)
    return hash_md5.hexdigest()