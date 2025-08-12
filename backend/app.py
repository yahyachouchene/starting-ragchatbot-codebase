import warnings

warnings.filterwarnings("ignore", message="resource_tracker: There appear to be.*")

import os
from typing import List, Optional, Union

from config import config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rag_system import RAGSystem

# Initialize FastAPI app
app = FastAPI(title="Course Materials RAG System", root_path="")

# Add trusted host middleware for proxy
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Enable CORS with proper settings for proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Initialize RAG system
rag_system = RAGSystem(config)


# Pydantic models for request/response
class SourceItem(BaseModel):
    """Model for source items with optional links"""

    text: str
    link: Optional[str] = None


class QueryRequest(BaseModel):
    """Request model for course queries"""

    query: str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    """Response model for course queries"""

    answer: str
    sources: List[Union[str, SourceItem]]
    session_id: str


class CourseStats(BaseModel):
    """Response model for course statistics"""

    total_courses: int
    course_titles: List[str]


# API Endpoints


@app.post("/api/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """Process a query and return response with sources"""
    try:
        # Create session if not provided
        session_id = request.session_id
        if not session_id:
            session_id = rag_system.session_manager.create_session()

        # Process query using RAG system
        answer, sources = rag_system.query(request.query, session_id)

        return QueryResponse(answer=answer, sources=sources, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/courses", response_model=CourseStats)
async def get_course_stats():
    """Get course analytics and statistics"""
    try:
        analytics = rag_system.get_course_analytics()
        return CourseStats(
            total_courses=analytics["total_courses"],
            course_titles=analytics["course_titles"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """Clear conversation history for a specific session"""
    try:
        rag_system.session_manager.clear_session(session_id)
        return {"message": "Session cleared successfully", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup_event():
    """Load initial documents on startup"""
    docs_path = "../docs"
    if os.path.exists(docs_path):
        print("Loading initial documents...")
        try:
            courses, chunks = rag_system.add_course_folder(
                docs_path, clear_existing=False
            )
            print(f"Loaded {courses} courses with {chunks} chunks")
        except Exception as e:
            print(f"Error loading documents: {e}")


import os
from pathlib import Path

from fastapi.responses import FileResponse

# Custom static file handler with no-cache headers for development
from fastapi.staticfiles import StaticFiles


class DevStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if isinstance(response, FileResponse):
            # Add no-cache headers for development
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


# Serve static files for the frontend
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")
