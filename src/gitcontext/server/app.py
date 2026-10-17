"""FastAPI application factory and server entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gitcontext.server.routes import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI web application."""
    app = FastAPI(
        title="GitContext AI Copilot",
        description="Copilot-style AI coding agent with hybrid RAG, investigation tools, and patch verification",
        version="0.1.0",
    )

    # Enable CORS for local dev server (Vite on 5173 / 3000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(router)

    # Check if frontend distribution build exists
    workspace_root = Path.cwd().resolve()
    frontend_dist = workspace_root / "frontend" / "dist"

    if frontend_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Don't intercept API routes
            if full_path.startswith("api/"):
                return {"error": "API route not found"}
            file_target = frontend_dist / full_path
            if file_target.is_file():
                return FileResponse(file_target)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()


def start_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run server with uvicorn."""
    import uvicorn

    uvicorn.run("gitcontext.server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    start_server()
