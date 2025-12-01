import logging
from tracking.config import get_settings
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)

_settings = get_settings()
_engine = create_engine(
    f"postgresql://{_settings.DB_USER}:{_settings.DB_PASSWORD}@{_settings.DB_HOST}:{_settings.DB_PORT}/{_settings.DB_NAME}"
)
_Session = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)


@contextmanager
def session_scope():
    """
    Provide a transactional scope around a series of operations.
    """
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        logger.exception("An error occurred, rolling back the session.")
        session.rollback()
        raise
    finally:
        session.close()
