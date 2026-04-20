"""Production entry point — run with: python server.py"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"Starting Meme Scavenger Agent on {settings.app_host}:{settings.app_port}")
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        workers=4,
    )
