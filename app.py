from __future__ import annotations
import os
import sys
import io
from pathlib import Path
import fnmatch

from textual.app import App, ComposeResult, Binding
from textual.widgets import Header, Footer, Tree, Static, Button, Label
from textual.containers import Center, Vertical, Horizontal
from textual.screen import ModalScreen
from rich.text import Text

# ----------------- Configuration (overridable via ENV) -----------------

ROOT = Path(os.environ.get("ROOT_DIR", ".")).resolve()
OUTPUT_FILE = os.environ.get("OUTPUT", "FILETREE.md")
# Comma-separated glob patterns (match path segments, e.g., "node_modules")
DEFAULT_EXCLUDES = [".git", "node_modules", "__pycache__", ".venv", ".mypy_cache"]
EXCLUDES = [s.strip() for s in os.environ.get("EXCLUDES", ",".join(DEFAULT_EXCLUDES)).split(",") if s.strip()]
INCLUDE_HIDDEN = os.environ.get("INCLUDE_HIDDEN", "1") not in ("0", "false", "False")
MAX_BYTES = int(os.environ.get("MAX_BYTES", "300000"))  # per file
READ_BINARY = os.environ.get("READ_BINARY", "0") in ("1", "true", "True")  # normally no

# Selection style (variant 10): radio button + color
SELECT_COLOR = os.environ.get("SELECT_COLOR", "green").strip().lower()
UNSELECT_COLOR = os.environ.get("UNSELECT_COLOR", "grey50").strip().lower()
# If you want different symbols instead of radio buttons for testing, swap them here
ICON_SELECTED = os.environ.get("ICON_SELECTED", "◉")
ICON_UNSELECTED = os.environ.get("ICON_UNSELECTED", "◯")

# Read .filetreeignore (optional extra patterns; one per line)
ignore_file = ROOT / ".filetreeignore"
if ignore_file.is_file():
    with open(ignore_file, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                EXCLUDES.append(line)

# ----------------- Helper functions -----------------

def path_matches_excludes(path: Path) -> bool:
    # check each path segment against all patterns
    parts = path.relative_to(ROOT).parts if path != ROOT else ()
    for i in range(len(parts)+1):
        sub = Path(*parts[:i])
        # match against the last segment and the full relative subpath
        segs = list(parts[:i])[-1:]  # last segment
        candidates = set()
        if segs:
            candidates.add(segs[0])
        rel_posix = str(sub).replace("\\", "/")
        if rel_posix:
            candidates.add(rel_posix)
        for pat in EXCLUDES:
            if any(fnmatch.fnmatchcase(c, pat) for c in candidates if c):
                return True
    return False

def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts if part not in (".",))

def detect_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    # Heuristic: lots of “non-text”
    text_chars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)))
    nontext = sample.translate(None, text_chars)
    return bool(len(nontext) > len(sample) * 0.30)

EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".json": "json", ".yml": "yaml", ".yaml": "yaml",
    ".toml": "toml", ".ini": "ini", ".sh": "bash",
    ".md": "markdown", ".html": "html", ".css": "css",
    ".go": "go", ".rs": "rust", ".java": "java",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php",
}

def code_lang_for(path: Path) -> str:
    return EXT_LANG.get(path.suffix.lower(), "")

# ----------------- TUI data objects -----------------

class NodeData:
    __slots__ = ("path", "selected", "is_dir")
    def __init__(self, path: Path, selected: bool = True):
        self.path = path
        self.selected = selected
        self.is_dir = path.is_dir()

# ----------------- Label renderer: variant 10 (radio + color) -----------------

def _radio_icon(selected: bool) -> str:
    return ICON_SELECTED if selected else ICON_UNSELECTED

def checkbox_label(selected: bool, path: Path) -> Text:
    """Create a colored radio-label as a Rich Text renderable."""
    icon = _radio_icon(selected)
    t = Text()
    if selected:
        t.append(icon, style=f"bold {SELECT_COLOR}")
        t.append(" ")
        t.append(path.name, style=f"bold {SELECT_COLOR}")
    else:
        t.append(icon, style=f"{UNSELECT_COLOR}")
        t.append(" ")
        t.append(path.name, style=f"{UNSELECT_COLOR}")
    return t

# ----------------- Confirmation dialog -----------------

class IncludeDialog(ModalScreen[bool | None]):
    def compose(self) -> ComposeResult:
        # Center one child in both axes
        with Center():
            # Reuse the same frame layout/IDs as the main screen
            with Vertical(id="frame"):
                yield Static(
                    "Should unselected files/folders be visible in the file tree (above)?",
                    id="question",
                )
                with Horizontal(id="buttons"):
                    yield Button("Yes", id="yes", classes="choice")
                    yield Button("No", id="no", classes="choice")
                    yield Button("Cancel", id="cancel", classes="choice")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(True)
        elif event.button.id == "no":
            self.dismiss(False)
        else:
            self.dismiss(None)


