from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.rag_routes import router as rag_router

app = FastAPI(
    title="RAG for Highlighted Summary of Notes",
    description=(
        "RAG with OpenAI and Chroma to query MeetTrack meetings, notes, "
        "activities, and highlights."
    ),
    version="1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router)
