import logging
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .routes import purchases, live_feed, ai, fourmeme, demo, report

app = FastAPI(title="Meme Scavenger Agent API", version="1.0.0")

app.include_router(purchases.router)
app.include_router(live_feed.router)
app.include_router(ai.router)
app.include_router(fourmeme.router)
app.include_router(demo.router)
app.include_router(report.router)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/images", StaticFiles(directory="frontend/images"), name="images")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse("frontend/index.html")


@app.get("/health")
def health():
    return {"status": "ok"}
