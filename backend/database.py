from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# This creates a local SQLite database file named netgen.db
SQLALCHEMY_DATABASE_URL = "sqlite:///./netgen.db"

# The "check_same_thread" argument is specifically required for SQLite in Fast API
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args = {"check_same_thread": False}
)

# This creates database sessions (the actual conversations with the DB)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This Base class is what our database models will inherit from
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()