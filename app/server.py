"""
Library Server - Simple HTTP server for Kobo-friendly book library
"""

import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

from indexer import scan_library, paginate_books, search_local_library
from html_generator import (
    generate_index_html,
    generate_local_search_results_html,
    generate_search_results_html,
    generate_message_html,
    generate_loading_html
)
from anna_integration import search_books, download_book, sort_results_by_preference


# Load environment variables
load_dotenv()

# Configuration
LIBRARY_PATH = Path(os.environ.get('LIBRARY_PATH', Path(__file__).parent.parent / "test_library"))
DOWNLOAD_DIR = Path(os.environ.get('DOWNLOAD_DIR', LIBRARY_PATH))
PREFERRED_LANGUAGE = os.environ.get('PREFERRED_LANGUAGE', 'English')
PREFERRED_FORMAT = os.environ.get('PREFERRED_FORMAT', 'epub')
PORT = 26657  # Spells 'BOOKS' on phone keypad (B=2, O=6, O=6, K=5, S=7)


class LibraryHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the library server."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query_params = parse_qs(parsed.query)
        
        if path == '/' or path == '/index.html':
            self.handle_index(query_params)
        elif path == '/search-anna':
            self.handle_anna_search(query_params)
        elif path == '/add':
            self.handle_add(query_params)
        elif path == '/download':
            self.handle_download(query_params)
        elif path == '/download-complete':
            self.handle_download_complete(query_params)
        else:
            self.send_error(404, "Page not found")
    
    def handle_index(self, query_params):
        """Handle the main library index page with optional local search."""
        query = query_params.get('q', [''])[0]
        
        # If there's a search query, show local search results
        if query:
            books = search_local_library(str(LIBRARY_PATH), query)
            html = generate_local_search_results_html(books, query)
        else:
            # No search query, show paginated library
            try:
                page = int(query_params.get('page', ['1'])[0])
            except (ValueError, IndexError):
                page = 1
            
            books = scan_library(str(LIBRARY_PATH))
            pagination_data = paginate_books(books, page=page, per_page=15)
            html = generate_index_html(pagination_data)
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def handle_anna_search(self, query_params):
        """Handle Anna's Archive search requests."""
        query = query_params.get('q', [''])[0]
        
        if not query:
            html = generate_message_html(
                "Search Error",
                "Please enter a search query."
            )
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return
        
        try:
            # Search Anna's Archive
            results = search_books(query, limit=10)
            
            # Sort results by user preferences (language and format)
            results = sort_results_by_preference(results, PREFERRED_LANGUAGE, PREFERRED_FORMAT)
            
            # Generate results HTML
            html = generate_search_results_html(results, query)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
        except Exception as e:
            html = generate_message_html(
                "Search Error",
                f"Error searching: {str(e)}"
            )
            self.send_response(500)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
    
    def handle_add(self, query_params):
        """Handle adding a book from Anna's Archive to the library."""
        md5 = query_params.get('md5', [''])[0]
        title = query_params.get('title', [''])[0]
        
        if not md5:
            html = generate_message_html(
                "Download Error",
                "No book selected."
            )
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return
        
        try:
            # Show loading spinner while downloading
            from html_generator import generate_loading_html
            
            # Download the book (this happens server-side)
            filepath = download_book(md5, DOWNLOAD_DIR, title)
            
            if filepath:
                # Show loading page that redirects to success page
                html = generate_loading_html(
                    "Adding to Library",
                    f"Downloading '{title or 'book'}' to your library...",
                    f"/download-complete?success=1&filename={filepath.name}"
                )
                self.send_response(200)
            else:
                # Show loading page that redirects to failure page
                html = generate_loading_html(
                    "Adding to Library",
                    "Attempting to download...",
                    "/download-complete?success=0"
                )
                self.send_response(200)
            
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
        except Exception as e:
            html = generate_message_html(
                "Download Error",
                f"Error: {str(e)}"
            )
            self.send_response(500)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
    
    def handle_download_complete(self, query_params):
        """Handle download completion redirect page."""
        success = query_params.get('success', ['0'])[0]
        filename = query_params.get('filename', [''])[0]
        
        if success == '1' and filename:
            html = generate_message_html(
                "Download Successful",
                f"Successfully added '{filename}' to your library!"
            )
        else:
            html = generate_message_html(
                "Download Failed",
                "Could not download the book. Please try again."
            )
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def handle_download(self, query_params):
        """Handle book file downloads."""
        file_param = query_params.get('file', [''])[0]
        
        if not file_param:
            self.send_error(400, "No file specified")
            return
        
        # Decode and resolve file path
        filepath = LIBRARY_PATH / unquote(file_param)
        
        # Security check: ensure path is within library
        try:
            filepath = filepath.resolve()
            if not str(filepath).startswith(str(LIBRARY_PATH.resolve())):
                self.send_error(403, "Access denied")
                return
        except Exception:
            self.send_error(403, "Invalid path")
            return
        
        # Check if file exists
        if not filepath.exists() or not filepath.is_file():
            self.send_error(404, "File not found")
            return
        
        try:
            # Determine content type
            ext = filepath.suffix.lower()
            content_types = {
                '.epub': 'application/epub+zip',
                '.pdf': 'application/pdf',
                '.mobi': 'application/x-mobipocket-ebook',
            }
            content_type = content_types.get(ext, 'application/octet-stream')
            
            # Read and send file
            with open(filepath, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{filepath.name}"')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            
        except Exception as e:
            self.send_error(500, f"Error reading file: {str(e)}")
    
    def log_message(self, format, *args):
        """Custom log message format."""
        print(f"{self.address_string()} - {format % args}")


def run_server(port=PORT):
    """Run the library server."""
    server_address = ('', port)
    httpd = HTTPServer(server_address, LibraryHandler)
    
    print(f"Library server starting on port {port}")
    print(f"Library path: {LIBRARY_PATH}")
    print(f"Download dir: {DOWNLOAD_DIR}")
    print(f"Access the library at: http://localhost:{port}")
    print(f"Or from Kobo: http://<your-ip>:{port}")
    print("\nPress Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        httpd.server_close()


if __name__ == '__main__':
    run_server()
