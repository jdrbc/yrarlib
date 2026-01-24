# Library App

A locally hosted, Kobo-friendly ebook library server with integrated Anna's Archive search and download capabilities.

## Features

- **📚 Local Library Management**: Browse your .epub and .pdf files sorted by newest first
- **🔍 Two-Tier Search**: Search your local library first, then expand to Anna's Archive
- **📱 Kobo-Optimized**: Large touch targets, simple navigation, no JavaScript required
- **⬇️ Server-Side Downloads**: The server handles downloads, not your Kobo browser
- **📄 Pagination**: Clean browsing with 15 books per page
- **⏳ Loading Indicators**: Visual feedback during download operations

## Quick Start

### Prerequisites

- Python 3.8+
- `uv` package manager (for dependency management)
- WiFi network (for Kobo access)

### Installation

1. **Clone or download this repository**

2. **Set up the environment**:
   ```bash
   cd app
   uv venv
   source .venv/bin/activate  # On macOS/Linux
   uv pip install requests beautifulsoup4 python-dotenv
   ```

3. **Configure your API key**:
   Create a `.env` file in the project root:
   ```
   FAST_DOWNLOAD_KEY=your_anna_archive_key_here
   ```

4. **Run the server**:
   ```bash
   cd app
   .venv/bin/python server.py
   ```

5. **Access from your computer**:
   Open browser to: `http://localhost:26657`

6. **Access from Kobo**:
   - Connect your Kobo to the same WiFi network
   - Open the Experimental Browser on your Kobo
   - Navigate to `http://<your-computer-ip>:26657`
