"""
Library Server - Simple HTTP server for Kobo-friendly book library
"""

import errno
import os
import time
import traceback
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
from anna_integration import search_books, download_book_with_diagnostics, sort_results_by_preference


# Load environment variables
load_dotenv()

# Configuration
LIBRARY_PATH = Path(os.environ.get('LIBRARY_PATH', Path(__file__).parent.parent / "test_library"))
DOWNLOAD_DIR = Path(os.environ.get('DOWNLOAD_DIR', LIBRARY_PATH))
PREFERRED_LANGUAGE = os.environ.get('PREFERRED_LANGUAGE', 'English')
PREFERRED_FORMAT = os.environ.get('PREFERRED_FORMAT', 'epub')
PORT = 26657  # Spells 'BOOKS' on phone keypad (B=2, O=6, O=6, K=5, S=7)
MAX_DOWNLOAD_DEBUG_LINES = 50
DOWNLOAD_DEBUG_LOGS = {}


class LibraryHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the library server."""

    @staticmethod
    def _is_client_disconnect(error: Exception) -> bool:
        """Return True if error is a normal client disconnect."""
        if isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError)):
            return True
        if isinstance(error, OSError):
            return error.errno in (errno.EPIPE, errno.ECONNRESET, errno.ECONNABORTED)
        return False

    @staticmethod
    def _safe_write_response(handler: BaseHTTPRequestHandler, status_code: int, html: str) -> bool:
        """Write an HTML response while tolerating normal client disconnects."""
        try:
            handler.send_response(status_code)
            handler.send_header('Content-type', 'text/html; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(html.encode('utf-8'))
            return True
        except Exception as e:
            if LibraryHandler._is_client_disconnect(e):
                if hasattr(handler, "log_message"):
                    handler.log_message("Client disconnected while sending response")
                return False
            raise

    @staticmethod
    def _make_debug_id() -> str:
        """Generate a compact debug identifier for download attempts."""
        return f"d{int(time.time() * 1000)}"

    @staticmethod
    def _trim_debug_lines(lines, max_lines: int = MAX_DOWNLOAD_DEBUG_LINES):
        """Keep only the most recent lines to avoid unbounded memory usage."""
        if len(lines) <= max_lines:
            return lines
        return lines[-max_lines:]

    @classmethod
    def _store_download_debug(cls, debug_id: str, lines) -> None:
        """Store per-download debug lines retrievable by /download-complete."""
        DOWNLOAD_DEBUG_LOGS[debug_id] = cls._trim_debug_lines(list(lines))

    @classmethod
    def _get_download_debug(cls, debug_id: str):
        return DOWNLOAD_DEBUG_LOGS.get(debug_id, [])

    def _log_download_event(self, debug_id: str, message: str) -> None:
        """Log download activity with a debug identifier."""
        self.log_message("[download:%s] %s", debug_id, message)
    
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
        
        self._safe_write_response(self, 200, html)
    
    def handle_anna_search(self, query_params):
        """Handle Anna's Archive search requests."""
        query = query_params.get('q', [''])[0]
        
        if not query:
            html = generate_message_html(
                "Search Error",
                "Please enter a search query."
            )
            self._safe_write_response(self, 400, html)
            return
        
        try:
            # Search Anna's Archive
            results = search_books(query, limit=10)
            
            # Sort results by user preferences (language and format)
            results = sort_results_by_preference(results, PREFERRED_LANGUAGE, PREFERRED_FORMAT)
            
            # Generate results HTML
            html = generate_search_results_html(results, query)
            
            self._safe_write_response(self, 200, html)
            
        except Exception as e:
            html = generate_message_html(
                "Search Error",
                f"Error searching: {str(e)}"
            )
            self._safe_write_response(self, 500, html)
    
    def handle_add(self, query_params):
        """Handle adding a book from Anna's Archive to the library."""
        md5 = query_params.get('md5', [''])[0]
        title = query_params.get('title', [''])[0]
        
        if not md5:
            html = generate_message_html(
                "Download Error",
                "No book selected."
            )
            self._safe_write_response(self, 400, html)
            return
        
        debug_id = self._make_debug_id()
        debug_lines = [
            f"debug_id={debug_id}",
            f"client={self.client_address[0]}",
            f"md5={md5}",
            f"title={title or '<untitled>'}",
            f"download_dir={DOWNLOAD_DIR}",
        ]
        self._log_download_event(debug_id, "Received add request")

        try:
            # Show loading spinner while downloading
            from html_generator import generate_loading_html

            # Download the book (this happens server-side)
            filepath, diagnostics = download_book_with_diagnostics(md5, DOWNLOAD_DIR, title)
            debug_lines.extend(diagnostics)

            if filepath:
                debug_lines.append(f"final_status=success filename={filepath.name}")
                self._store_download_debug(debug_id, debug_lines)
                self._log_download_event(debug_id, f"Download succeeded: {filepath.name}")

                # Show loading page that redirects to success page
                html = generate_loading_html(
                    "Adding to Library",
                    f"Downloading '{title or 'book'}' to your library...",
                    f"/download-complete?success=1&filename={filepath.name}&debug_id={debug_id}"
                )
                self._safe_write_response(self, 200, html)
            else:
                debug_lines.append("final_status=failed")
                self._store_download_debug(debug_id, debug_lines)
                for line in self._get_download_debug(debug_id):
                    self._log_download_event(debug_id, line)

                # Show loading page that redirects to failure page
                html = generate_loading_html(
                    "Adding to Library",
                    "Attempting to download...",
                    f"/download-complete?success=0&debug_id={debug_id}"
                )
                self._safe_write_response(self, 200, html)

        except Exception as e:
            debug_lines.append(f"exception={type(e).__name__}: {e}")
            debug_lines.append(traceback.format_exc().strip())
            debug_lines.append("final_status=exception")
            self._store_download_debug(debug_id, debug_lines)
            for line in self._get_download_debug(debug_id):
                self._log_download_event(debug_id, line)

            html = generate_message_html(
                "Download Error",
                "Error while processing download request.",
                details=self._get_download_debug(debug_id),
            )
            self._safe_write_response(self, 500, html)
    
    def handle_download_complete(self, query_params):
        """Handle download completion redirect page."""
        success = query_params.get('success', ['0'])[0]
        filename = query_params.get('filename', [''])[0]
        debug_id = query_params.get('debug_id', [''])[0]
        details = self._get_download_debug(debug_id) if debug_id else []
        
        if success == '1' and filename:
            if debug_id:
                self._log_download_event(debug_id, "Download complete page: success")
            html = generate_message_html(
                "Download Successful",
                f"Successfully added '{filename}' to your library!",
                details=details,
            )
        else:
            if debug_id:
                self._log_download_event(debug_id, "Download complete page: failure")
                for line in details:
                    self._log_download_event(debug_id, line)
            html = generate_message_html(
                "Download Failed",
                "Could not download the book. Please try again.",
                details=details,
            )
        
        self._safe_write_response(self, 200, html)
    
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
            if self._is_client_disconnect(e):
                self.log_message("Client disconnected during file download")
                return
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
