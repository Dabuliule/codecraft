from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter import Language, Node, Parser


@dataclass(frozen=True, slots=True)
class CodeChunk:
    start_line: int
    end_line: int
    kind: str
    symbol: str | None
    content: str


@dataclass(frozen=True, slots=True)
class CodeSymbol:
    name: str
    kind: str
    line: int
    signature: str


@dataclass(frozen=True, slots=True)
class ChunkedFile:
    language: str
    chunks: tuple[CodeChunk, ...]
    symbols: tuple[CodeSymbol, ...]


_EXTENSIONS = {
    ".go": "go",
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
}

_SYMBOL_NODES = {
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "javascript": {
        "class_declaration",
        "function_declaration",
        "generator_function_declaration",
        "method_definition",
    },
    "python": {"class_definition", "function_definition"},
    "typescript": {
        "class_declaration",
        "function_declaration",
        "generator_function_declaration",
        "interface_declaration",
        "method_definition",
        "type_alias_declaration",
    },
    "tsx": {
        "class_declaration",
        "function_declaration",
        "generator_function_declaration",
        "interface_declaration",
        "method_definition",
        "type_alias_declaration",
    },
}


class TreeSitterChunker:
    def __init__(self, *, max_lines: int = 120, overlap_lines: int = 12) -> None:
        if max_lines < 1:
            raise ValueError("max_lines must be positive")
        if overlap_lines < 0 or overlap_lines >= max_lines:
            raise ValueError("overlap_lines must be between 0 and max_lines")
        self.max_lines = max_lines
        self.overlap_lines = overlap_lines
        self._languages = _load_languages()

    def chunk(self, path: Path, content: str) -> ChunkedFile:
        language_name = _EXTENSIONS.get(path.suffix.casefold(), "text")
        language = self._languages.get(language_name)
        if language is None:
            return ChunkedFile(
                language=language_name,
                chunks=tuple(self._line_chunks(content, kind="text")),
                symbols=(),
            )

        source = content.encode("utf-8")
        tree = Parser(language).parse(source)
        symbol_nodes = list(_walk_symbol_nodes(tree.root_node, language_name))
        outer_nodes = _outermost_nodes(symbol_nodes)
        lines = content.splitlines()
        chunks: list[CodeChunk] = []
        cursor = 0
        for node in outer_nodes:
            start = node.start_point.row
            end = min(len(lines), node.end_point.row + 1)
            if start > cursor:
                chunks.extend(self._range_chunks(lines, cursor, start, kind="module"))
            name = _node_name(node, source)
            chunks.extend(
                self._range_chunks(
                    lines,
                    start,
                    end,
                    kind=node.type,
                    symbol=name,
                )
            )
            cursor = max(cursor, end)
        if cursor < len(lines):
            chunks.extend(self._range_chunks(lines, cursor, len(lines), kind="module"))
        if not chunks:
            chunks.extend(self._line_chunks(content, kind="module"))

        symbols = tuple(
            CodeSymbol(
                name=name,
                kind=node.type,
                line=node.start_point.row + 1,
                signature=_signature(lines, node.start_point.row),
            )
            for node in symbol_nodes
            if (name := _node_name(node, source))
        )
        return ChunkedFile(
            language=language_name,
            chunks=tuple(chunks),
            symbols=symbols,
        )

    def _line_chunks(self, content: str, *, kind: str) -> list[CodeChunk]:
        lines = content.splitlines()
        return self._range_chunks(lines, 0, len(lines), kind=kind)

    def _range_chunks(
        self,
        lines: list[str],
        start: int,
        end: int,
        *,
        kind: str,
        symbol: str | None = None,
    ) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        step = self.max_lines - self.overlap_lines
        position = start
        while position < end:
            chunk_end = min(position + self.max_lines, end)
            content = "\n".join(lines[position:chunk_end]).strip()
            if content:
                chunks.append(
                    CodeChunk(
                        start_line=position + 1,
                        end_line=chunk_end,
                        kind=kind,
                        symbol=symbol,
                        content=content,
                    )
                )
            if chunk_end >= end:
                break
            position += step
        return chunks


def _load_languages() -> dict[str, Language]:
    import tree_sitter_go
    import tree_sitter_javascript
    import tree_sitter_python
    import tree_sitter_typescript

    return {
        "go": Language(tree_sitter_go.language()),
        "javascript": Language(tree_sitter_javascript.language()),
        "python": Language(tree_sitter_python.language()),
        "typescript": Language(tree_sitter_typescript.language_typescript()),
        "tsx": Language(tree_sitter_typescript.language_tsx()),
    }


def _walk_symbol_nodes(node: Node, language: str) -> Any:
    if node.type in _SYMBOL_NODES[language]:
        yield node
    for child in node.named_children:
        yield from _walk_symbol_nodes(child, language)


def _outermost_nodes(nodes: list[Node]) -> list[Node]:
    ordered = sorted(nodes, key=lambda node: (node.start_byte, -node.end_byte))
    selected: list[Node] = []
    for node in ordered:
        if any(
            parent.start_byte <= node.start_byte and parent.end_byte >= node.end_byte
            for parent in selected
        ):
            continue
        selected.append(node)
    return selected


def _node_name(node: Node, source: bytes) -> str | None:
    name = node.child_by_field_name("name")
    if name is None and node.type == "type_declaration":
        name = next(
            (child for child in node.named_children if child.type == "type_spec"),
            None,
        )
        if name is not None:
            name = name.child_by_field_name("name")
    if name is None:
        return None
    return source[name.start_byte : name.end_byte].decode("utf-8", errors="replace")


def _signature(lines: list[str], row: int) -> str:
    if row >= len(lines):
        return ""
    return lines[row].strip()[:240]
