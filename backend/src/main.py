"""App entry: ties agents + API together (techspec §9)."""

import os

from fastapi import FastAPI

app = FastAPI(title="Market Briefing Agent")


@app.get("/api/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "model": os.environ.get("LLM_MODEL", "unconfigured"),
        "daily_briefs_remaining": int(os.environ.get("GLOBAL_DAILY_BRIEFS", "100")),
    }
