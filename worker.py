"""Точка входа фонового worker (pm2: songforge-worker)."""
from backend.worker import run_forever

if __name__ == "__main__":
    run_forever()