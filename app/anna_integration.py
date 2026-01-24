"""
Anna's Archive integration - search and download functionality
"""

import os
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import List, Dict, Optional
import re


def get_fast_download_key() -> str:
    """Get the fast download key from environment variable."""
    key = os.getenv('FAST_DOWNLOAD_KEY')
    if not key:
        raise ValueError("FAST_DOWNLOAD_KEY not found in environment variables")
    return key


def sort_results_by_preference(results: List[Dict], preferred_language: str = "English", preferred_format: str = "epub") -> List[Dict]:
    """
    Sort search results to prioritize preferred language and format.
    
    Args:
        results: List of book dictionaries from search
        preferred_language: Preferred language (default: English)
        preferred_format: Preferred file format (default: epub)
        
    Returns:
        Sorted list with preferred results first
    """
    def score(book: Dict) -> int:
        """Calculate preference score (lower is better)."""
        s = 0
        
        # Language match is most important
        book_lang = book.get('language', '').lower()
        if book_lang and book_lang == preferred_language.lower():
            s -= 100
        elif not book_lang:
            s -= 10  # Unknown language gets slight preference over known non-match
        
        # Format match is secondary
        book_ext = book.get('extension', '').lower()
        if book_ext and book_ext == preferred_format.lower():
            s -= 50
        elif not book_ext:
            s -= 5  # Unknown format gets slight preference over known non-match
        
        return s
    
    return sorted(results, key=score)


def search_books(query: str, limit: int = 10) -> List[Dict]:
    """
    Search Anna's Archive for books.
    
    Args:
        query: Search query string
        limit: Maximum number of results to return
        
    Returns:
        List of book dictionaries with metadata
    """
    base_url = "https://annas-archive.li"
    search_url = f"{base_url}/search"
    
    params = {
        'q': query,
        'lang': '',
        'content': '',
        'ext': '',
        'sort': '',
        'page': 1
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(search_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        books = []
        
        # Find all MD5 links
        md5_links = soup.find_all('a', href=re.compile(r'/md5/[a-f0-9]{32}'))
        seen_md5s = set()
        
        for link in md5_links[:limit * 3]:
            if len(books) >= limit:
                break
                
            md5_match = re.search(r'/md5/([a-f0-9]{32})', link.get('href', ''))
            if not md5_match:
                continue
                
            md5_hash = md5_match.group(1)
            
            if md5_hash in seen_md5s:
                continue
            seen_md5s.add(md5_hash)
            
            book = {'id': md5_hash}
            
            # Get title from link text
            link_text = link.get_text(strip=True)
            if link_text and len(link_text) > 3:
                book['title'] = link_text
            
            # Get parent div for more context
            parent = link.parent
            if parent:
                text = parent.get_text()
                
                if 'title' not in book:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    for line in lines:
                        if len(line) > 10 and not line.startswith('nexusstc') and '.pdf' not in line.lower():
                            book['title'] = line
                            break
                
                # Extract metadata
                year_match = re.search(r'\b(19|20)\d{2}\b', text)
                if year_match:
                    book['year'] = year_match.group(0)
                
                ext_match = re.search(r'\.([a-z0-9]{2,5})(?:\s|$|,)', text.lower())
                if ext_match:
                    ext = ext_match.group(1)
                    if ext in ['epub', 'pdf', 'mobi', 'azw3', 'djvu', 'azw', 'txt', 'fb2']:
                        book['extension'] = ext
                
                size_match = re.search(r'(\d+(?:\.\d+)?\s*(?:KB|MB|GB))', text, re.IGNORECASE)
                if size_match:
                    book['filesize'] = size_match.group(1)
                
                lang_match = re.search(r'\b(English|Spanish|French|German|Russian|Chinese|Japanese)\b', text, re.IGNORECASE)
                if lang_match:
                    book['language'] = lang_match.group(1)
            
            if book.get('title'):
                books.append(book)
        
        return books[:limit]
        
    except Exception as e:
        print(f"Error searching Anna's Archive: {e}")
        return []


def get_download_url(md5_hash: str) -> Optional[str]:
    """
    Get the download URL for a book using the JSON API.
    
    Args:
        md5_hash: MD5 hash of the book
        
    Returns:
        Download URL or None if not found
    """
    base_url = "https://annas-archive.li"
    api_url = f"{base_url}/dyn/api/fast_download.json"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    params = {
        'md5': md5_hash,
        'key': get_fast_download_key()
    }
    
    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('download_url'):
            return data['download_url']
        
        return None
        
    except Exception as e:
        print(f"Error fetching download URL: {e}")
        return None


def download_book(md5_hash: str, output_dir: Path, title: str = "") -> Optional[Path]:
    """
    Download a book from Anna's Archive.
    
    Args:
        md5_hash: MD5 hash of the book
        output_dir: Directory to save the downloaded file
        title: Optional title for filename
        
    Returns:
        Path to the downloaded file or None if failed
    """
    download_url = get_download_url(md5_hash)
    
    if not download_url:
        print("Could not get download URL")
        return None
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(download_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # Try to get filename from Content-Disposition header
        filename = None
        content_disposition = response.headers.get('Content-Disposition', '')
        filename_match = re.search(r'filename="?([^"]+)"?', content_disposition)
        
        if filename_match:
            filename = filename_match.group(1)
        else:
            # Generate filename from title or MD5
            if title:
                # Clean title for filename
                safe_title = re.sub(r'[^\w\s\-\.]', '', title)
                safe_title = safe_title[:100]  # Limit length
                
                # Remove existing extension if present
                known_extensions = ['.epub', '.pdf', '.mobi', '.azw3', '.azw', '.djvu', '.txt', '.fb2']
                for ext in known_extensions:
                    if safe_title.lower().endswith(ext):
                        safe_title = safe_title[:-len(ext)]
                        break
                
                # Guess extension from Content-Type
                content_type = response.headers.get('Content-Type', '')
                ext = 'epub'
                if 'pdf' in content_type:
                    ext = 'pdf'
                elif 'mobi' in content_type:
                    ext = 'mobi'
                
                filename = f"{safe_title}.{ext}"
            else:
                filename = f"{md5_hash}.epub"
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = output_dir / filename
        
        # Download in chunks
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"Downloaded: {filename}")
        return filepath
        
    except Exception as e:
        print(f"Download failed: {e}")
        return None
