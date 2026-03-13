"""Deterministic document-reading and summarization helpers."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".rst",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".tsv",
    ".log",
    ".xml",
    ".html",
    ".htm",
}
DOCX_SUFFIXES = {".docx"}
XLSX_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | DOCX_SUFFIXES | XLSX_SUFFIXES | PDF_SUFFIXES

SUMMARY_SCOPES = {"all", "per_file", "global", "file"}

ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "are",
    "was",
    "were",
    "into",
    "then",
    "only",
    "file",
    "files",
    "folder",
    "summary",
    "project",
    "documents",
    "current",
    "report",
    "route",
    "routes",
    "摘要",
    "文档",
    "文件",
    "目录",
    "项目",
    "整体",
    "输出",
}


@dataclass(frozen=True)
class SummaryRequest:
    path: Path
    scope: str = "per_file"
    file_path: str = ""
    max_files: int = 20


@dataclass(frozen=True)
class FileSummary:
    relative_path: str
    file_type: str
    title: str
    summary: str
    excerpt: str
    char_count: int
    warning: str = ""


class DocumentSummaryTool:
    """Read supported documents and return deterministic markdown summaries."""

    def __init__(self, *, data_dir: Path) -> None:
        self.data_dir = data_dir

    def summarize(self, raw_input: str) -> str:
        request = self._parse_request(raw_input)
        target_path = self._resolve_target_path(request)
        if target_path is None:
            return "Document path does not exist."

        if target_path.is_file():
            file_summary = self._summarize_file(target_path, root=target_path.parent)
            if file_summary is None:
                return "Document type is not supported."
            return self._render_single_file_summary(file_summary, target_path.parent)

        summaries = self._collect_summaries(target_path, request)
        if isinstance(summaries, str):
            return summaries

        if request.scope == "global":
            return self._render_global_summary(root=target_path, summaries=summaries)
        return self._render_directory_summary(root=target_path, summaries=summaries)

    def summarize_semantic(self, raw_input: str) -> str:
        request = self._parse_request(raw_input)
        target_path = self._resolve_target_path(request)
        if target_path is None:
            return "Document path does not exist."

        if target_path.is_file():
            file_summary = self._summarize_file(target_path, root=target_path.parent)
            if file_summary is None:
                return "Document type is not supported."
            return self._render_semantic_summary(root=target_path.parent, summaries=[file_summary])

        summaries = self._collect_summaries(target_path, request)
        if isinstance(summaries, str):
            return summaries
        return self._render_semantic_summary(root=target_path, summaries=summaries)

    def _parse_request(self, raw_input: str) -> SummaryRequest:
        text = raw_input.strip()
        if not text:
            return SummaryRequest(path=Path.cwd())

        if text.startswith("{"):
            payload = json.loads(text)
            scope = str(payload.get("scope", "per_file")).strip().lower() or "per_file"
            if scope not in SUMMARY_SCOPES:
                scope = "per_file"
            return SummaryRequest(
                path=Path(str(payload.get("path", "."))),
                scope=scope,
                file_path=str(payload.get("file_path", "")),
                max_files=int(payload.get("max_files", 20) or 20),
            )

        if "|" in text:
            base, file_path = text.split("|", 1)
            return SummaryRequest(
                path=Path(base.strip() or "."),
                scope="file",
                file_path=file_path.strip(),
            )

        return SummaryRequest(path=Path(text))

    def _resolve_target_path(self, request: SummaryRequest) -> Path | None:
        candidate = request.path
        search_order = []
        if candidate.is_absolute():
            search_order.append(candidate)
        else:
            search_order.append(Path.cwd() / candidate)
            search_order.append(self.data_dir / candidate)
        for target in search_order:
            if target.exists():
                return target
        return None

    @staticmethod
    def _collect_supported_files(root: Path, *, max_files: int) -> list[Path]:
        files: list[Path] = []
        for path in sorted(root.rglob("*")):
            if len(files) >= max_files:
                break
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            files.append(path)
        return files

    def _collect_summaries(self, target_path: Path, request: SummaryRequest) -> list[FileSummary] | str:
        if request.scope == "file" and request.file_path:
            chosen = target_path / request.file_path
            if not chosen.exists() or not chosen.is_file():
                return "Requested file does not exist."
            file_summary = self._summarize_file(chosen, root=target_path)
            if file_summary is None:
                return "Document type is not supported."
            return [file_summary]

        files = self._collect_supported_files(target_path, max_files=request.max_files)
        if not files:
            return "No supported documents found."

        summaries = [
            summary
            for summary in (self._summarize_file(path, root=target_path) for path in files)
            if summary is not None
        ]
        if not summaries:
            return "No supported documents found."
        return summaries

    def _summarize_file(self, path: Path, *, root: Path) -> FileSummary | None:
        text, warning = self._read_document(path)
        if text is None:
            return None
        normalized = self._normalize_text(text)
        return FileSummary(
            relative_path=str(path.relative_to(root)),
            file_type=path.suffix.lower().lstrip(".") or "text",
            title=self._infer_title(normalized, path),
            summary=self._generate_summary(normalized),
            excerpt=self._build_excerpt(normalized),
            char_count=len(normalized),
            warning=warning,
        )

    def _read_document(self, path: Path) -> tuple[str | None, str]:
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            return self._read_text_file(path), ""
        if suffix in DOCX_SUFFIXES:
            return self._read_docx_file(path), ""
        if suffix in XLSX_SUFFIXES:
            return self._read_xlsx_file(path), ""
        if suffix in PDF_SUFFIXES:
            return self._read_pdf_file(path)
        return None, ""

    @staticmethod
    def _read_text_file(path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _read_docx_file(path: Path) -> str:
        with zipfile.ZipFile(path) as archive:
            content = archive.read("word/document.xml")
        root = ET.fromstring(content)
        paragraphs: list[str] = []
        current: list[str] = []
        for element in root.iter():
            if element.tag.endswith("}t") and element.text:
                current.append(element.text)
            elif element.tag.endswith("}p"):
                joined = "".join(current).strip()
                if joined:
                    paragraphs.append(joined)
                current = []
        if current:
            joined = "".join(current).strip()
            if joined:
                paragraphs.append(joined)
        return "\n".join(paragraphs)

    @staticmethod
    def _read_xlsx_file(path: Path) -> str:
        with zipfile.ZipFile(path) as archive:
            shared_strings = _read_shared_strings(archive)
            workbook_sheets = _read_workbook_sheets(archive)
            lines: list[str] = []
            for sheet_path, sheet_name in workbook_sheets:
                if sheet_path not in archive.namelist():
                    continue
                rows = _read_sheet_rows(archive.read(sheet_path), shared_strings)
                lines.append(f"[Sheet] {sheet_name}")
                for row in rows[:10]:
                    values = [cell for cell in row if cell]
                    if values:
                        lines.append(" | ".join(values))
                lines.append("")
        return "\n".join(line for line in lines if line.strip())

    @staticmethod
    def _read_pdf_file(path: Path) -> tuple[str, str]:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text, ""
        except Exception:
            pass

        try:
            from PyPDF2 import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text, ""
        except Exception:
            pass

        pdftotext_path = shutil.which("pdftotext")
        if pdftotext_path:
            proc = subprocess.run(
                [pdftotext_path, str(path), "-"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout, ""

        return "", "PDF support requires pypdf, PyPDF2, or pdftotext."

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _infer_title(text: str, path: Path) -> str:
        for line in text.splitlines():
            candidate = line.strip().strip("#").strip()
            if 3 <= len(candidate) <= 120:
                return candidate
        return path.name

    @staticmethod
    def _generate_summary(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "No readable content extracted."
        selected: list[str] = []
        for line in lines:
            if len(selected) >= 3:
                break
            if line.startswith(("-", "*", "1.", "2.", "3.")):
                selected.append(line)
                continue
            if ":" in line and len(line) <= 120:
                selected.append(line)
                continue
            if not selected:
                selected.append(line[:180])
        return " ".join(selected)[:400]

    @staticmethod
    def _build_excerpt(text: str) -> str:
        return " ".join(text.split())[:500]

    @staticmethod
    def _render_single_file_summary(summary: FileSummary, root: Path) -> str:
        lines = [
            "# Document Summary",
            "",
            f"- Root: `{root}`",
            f"- File: `{summary.relative_path}`",
            f"- Type: `{summary.file_type}`",
            f"- Title: {summary.title}",
            f"- Characters: {summary.char_count}",
        ]
        if summary.warning:
            lines.append(f"- Warning: {summary.warning}")
        lines.extend(
            [
                "",
                "## Summary",
                summary.summary or "(empty)",
                "",
                "## Excerpt",
                summary.excerpt or "(empty)",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _render_directory_summary(*, root: Path, summaries: Iterable[FileSummary]) -> str:
        items = list(summaries)
        type_counts = _count_file_types(items)

        lines = [
            "# Directory Document Summary",
            "",
            f"- Root: `{root}`",
            f"- Files summarized: {len(items)}",
            f"- Types: {', '.join(f'{kind}={count}' for kind, count in sorted(type_counts.items()))}",
            "",
            "## Files",
        ]
        for item in items:
            lines.extend(
                [
                    f"### {item.relative_path}",
                    f"- Type: `{item.file_type}`",
                    f"- Title: {item.title}",
                    f"- Summary: {item.summary or '(empty)'}",
                ]
            )
            if item.warning:
                lines.append(f"- Warning: {item.warning}")
        return "\n".join(lines)

    @staticmethod
    def _render_global_summary(*, root: Path, summaries: Iterable[FileSummary]) -> str:
        items = list(summaries)
        type_counts = _count_file_types(items)
        top_titles = [item.title for item in sorted(items, key=lambda row: row.char_count, reverse=True)[:5]]

        lines = [
            "# Global Document Summary",
            "",
            f"- Root: `{root}`",
            f"- Files summarized: {len(items)}",
            f"- Types: {', '.join(f'{kind}={count}' for kind, count in sorted(type_counts.items()))}",
            "",
            "## Overview",
            _compose_global_overview(items),
            "",
            "## Dominant Files",
        ]
        for title in top_titles:
            lines.append(f"- {title}")
        return "\n".join(lines)

    @staticmethod
    def _render_semantic_summary(*, root: Path, summaries: Iterable[FileSummary]) -> str:
        items = list(summaries)
        keywords = _extract_keywords(items)
        overview = _compose_global_overview(items)
        lines = [
            "# Semantic Document Summary",
            "",
            f"- Root: `{root}`",
            f"- Files analyzed: {len(items)}",
            f"- Themes: {', '.join(keywords) if keywords else '(none)'}",
            "",
            "## Semantic Overview",
            overview,
            "",
            "## Priority Files",
        ]
        for item in sorted(items, key=lambda row: row.char_count, reverse=True)[:5]:
            lines.append(f"- {item.relative_path}: {item.summary}")
        return "\n".join(lines)


def _count_file_types(items: Iterable[FileSummary]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.file_type] = counts.get(item.file_type, 0) + 1
    return counts


def _compose_global_overview(items: list[FileSummary]) -> str:
    if not items:
        return "No readable content extracted."
    lead = [item.summary for item in sorted(items, key=lambda row: row.char_count, reverse=True)[:3] if item.summary]
    if not lead:
        return "No readable content extracted."
    return " ".join(lead)[:600]


def _extract_keywords(items: list[FileSummary]) -> list[str]:
    counter: Counter[str] = Counter()
    for item in items:
        text = f"{item.title}\n{item.summary}"
        for token in ASCII_TOKEN_RE.findall(text.lower()):
            if token in STOPWORDS:
                continue
            counter[token] += 1
        for token in CJK_TOKEN_RE.findall(text):
            if token in STOPWORDS:
                continue
            counter[token] += 1
    return [token for token, _ in counter.most_common(8)]


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for si in root.findall(".//{*}si"):
        parts = [node.text or "" for node in si.findall(".//{*}t")]
        values.append("".join(parts))
    return values


def _read_workbook_sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    if "xl/workbook.xml" not in archive.namelist():
        return []
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rel_map: dict[str, str] = {}
    rels_path = "xl/_rels/workbook.xml.rels"
    if rels_path in archive.namelist():
        rels_root = ET.fromstring(archive.read(rels_path))
        for rel in rels_root.findall(".//{*}Relationship"):
            rel_map[rel.attrib.get("Id", "")] = rel.attrib.get("Target", "")

    sheets: list[tuple[str, str]] = []
    for sheet in workbook_root.findall(".//{*}sheet"):
        name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rel_map.get(rel_id, "")
        if target:
            sheets.append(("xl/" + target.lstrip("/"), name))
    if sheets:
        return sheets

    fallback = []
    for name in archive.namelist():
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
            fallback.append((name, Path(name).stem))
    return fallback


def _read_sheet_rows(content: bytes, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(content)
    rows: list[list[str]] = []
    for row in root.findall(".//{*}row"):
        values: list[str] = []
        for cell in row.findall("{*}c"):
            cell_type = cell.attrib.get("t", "")
            value = ""
            if cell_type == "s":
                raw = cell.findtext("{*}v", default="")
                if raw.isdigit() and int(raw) < len(shared_strings):
                    value = shared_strings[int(raw)]
            elif cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
            else:
                value = cell.findtext("{*}v", default="")
            values.append(value.strip())
        rows.append(values)
    return rows
