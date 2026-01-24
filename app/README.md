# Library Server

A locally hosted, Kobo-friendly library server that manages your ebook collection and integrates with Anna's Archive.

## Features

- **Browse Library**: View your .epub and .pdf files sorted by newest first
- **Kobo-Optimized UI**: Large touch targets, no JavaScript, simple navigation
- **Pagination**: Easy browsing with 15 books per page
- **Anna's Archive Integration**: Search and download books directly to your library
- **Server-Side Downloads**: The server handles downloads, not your Kobo

## Setup

1. **Install dependencies**:
   ```bash
   cd app
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```

2. **Configure environment**:
   Ensure your `.env` file in the project root contains:
   ```
   FAST_DOWNLOAD_KEY=your_key_here
   ```

3. **Run the server**:
   ```bash
   python server.py
   ```

4. **Access from Kobo**:
   - Connect your Kobo to the same WiFi network
   - Open the browser on your Kobo
   - Navigate to `http://<your-computer-ip>:26657`

## Usage

### Browsing Your Library
- The main page shows your books sorted by newest first
- Use "Prev" and "Next" buttons to navigate pages
- Click "Download" to download a book to your Kobo

### Adding Books from Anna's Archive
1. Enter a search query (title, author, keywords)
2. Click "Search"
3. Browse the results
4. Click "Add to Library" on any book
5. The server downloads it to your library automatically

## Configuration

- **Library Path**: Edit `LIBRARY_PATH` in `server.py` (default: `../test_library`)
- **Port**: Edit `PORT` in `server.py` (default: `26657` - spells 'BOOKS' on phone keypad)
- **Books Per Page**: Edit `per_page` parameter in `server.py` (default: `15`)

## File Structure

```
app/
├── server.py              # Main HTTP server
├── indexer.py             # Library scanning and pagination
├── html_generator.py      # Kobo-friendly HTML generation
├── anna_integration.py    # Anna's Archive search & download
├── pyproject.toml         # Dependencies
└── README.md              # This file
```

## Finding Your Computer's IP Address

**macOS/Linux**:
```bash
ifconfig | grep "inet "
```

**Windows**:
```cmd
ipconfig
```

Look for your local network IP (usually starts with `192.168.` or `10.`)

## Troubleshooting

- **Can't connect from Kobo**: Make sure both devices are on the same WiFi network
- **Search not working**: Check that `FAST_DOWNLOAD_KEY` is set in `.env`
- **Downloads failing**: Verify your internet connection and Anna's Archive availability
- **Books not showing**: Check that `LIBRARY_PATH` points to the correct directory

## License

MIT
