import os

class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/luvcraft")
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "pyamqp://luvcraft:luvcraft@localhost:5672//")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", f"db+{DATABASE_URL}")

settings = Settings()
