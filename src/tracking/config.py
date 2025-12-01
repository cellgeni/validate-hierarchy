import os
from dotenv import load_dotenv
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str


def get_settings() -> Config:
    load_dotenv()  # Load environment variables from .env file if present

    return Config(
        DB_USER=os.getenv("DB_USER"),
        DB_PASSWORD=os.getenv("DB_PASSWORD"),
        DB_HOST=os.getenv("DB_HOST"),
        DB_PORT=int(os.getenv("DB_PORT", 5432)),  # Default to 5432 if not set
        DB_NAME=os.getenv("DB_NAME"),
    )
