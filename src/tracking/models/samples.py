"""A class that represents a sample in a tracking dataset."""

from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class Sample(Base):
    """
    A class that represents a sample in a tracking dataset.
    """

    __tablename__ = "samples"

    id = Column(Integer, primary_key=True)
    sample_name = Column(String(30), nullable=False)
    dataset_name = Column(String(30), nullable=False)
    is_10x = Column(Boolean)  # This is qiestionable? Maybe not Bool???
    status = Column(
        ENUM("success", "fail", "skip", "pending", name="status_enum"),
        nullable=False,
        default="pending",
    )
    library_type = Column(String(100))
    sanger_id = Column(String(50), unique=True)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    def __repr__(self):
        return f"<Sample(id={self.id}, sample_name='{self.sample_name}', dataset_name='{self.dataset_name}')>"
