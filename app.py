"""SongForge entrypoint — запуск: python app.py"""
import os

from dotenv import load_dotenv
load_dotenv()
print("API_KEY:", os.getenv("GETPLATINUM_API_KEY"))

import uvicorn

from backend.app import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
