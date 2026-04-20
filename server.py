"""Production entry point — run with: python server.py"""
from waitress import serve
from app.main import app
from app.config import settings

if __name__ == "__main__":
    print(f"Starting Meme Scavenger Agent on {settings.app_host}:{settings.app_port}")
    serve(app, host=settings.app_host, port=settings.app_port, threads=8)
