# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Quick start (recommended)
chmod +x run.sh && ./run.sh

# Manual start
cd backend && uv run uvicorn app:app --reload --port 8000
```

### Package Management
```bash
# Install/sync dependencies
uv sync

# Add new dependency
uv add package-name

# Clear ChromaDB vector store (if needed for fresh start)
rm -rf backend/chroma_db
```

### Environment Setup
Create `.env` file in root with:
```
ANTHROPIC_API_KEY=your_api_key_here
```

Application serves at:
- Web Interface: `http://localhost:8000`
- API Documentation: `http://localhost:8000/docs`

## Architecture Overview

This is a RAG (Retrieval-Augmented Generation) system with a FastAPI backend and vanilla JavaScript frontend.

### Core Data Flow
1. **Document Processing**: Course documents (`docs/*.txt`) are parsed into structured Course/Lesson objects with metadata (title, instructor, links)
2. **Text Chunking**: Content split into 800-character chunks with 100-character overlap using sentence boundaries
3. **Vector Storage**: Dual ChromaDB collections - `course_catalog` for metadata, `course_content` for searchable chunks
4. **Query Processing**: User queries routed through RAG system → AI Generator → Tool Manager → Vector Search
5. **AI Orchestration**: Claude decides whether to search course content or use existing knowledge via tool calling

### Key Components

**Backend Architecture** (`backend/`):
- `app.py`: FastAPI server with `/api/query` and `/api/courses` endpoints
- `rag_system.py`: Main orchestrator coordinating all components
- `document_processor.py`: Parses structured course documents and creates chunks
- `vector_store.py`: ChromaDB interface with dual collections and semantic search
- `ai_generator.py`: Anthropic Claude API wrapper with tool calling support
- `search_tools.py`: Tool definitions and execution for course content search
- `session_manager.py`: Conversation history management
- `models.py`: Pydantic models (Course, Lesson, CourseChunk)
- `config.py`: Environment-based configuration

**Frontend** (`frontend/`):
- Single-page application with chat interface
- Course statistics sidebar with collapsible sections
- Markdown rendering for AI responses
- Source attribution from vector search results

### Document Format Requirements

Course documents must follow this structure:
```
Course Title: [title]
Course Link: [optional_url]
Course Instructor: [instructor_name]

Lesson 0: Introduction
Lesson Link: [optional_lesson_url]
[lesson content...]

Lesson 1: Next Topic
[lesson content...]
```

### Vector Search Strategy

The system uses a two-phase search approach:
1. **Course Resolution**: Fuzzy matching course names via vector similarity in `course_catalog`
2. **Content Search**: Semantic search in `course_content` with course/lesson filters
3. **Context Enhancement**: Chunks prefixed with "Course X Lesson Y content:" for better retrieval

### Session Management

Conversations maintain context through:
- Session IDs generated on first query (`session_{counter}` format)
- History limited to last 2 exchanges (configurable via `MAX_HISTORY` in `config.py`)
- In-memory storage (sessions lost on server restart)
- Tool execution results tracked separately for UI source attribution

### Configuration Points

Key settings in `config.py`:
- `CHUNK_SIZE`: 800 characters (balance between context and precision)
- `CHUNK_OVERLAP`: 100 characters (maintains context continuity)
- `MAX_RESULTS`: 5 search results returned
- `EMBEDDING_MODEL`: "all-MiniLM-L6-v2" (sentence transformers)
- `ANTHROPIC_MODEL`: "claude-sonnet-4-20250514"

### Tool System Design

The AI uses a single search tool with parameters:
- `query`: What to search for in course content
- `course_name`: Optional course filter (supports partial matching)
- `lesson_number`: Optional lesson number filter

Claude autonomously decides whether to search based on query content, following the principle of one search per query maximum.

## Important Implementation Notes

### Startup Behavior
- Server automatically loads documents from `docs/` folder on startup (`app.py:89`)
- Existing courses are not re-processed (checks course titles to avoid duplicates)
- Documents must be `.pdf`, `.docx`, or `.txt` format

### Error Handling
- Vector store operations include try-catch with fallback responses
- API endpoints return structured error messages via FastAPI HTTPException
- Frontend displays error messages in chat interface

### Data Persistence
- ChromaDB data persisted in `backend/chroma_db/` directory
- Session data is in-memory only (lost on restart)
- No user authentication or data isolation between sessions