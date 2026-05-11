# Graph Report - .  (2026-05-11)

## Corpus Check
- Corpus is ~4,291 words - fits in a single context window. You may not need a graph.

## Summary
- 141 nodes · 242 edges · 11 communities (9 shown, 2 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 16 edges (avg confidence: 0.87)
- Token cost: 0 input · 57,110 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Collection Panel UI|Collection Panel UI]]
- [[_COMMUNITY_Project Architecture|Project Architecture]]
- [[_COMMUNITY_QThread Workers|QThread Workers]]
- [[_COMMUNITY_Main Window & Search|Main Window & Search]]
- [[_COMMUNITY_MCP HTTP Backend|MCP HTTP Backend]]
- [[_COMMUNITY_CLI Backend|CLI Backend]]
- [[_COMMUNITY_Collection Dialogs|Collection Dialogs]]
- [[_COMMUNITY_Collection Data & Status|Collection Data & Status]]

## God Nodes (most connected - your core abstractions)
1. `CollectionPanel` - 27 edges
2. `CLIBackend` - 20 edges
3. `MCPBackend` - 20 edges
4. `QMDMainWindow` - 19 edges
5. `AddCollectionDialog` - 8 edges
6. `AsyncWorker` - 8 edges
7. `CLIBackend` - 8 edges
8. `CollectionPanel widget` - 8 edges
9. `QMDMainWindow` - 8 edges
10. `CollectionWorker` - 7 edges

## Surprising Connections (you probably didn't know these)
- `Future feature: context editor (qmd context add/rm)` --conceptually_related_to--> `CollectionPanel widget`  [INFERRED]
  to-do.txt → qmd_gui.py
- `Hybrid Search (BM25 + Vector + rerank)` --rationale_for--> `QMDMainWindow`  [INFERRED]
  README.md → qmd_gui.py
- `Future feature: keyboard shortcuts (Ctrl+F, Ctrl+1/2/3)` --conceptually_related_to--> `QMDMainWindow`  [INFERRED]
  to-do.txt → qmd_gui.py
- `Dual Backend architecture (CLI vs MCP HTTP)` --rationale_for--> `CLIBackend`  [INFERRED]
  README.md → qmd_gui.py
- `Dual Backend architecture (CLI vs MCP HTTP)` --rationale_for--> `MCPBackend`  [INFERRED]
  README.md → qmd_gui.py

## Hyperedges (group relationships)
- **Qt worker thread family for async backend ops** — qmd_gui_searchworker, qmd_gui_docworker, qmd_gui_collectionworker, qmd_gui_asyncworker, qmd_gui_embedworker [INFERRED 0.85]
- **Embedding progress pipeline (UI panel -> EmbedWorker -> PTY runner -> qmd embed)** — qmd_gui_collectionpanel, qmd_gui_embedworker, embed_runner_main, readme_pty_progress_parsing [INFERRED 0.85]
- **Dual-backend interchangeable interface used by workers and main window** — qmd_gui_clibackend, qmd_gui_mcpbackend, qmd_gui_qmdmainwindow, readme_dual_backend [INFERRED 0.85]

## Communities (11 total, 2 thin omitted)

### Community 0 - "Collection Panel UI"
Cohesion: 0.14
Nodes (3): CollectionPanel, Panel for managing QMD collections., QWidget

### Community 1 - "Project Architecture"
Cohesion: 0.14
Nodes (24): embed_runner main (PTY proxy), main.py stub entry, AddCollectionDialog, AsyncWorker QThread, CLIBackend, CollectionInfo dataclass, CollectionPanel widget, CollectionWorker QThread (+16 more)

### Community 2 - "QThread Workers"
Cohesion: 0.12
Nodes (10): AsyncWorker, CollectionWorker, DocWorker, EmbedWorker, Generic async worker that passes result as object., Worker that runs embed_runner.py and reads JSON progress lines., Generic worker for collection operations., SearchResult (+2 more)

### Community 3 - "Main Window & Search"
Cohesion: 0.15
Nodes (4): QMainWindow, QMDMainWindow, Refresh the search tab's collection dropdown., Convert markdown to HTML and display in preview tab.

### Community 4 - "MCP HTTP Backend"
Cohesion: 0.18
Nodes (3): main(), MCPBackend, QMD backend using MCP Streamable HTTP (JSON-RPC 2.0).

### Community 6 - "Collection Dialogs"
Cohesion: 0.2
Nodes (5): QDialog, AddCollectionDialog, Dialog to add a new collection., Dialog to rename a collection., RenameCollectionDialog

## Knowledge Gaps
- **15 isolated node(s):** `QMD backend using subprocess calls.`, `QMD backend using MCP Streamable HTTP (JSON-RPC 2.0).`, `Generic worker for collection operations.`, `Dialog to add a new collection.`, `Dialog to rename a collection.` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CollectionPanel` connect `Collection Panel UI` to `QThread Workers`, `Collection Dialogs`?**
  _High betweenness centrality (0.210) - this node is a cross-community bridge._
- **Why does `QMDMainWindow` connect `Main Window & Search` to `Collection Panel UI`, `QThread Workers`, `MCP HTTP Backend`, `Collection Data & Status`?**
  _High betweenness centrality (0.162) - this node is a cross-community bridge._
- **Why does `MCPBackend` connect `MCP HTTP Backend` to `Search Result Parsing`, `QThread Workers`, `Collection Data & Status`?**
  _High betweenness centrality (0.133) - this node is a cross-community bridge._
- **What connects `QMD backend using subprocess calls.`, `QMD backend using MCP Streamable HTTP (JSON-RPC 2.0).`, `Generic worker for collection operations.` to the rest of the system?**
  _15 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Collection Panel UI` be split into smaller, more focused modules?**
  _Cohesion score 0.14 - nodes in this community are weakly interconnected._
- **Should `Project Architecture` be split into smaller, more focused modules?**
  _Cohesion score 0.14 - nodes in this community are weakly interconnected._
- **Should `QThread Workers` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._