# ----------------- Main app -----------------
class FileTreeApp(App):
    CSS = """
    /* Same frame look as first screen */
    #frame {
        width: 96%;
        height: 96%;
        border: round green;
        padding: 1 1 0 1;
        background: #000000;
    }

    /* Dialog buttons */
    #buttons { align: center middle; }
    #buttons Button { margin: 0 1; }
    #buttons .choice { border: round green; padding: 0 2; height: auto; }
    #question {
        padding-bottom: 1;
        text-align: center; 
        width: 100%; 
        content-align: center middle; 
    }

    /* Global look */
    Screen { background: #000000; }
    Header, Footer, Tree, Static, Label, Button { background: #000000; }

    #outer { width: 100%; height: 100%; align: center middle; }
    #frame > * { margin: 0; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("enter", "expand_collapse", "Expand/Collapse"),
        Binding("space", "toggle", "Toggle selection"),
        Binding("a", "select_all", "Select all"),
        Binding("n", "select_none", "Select none"),
        Binding("g", "generate", "Generate Markdown"),
        Binding("r", "refresh", "Reload tree"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="outer"):
            with Vertical(id="frame"):
                yield Header(show_clock=False)
                yield Label(f"Root: {ROOT}", id="rootlabel")
                self.file_tree = Tree(checkbox_label(True, ROOT), data=NodeData(ROOT, True))
                self.node_index = {}  # NEW: path -> node index
                # index the root immediately
                self.node_index[ROOT] = self.file_tree.root  # NEW
                yield self.file_tree
                yield Footer()


    # ----- Tree construction -----

    def on_mount(self) -> None:
        self.file_tree.show_root = True
        self.file_tree.root.allow_expand = True
        self.populate_children(self.file_tree.root, ROOT)
        self.file_tree.root.expand()
        self.set_focus(self.file_tree)

    def should_skip(self, p: Path) -> bool:
        if not INCLUDE_HIDDEN and is_hidden(p):
            return True
        if p != ROOT and path_matches_excludes(p):
            return True
        return False

    def populate_children(self, node, path: Path) -> None:
        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:
            return
        for child_path in entries:
            if self.should_skip(child_path):
                continue
            child = node.add(
                checkbox_label(node.data.selected, child_path),
                data=NodeData(child_path, node.data.selected)
            )
            child.allow_expand = child_path.is_dir()
            self.node_index[child_path] = child  # NEW: keep index up to date

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        # Populate only once
        if not node.children:
            self.populate_children(node, node.data.path)

    # ----- Selection helpers -----

    def set_node_selected(self, node, selected: bool) -> None:
        data = node.data
        data.selected = selected
        node.set_label(checkbox_label(selected, data.path))
        # Apply recursively to loaded children
        for child in node.children:
            self.set_node_selected(child, selected)
    
    def update_parent_selection(self, node) -> None:
        """If all siblings are selected/unselected, update the parent node accordingly."""
        cur = node
        while cur and cur.parent is not None:
            parent = cur.parent
            # Only check if the parent has children
            if parent.children:
                all_selected = all(ch.data.selected for ch in parent.children)
                all_unselected = all(not ch.data.selected for ch in parent.children)
                if all_selected or all_unselected:
                    new_val = all_selected  # True if all selected, else False
                    if parent.data.selected != new_val:
                        parent.data.selected = new_val
                        parent.set_label(checkbox_label(new_val, parent.data.path))
                    # keep moving upward
                    cur = parent
                    continue
            # mixed state or no children -> stop
            break

    # ----- Actions -----

    def action_expand_collapse(self) -> None:
        node = self.file_tree.cursor_node or self.file_tree.root
        if getattr(node, "allow_expand", False):
            if node.is_expanded:
                node.collapse()
            else:
                node.expand()
                
    # Click a row to toggle ◉/◯
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        self.set_focus(self.file_tree)
        try:
            self.file_tree.scroll_to_node(node)
        except AttributeError:
            pass
        # toggle selection
        self.set_node_selected(node, not node.data.selected)
        self.update_parent_selection(node)

    def action_toggle(self) -> None:
        node = self.file_tree.cursor_node or self.file_tree.root
        self.set_node_selected(node, not node.data.selected)
        self.update_parent_selection(node)

    def action_select_all(self) -> None:
        self.set_node_selected(self.file_tree.root, True)

    def action_select_none(self) -> None:
        self.set_node_selected(self.file_tree.root, False)

    def action_refresh(self) -> None:
        # Rebuild completely (e.g., when files have been added)
        root_selected = self.file_tree.root.data.selected
        self.file_tree.clear()
        self.file_tree.root.set_label(checkbox_label(root_selected, ROOT))
        self.file_tree.root.data.selected = root_selected
        self.file_tree.root.allow_expand = True
        self.node_index.clear()                    # NEW: reset index
        self.node_index[ROOT] = self.file_tree.root  # NEW: reindex root
        self.populate_children(self.file_tree.root, ROOT)
        self.file_tree.root.expand()


    # ----- Markdown generation -----

    def action_generate(self) -> None:
        # Modal dialog: Should unselected items appear in the tree above?
        self.push_screen(IncludeDialog(), self._after_dialog)

    def _after_dialog(self, include_unselected: bool | None) -> None:
        if include_unselected is None:
            return
        try:
            md = self.build_markdown(include_unselected=include_unselected)
            out_path = ROOT / OUTPUT_FILE
            out_path.write_text(md, encoding="utf-8")
            # Optional: bell/notify — might not be visible if we exit immediately.
            # self.bell()
            # self.notify(f"{OUTPUT_FILE} generated", timeout=4)

            # Exit right after export
            self.exit(0)

        except Exception as e:
            self.notify(f"Error: {e}", severity="error", timeout=6)

    # Effective selection: nodes not loaded inherit their parent's selection state
    def is_selected_effective(self, path: Path) -> bool:
        # Find the nearest existing node (walk upwards)
        cur = path
        while True:
            node = self.find_node_by_path(cur)
            if node:
                return node.data.selected
            if cur == ROOT:
                break
            cur = cur.parent
        return True

    def find_node_by_path(self, path: Path):
        return self.node_index.get(path) 


    def build_markdown(self, include_unselected: bool) -> str:
        lines = []
        lines.append(f"# File Tree for `{ROOT.name}`\n")

        # --- Draw tree ---
        def tree_lines(dir_path: Path, prefix: str = "", is_last: bool = True):
            entries = []
            try:
                entries = sorted(
                    [p for p in dir_path.iterdir() if not self.should_skip(p)],
                    key=lambda x: (not x.is_dir(), x.name.lower()),
                )
            except Exception:
                return
            for idx, p in enumerate(entries):
                last = idx == len(entries) - 1
                sel = self.is_selected_effective(p)
                if include_unselected or sel:
                    branch = "└── " if last else "├── "
                    check = ICON_SELECTED if sel else ICON_UNSELECTED  # radio icons in Markdown too
                    lines.append(f"{prefix}{branch}{check} {p.name}")
                if p.is_dir():
                    new_prefix = f"{prefix}{'    ' if last else '│   '}"
                    # even if not present in the loaded tree, recursion walks the structure
                    tree_lines(p, new_prefix, last)

        lines.append(f"{ROOT.name}")
        tree_lines(ROOT, "")

        # --- Contents ---
        lines.append("\n---\n")
        lines.append("## Selected files\n")
        for path in self.iter_files(ROOT):
            if not self.is_selected_effective(path):
                continue
            if path.is_dir():
                continue
            rel = path.relative_to(ROOT).as_posix()
            lines.append(f"\n### `{rel}`\n")
            try:
                with open(path, "rb") as fh:
                    sample = fh.read(min(MAX_BYTES + 1, 8192))
                    bin_file = detect_binary(sample)
                    if bin_file and not READ_BINARY:
                        lines.append("_Binary file — content not embedded._")
                        continue
                    # Full/partial content
                    content = sample
                    if len(sample) <= 8192:
                        # load remainder if needed
                        rest = fh.read(MAX_BYTES + 1 - len(sample))
                        content += rest
                    truncated = len(content) > MAX_BYTES
                    if truncated:
                        content = content[:MAX_BYTES]
                    try:
                        text = content.decode("utf-8")
                    except UnicodeDecodeError:
                        # best effort
                        text = content.decode("utf-8", errors="replace")
                    fence = f"```{code_lang_for(path)}" if code_lang_for(path) else "```"
                    lines.append(fence)
                    lines.append(text.rstrip("\n"))
                    lines.append("```")
                    if truncated:
                        lines.append(f"_...truncated at {MAX_BYTES} bytes_")
            except Exception as e:
                lines.append(f"_Error reading file: {e}_")

        return "\n".join(lines)

    def iter_files(self, start: Path):
        # recursively yield all files (respecting hidden/excludes)
        try:
            for p in start.iterdir():
                if self.should_skip(p):
                    continue
                if p.is_dir():
                    yield from self.iter_files(p)
                else:
                    yield p
        except Exception:
            return

if __name__ == "__main__":
    if not ROOT.exists():
        print(f"Root directory does not exist: {ROOT}", file=sys.stderr)
        sys.exit(2)
    FileTreeApp().run()
