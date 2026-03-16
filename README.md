# QMD GUI

A Python/Qt desktop GUI application for [QMD](https://github.com/tobi/qmd) (Query Markup Documents).

QMD is an on-device search engine that indexes your markdown documents locally and provides hybrid search combining BM25 keyword search, vector semantic search, and LLM re-ranking. QMD GUI lets you use all these features through a graphical interface without touching the terminal.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Qt](https://img.shields.io/badge/GUI-PySide6-green)

## Features

- **Hybrid Search** — Three search modes: BM25 (keyword), Vector (semantic), and Hybrid (BM25 + Vector + re-ranking)
- **Color-Coded Results** — Score-based coloring (green ≥70%, yellow ≥40%, gray below)
- **Markdown Preview** — Rendered markdown preview using QWebEngineView
- **Collection Management** — Add/remove/rename collections, browse file lists, update indexes
- **Embedding Generation** — Generate vector embeddings with real-time progress bar (PTY-based parsing)
- **Index Status** — View QMD index status and collection info
- **Dual Backend** — CLI (subprocess) mode and MCP HTTP mode
- **Dark Theme** — Catppuccin Mocha-based dark UI with external stylesheet

## Requirements

- Python 3.10+
- [QMD](https://github.com/tobi/qmd) installed with `qmd` command available in PATH
- PySide6
- PySide6-WebEngine (bundled with PySide6 on macOS)
- markdown
- requests

## Installation

```bash
git clone https://github.com/nyang-police/QMD-gui.git
cd qmd-gui
pip install PySide6 markdown requests
```

With `uv`:

```bash
uv add PySide6 markdown requests
```

## Usage

### CLI Mode (default)

Calls `qmd` via subprocess. No server required.

```bash
python qmd_gui.py
```

### MCP HTTP Mode

Connects to the MCP server for faster responses. Models stay loaded in memory across requests.

```bash
# Start the MCP server first
qmd mcp --http

# Run the GUI
python qmd_gui.py --mcp
```

Custom port:

```bash
qmd mcp --http --port 9000
python qmd_gui.py --mcp --port 9000
```

Falls back to CLI mode automatically if the MCP server is unreachable.

## Project Structure

```text
qmd-gui/
├── qmd_gui.py        # Main application
├── embed_runner.py    # PTY proxy for embedding progress parsing
├── style.qss          # Qt stylesheet (Catppuccin Mocha theme)
└── README.md
```

## Tabs

### Search

Enter a search query and browse results.

- **Search Modes**: BM25 (keyword), Vector (semantic), Hybrid (with re-ranking)
- **Collection Filter**: Restrict search to a specific collection
- **Result Limits**: Set max results and minimum score threshold
- **Result Tabs**:
  - **Snippet** — Search result excerpt
  - **Full Document** — Full document content (raw markdown)
  - **Preview** — Rendered markdown preview
  - **Metadata** — Title, path, doc ID, score, and other metadata

### Collections

Manage QMD collections.

- Browse collection list and select to view details
- View file list for the selected collection
- Add, remove, and rename collections
- Update index and generate vector embeddings with real-time progress

### Status

Displays QMD index status information.

## Backends

|Mode|Command|Description|
|---|---|---|
|CLI (default)|`python qmd_gui.py`|No server needed, calls `qmd` via subprocess|
|MCP HTTP|`python qmd_gui.py --mcp`|Faster responses, models stay in memory, requires `qmd mcp --http`|

## Customizing the Theme

Edit `style.qss` to change the UI theme. The default uses the Catppuccin Mocha color palette.

|Role|Color|
|---|---|
|Base|`#1e1e2e`|
|Surface|`#313244`|
|Mantle|`#181825`|
|Border|`#45475a`|
|Text|`#cdd6f4`|
|Accent (Blue)|`#89b4fa`|

## Notes

This application has only been tested on macOS. It may work on Windows and Linux but is not guaranteed.
