from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import router
import os

app = FastAPI(title="EPUB-TTS Backend", version="1.0.0")

# CORS Configuration
origins = [
    "http://localhost:5173",  # Vite Dev Server
    "http://127.0.0.1:5173",
    "*"  # Allow all for local dev convenience
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure data directories exist
os.makedirs("data/uploads", exist_ok=True)
os.makedirs("data/audio", exist_ok=True)

# Mount static files for audio playback
app.mount("/audio", StaticFiles(directory="data/audio"), name="audio")
app.mount("/covers", StaticFiles(directory="data/uploads"), name="covers")

# Include API Router
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "EPUB-TTS Backend is running", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
