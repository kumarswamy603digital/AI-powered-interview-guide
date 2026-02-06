from sqlalchemy.orm import declarative_base

from app.db.session import engine


Base = declarative_base()


def init_db() -> None:
    """
    Initialize database schema.

    Import models inside this function so Base is defined before models
    reference it, avoiding circular imports.
    """
    # Local imports to register models with Base metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

