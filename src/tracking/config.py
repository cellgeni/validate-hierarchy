"""Configuration module for tracking application."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """
    Configuration settings for database connection.
    """
    DB_USER: str | None
    DB_PASSWORD: str | None
    DB_HOST: str | None
    DB_PORT: int | None
    DB_NAME: str | None


def get_settings() -> Config:
    """
    Load configuration settings from environment variables.
    """
    load_dotenv()  # Load environment variables from .env file if present

    return Config(
        DB_USER=os.getenv("DB_USER"),
        DB_PASSWORD=os.getenv("DB_PASSWORD"),
        DB_HOST=os.getenv("DB_HOST"),
        DB_PORT=int(os.getenv("DB_PORT", 5432)),  # Default to 5432 if not set
        DB_NAME=os.getenv("DB_NAME"),
    )
