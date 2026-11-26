"""Background tasks for asynchronous PDF paper extraction and AI question generation."""

import os
import threading

from celery import Celery

celery_app = Celery(
    "gate_intelligence",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)


@celery_app.task(name="worker.tasks.process_paper_job_task")
def process_paper_job_task(job_id: int) -> str:
    """Celery task entrypoint for PDF extraction pipeline."""
    from app import create_app
    from app.services.paper_pipeline import process_extraction_job

    flask_app = create_app()
    with flask_app.app_context():
        job = process_extraction_job(job_id)
        return job.status


@celery_app.task(name="worker.tasks.run_generation_job_task")
def run_generation_job_task(job_id: int) -> str:
    """Celery task entrypoint for AI original question generation."""
    from app import create_app
    from app.services.ai_question_generator import run_generation_job

    flask_app = create_app()
    with flask_app.app_context():
        job = run_generation_job(job_id)
        return job.status


def enqueue_paper_job(app, job_id: int, run_async: bool = True) -> None:
    """Dispatch PDF extraction job to Celery if enabled, else run in background thread or inline."""
    if app.config.get("USE_CELERY"):
        process_paper_job_task.delay(job_id)
        return

    if not run_async:
        from app.services.paper_pipeline import process_extraction_job

        process_extraction_job(job_id)
        return

    def _runner():
        with app.app_context():
            try:
                from app.services.paper_pipeline import process_extraction_job

                process_extraction_job(job_id)
            finally:
                from app.extensions import db

                db.session.remove()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()


def enqueue_generation_job(app, job_id: int, run_async: bool = True) -> None:
    """Dispatch AI generation job to Celery if enabled, else run in background thread or inline."""
    if app.config.get("USE_CELERY"):
        run_generation_job_task.delay(job_id)
        return

    if not run_async:
        from app.services.ai_question_generator import run_generation_job

        run_generation_job(job_id)
        return

    def _runner():
        with app.app_context():
            try:
                from app.services.ai_question_generator import run_generation_job

                run_generation_job(job_id)
            finally:
                from app.extensions import db

                db.session.remove()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
