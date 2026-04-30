"""文档接入与原始文本抽取。"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .paths import DATA_DIR, EXTRACTED_DIR, ROOT_DIR
from .records import DocumentRecord
from .utils import normalize_text, slugify_name


def discover_book_files() -> list[Path]:
    supported_suffixes = {".pdf", ".epub"}
    return sorted(
        path
        for path in DATA_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in supported_suffixes
    )


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(path)
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(page for page in pages if page)


def _epub_spine_documents(archive: zipfile.ZipFile) -> list[str]:
    container_xml = archive.read("META-INF/container.xml")
    container_root = ElementTree.fromstring(container_xml)
    container_ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile = container_root.find(".//c:rootfile", container_ns)
    if rootfile is None:
        raise ValueError("EPUB container.xml does not include a rootfile entry.")

    opf_path = rootfile.attrib["full-path"]
    opf_dir = Path(opf_path).parent
    opf_xml = archive.read(opf_path)
    opf_root = ElementTree.fromstring(opf_xml)

    namespace = {"opf": "http://www.idpf.org/2007/opf"}
    manifest: dict[str, str] = {}
    for item in opf_root.findall(".//opf:manifest/opf:item", namespace):
        href = item.attrib.get("href", "")
        media_type = item.attrib.get("media-type", "")
        if media_type in {"application/xhtml+xml", "text/html"}:
            manifest[item.attrib["id"]] = str((opf_dir / href).as_posix())

    ordered_docs: list[str] = []
    for itemref in opf_root.findall(".//opf:spine/opf:itemref", namespace):
        item_id = itemref.attrib.get("idref")
        if item_id and item_id in manifest:
            ordered_docs.append(manifest[item_id])

    if ordered_docs:
        return ordered_docs

    return sorted(
        name
        for name in archive.namelist()
        if name.lower().endswith((".xhtml", ".html", ".htm"))
    )


def extract_epub_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        texts: list[str] = []
        for name in _epub_spine_documents(archive):
            try:
                raw_bytes = archive.read(name)
            except (KeyError, zipfile.BadZipFile):
                continue
            soup = BeautifulSoup(raw_bytes, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)
            if text:
                texts.append(text)
        return "\n\n".join(texts)


def extract_documents(book_paths: list[Path]) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []
    for index, path in enumerate(book_paths, start=1):
        raw_text = extract_pdf_text(path) if path.suffix.lower() == ".pdf" else extract_epub_text(path)
        text = normalize_text(raw_text)
        title = next((line.strip() for line in text.splitlines() if line.strip()), path.stem)
        document_id = f"doc_{index:02d}_{slugify_name(path.stem)[:48]}"
        record = DocumentRecord(
            document_id=document_id,
            title=title,
            source_path=str(path.relative_to(ROOT_DIR)),
            format=path.suffix.lower().lstrip("."),
            text=text,
        )
        documents.append(record)
        (EXTRACTED_DIR / f"{document_id}.txt").write_text(text, encoding="utf-8")
    return documents
