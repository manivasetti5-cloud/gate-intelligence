"""Seed default administrator account and student roles."""

import os

from app.services.auth_service import create_admin_user, ensure_default_roles


def seed_admin() -> None:
    """Ensure roles exist and seed the configured administrator user."""
    ensure_default_roles()
    email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@gateintelligence.local")
    password = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@Gate2026!")
    create_admin_user(
        email=email,
        full_name="GATE Platform Administrator",
        password=password,
        department="Academic & Assessment Operations",
    )


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        seed_admin()
        print("Roles and default administrator seeded.")
