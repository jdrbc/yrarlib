"""
Library indexer - scans directory for books and sorts by modification time
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict


def scan_library(library_path: str) -> List[Dict]:
    """
    Recursively scan a directory for .epub and .pdf files.
    
    Args:
        library_path: Path to the library directory
        
    Returns:
        List of book dictionaries sorted by modification time (newest first)
    """
    books = []
    library_path = Path(library_path).resolve()
    
    # Supported extensions
    extensions = ('.epub', '.pdf')
    
    # Walk through directory
    for root, dirs, files in os.walk(library_path):
        for filename in files:
            if filename.lower().endswith(extensions):
                filepath = Path(root) / filename
                
                # Get file stats
                try:
                    stat = filepath.stat()
                    modified_time = stat.st_mtime
                    file_size = stat.st_size
                    
                    # Get relative path from library root
                    try:
                        relative_path = filepath.relative_to(library_path)
                    except ValueError:
                        # If relative_to fails, use absolute path
                        relative_path = filepath
                    
                    books.append({
                        'filename': filename,
                        'filepath': str(filepath),
                        'relative_path': str(relative_path),
                        'modified_time': modified_time,
                        'modified_date': datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M'),
                        'size': format_file_size(file_size),
                        'size_bytes': file_size,
                        'extension': filepath.suffix.lower()
                    })
                    
                except (OSError, PermissionError) as e:
                    print(f"Error accessing {filepath}: {e}")
                    continue
    
    # Sort by modification time, newest first
    books.sort(key=lambda x: x['modified_time'], reverse=True)
    
    return books


def search_local_library(library_path: str, query: str) -> List[Dict]:
    """
    Search the local library for books matching the query.
    
    Args:
        library_path: Path to the library directory
        query: Search query string
        
    Returns:
        List of matching book dictionaries
    """
    all_books = scan_library(library_path)
    
    if not query:
        return all_books
    
    # Normalize query for case-insensitive matching
    query_lower = query.lower()
    query_parts = query_lower.split()
    
    # Filter books where any part of query matches filename or path
    matching_books = []
    for book in all_books:
        searchable = f"{book['filename']} {book['relative_path']}".lower()
        
        # Check if all query parts are in the searchable text
        if all(part in searchable for part in query_parts):
            matching_books.append(book)
    
    return matching_books


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def paginate_books(books: List[Dict], page: int = 1, per_page: int = 15) -> Dict:
    """
    Paginate the book list.
    
    Args:
        books: List of all books
        page: Current page number (1-indexed)
        per_page: Number of books per page
        
    Returns:
        Dictionary with paginated books and pagination info
    """
    total = len(books)
    total_pages = (total + per_page - 1) // per_page  # Ceiling division
    
    # Ensure page is valid
    page = max(1, min(page, total_pages if total_pages > 0 else 1))
    
    # Calculate slice indices
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    return {
        'books': books[start_idx:end_idx],
        'page': page,
        'per_page': per_page,
        'total_books': total,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages
    }
