"""PDF text, layout, and embedded diagram/image extraction with pure-Python fallback."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass
class ExtractedPage:
    """Extracted text and preserved diagram image paths for a single PDF page."""

    page_number: int
    text: str
    image_paths: list[str] = field(default_factory=list)
    used_ocr: bool = False
    backend: str = "pymupdf"


def _safe_img_ref(out_file: Path, static_root: Path) -> str:
    try:
        return out_file.relative_to(static_root).as_posix()
    except ValueError:
        return out_file.as_posix()


def _try_pymupdf_extract(pdf_path: Path, output_dir: Path, static_root: Path) -> list[ExtractedPage] | None:
    """Attempt extraction with PyMuPDF (fitz); returns None if native DLL is unavailable or blocked."""
    try:
        import fitz  # type: ignore
    except Exception:
        return None

    pages: list[ExtractedPage] = []
    doc = fitz.open(str(pdf_path))
    try:
        for page_idx, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            saved_imgs: list[str] = []
            for img_idx, img_info in enumerate(page.get_images(full=True), start=1):
                xref = img_info[0]
                base = doc.extract_image(xref)
                if not base or not base.get("image"):
                    continue
                ext = base.get("ext", "png")
                img_name = f"page_{page_idx}_fig_{img_idx}.{ext}"
                out_file = output_dir / img_name
                out_file.write_bytes(base["image"])
                rel_path = _safe_img_ref(out_file, static_root)
                saved_imgs.append(rel_path)

            # If page has little text (possible scan), render page PNG for OCR/crop preservation
            if len(text.strip()) < 40:
                pix = page.get_pixmap(dpi=200)
                scan_file = output_dir / f"page_{page_idx}_render.png"
                pix.save(str(scan_file))
                rel_path = _safe_img_ref(scan_file, static_root)
                saved_imgs.append(rel_path)

            pages.append(
                ExtractedPage(
                    page_number=page_idx,
                    text=text,
                    image_paths=saved_imgs,
                    backend="pymupdf",
                )
            )
    finally:
        doc.close()
    return pages


def _pypdf_extract(pdf_path: Path, output_dir: Path, static_root: Path) -> list[ExtractedPage]:
    """Pure-Python PDF extraction using pypdf (works even when native DLLs are restricted)."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages: list[ExtractedPage] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        saved_imgs: list[str] = []
        try:
            for img_idx, img_obj in enumerate(getattr(page, "images", []), start=1):
                raw_name = getattr(img_obj, "name", f"fig_{img_idx}.png")
                ext = Path(raw_name).suffix.lower() or ".png"
                out_file = output_dir / f"page_{page_idx}_fig_{img_idx}{ext}"
                out_file.write_bytes(img_obj.data)
                # Normalize image dimensions check via Pillow
                try:
                    with Image.open(out_file) as im:
                        if im.width >= 20 and im.height >= 20:
                            saved_imgs.append(_safe_img_ref(out_file, static_root))
                except Exception:
                    out_file.unlink(missing_ok=True)
        except Exception:
            pass

        pages.append(
            ExtractedPage(
                page_number=page_idx,
                text=text,
                image_paths=saved_imgs,
                backend="pypdf",
            )
        )
    return pages


def extract_pdf_document(
    pdf_path: str | Path,
    output_dir: str | Path,
    static_root: str | Path,
) -> dict[str, Any]:
    """
    Extract text and embedded diagrams from a PDF document.
    Tries PyMuPDF first and falls back to pure-Python pypdf cleanly.
    """
    src = Path(pdf_path)
    out = Path(output_dir)
    sroot = Path(static_root)
    out.mkdir(parents=True, exist_ok=True)

    pages = _try_pymupdf_extract(src, out, sroot)
    if pages is None:
        pages = _pypdf_extract(src, out, sroot)

    return {
        "page_count": len(pages),
        "backend": pages[0].backend if pages else "pypdf",
        "pages": pages,
    }
