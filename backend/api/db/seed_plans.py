"""
Seed script to add permanent Plan entries to the Plan table.
Usage:
    python -m api.db.seed_plans
"""

from decimal import Decimal
from sqlmodel import Session, select
from api.db.database import engine
from api.db.models import Plan, Status

def seed_statuses():
    """Add default status entries to the Status table."""
    with Session(engine) as session:
        existing_statuses = session.exec(select(Status)).all()
        if existing_statuses:
            return

        print("Seeding statuses...")
        status_templates = [
            {"id": 1, "name": "Aktyvi"},
            {"id": 2, "name": "Atšaukta"},
            {"id": 3, "name": "Pasibaigusi"}
        ]
        
        for item in status_templates:
            status_entry = Status(id=item["id"], name=item["name"])
            session.add(status_entry)
        
        session.commit()
        print("Successfully seeded statuses!")

def seed_plans():
    """Add default plan entries to the database if they don't already exist."""
    
    with Session(engine) as session:
        # Check if plans already exist
        existing_plans = session.exec(select(Plan)).all()
        if existing_plans:
            print(f"Plans already exist ({len(existing_plans)} found):")
            for plan in existing_plans:
                print(f"  - {plan.title}: ${plan.price} ({plan.query_limit} queries, {plan.duration} days)")
            return
        
        print("Seeding plans to Plan table...\n")
        
        # Define plan data
        plan_templates = [
            {
                "title": "Free Plan",
                "price": Decimal("0.00"),
                "duration": 30,  # days
                "query_limit": 10
            },
            {
                "title": "Pro Plan",
                "price": Decimal("4.99"),
                "duration": 30,
                "query_limit": 200
            },
            {
                "title": "Enterprise Plan",
                "price": Decimal("9.99"),
                "duration": 30,
                "query_limit": 500
            }
        ]
        
        created_count = 0
        for template in plan_templates:
            plan = Plan(
                title=template["title"],
                price=template["price"],
                duration=template["duration"],
                query_limit=template["query_limit"]
            )
            session.add(plan)
            print(f" {plan.title}: ${plan.price} ({plan.query_limit} queries, {plan.duration} days)")
            created_count += 1
        
        session.commit()
        print(f"\nSuccessfully seeded {created_count} plans to the Plan table!")

if __name__ == "__main__":
    seed_statuses()
    seed_plans()
