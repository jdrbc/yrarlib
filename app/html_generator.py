"""
HTML generator for Kobo-friendly library interface using Jinja2 templates
"""

from pathlib import Path
from typing import List, Dict, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape


# Setup Jinja2 environment
TEMPLATE_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True
)


def generate_index_html(pagination_data: Dict, search_query: str = "") -> str:
    """
    Generate a Kobo-friendly HTML page for the library.
    
    Args:
        pagination_data: Dictionary with books and pagination info from indexer
        search_query: Optional search query to display
        
    Returns:
        HTML string
    """
    template = jinja_env.get_template('index.html')
    return template.render(
        books=pagination_data['books'],
        page=pagination_data['page'],
        total_pages=pagination_data['total_pages'],
        total_books=pagination_data['total_books'],
        has_prev=pagination_data['has_prev'],
        has_next=pagination_data['has_next'],
        search_query=search_query
    )


def generate_local_search_results_html(books: List[Dict], query: str) -> str:
    """
    Generate HTML for local library search results.
    
    Args:
        books: List of book dictionaries from local library
        query: The search query
        
    Returns:
        HTML string
    """
    template = jinja_env.get_template('local_search_results.html')
    return template.render(
        books=books,
        query=query
    )


def generate_search_results_html(results: List[Dict], query: str) -> str:
    """
    Generate HTML for Anna's Archive search results.
    
    Args:
        results: List of search result dictionaries
        query: The search query
        
    Returns:
        HTML string
    """
    template = jinja_env.get_template('anna_search_results.html')
    return template.render(
        results=results,
        query=query
    )


def generate_loading_html(title: str, message: str, target_url: str) -> str:
    """
    Generate a loading page with CSS spinner that redirects after completion.
    
    Args:
        title: Page title
        message: Loading message
        target_url: URL to redirect to after a delay
        
    Returns:
        HTML string
    """
    template = jinja_env.get_template('loading.html')
    return template.render(
        title=title,
        message=message,
        target_url=target_url
    )


def generate_message_html(
    title: str,
    message: str,
    back_link: bool = True,
    details: Optional[List[str]] = None
) -> str:
    """
    Generate a simple message page.
    
    Args:
        title: Page title
        message: Message to display
        back_link: Whether to show back to library link
        details: Optional detail lines to render for debugging
        
    Returns:
        HTML string
    """
    template = jinja_env.get_template('message.html')
    return template.render(
        title=title,
        message=message,
        back_link=back_link,
        details=details or []
    )
