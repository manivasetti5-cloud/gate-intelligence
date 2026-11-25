"""Seed the five official GATE examination branches."""

from app.extensions import db
from app.models.syllabus import Branch

OFFICIAL_BRANCHES = [
    {
        "code": "CS",
        "name": "Computer Science and Information Technology",
        "description": "Algorithms, Data Structures, OS, DBMS, Computer Networks, TOC, Compiler Design, COA, Digital Logic, and Engineering Mathematics.",
    },
    {
        "code": "DA",
        "name": "Data Science and Artificial Intelligence",
        "description": "Probability & Statistics, Linear Algebra, Calculus & Optimization, Python & DSA, DBMS & Warehousing, Machine Learning, and AI.",
    },
    {
        "code": "EC",
        "name": "Electronics and Communication Engineering",
        "description": "Networks, Signals & Systems, Electronic Devices, Analog & Digital Circuits, Control Systems, Communications, and Electromagnetics.",
    },
    {
        "code": "ME",
        "name": "Mechanical Engineering",
        "description": "Applied Mechanics & Design, Fluid Mechanics & Thermal Sciences, Materials, Manufacturing & Industrial Engineering, and Engineering Mathematics.",
    },
    {
        "code": "EE",
        "name": "Electrical Engineering",
        "description": "Electric Circuits, Electromagnetic Fields, Signals, Electrical Machines, Power Systems, Control Systems, Measurements, Electronics, and Power Electronics.",
    },
]


def seed_branches() -> dict[str, Branch]:
    """Idempotently seed all 5 GATE branches."""
    result: dict[str, Branch] = {}
    for item in OFFICIAL_BRANCHES:
        branch = Branch.query.filter_by(code=item["code"]).first()
        if not branch:
            branch = Branch(
                code=item["code"],
                name=item["name"],
                description=item["description"],
                is_active=True,
            )
            db.session.add(branch)
            db.session.flush()
        result[item["code"]] = branch
    db.session.commit()
    return result


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        seeded = seed_branches()
        print(f"Seeded branches: {', '.join(seeded.keys())}")
