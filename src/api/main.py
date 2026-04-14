import os
import sys
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure project root is on sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.runtime.secrets import init_runtime_secrets
init_runtime_secrets()

from src.config import CORS_ORIGINS, PROJECT_ROOT
from src.api.routers import auth, admin, niche, trends, clusters, ads, my_brands, monitoring

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Trends Research API",
    description="Intelligence platform for Discovering, Tracking, and Analyzing emerging trends.",
    version="2.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(niche.router)
app.include_router(trends.router)
app.include_router(clusters.router)
app.include_router(ads.router)
app.include_router(my_brands.router)
app.include_router(monitoring.router)

# Static files and SPA serving
_frontend_dist = os.path.join(PROJECT_ROOT, "frontend", "dist")

if os.path.isdir(_frontend_dist):
    # Assets folder for Vite
    _assets = os.path.join(_frontend_dist, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")
    
    # Root redirect to index.html for SPA
    @app.get("/", include_in_schema=False)
    def serve_root():
        _index = os.path.join(_frontend_dist, "index.html")
        if os.path.isfile(_index):
            return FileResponse(_index)
        return {"message": "API is running, but frontend dist/index.html not found."}

    # Catch-all for SPA routing (wouter, etc.)
    @app.get("/{full_path:path}", include_in_schema=False)
    def catch_all(full_path: str):
        _index = os.path.join(_frontend_dist, "index.html")
        if os.path.isfile(_index):
            return FileResponse(_index)
        return {"message": f"API is running. Requested path: {full_path}"}
else:
    @app.get("/", include_in_schema=False)
    def serve_root():
        return {"message": "Trends Research API v2.0 is running. Frontend build not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
