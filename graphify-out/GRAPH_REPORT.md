# Graph Report - .  (2026-05-11)

## Corpus Check
- Corpus is ~4,463 words - fits in a single context window. You may not need a graph.

## Summary
- 129 nodes · 211 edges · 13 communities (8 shown, 5 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Collection Panel UI|Collection Panel UI]]
- [[_COMMUNITY_Project Architecture|Project Architecture]]
- [[_COMMUNITY_QThread Workers|QThread Workers]]
- [[_COMMUNITY_Main Window & Search|Main Window & Search]]
- [[_COMMUNITY_MCP HTTP Backend|MCP HTTP Backend]]
- [[_COMMUNITY_CLI Backend|CLI Backend]]
- [[_COMMUNITY_Collection Dialogs|Collection Dialogs]]
- [[_COMMUNITY_Collection Data & Status|Collection Data & Status]]
- [[_COMMUNITY_Embed Runner PTY|Embed Runner PTY]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]

## God Nodes (most connected - your core abstractions)
1. `CollectionPanel` - 27 edges
2. `CLIBackend` - 20 edges
3. `MCPBackend` - 20 edges
4. `QMDMainWindow` - 19 edges
5. `AddCollectionDialog` - 8 edges
6. `AsyncWorker` - 8 edges
7. `CollectionWorker` - 7 edges
8. `RenameCollectionDialog` - 7 edges
9. `EmbedWorker` - 6 edges
10. `QMD GUI project README` - 5 edges

## Surprising Connections (you probably didn't know these)
- `embed_runner main (PTY proxy)` --rationale_for--> `PTY-based embedding progress parsing`  [INFERRED]
  embed_runner.py → README.md

## Hyperedges (group relationships)
- **Qt worker thread family for async backend ops** — qmd_gui_searchworker, qmd_gui_docworker, qmd_gui_collectionworker, qmd_gui_asyncworker, qmd_gui_embedworker [INFERRED 0.85]
- **Embedding progress pipeline (UI panel -> EmbedWorker -> PTY runner -> qmd embed)** — qmd_gui_collectionpanel, qmd_gui_embedworker, embed_runner_main, readme_pty_progress_parsing [INFERRED 0.85]
- **Dual-backend interchangeable interface used by workers and main window** — qmd_gui_clibackend, qmd_gui_mcpbackend, qmd_gui_qmdmainwindow, readme_dual_backend [INFERRED 0.85]

## Communities (13 total, 5 thin omitted)

### Community 0 - "Collection Panel UI"
Cohesion: 0.12
Nodes (4): CollectionInfo, main(), MCPBackend, QMD backend using MCP Streamable HTTP (JSON-RPC 2.0).

### Community 1 - "Project Architecture"
Cohesion: 0.11
Nodes (10): AsyncWorker, CollectionWorker, DocWorker, EmbedWorker, Generic async worker that passes result as object., Worker that runs embed_runner.py and reads JSON progress lines., Generic worker for collection operations., SearchResult (+2 more)

### Community 2 - "QThread Workers"
Cohesion: 0.16
Nodes (3): CollectionPanel, Panel for managing QMD collections., QWidget

### Community 3 - "Main Window & Search"
Cohesion: 0.15
Nodes (4): QMainWindow, QMDMainWindow, Refresh the search tab's collection dropdown., Convert markdown to HTML and display in preview tab.

### Community 5 - "CLI Backend"
Cohesion: 0.2
Nodes (5): QDialog, AddCollectionDialog, Dialog to add a new collection., Dialog to rename a collection., RenameCollectionDialog

### Community 6 - "Collection Dialogs"
Cohesion: 0.29
Nodes (7): embed_runner main (PTY proxy), Catppuccin Mocha dark theme, Dual Backend architecture (CLI vs MCP HTTP), Hybrid Search (BM25 + Vector + rerank), PTY-based embedding progress parsing, QMD GUI project README, QMD upstream project

## Knowledge Gaps
- **19 isolated node(s):** `embed_runner main (PTY proxy)`, `main.py stub entry`, `QMD upstream project`, `Hybrid Search (BM25 + Vector + rerank)`, `Dual Backend architecture (CLI vs MCP HTTP)` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CollectionPanel` connect `QThread Workers` to `Project Architecture`, `CLI Backend`, `Collection Data & Status`?**
  _High betweenness centrality (0.253) - this node is a cross-community bridge._
- **Why does `QMDMainWindow` connect `Main Window & Search` to `Collection Panel UI`, `Project Architecture`, `QThread Workers`?**
  _High betweenness centrality (0.198) - this node is a cross-community bridge._
- **Why does `MCPBackend` connect `Collection Panel UI` to `Project Architecture`?**
  _High betweenness centrality (0.162) - this node is a cross-community bridge._
- **What connects `embed_runner main (PTY proxy)`, `main.py stub entry`, `QMD upstream project` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Collection Panel UI` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._
- **Should `Project Architecture` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._