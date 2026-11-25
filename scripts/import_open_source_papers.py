"""Bulk-import real GATE PYQ PDF papers from open-source archives via the automatic extraction pipeline."""

import argparse
import hashlib
from pathlib import Path
import shutil

from app import create_app
from app.extensions import db
from app.models.paper import ExtractionJob, Paper, PaperVersion
from app.models.syllabus import Branch
from app.services.paper_pipeline import process_extraction_job


def import_pdf_folder(folder_path: str | Path, branch_code: str, exam_year: int) -> list[dict]:
    """Ingest all PDF files in a folder through the 9-step automatic GATE extraction pipeline."""
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    branch = Branch.query.filter_by(code=branch_code.upper()).first()
    if not branch:
        raise ValueError(f"Unknown GATE branch code: {branch_code}")

    from flask import current_app

    static_root = Path(current_app.root_path) / "static"
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"]) / "papers"
    upload_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for pdf_file in sorted(folder.glob("*.pdf")):
        raw_bytes = pdf_file.read_bytes()
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        if PaperVersion.query.filter_by(file_hash=file_hash).first():
            summaries.append({"file": pdf_file.name, "status": "skipped_duplicate"})
            continue

        dest = upload_dir / f"{branch.code}_{exam_year}_{file_hash[:10]}_{pdf_file.name}"
        shutil.copy2(pdf_file, dest)
        rel_path = dest.relative_to(static_root).as_posix()

        paper = Paper(
            branch_id=branch.id,
            exam_year=exam_year,
            title=f"GATE {exam_year} {branch.code} – {pdf_file.stem}",
            source_authority="Open-Source GATE PDF Archive",
        )
        db.session.add(paper)
        db.session.flush()

        pv = PaperVersion(
            paper_id=paper.id,
            file_path=rel_path,
            file_hash=file_hash,
            file_size_bytes=len(raw_bytes),
        )
        db.session.add(pv)
        db.session.flush()

        job = ExtractionJob(paper_version_id=pv.id, status="uploaded", progress_percent=5)
        db.session.add(job)
        db.session.commit()

        done_job = process_extraction_job(job.id)
        summaries.append(
            {
                "file": pdf_file.name,
                "job_id": done_job.id,
                "status": done_job.status,
                "detected": done_job.total_detected,
                "published": done_job.published_count,
                "review": done_job.review_count,
            }
        )
    return summaries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk-import GATE PDFs through the extraction pipeline.")
    parser.add_argument("--dir", required=True, help="Directory containing GATE PDF papers.")
    parser.add_argument("--branch", required=True, choices=["CS", "DA", "EC", "ME", "EE"])
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        out = import_pdf_folder(args.dir, args.branch, args.year)
        for row in out:
            print(row)
