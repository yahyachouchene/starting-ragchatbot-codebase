import pytest
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch
from fastapi.testclient import TestClient
from pathlib import Path
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Course, Lesson, CourseChunk


@pytest.fixture
def mock_course():
    """Create a mock Course object for testing"""
    return Course(
        title="Test Course",
        instructor="Test Instructor",
        course_link="https://example.com/course",
        lessons=[
            Lesson(
                lesson_number=0,
                title="Introduction",
                content="This is the introduction lesson content.",
                lesson_link="https://example.com/lesson-0"
            ),
            Lesson(
                lesson_number=1,
                title="Advanced Topics",
                content="This covers advanced machine learning topics.",
                lesson_link="https://example.com/lesson-1"
            )
        ]
    )


@pytest.fixture
def mock_course_chunks():
    """Create mock CourseChunk objects for testing"""
    return [
        CourseChunk(
            text="This is the introduction lesson content.",
            course_title="Test Course",
            lesson_number=0,
            lesson_title="Introduction",
            lesson_link="https://example.com/lesson-0",
            course_link="https://example.com/course"
        ),
        CourseChunk(
            text="This covers advanced machine learning topics.",
            course_title="Test Course",
            lesson_number=1,
            lesson_title="Advanced Topics", 
            lesson_link="https://example.com/lesson-1",
            course_link="https://example.com/course"
        )
    ]


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client for testing"""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.content = [Mock()]
    mock_response.content[0].text = "This is a test response from Claude"
    mock_response.content[0].type = "text"
    mock_client.messages.create.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store for testing"""
    mock_store = Mock()
    mock_store.search.return_value = [
        {
            "text": "Test Course - Lesson 1: Advanced Topics",
            "course_title": "Test Course",
            "lesson_number": 1,
            "lesson_title": "Advanced Topics",
            "lesson_link": "https://example.com/lesson-1",
            "course_link": "https://example.com/course",
            "distance": 0.2
        }
    ]
    mock_store.add_course.return_value = None
    mock_store.get_course_analytics.return_value = {
        "total_courses": 1,
        "course_titles": ["Test Course"]
    }
    return mock_store


@pytest.fixture
def mock_rag_system():
    """Create a mock RAG system for testing"""
    mock_rag = Mock()
    mock_rag.query.return_value = (
        "This is a test response from the RAG system",
        [{"text": "Test source", "link": "https://example.com"}]
    )
    mock_rag.get_course_analytics.return_value = {
        "total_courses": 1,
        "course_titles": ["Test Course"]
    }
    
    # Mock session manager
    mock_rag.session_manager = Mock()
    mock_rag.session_manager.create_session.return_value = "test_session_123"
    mock_rag.session_manager.clear_session.return_value = None
    
    return mock_rag


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing"""
    mock_config = Mock()
    mock_config.ANTHROPIC_API_KEY = "test_api_key"
    mock_config.ANTHROPIC_MODEL = "claude-3-haiku-20240307"
    mock_config.CHUNK_SIZE = 800
    mock_config.CHUNK_OVERLAP = 100
    mock_config.MAX_RESULTS = 5
    mock_config.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    mock_config.COLLECTION_NAME_CONTENT = "course_content"
    mock_config.COLLECTION_NAME_CATALOG = "course_catalog"
    mock_config.CHROMA_PATH = ":memory:"
    return mock_config


@pytest.fixture
def test_app():
    """Create a test FastAPI app without static file mounting"""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from pydantic import BaseModel
    from typing import List, Optional, Union
    
    # Create test app without static files
    app = FastAPI(title="Test Course Materials RAG System", root_path="")
    
    # Add middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    
    # Import models
    class SourceItem(BaseModel):
        text: str
        link: Optional[str] = None

    class QueryRequest(BaseModel):
        query: str
        session_id: Optional[str] = None

    class QueryResponse(BaseModel):
        answer: str
        sources: List[Union[str, SourceItem]]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: List[str]
    
    return app, QueryRequest, QueryResponse, CourseStats, SourceItem


@pytest.fixture
def test_client(test_app, mock_rag_system):
    """Create a test client with mocked RAG system"""
    app, QueryRequest, QueryResponse, CourseStats, SourceItem = test_app
    
    # Define endpoints using the mock RAG system
    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag_system.session_manager.create_session()
            
            answer, sources = mock_rag_system.query(request.query, session_id)
            
            return QueryResponse(
                answer=answer,
                sources=sources,
                session_id=session_id
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"]
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/sessions/{session_id}/clear")
    async def clear_session(session_id: str):
        try:
            mock_rag_system.session_manager.clear_session(session_id)
            return {"message": "Session cleared successfully", "session_id": session_id}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/")
    async def read_root():
        return {"message": "Course Materials RAG System"}
    
    return TestClient(app)


@pytest.fixture
def temp_docs_dir():
    """Create a temporary directory with test documents"""
    temp_dir = tempfile.mkdtemp()
    
    # Create a test course document
    course_content = """Course Title: Machine Learning Fundamentals
Course Link: https://example.com/ml-course
Course Instructor: Dr. Jane Smith

Lesson 0: Introduction to Machine Learning
Lesson Link: https://example.com/ml-course/lesson-0
This lesson covers the basic concepts of machine learning, including supervised and unsupervised learning approaches.

Lesson 1: Linear Regression
Lesson Link: https://example.com/ml-course/lesson-1
Linear regression is a fundamental algorithm for predicting continuous values based on input features.
"""
    
    course_file = Path(temp_dir) / "ml_course.txt"
    with open(course_file, 'w', encoding='utf-8') as f:
        f.write(course_content)
    
    yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_query_data():
    """Sample query data for testing"""
    return {
        "valid_query": {
            "query": "What is machine learning?",
            "session_id": "test_session_123"
        },
        "query_without_session": {
            "query": "Explain linear regression"
        },
        "empty_query": {
            "query": "",
            "session_id": "test_session_123"
        }
    }


@pytest.fixture(autouse=True)
def mock_environment_variables():
    """Mock environment variables for testing"""
    with patch.dict(os.environ, {
        'ANTHROPIC_API_KEY': 'test_api_key_12345',
        'CHROMA_PATH': ':memory:',
    }):
        yield


@pytest.fixture
def mock_search_results():
    """Mock search results for testing"""
    return [
        {
            "text": "Machine learning is a subset of artificial intelligence.",
            "course_title": "AI Fundamentals",
            "lesson_number": 1,
            "lesson_title": "Introduction to ML",
            "lesson_link": "https://example.com/ai/lesson-1",
            "course_link": "https://example.com/ai-course",
            "distance": 0.15
        },
        {
            "text": "Supervised learning uses labeled training data.",
            "course_title": "AI Fundamentals", 
            "lesson_number": 2,
            "lesson_title": "Supervised Learning",
            "lesson_link": "https://example.com/ai/lesson-2",
            "course_link": "https://example.com/ai-course",
            "distance": 0.25
        }
    ]