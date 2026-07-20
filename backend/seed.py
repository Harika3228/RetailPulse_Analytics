import bcrypt

from backend.database import SessionLocal
from backend.models import Company, User


def seed_demo_data() -> None:
    session = SessionLocal()
    try:
        retail_co = session.query(Company).first()
        if retail_co is None:
            retail_co = Company(
                name="RetailPulse North",
                industry="Retail",
                email="hello@retailpulse.com",
                address="123 Main Street",
                phone="555-0100",
            )
            session.add(retail_co)
            session.flush()

        admin_user = session.query(User).filter(User.email == "admin@retailpulse.com").first()
        analyst_user = session.query(User).filter(User.email == "analyst@retailpulse.com").first()

        if admin_user is None:
            admin_user = User(
                email="admin@retailpulse.com",
                password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                companyId=retail_co.id,
                role="super_admin",
                name="RetailPulse Admin",
            )
            session.add(admin_user)
        else:
            if not admin_user.password:
                admin_user.password = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
            if admin_user.companyId is None:
                admin_user.companyId = retail_co.id

        if analyst_user is None:
            analyst_user = User(
                email="analyst@retailpulse.com",
                password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                companyId=retail_co.id,
                role="analyst",
                name="RetailPulse Analyst",
            )
            session.add(analyst_user)
        else:
            if not analyst_user.password:
                analyst_user.password = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
            if analyst_user.companyId is None:
                analyst_user.companyId = retail_co.id

        session.commit()
    finally:
        session.close()
