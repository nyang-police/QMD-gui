#!/usr/bin/env python3
"""
QMD GUI — A Python/Qt desktop interface for QMD (github.com/tobi/qmd)

Supports two backends:
  - CLI mode: calls `qmd` via subprocess (default, no server needed)
  - MCP HTTP mode: connects to `qmd mcp --http` server (faster, models stay loaded)

Usage:
  python qmd_gui.py              # CLI mode
  python qmd_gui.py --mcp        # MCP HTTP mode (run `qmd mcp --http` first)
  python qmd_gui.py --mcp --port 9000  # custom port
"""

import sys
import os
import json
import subprocess
import argparse
import platform
from typing import Optional
from dataclasses import dataclass, field

import requests
import markdown

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QComboBox,
    QLabel,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QStatusBar,
    QGroupBox,
    QSpinBox,
    QCheckBox,
    QMessageBox,
    QTabWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFileDialog,
    QProgressBar,
    QFrame,
    QTabBar,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QAction, QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView


# ──────────────────────────────────────────────
#  Platform-specific monospace font
# ──────────────────────────────────────────────

if platform.system() == "Darwin":
    MONO_FONT = "Menlo"
elif platform.system() == "Windows":
    MONO_FONT = "Consolas"
else:
    MONO_FONT = "Monospace"


# ──────────────────────────────────────────────
#  Data Models
# ──────────────────────────────────────────────


@dataclass
class SearchResult:
    title: str = ""
    path: str = ""
    docid: str = ""
    score: float = 0.0
    snippet: str = ""
    context: str = ""
    collection: str = ""


@dataclass
class CollectionInfo:
    name: str = ""
    path: str = ""
    doc_count: int = 0
    active_count: int = 0
    glob_pattern: str = ""


def _parse_context_list(output: str, known_collections: set[str]) -> list["ContextEntry"]:
    """Parse `qmd context list` text output into ContextEntry list.

    Format observed:
        Configured Contexts

        *                            <-- global marker (indent 0)
          /                          <-- sub_path under global (indent 2)
            Text line 1              <-- text body (indent 4)
        Text line 2                  <-- multiline continuation (flush left!)
        <collection_name>            <-- indent 0
          <sub_path possibly nested> <-- indent 2
            <text>

    Multiline text continuations appear at indent 0, so we use the known
    collection name set (+ "*") to distinguish them from a new section.
    """
    if "No contexts configured" in output:
        return []

    entries: list[ContextEntry] = []
    current_collection: Optional[str] = None  # "" means global section
    current_sub: Optional[str] = None
    current_text: list[str] = []
    is_global = False

    def flush() -> None:
        if current_sub is None:
            return
        entries.append(
            ContextEntry(
                collection="" if is_global else (current_collection or ""),
                sub_path=current_sub,
                text="\n".join(current_text).rstrip(),
            )
        )

    section_markers = known_collections | {"*"}

    for raw in output.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.strip() == "Configured Contexts":
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped in section_markers:
            flush()
            current_text = []
            if stripped == "*":
                is_global = True
                current_collection = ""
            else:
                is_global = False
                current_collection = stripped
            current_sub = None
            continue

        if indent == 2 and current_collection is not None or (indent == 2 and is_global):
            flush()
            current_text = []
            # `qmd context list` renders a collection-root context as the literal
            # "/ (root)" — normalize to empty sub_path so rebuilding the qmd_path
            # yields `qmd://<col>/` (which is what `qmd context rm` expects).
            if not is_global and (stripped == "/ (root)" or stripped.startswith("/ ")):
                current_sub = ""
            else:
                current_sub = stripped
            continue

        if indent >= 4 or current_sub is not None:
            current_text.append(stripped)

    flush()
    return entries


@dataclass
class ContextEntry:
    """A human-written context attached to a qmd path.

    `collection` is "" and `sub_path` is "/" for the global context.
    For collection-scoped entries `sub_path` is the path under the
    collection (e.g. "" for the collection root, or "qmd-gui/src").
    """
    collection: str = ""
    sub_path: str = ""
    text: str = ""

    @property
    def qmd_path(self) -> str:
        if self.sub_path == "/" and not self.collection:
            return "/"
        base = f"qmd://{self.collection}/"
        if self.sub_path:
            return base + self.sub_path.lstrip("/")
        return base


QMD_INDEX_YML = os.path.expanduser("~/.config/qmd/index.yml")


def load_collection_abs_paths(index_path: str = QMD_INDEX_YML) -> dict[str, str]:
    """Read ~/.config/qmd/index.yml and return {collection_name: absolute_path}.

    Hand-parsed to avoid a PyYAML dependency. The file's structure is shallow:
        collections:
          <name>:
            path: <absolute path>
            pattern: "..."
    """
    result: dict[str, str] = {}
    if not os.path.isfile(index_path):
        return result
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return result

    in_collections = False
    current_name: Optional[str] = None
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            in_collections = stripped.rstrip(":") == "collections"
            current_name = None
            continue
        if not in_collections:
            continue
        if indent == 2 and stripped.endswith(":"):
            current_name = stripped[:-1].strip()
        elif indent >= 4 and current_name and stripped.startswith("path:"):
            value = stripped[len("path:"):].strip().strip('"').strip("'")
            if value:
                result[current_name] = os.path.expanduser(value)
    return result


# ──────────────────────────────────────────────
#  Backend: CLI (subprocess)
# ──────────────────────────────────────────────


