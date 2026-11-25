"""Flask application factory for GATE Intelligence."""

import os
from pathlib import Path

from flask import Flask, render_template

from app.config import CONFIG_MAP
from app.extensions import csrf, db, limiter, login_manager, migrate
from app.models.user import User


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application instance."""
    env_name = config_name or os.getenv("FLASK_ENV", "development")
    config_cls = CONFIG_MAP.get(env_name, CONFIG_MAP["development"])

    app = Flask(__name__)
    app.config.from_object(config_cls)

    # Ensure upload and instance directories exist
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    upload_root = Path(app.config["UPLOAD_FOLDER"])
    for sub in ("papers", "extracted", "images"):
        (upload_root / sub).mkdir(parents=True, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Import models so Alembic sees all metadata
    from app import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.routes.admin import admin_bp
    from app.routes.analytics import analytics_bp
    from app.routes.assessments import assessments_bp
    from app.routes.auth import auth_bp
    from app.routes.questions import questions_bp
    from app.routes.results import results_bp
    from app.routes.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(questions_bp)
    app.register_blueprint(analytics_bp)

    # Security response headers
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    # Error handlers
    @app.errorhandler(403)
    def forbidden(_err):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_err):
        return render_template("errors/404.html"), 404

    @app.cli.command("seed")
    def seed_cli():
        """Seed roles, admin, branches, exam patterns, syllabi, and formula library."""
        from scripts.seed_all import run_all_seeds

        summary = run_all_seeds()
        print("Database seed complete:", summary)

    return app
