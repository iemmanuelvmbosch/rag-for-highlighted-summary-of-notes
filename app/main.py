from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.rag_routes import router as rag_router

app = FastAPI(
    title="RAG for Highlighted Summary of Notes",
    description="RAG con OpenAI y Chroma para consultar reuniones, notas, actividades y highlights de MeetTrack.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router)


@app.get("/")
def root():
    return {
        "message": "RAG API running",
        "docs": "/docs",
        "rag_health": "/api/rag/health",
    }