class CLIBackend:
    """QMD backend using subprocess calls."""

    def search(
        self,
        query: str,
        mode: str = "search",
        collection: str = "",
        limit: int = 20,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        cmd = ["qmd", mode, "--json", "-n", str(limit)]
        if min_score > 0:
            cmd += ["--min-score", str(min_score)]
        if collection:
            cmd += ["-c", collection]
        cmd.append(query)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"qmd error: {result.stderr.strip()}")

        data = json.loads(result.stdout)
        return self._parse_results(data)

    def get_document(self, path_or_id: str, full: bool = True) -> str:
        cmd = ["qmd", "get", path_or_id]
        if full:
            cmd.append("--full")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"qmd get error: {result.stderr.strip()}")
        return result.stdout

    def get_collections(self) -> list[CollectionInfo]:
        result = subprocess.run(
            ["qmd", "collection", "list"], capture_output=True, text=True, timeout=10
        )
        collections = []
        if result.returncode != 0:
            return collections

        current = None
        for line in result.stdout.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            # 헤더 라인: "Collections (4):" 건너뛰기
            if stripped.startswith("Collections"):
                continue

            # 컬렉션 이름 라인: "research (qmd://research/)"
            # 들여쓰기가 없는 라인 = 새 컬렉션
            if not line.startswith(" ") and not line.startswith("\t"):
                # "research (qmd://research/)" 에서 이름 추출
                name = stripped.split("(")[0].strip()
                # qmd:// URL에서 경로 추출 시도
                path = ""
                if "qmd://" in stripped:
                    start = stripped.index("qmd://")
                    end = (
                        stripped.index(")", start)
                        if ")" in stripped[start:]
                        else len(stripped)
                    )
                    path = stripped[start:end]
                current = CollectionInfo(name=name, path=path)
                collections.append(current)
                continue

            # 상세 라인 (들여쓰기 있음): "  Pattern:  **/*.md"
            if current and ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip().lower()
                value = value.strip()
                if key == "pattern":
                    current.glob_pattern = value
                elif key == "files":
                    try:
                        current.doc_count = int(value)
                    except ValueError:
                        pass

        return collections

    def get_status(self) -> str:
        result = subprocess.run(
            ["qmd", "status"], capture_output=True, text=True, timeout=10
        )
        return result.stdout if result.returncode == 0 else result.stderr

    def add_collection(self, path: str, name: str, mask: str = "") -> str:
        cmd = ["qmd", "collection", "add", path, "--name", name]
        if mask:
            cmd += ["--mask", mask]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def remove_collection(self, name: str) -> str:
        result = subprocess.run(
            ["qmd", "collection", "remove", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def rename_collection(self, old_name: str, new_name: str) -> str:
        result = subprocess.run(
            ["qmd", "collection", "rename", old_name, new_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def update_index(self, collection: str = "") -> str:
        cmd = ["qmd", "update"]
        if collection:
            cmd += ["--collection", collection]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def embed(self, force: bool = False) -> str:
        cmd = ["qmd", "embed"]
        if force:
            cmd.append("-f")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def list_files(self, collection: str) -> str:
        result = subprocess.run(
            ["qmd", "ls", collection], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def list_contexts(self) -> list[ContextEntry]:
        result = subprocess.run(
            ["qmd", "context", "list"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return _parse_context_list(result.stdout, set(load_collection_abs_paths().keys()))

    def add_context(self, qmd_path: str, text: str) -> str:
        result = subprocess.run(
            ["qmd", "context", "add", qmd_path, text],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def remove_context(self, qmd_path: str) -> str:
        result = subprocess.run(
            ["qmd", "context", "rm", qmd_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def _parse_results(self, data) -> list[SearchResult]:
        results = []
        items = data if isinstance(data, list) else data.get("results", [])
        for item in items:
            docid = item.get("docid", "")
            path = (
                item.get("path", "")
                or item.get("displayPath", "")
                or item.get("file", "")
            )
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    path=path,
                    docid=docid,
                    score=item.get("score", 0.0),
                    snippet=item.get("snippet", ""),
                    context=item.get("context", ""),
                    collection=item.get("collection", ""),
                )
            )
        return results


# ──────────────────────────────────────────────
#  Backend: MCP HTTP (JSON-RPC)
# ──────────────────────────────────────────────


class MCPBackend:
    """QMD backend using MCP Streamable HTTP (JSON-RPC 2.0)."""

    def __init__(self, host: str = "localhost", port: int = 8181):
        self.base_url = f"http://{host}:{port}"
        self.mcp_url = f"{self.base_url}/mcp"
        self._request_id = 0
        self._initialized = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _call(self, method: str, params: Optional[dict] = None) -> dict:
        if not self._initialized and method != "initialize":
            self._initialize()
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        resp = requests.post(
            self.mcp_url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=120,
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"MCP error: {body['error']}")
        return body.get("result", {})

    def _initialize(self):
        self._call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "qmd-gui", "version": "1.0.0"},
            },
        )
        requests.post(
            self.mcp_url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        self._initialized = True

    def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        result = self._call("tools/call", {"name": tool_name, "arguments": arguments})
        contents = result.get("content", [])
        for c in contents:
            if c.get("type") == "text":
                try:
                    return json.loads(c["text"])
                except (json.JSONDecodeError, KeyError):
                    return {"text": c.get("text", "")}
        return result

    def search(
        self,
        query: str,
        mode: str = "search",
        collection: str = "",
        limit: int = 20,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        arguments = {"query": query, "limit": limit}
        if collection:
            arguments["collection"] = collection
        if mode == "query":
            data = self._call_tool("query", arguments)
        else:
            query_type = "lex" if mode == "search" else "vec"
            arguments["queries"] = [{"type": query_type, "query": query}]
            arguments.pop("query", None)
            data = self._call_tool("query", arguments)
        return self._parse_results(data)

    def get_document(self, path_or_id: str, full: bool = True) -> str:
        data = self._call_tool("get", {"path": path_or_id})
        if isinstance(data, dict):
            if "text" in data:
                return data["text"]
            return data.get("body", data.get("content", json.dumps(data, indent=2)))
        return str(data)

    def get_collections(self) -> list[CollectionInfo]:
        data = self._call_tool("status", {})
        collections = []
        if isinstance(data, dict):
            for col in data.get("collections", []):
                collections.append(
                    CollectionInfo(
                        name=col.get("name", ""),
                        path=col.get("path", col.get("pwd", "")),
                        doc_count=col.get("doc_count", col.get("documents", 0)),
                    )
                )
        return collections

    def get_status(self) -> str:
        data = self._call_tool("status", {})
        return (
            json.dumps(data, indent=2, ensure_ascii=False)
            if isinstance(data, dict)
            else str(data)
        )

    # MCP doesn't expose collection management tools, fall back to CLI
    def add_collection(self, path: str, name: str, mask: str = "") -> str:
        return CLIBackend().add_collection(path, name, mask)

    def remove_collection(self, name: str) -> str:
        return CLIBackend().remove_collection(name)

    def rename_collection(self, old_name: str, new_name: str) -> str:
        return CLIBackend().rename_collection(old_name, new_name)

    def update_index(self, collection: str = "") -> str:
        return CLIBackend().update_index(collection)

    def embed(self, force: bool = False) -> str:
        return CLIBackend().embed(force)

    def list_files(self, collection: str) -> str:
        return CLIBackend().list_files(collection)

    def list_contexts(self) -> list[ContextEntry]:
        return CLIBackend().list_contexts()

    def add_context(self, qmd_path: str, text: str) -> str:
        return CLIBackend().add_context(qmd_path, text)

    def remove_context(self, qmd_path: str) -> str:
        return CLIBackend().remove_context(qmd_path)

    def is_healthy(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def _parse_results(self, data) -> list[SearchResult]:
        results = []
        items = (
            data
            if isinstance(data, list)
            else data.get("results", data.get("documents", []))
        )
        if not isinstance(items, list):
            return results
        for item in items:
            docid = item.get("docid", "")
            path = (
                item.get("path", "")
                or item.get("displayPath", "")
                or item.get("file", "")
            )
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    path=path,
                    docid=docid,
                    score=item.get("score", 0.0),
                    snippet=item.get("snippet", ""),
                    context=item.get("context", ""),
                    collection=item.get("collection", ""),
                )
            )
        return results


# ──────────────────────────────────────────────
#  Worker Threads
# ──────────────────────────────────────────────


class SearchWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, backend, query, mode, collection, limit, min_score):
        super().__init__()
        self.backend = backend
        self.query = query
        self.mode = mode
        self.collection = collection
        self.limit = limit
        self.min_score = min_score

    def run(self):
        try:
            results = self.backend.search(
                self.query,
                self.mode,
                self.collection,
                self.limit,
                self.min_score,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class DocWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, backend, path_or_id):
        super().__init__()
        self.backend = backend
        self.path_or_id = path_or_id

    def run(self):
        try:
            content = self.backend.get_document(self.path_or_id)
            self.finished.emit(content)
        except Exception as e:
            self.error.emit(str(e))


class CollectionWorker(QThread):
    """Generic worker for collection operations."""

    finished = Signal(str)
    error = Signal(str)

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        try:
            result = self.func(*self.args)
            self.finished.emit(str(result))
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────
#  Dialogs
# ──────────────────────────────────────────────


class AddCollectionDialog(QDialog):
    """Dialog to add a new collection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Collection")
        self.setMinimumWidth(500)

        layout = QFormLayout(self)

        # Name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. notes, docs, meetings")
        layout.addRow("Name:", self.name_input)

        # Path
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("/path/to/your/markdown/files")
        path_layout.addWidget(self.path_input)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self.browse_btn)
        layout.addRow("Path:", path_layout)

        # Glob mask
        self.mask_input = QLineEdit()
        self.mask_input.setPlaceholderText("**/*.md (default)")
        layout.addRow("Glob Mask:", self.mask_input)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.path_input.setText(folder)
            # Auto-fill name from folder name if empty
            if not self.name_input.text():
                self.name_input.setText(os.path.basename(folder))

    def _validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        if not self.path_input.text().strip():
            QMessageBox.warning(self, "Validation", "Path is required.")
            return
        if not os.path.isdir(self.path_input.text().strip()):
            QMessageBox.warning(self, "Validation", "Path does not exist.")
            return
        self.accept()

    def get_values(self) -> tuple[str, str, str]:
        return (
            self.path_input.text().strip(),
            self.name_input.text().strip(),
            self.mask_input.text().strip(),
        )


class RenameCollectionDialog(QDialog):
    """Dialog to rename a collection."""

    def __init__(self, old_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rename Collection: {old_name}")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.old_name_label = QLabel(old_name)
        self.old_name_label.setFont(QFont(MONO_FONT, 11))
        layout.addRow("Current Name:", self.old_name_label)

        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("New name...")
        self.new_name_input.setText(old_name)
        self.new_name_input.selectAll()
        layout.addRow("New Name:", self.new_name_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _validate_and_accept(self):
        if not self.new_name_input.text().strip():
            QMessageBox.warning(self, "Validation", "New name is required.")
            return
        self.accept()

    def get_new_name(self) -> str:
        return self.new_name_input.text().strip()


class AddContextDialog(QDialog):
    """Dialog to add a context attached to a qmd path."""

    SCOPE_COLLECTION = "Collection root"
    SCOPE_SUBPATH = "Sub-path"
    SCOPE_GLOBAL = "Global (all collections)"

    def __init__(self, collection_name: str, subpaths: Optional[list[str]] = None, parent=None):
        super().__init__(parent)
        self.collection_name = collection_name
        self.setWindowTitle(f"Add Context — {collection_name or 'global'}")
        self.setMinimumWidth(520)

        layout = QFormLayout(self)

        self.scope_combo = QComboBox()
        self.scope_combo.addItems(
            [self.SCOPE_COLLECTION, self.SCOPE_SUBPATH, self.SCOPE_GLOBAL]
        )
        self.scope_combo.currentTextChanged.connect(self._on_scope_changed)
        layout.addRow("Scope:", self.scope_combo)

        self.sub_path_combo = QComboBox()
        self.sub_path_combo.setEditable(True)
        self.sub_path_combo.lineEdit().setPlaceholderText(
            "Pick or type a sub-path (e.g. subfolder, subfolder/file.md)"
        )
        if subpaths:
            self.sub_path_combo.addItem("")  # empty default so nothing is pre-selected
            self.sub_path_combo.addItems(subpaths)
            self.sub_path_combo.setCurrentIndex(0)
        self.sub_path_combo.setEnabled(False)
        layout.addRow("Sub-path:", self.sub_path_combo)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Context text (human-written summary)...")
        self.text_input.setMinimumHeight(120)
        layout.addRow("Context:", self.text_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_scope_changed(self, scope: str):
        self.sub_path_combo.setEnabled(scope == self.SCOPE_SUBPATH)
        if scope != self.SCOPE_SUBPATH:
            self.sub_path_combo.setCurrentIndex(0) if self.sub_path_combo.count() else None
            self.sub_path_combo.setEditText("")

    def _validate_and_accept(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Validation", "Context text is required.")
            return
        if self.scope_combo.currentText() == self.SCOPE_SUBPATH:
            if not self.sub_path_combo.currentText().strip():
                QMessageBox.warning(
                    self, "Validation", "Sub-path is required for this scope."
                )
                return
        self.accept()

    def get_values(self) -> tuple[str, str]:
        """Return (qmd_path, text) ready for `qmd context add`."""
        scope = self.scope_combo.currentText()
        text = self.text_input.toPlainText().strip()
        if scope == self.SCOPE_GLOBAL:
            return "/", text
        if scope == self.SCOPE_SUBPATH:
            sub = self.sub_path_combo.currentText().strip().lstrip("/")
            return f"qmd://{self.collection_name}/{sub}", text
        return f"qmd://{self.collection_name}/", text


# ──────────────────────────────────────────────
#  Collection Management Panel
# ──────────────────────────────────────────────


class CollectionPanel(QWidget):
    """Panel for managing QMD collections."""

    collections_changed = Signal()

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.collections: list[CollectionInfo] = []
        self.abs_paths: dict[str, str] = {}
        self.contexts: list[ContextEntry] = []
        self.collection_subpaths: list[str] = []
        self.worker: Optional[CollectionWorker] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Toolbar ──
        toolbar_layout = QHBoxLayout()

        self.add_btn = QPushButton("+ Add")
        self.add_btn.clicked.connect(self._add_collection)
        toolbar_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("- Remove")
        self.remove_btn.clicked.connect(self._remove_collection)
        self.remove_btn.setEnabled(False)
        toolbar_layout.addWidget(self.remove_btn)

        self.rename_btn = QPushButton("Rename")
        self.rename_btn.clicked.connect(self._rename_collection)
        self.rename_btn.setEnabled(False)
        toolbar_layout.addWidget(self.rename_btn)

        toolbar_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_collections)
        toolbar_layout.addWidget(self.refresh_btn)

        layout.addLayout(toolbar_layout)

        # ── Upper area: Collection list (left) + File list (right) ──
        upper_splitter = QSplitter(Qt.Orientation.Horizontal)
        upper_splitter.setHandleWidth(0)

        # Left: Collection list in QTabWidget
        self.collection_tabs = QTabWidget()
        self.collection_tabs.setObjectName("collectionTabs")

        collection_widget = QWidget()
        collection_layout = QVBoxLayout(collection_widget)
        collection_layout.setContentsMargins(0, 0, 0, 0)
        collection_layout.setSpacing(0)

        self.collection_list = QListWidget()
        self.collection_list.setFont(QFont(MONO_FONT, 11))
        self.collection_list.setObjectName("collectionList")
        self.collection_list.currentRowChanged.connect(self._on_selection_changed)
        collection_layout.addWidget(self.collection_list)

        self.collection_tabs.addTab(collection_widget, "Collections")
        upper_splitter.addWidget(self.collection_tabs)

        # Right: File list in QTabWidget
        self.files_tabs = QTabWidget()
        self.files_tabs.setObjectName("filesTabs")

        files_widget = QWidget()
        files_layout = QVBoxLayout(files_widget)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(0)

        self.file_path_label = QLabel("")
        self.file_path_label.setObjectName("filePathLabel")
        self.file_path_label.setFont(QFont(MONO_FONT, 10))
        self.file_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.file_path_label.setContentsMargins(8, 6, 8, 6)
        self.file_path_label.setVisible(False)
        files_layout.addWidget(self.file_path_label)

        self.file_list = QListWidget()
        self.file_list.setFont(QFont(MONO_FONT, 10))
        self.file_list.setObjectName("fileList")
        files_layout.addWidget(self.file_list)

        self.files_tabs.addTab(files_widget, "Files")

        # ── Contexts tab ──
        contexts_widget = QWidget()
        contexts_layout = QVBoxLayout(contexts_widget)
        contexts_layout.setContentsMargins(0, 0, 0, 0)
        contexts_layout.setSpacing(0)

        self.context_list = QListWidget()
        self.context_list.setFont(QFont(MONO_FONT, 10))
        self.context_list.setObjectName("contextList")
        self.context_list.setWordWrap(True)
        contexts_layout.addWidget(self.context_list)

        ctx_btn_row = QHBoxLayout()
        ctx_btn_row.setContentsMargins(6, 4, 6, 4)
        self.add_context_btn = QPushButton("+ Add Context")
        self.add_context_btn.clicked.connect(self._add_context)
        self.add_context_btn.setEnabled(False)
        ctx_btn_row.addWidget(self.add_context_btn)

        self.remove_context_btn = QPushButton("- Remove Context")
        self.remove_context_btn.clicked.connect(self._remove_context)
        self.remove_context_btn.setEnabled(False)
        ctx_btn_row.addWidget(self.remove_context_btn)

        ctx_btn_row.addStretch()

        self.refresh_contexts_btn = QPushButton("Refresh")
        self.refresh_contexts_btn.clicked.connect(self._refresh_contexts)
        ctx_btn_row.addWidget(self.refresh_contexts_btn)

        contexts_layout.addLayout(ctx_btn_row)

        self.context_list.currentRowChanged.connect(self._on_context_selection_changed)

        self.files_tabs.addTab(contexts_widget, "Contexts")
        upper_splitter.addWidget(self.files_tabs)

        upper_splitter.setSizes([300, 500])

        # ── Lower area: Collection detail info ──
        self.detail_view = QTextEdit()
        self.detail_view.setObjectName("detailView")
        self.detail_view.setReadOnly(True)
        self.detail_view.setFont(QFont(MONO_FONT, 10))
        self.detail_view.setMaximumHeight(120)

        # ── Combine upper + lower with vertical splitter ──
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setHandleWidth(0)
        main_splitter.addWidget(upper_splitter)
        main_splitter.addWidget(self.detail_view)
        main_splitter.setSizes([400, 120])

        layout.addWidget(main_splitter, stretch=1)

        # ── Index actions ──
        index_layout = QHBoxLayout()

        self.update_btn = QPushButton("Update Index")
        self.update_btn.setToolTip("Re-index selected collection (or all)")
        self.update_btn.clicked.connect(self._update_index)
        index_layout.addWidget(self.update_btn)

        self.embed_btn = QPushButton("Generate Embeddings")
        self.embed_btn.setToolTip("Generate vector embeddings for semantic search")
        self.embed_btn.clicked.connect(self._embed)
        index_layout.addWidget(self.embed_btn)

        self.force_embed_check = QCheckBox("Force re-embed")
        self.force_embed_check.setToolTip("Re-embed all documents, even unchanged ones")
        index_layout.addWidget(self.force_embed_check)

        index_layout.addStretch()
        layout.addLayout(index_layout)

        # ── Progress ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

    def _on_selection_changed(self, row: int):
        has_selection = row >= 0
        self.remove_btn.setEnabled(has_selection)
        self.rename_btn.setEnabled(has_selection)

        if has_selection and row < len(self.collections):
            col = self.collections[row]
            abs_path = self.abs_paths.get(col.name, "")

            details = [
                f"Name:       {col.name}",
                f"Path:       {abs_path or col.path}",
                f"Documents:  {col.doc_count}",
                f"Pattern:    {col.glob_pattern or '**/*.md'}",
            ]
            self.detail_view.setPlainText("\n".join(details))

            display_path = abs_path or col.path
            self.file_path_label.setText(display_path)
            self.file_path_label.setToolTip(display_path)
            self.file_path_label.setVisible(bool(display_path))

            self.files_tabs.setTabText(0, f"Files — {col.name}")
            self.file_list.clear()
            self.file_list.addItem("Loading...")
            self._file_worker = CollectionWorker(self.backend.list_files, col.name)
            self._file_worker.finished.connect(self._on_files_loaded)
            self._file_worker.error.connect(self._on_files_error)
            self._file_worker.start()

            self._render_contexts()
        else:
            self.detail_view.clear()
            self.file_list.clear()
            self.file_path_label.clear()
            self.file_path_label.setVisible(False)
            self.files_tabs.setTabText(0, "Files")
            self._render_contexts()

    def _on_files_loaded(self, output: str):
        self.file_list.clear()
        name = self._get_selected_name() or ""
        prefix = f"qmd://{name}/"
        subpaths: set[str] = set()
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            self.file_list.addItem(line)
            # Extract everything after `qmd://<collection>/` if present
            idx = line.find(prefix)
            if name and idx != -1:
                sub = line[idx + len(prefix):].strip()
                if sub:
                    subpaths.add(sub)
                    parent = "/".join(sub.split("/")[:-1])
                    while parent:
                        subpaths.add(parent)
                        parent = "/".join(parent.split("/")[:-1])
        self.collection_subpaths = sorted(subpaths)
        count = self.file_list.count()
        self.files_tabs.setTabText(0, f"Files — {name} ({count})")

    def _on_files_error(self, msg: str):
        self.file_list.clear()
        self.file_list.addItem(f"(Error: {msg})")

    def refresh_collections(self):
        self.collection_list.clear()
        self.collection_list.addItem("Loading...")
        self.detail_view.clear()
        self.file_list.clear()
        self.file_path_label.clear()
        self.file_path_label.setVisible(False)
        self.files_tabs.setTabText(0, "Files")
        self.remove_btn.setEnabled(False)
        self.rename_btn.setEnabled(False)

        self._refresh_worker = AsyncWorker(self.backend.get_collections)
        self._refresh_worker.finished.connect(self._on_refresh_done)
        self._refresh_worker.error.connect(self._on_refresh_error)
        self._refresh_worker.start()

        self._refresh_contexts()

    def _on_refresh_done(self, collections):
        self.collections = collections
        self.abs_paths = load_collection_abs_paths()
        self.collection_list.clear()
        for col in self.collections:
            doc_info = f" ({col.doc_count} docs)" if col.doc_count else ""
            self.collection_list.addItem(f"{col.name}{doc_info}")

    # ── Contexts ───────────────────────────────────────────────

    def _refresh_contexts(self):
        self.context_list.clear()
        self.context_list.addItem("Loading...")
        self.add_context_btn.setEnabled(False)
        self.remove_context_btn.setEnabled(False)
        self._ctx_worker = AsyncWorker(self.backend.list_contexts)
        self._ctx_worker.finished.connect(self._on_contexts_loaded)
        self._ctx_worker.error.connect(self._on_contexts_error)
        self._ctx_worker.start()

    def _on_contexts_loaded(self, entries):
        self.contexts = entries or []
        self._render_contexts()

    def _on_contexts_error(self, msg: str):
        self.contexts = []
        self.context_list.clear()
        self.context_list.addItem(f"(Error: {msg})")
        self.add_context_btn.setEnabled(True)

    def _render_contexts(self):
        self.context_list.clear()
        selected = self._get_selected_name()
        self.add_context_btn.setEnabled(True)
        self.remove_context_btn.setEnabled(False)

        visible: list[ContextEntry] = []
        for e in self.contexts:
            if not e.collection:  # global
                visible.append(e)
            elif selected and e.collection == selected:
                visible.append(e)

        if not visible:
            placeholder = (
                "(No contexts for this collection)"
                if selected
                else "(Select a collection to see its contexts; global contexts also appear here)"
            )
            self.context_list.addItem(placeholder)
            item = self.context_list.item(0)
            if item:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        else:
            for e in visible:
                scope_tag = "[global]" if not e.collection else (e.sub_path or "/")
                first_line = e.text.splitlines()[0] if e.text else ""
                label = f"{scope_tag:30s}  {first_line}"
                item = QListWidgetItem(label)
                item.setToolTip(e.text or "")
                item.setData(Qt.ItemDataRole.UserRole, e)
                self.context_list.addItem(item)

        self.files_tabs.setTabText(1, f"Contexts ({len(visible)})")

    def _on_context_selection_changed(self, row: int):
        item = self.context_list.item(row) if row >= 0 else None
        has_entry = bool(item and item.data(Qt.ItemDataRole.UserRole))
        self.remove_context_btn.setEnabled(has_entry)

    def _add_context(self):
        selected = self._get_selected_name() or ""
        dialog = AddContextDialog(selected, self.collection_subpaths, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        qmd_path, text = dialog.get_values()
        self._set_busy(True, f"Adding context for '{qmd_path}'...")
        self._ctx_op = CollectionWorker(self.backend.add_context, qmd_path, text)
        self._ctx_op.finished.connect(self._on_context_op_done)
        self._ctx_op.error.connect(self._on_context_op_error)
        self._ctx_op.start()

    def _remove_context(self):
        row = self.context_list.currentRow()
        item = self.context_list.item(row) if row >= 0 else None
        entry = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(entry, ContextEntry):
            return
        reply = QMessageBox.question(
            self,
            "Remove Context",
            f"Remove context for:\n  {entry.qmd_path}\n\n"
            "The context text will be deleted (your files are not affected).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True, f"Removing context '{entry.qmd_path}'...")
        self._ctx_op = CollectionWorker(self.backend.remove_context, entry.qmd_path)
        self._ctx_op.finished.connect(self._on_context_op_done)
        self._ctx_op.error.connect(self._on_context_op_error)
        self._ctx_op.start()

    def _on_context_op_done(self, message: str):
        self._set_busy(False)
        self._refresh_contexts()
        if message:
            self.detail_view.setPlainText(message)

    def _on_context_op_error(self, message: str):
        self._set_busy(False)
        QMessageBox.warning(self, "Error", message)

    def _on_refresh_error(self, msg: str):
        self.collection_list.clear()
        QMessageBox.warning(self, "Error", f"Failed to load collections:\n{msg}")

    def _get_selected_name(self) -> Optional[str]:
        row = self.collection_list.currentRow()
        if row < 0 or row >= len(self.collections):
            return None
        return self.collections[row].name

    def _set_busy(self, busy: bool, message: str = ""):
        self.progress_bar.setVisible(busy)
        self.progress_label.setVisible(busy)
        self.progress_label.setText(message)
        self.add_btn.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy and self.collection_list.currentRow() >= 0)
        self.rename_btn.setEnabled(not busy and self.collection_list.currentRow() >= 0)
        self.update_btn.setEnabled(not busy)
        self.embed_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)

        if busy:
            # 기본은 indeterminate, embed에서는 별도로 range 설정
            self.progress_bar.setRange(0, 0)

    def _on_worker_finished(self, message: str):
        self._set_busy(False)
        self.refresh_collections()
        self.collections_changed.emit()
        if message:
            self.detail_view.setPlainText(message)

    def _on_worker_error(self, message: str):
        self._set_busy(False)
        QMessageBox.warning(self, "Error", message)

    def _run_worker(self, func, *args, busy_message="Working..."):
        self._set_busy(True, busy_message)
        self.worker = CollectionWorker(func, *args)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.start()

    def _add_collection(self):
        dialog = AddCollectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            path, name, mask = dialog.get_values()
            self._run_worker(
                self.backend.add_collection,
                path,
                name,
                mask,
                busy_message=f"Adding collection '{name}'...",
            )

    def _remove_collection(self):
        name = self._get_selected_name()
        if not name:
            return
        reply = QMessageBox.question(
            self,
            "Remove Collection",
            f"Are you sure you want to remove collection '{name}'?\n\n"
            "This removes the index only. Your files will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_worker(
                self.backend.remove_collection,
                name,
                busy_message=f"Removing '{name}'...",
            )

    def _rename_collection(self):
        old_name = self._get_selected_name()
        if not old_name:
            return
        dialog = RenameCollectionDialog(old_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = dialog.get_new_name()
            if new_name != old_name:
                self._run_worker(
                    self.backend.rename_collection,
                    old_name,
                    new_name,
                    busy_message=f"Renaming '{old_name}' → '{new_name}'...",
                )

    def _update_index(self):
        name = self._get_selected_name() or ""
        label = f"'{name}'" if name else "all collections"
        self._run_worker(
            self.backend.update_index,
            name,
            busy_message=f"Updating index for {label}...",
        )

    def _embed(self):
        force = self.force_embed_check.isChecked()

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Starting embedding...")

        self.add_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.rename_btn.setEnabled(False)
        self.update_btn.setEnabled(False)
        self.embed_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)

        self._embed_worker = EmbedWorker(force=force)
        self._embed_worker.progress.connect(self._on_embed_progress)
        self._embed_worker.log.connect(self._on_embed_log)
        self._embed_worker.finished.connect(self._on_embed_finished)
        self._embed_worker.error.connect(self._on_embed_error)
        self._embed_worker.start()

    def _on_embed_progress(self, pct: int):
        self.progress_bar.setValue(pct)
        self.progress_label.setText(f"Embedding... {pct}%")

    def _on_embed_log(self, line: str):
        # 로그를 detail_view에 추가
        current = self.detail_view.toPlainText()
        if current:
            self.detail_view.setPlainText(current + "\n" + line)
        else:
            self.detail_view.setPlainText(line)
        # 자동 스크롤
        scrollbar = self.detail_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_embed_finished(self, msg: str):
        self._set_busy(False)
        self.progress_bar.setValue(100)
        self.progress_label.setText(msg)
        self.refresh_collections()
        self.collections_changed.emit()
        # 3초 후 프로그레스 숨기기
        QTimer.singleShot(3000, self._hide_progress)

    def _on_embed_error(self, msg: str):
        self._set_busy(False)
        self.progress_bar.setValue(0)
        QMessageBox.warning(self, "Embedding Error", msg)
        self._hide_progress()

    def _hide_progress(self):
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(False)
        self.progress_label.setText("")


# ──────────────────────────────────────────────
#  Main Window
# ──────────────────────────────────────────────


class QMDMainWindow(QMainWindow):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.current_results: list[SearchResult] = []
        self.worker: Optional[SearchWorker] = None
        self.doc_worker: Optional[DocWorker] = None

        self.setWindowTitle("QMD GUI — Query Markup Documents")
        self.setMinimumSize(1200, 750)
        self._build_ui()
        self._load_collections()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.main_tabs = QTabWidget()

        # === Tab 1: Search ===
        search_tab = QWidget()
        search_layout = QVBoxLayout(search_tab)

        search_group = QGroupBox("Search")
        search_group_layout = QVBoxLayout(search_group)

        row1 = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter search query...")
        self.query_input.setFont(QFont(MONO_FONT, 12))
        self.query_input.returnPressed.connect(self._do_search)
        row1.addWidget(self.query_input, stretch=5)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            ["search (BM25)", "vsearch (Vector)", "query (Hybrid)"]
        )
        self.mode_combo.setCurrentIndex(2)
        row1.addWidget(self.mode_combo, stretch=1)

        self.collection_combo = QComboBox()
        self.collection_combo.addItem("All Collections", "")
        row1.addWidget(self.collection_combo, stretch=1)

        search_group_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Max results:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100)
        self.limit_spin.setValue(20)
        row2.addWidget(self.limit_spin)

        row2.addWidget(QLabel("Min score:"))
        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(0, 100)
        self.min_score_spin.setValue(0)
        self.min_score_spin.setSuffix("%")
        row2.addWidget(self.min_score_spin)

        row2.addStretch()

        self.search_btn = QPushButton("Search")
        self.search_btn.setFont(QFont(MONO_FONT, 11))
        self.search_btn.clicked.connect(self._do_search)
        row2.addWidget(self.search_btn)

        search_group_layout.addLayout(row2)
        search_layout.addWidget(search_group)

        # === Results area: two QTabWidgets in a QSplitter ===
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(0)

        # Left: Result list in QTabWidget
        self.result_tabs = QTabWidget()
        self.result_tabs.setObjectName("resultTabs")

        result_widget = QWidget()
        result_layout = QVBoxLayout(result_widget)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(0)

        self.result_list = QListWidget()
        self.result_list.setFont(QFont(MONO_FONT, 10))
        self.result_list.setObjectName("resultList")
        self.result_list.currentRowChanged.connect(self._on_result_selected)
        result_layout.addWidget(self.result_list)

        self.result_tabs.addTab(result_widget, "Results (0)")
        splitter.addWidget(self.result_tabs)

        # Right: Document views in QTabWidget
        self.doc_tabs = QTabWidget()
        self.doc_tabs.setObjectName("docTabs")

        self.snippet_view = QTextEdit()
        self.snippet_view.setReadOnly(True)
        self.snippet_view.setFont(QFont(MONO_FONT, 11))
        self.snippet_view.setObjectName("snippetView")
        self.doc_tabs.addTab(self.snippet_view, "Snippet")

        self.doc_view = QTextEdit()
        self.doc_view.setReadOnly(True)
        self.doc_view.setFont(QFont(MONO_FONT, 11))
        self.doc_view.setObjectName("docView")
        self.doc_tabs.addTab(self.doc_view, "Full Document")

        self.preview_view = QWebEngineView()
        self.preview_view.setObjectName("previewView")
        self.doc_tabs.addTab(self.preview_view, "Preview")

        self.meta_view = QTextEdit()
        self.meta_view.setReadOnly(True)
        self.meta_view.setFont(QFont(MONO_FONT, 10))
        self.meta_view.setObjectName("metaView")
        self.doc_tabs.addTab(self.meta_view, "Metadata")

        splitter.addWidget(self.doc_tabs)
        splitter.setSizes([400, 700])

        search_layout.addWidget(splitter, stretch=1)
        self.main_tabs.addTab(search_tab, "Search")

        # === Tab 2: Collections ===
        self.collection_panel = CollectionPanel(self.backend)
        self.collection_panel.collections_changed.connect(self._on_collections_changed)
        self.main_tabs.addTab(self.collection_panel, "Collections")

        # === Tab 3: Status ===
        status_tab = QWidget()
        status_layout = QVBoxLayout(status_tab)

        status_toolbar = QHBoxLayout()
        self.status_refresh_btn = QPushButton("Refresh")
        self.status_refresh_btn.clicked.connect(self._refresh_status)
        status_toolbar.addWidget(self.status_refresh_btn)
        status_toolbar.addStretch()
        status_layout.addLayout(status_toolbar)

        self.status_view = QTextEdit()
        self.status_view.setReadOnly(True)
        self.status_view.setFont(QFont(MONO_FONT, 11))
        status_layout.addWidget(self.status_view)

        self.main_tabs.addTab(status_tab, "Status")

        main_layout.addWidget(self.main_tabs)

        self.statusBar().showMessage("Ready")
        self.main_tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        if index == 1:  # Collections tab
            self.collection_panel.refresh_collections()
        elif index == 2:  # Status tab
            self._refresh_status()

    def _refresh_status(self):
        self.status_view.setPlainText("Loading...")
        self._status_loader = AsyncWorker(self.backend.get_status)
        self._status_loader.finished.connect(
            lambda text: self.status_view.setPlainText(text)
        )
        self._status_loader.error.connect(
            lambda e: self.status_view.setPlainText(f"Error loading status:\n{e}")
        )
        self._status_loader.start()

    def _on_collections_changed(self):
        """Refresh the search tab's collection dropdown."""
        self._load_collections()

    # ── Search Actions ──

    def _get_mode(self) -> str:
        modes = ["search", "vsearch", "query"]
        return modes[self.mode_combo.currentIndex()]

    def _do_search(self):
        query = self.query_input.text().strip()
        if not query:
            return

        self.search_btn.setEnabled(False)
        self.statusBar().showMessage(f"Searching: {query}...")
        self.result_list.clear()
        self.result_tabs.setTabText(0, "Results (0)")
        self.snippet_view.clear()
        self.doc_view.clear()
        self.meta_view.clear()

        mode = self._get_mode()
        collection = self.collection_combo.currentData() or ""
        limit = self.limit_spin.value()
        min_score = self.min_score_spin.value() / 100.0

        self.worker = SearchWorker(
            self.backend, query, mode, collection, limit, min_score
        )
        self.worker.finished.connect(self._on_search_done)
        self.worker.error.connect(self._on_search_error)
        self.worker.start()

    def _on_search_done(self, results: list[SearchResult]):
        self.current_results = results
        self.result_tabs.setTabText(0, f"Results ({len(results)})")
        self.search_btn.setEnabled(True)

        for r in results:
            score_pct = int(r.score * 100) if r.score <= 1.0 else int(r.score)
            display = f"[{score_pct:3d}%] {r.title or r.path}"
            if r.collection:
                display += f"  ({r.collection})"
            item = QListWidgetItem(display)

            if r.score >= 0.7:
                item.setForeground(QColor("#2ecc71"))
            elif r.score >= 0.4:
                item.setForeground(QColor("#f39c12"))
            else:
                item.setForeground(QColor("#95a5a6"))

            self.result_list.addItem(item)

        count = len(results)
        self.statusBar().showMessage(f"Found {count} result{'s' if count != 1 else ''}")

    def _on_search_error(self, msg: str):
        self.search_btn.setEnabled(True)
        self.statusBar().showMessage(f"Error: {msg}")
        QMessageBox.warning(self, "Search Error", msg)

    def _on_result_selected(self, row: int):
        if row < 0 or row >= len(self.current_results):
            return

        r = self.current_results[row]

        # Snippet
        self.snippet_view.setPlainText(r.snippet or "(no snippet)")

        # Metadata
        meta_lines = [
            f"Title:      {r.title}",
            f"Path:       {r.path}",
            f"Doc ID:     {r.docid}",
            f"Collection: {r.collection}",
            f"Context:    {r.context}",
            f"Score:      {r.score:.4f} ({int(r.score * 100)}%)",
        ]
        self.meta_view.setPlainText("\n".join(meta_lines))

        # Full document
        if r.docid:
            doc_ref = r.docid if r.docid.startswith("#") else f"#{r.docid}"
        elif r.path:
            doc_ref = r.path
        else:
            self.doc_view.setPlainText("(no path or docid available)")
            return

        self.doc_view.setPlainText("Loading...")
        self.doc_worker = DocWorker(self.backend, doc_ref)
        self.doc_worker.finished.connect(self._on_doc_loaded)
        self.doc_worker.error.connect(self._on_doc_error)
        self.doc_worker.start()

    def _on_doc_loaded(self, content: str):
        self.doc_view.setPlainText(content)
        self._render_preview(content)

    def _render_preview(self, md_text: str):
        """Convert markdown to HTML and display in preview tab."""
        extensions = [
            "markdown.extensions.fenced_code",
            "markdown.extensions.tables",
            "markdown.extensions.toc",
            "markdown.extensions.codehilite",
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
        ]
        extension_configs = {
            "markdown.extensions.codehilite": {
                "css_class": "highlight",
                "guess_lang": False,
            }
        }

        body_html = markdown.markdown(
            md_text,
            extensions=extensions,
            extension_configs=extension_configs,
        )

        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{
        background: #1e1e2e;
        color: #cdd6f4;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        font-size: 15px;
        line-height: 1.7;
        padding: 20px 32px;
        max-width: 860px;
        margin: 0 auto;
    }}
    h1 {{ color: #89b4fa; border-bottom: 1px solid #45475a; padding-bottom: 8px; }}
    h2 {{ color: #89b4fa; border-bottom: 1px solid #45475a; padding-bottom: 6px; }}
    h3 {{ color: #74c7ec; }}
    h4, h5, h6 {{ color: #94e2d5; }}
    a {{ color: #89b4fa; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
        background: #313244;
        color: #fab387;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: "{MONO_FONT}", monospace;
        font-size: 0.9em;
    }}
    pre {{
        background: #181825;
        border: 1px solid #45475a;
        border-radius: 6px;
        padding: 16px;
        overflow-x: auto;
    }}
    pre code {{
        background: none;
        color: #cdd6f4;
        padding: 0;
    }}
    blockquote {{
        border-left: 4px solid #89b4fa;
        margin: 16px 0;
        padding: 8px 16px;
        background: #181825;
        color: #a6adc8;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin: 16px 0;
    }}
    th, td {{
        border: 1px solid #45475a;
        padding: 8px 12px;
        text-align: left;
    }}
    th {{
        background: #313244;
        color: #89b4fa;
        font-weight: 600;
    }}
    tr:nth-child(even) {{
        background: #181825;
    }}
    hr {{
        border: none;
        border-top: 1px solid #45475a;
        margin: 24px 0;
    }}
    ul, ol {{
        padding-left: 24px;
    }}
    li {{
        margin: 4px 0;
    }}
    img {{
        max-width: 100%;
        border-radius: 6px;
    }}
    .highlight {{
        background: #181825;
        border-radius: 6px;
        padding: 16px;
    }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

        self.preview_view.setHtml(full_html)

    def _on_doc_error(self, msg: str):
        self.doc_view.setPlainText(f"Error loading document:\n{msg}")

    def _load_collections(self):
        self.collection_combo.clear()
        self.collection_combo.addItem("All Collections", "")
        self._col_loader = AsyncWorker(self.backend.get_collections)
        self._col_loader.finished.connect(self._on_collections_loaded)
        self._col_loader.error.connect(
            lambda e: self.statusBar().showMessage(f"Could not load collections: {e}")
        )
        self._col_loader.start()

    def _on_collections_loaded(self, collections):
        for col in collections:
            label = col.name
            if col.doc_count:
                label += f" ({col.doc_count} docs)"
            self.collection_combo.addItem(label, col.name)

    def _show_status(self):
        try:
            status_text = self.backend.get_status()
            self.doc_tabs.setCurrentIndex(2)
            self.meta_view.setPlainText(status_text)
            self.statusBar().showMessage("Status loaded")
        except Exception as e:
            QMessageBox.warning(self, "Status Error", str(e))


# ──────────────────────────────────────────────
#  Async Worker (for generic tasks)
# ──────────────────────────────────────────────


class AsyncWorker(QThread):
    """Generic async worker that passes result as object."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        try:
            result = self.func(*self.args)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────
#  Embed Worker (for running qmd embed with progress parsing)
# ──────────────────────────────────────────────


class EmbedWorker(QThread):
    """Worker that runs embed_runner.py and reads JSON progress lines."""

    progress = Signal(int)
    detail = Signal(str)
    log = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, force: bool = False):
        super().__init__()
        self.force = force

    def run(self):
        try:
            # embed_runner.py 경로 (qmd_gui.py와 같은 디렉토리)
            runner_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "embed_runner.py"
            )

            cmd = [sys.executable, runner_path]
            if self.force:
                cmd.append("--force")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if process.stdout is None:
                self.error.emit("Failed to capture stdout")
                return

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                if msg_type == "progress":
                    self.progress.emit(msg["pct"])
                    if msg.get("detail"):
                        self.detail.emit(msg["detail"])
                elif msg_type == "log":
                    self.log.emit(msg["text"])
                elif msg_type == "done":
                    if msg["exit_code"] != 0:
                        self.error.emit(
                            f"qmd embed exited with code {msg['exit_code']}"
                        )
                        return

            process.wait()
            self.progress.emit(100)
            self.finished.emit("Embedding complete!")

        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────
#  Entry Point
# ──────────────────────────────────────────────


def main():
    os.environ["QT_MAC_WANTS_LAYER"] = "1"
    os.environ["QT_LOGGING_RULES"] = "*.debug=false"

    parser = argparse.ArgumentParser(description="QMD GUI")
    parser.add_argument("--mcp", action="store_true", help="Use MCP HTTP backend")
    parser.add_argument("--host", default="localhost", help="MCP server host")
    parser.add_argument("--port", type=int, default=8181, help="MCP server port")
    args = parser.parse_args()

    if args.mcp:
        backend = MCPBackend(host=args.host, port=args.port)
        if not backend.is_healthy():
            print(f"⚠ MCP server not reachable at {args.host}:{args.port}")
            print("  Start it with: qmd mcp --http")
            print("  Falling back to CLI mode.")
            backend = CLIBackend()
    else:
        backend = CLIBackend()

    app = QApplication(sys.argv)

    style_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.qss")
    with open(style_path, "r") as f:
        app.setStyleSheet(f.read())

    window = QMDMainWindow(backend)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
