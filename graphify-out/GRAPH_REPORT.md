# Graph Report - .  (2026-05-11)

## Corpus Check
- Corpus is ~5,869 words - fits in a single context window. You may not need a graph.

## Summary
- 182 nodes · 318 edges · 10 communities (9 shown, 1 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 20 edges (avg confidence: 0.83)
- Token cost: 65,305 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Backend Adapters (CLI & MCP)|Backend Adapters (CLI & MCP)]]
- [[_COMMUNITY_Collection Panel UI|Collection Panel UI]]
- [[_COMMUNITY_Module Architecture & Concepts|Module Architecture & Concepts]]
- [[_COMMUNITY_Async Worker Threads|Async Worker Threads]]
- [[_COMMUNITY_Main Window UI|Main Window UI]]
- [[_COMMUNITY_Modal Dialogs|Modal Dialogs]]
- [[_COMMUNITY_Coding Guidelines (CLAUDE.md)|Coding Guidelines (CLAUDE.md)]]
- [[_COMMUNITY_TODO Keyboard Shortcuts|TODO: Keyboard Shortcuts]]

## God Nodes (most connected - your core abstractions)
1. `CollectionPanel` - 36 edges
2. `CLIBackend` - 26 edges
3. `MCPBackend` - 23 edges
4. `QMDMainWindow` - 19 edges
5. `CLIBackend` - 14 edges
6. `CollectionPanel` - 12 edges
7. `MCPBackend` - 11 edges
8. `CollectionWorker` - 9 edges
9. `AsyncWorker` - 9 edges
10. `QMDMainWindow` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Hybrid Search (BM25 + Vector + rerank)` --rationale_for--> `QMDMainWindow`  [INFERRED]
  README.md → qmd_gui.py
- `main.py stub entry` --semantically_similar_to--> `main`  [INFERRED] [semantically similar]
  main.py → qmd_gui.py
- `PTY-based embedding progress parsing` --rationale_for--> `embed_runner main (PTY proxy)`  [INFERRED]
  README.md → embed_runner.py
- `Dual Backend architecture (CLI vs MCP HTTP)` --rationale_for--> `CLIBackend`  [INFERRED]
  README.md → qmd_gui.py
- `Dual Backend architecture (CLI vs MCP HTTP)` --rationale_for--> `MCPBackend`  [INFERRED]
  README.md → qmd_gui.py

## Hyperedges (group relationships)
- **Dual backend abstraction (CLI + MCP)** — qmd_gui_clibackend, qmd_gui_mcpbackend, qmd_gui_backend_abstraction, qmd_gui_main [INFERRED 0.85]
- **Async worker thread family** — qmd_gui_searchworker, qmd_gui_docworker, qmd_gui_collectionworker, qmd_gui_asyncworker, qmd_gui_embedworker, qmd_gui_qthread_worker_pattern [INFERRED 0.85]
- **Main window orchestrates tabs and workers** — qmd_gui_qmdmainwindow, qmd_gui_collectionpanel, qmd_gui_searchworker, qmd_gui_docworker, qmd_gui_asyncworker [INFERRED 0.85]

## Communities (10 total, 1 thin omitted)

### Community 0 - "Backend Adapters (CLI & MCP)"
Cohesion: 0.08
Nodes (7): CLIBackend, CollectionInfo, main(), MCPBackend, QMD backend using subprocess calls., QMD backend using MCP Streamable HTTP (JSON-RPC 2.0)., SearchResult

### Community 1 - "Collection Panel UI"
Cohesion: 0.1
Nodes (6): CollectionPanel, CollectionWorker, Generic worker for collection operations., Return (qmd_path, text) ready for `qmd context add`., Panel for managing QMD collections., QWidget

### Community 2 - "Module Architecture & Concepts"
Cohesion: 0.12
Nodes (31): embed_runner main (PTY proxy), main.py stub entry, AddCollectionDialog, AddContextDialog, AsyncWorker, Backend abstraction pattern, CLIBackend, CollectionInfo (+23 more)

### Community 3 - "Async Worker Threads"
Cohesion: 0.1
Nodes (13): AsyncWorker, ContextEntry, DocWorker, EmbedWorker, load_collection_abs_paths(), _parse_context_list(), A human-written context attached to a qmd path.      `collection` is "" and `sub, Generic async worker that passes result as object. (+5 more)

### Community 4 - "Main Window UI"
Cohesion: 0.14
Nodes (4): QMainWindow, QMDMainWindow, Refresh the search tab's collection dropdown., Convert markdown to HTML and display in preview tab.

### Community 5 - "Modal Dialogs"
Cohesion: 0.12
Nodes (7): QDialog, AddCollectionDialog, AddContextDialog, Dialog to add a new collection., Dialog to rename a collection., Dialog to add a context attached to a qmd path., RenameCollectionDialog

### Community 6 - "Coding Guidelines (CLAUDE.md)"
Cohesion: 0.5
Nodes (4): Goal-Driven Execution, Simplicity First, Surgical Changes, Think Before Coding

## Knowledge Gaps
- **28 isolated node(s):** `Parse `qmd context list` text output into ContextEntry list.      Format observe`, `A human-written context attached to a qmd path.      `collection` is "" and `sub`, `Read ~/.config/qmd/index.yml and return {collection_name: absolute_path}.      H`, `QMD backend using subprocess calls.`, `QMD backend using MCP Streamable HTTP (JSON-RPC 2.0).` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CollectionPanel` connect `Collection Panel UI` to `Async Worker Threads`, `Main Window UI`, `Modal Dialogs`?**
  _High betweenness centrality (0.209) - this node is a cross-community bridge._
- **Why does `CLIBackend` connect `Backend Adapters (CLI & MCP)` to `Async Worker Threads`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Why does `QMDMainWindow` connect `Main Window UI` to `Backend Adapters (CLI & MCP)`, `Async Worker Threads`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `CLIBackend` (e.g. with `Dual Backend architecture (CLI vs MCP HTTP)` and `MCPBackend`) actually correct?**
  _`CLIBackend` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Parse `qmd context list` text output into ContextEntry list.      Format observe`, `A human-written context attached to a qmd path.      `collection` is "" and `sub`, `Read ~/.config/qmd/index.yml and return {collection_name: absolute_path}.      H` to the rest of the system?**
  _28 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Backend Adapters (CLI & MCP)` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._
- **Should `Collection Panel UI` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._