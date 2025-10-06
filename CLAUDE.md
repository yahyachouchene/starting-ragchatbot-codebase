# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

- **Start app**: `./run.sh` (serves on port 8001)
- **Run tests**: `uv run pytest`
- **Format code**: `./scripts/format.sh`
- **Quality checks**: `./scripts/quality-check.sh`
- **Clear vector DB**: `rm -rf backend/chroma_db`

## Development Commands

### Running the Application
```bash
# Quick start (recommended)
chmod +x run.sh && ./run.sh

# Manual start
cd backend && uv run uvicorn app:app --reload --port 8001
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

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest backend/tests/test_api_endpoints.py

# Run specific test class
uv run pytest backend/tests/test_api_endpoints.py::TestQueryEndpoint

# Run specific test function
uv run pytest backend/tests/test_api_endpoints.py::TestQueryEndpoint::test_query_with_session_id

# Run with verbose output
uv run pytest -v

# Run with coverage (if configured)
uv run pytest --cov=backend
```

### Code Quality Tools
```bash
# Format code with Black and sort imports with isort
./scripts/format.sh

# Run linting checks (flake8, import sorting, formatting)
./scripts/lint.sh

# Run type checking with mypy
./scripts/typecheck.sh

# Run all quality checks (lint + typecheck)
./scripts/quality-check.sh

# Manual commands (if needed)
uv run black .              # Format code
uv run isort .              # Sort imports
uv run flake8 .             # Lint code
uv run mypy backend/        # Type check
```

### Environment Setup
Create `.env` file in root with:
```
ANTHROPIC_API_KEY=your_api_key_here
```

Application serves at:
- Web Interface: `http://localhost:8001`
- API Documentation: `http://localhost:8001/docs`

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

The AI uses two main tools:
1. `search_course_content` - Semantic search with parameters:
   - `query`: What to search for in course content
   - `course_name`: Optional course filter (supports partial matching)
   - `lesson_number`: Optional lesson number filter

2. `get_course_outline` - Retrieve course metadata and lesson structure:
   - `course_name`: Course title or partial title

Claude autonomously decides whether to search based on query content.

## Important Implementation Notes

### Startup Behavior
- Server automatically loads documents from `docs/` folder on startup (`app.py:109`)
- Existing courses are not re-processed (checks course titles to avoid duplicates)
- Documents must be `.pdf`, `.docx`, or `.txt` format

### Data Persistence
- ChromaDB data persisted in `backend/chroma_db/` directory
- Session data is in-memory only (lost on restart)
- No user authentication or data isolation between sessions

## Component Interaction Flow

Request flow for queries:

1. **FastAPI Endpoint** (`app.py:69`) receives POST to `/api/query`
2. **Session Manager** creates or retrieves session ID
3. **RAG System** (`rag_system.py:122`) orchestrates:
   - Retrieves conversation history from session
   - Passes query + history + tool definitions to AI Generator
4. **AI Generator** calls Claude API with:
   - User query
   - Conversation history (last 2 exchanges)
   - Tool definitions (search_course_content, get_course_outline)
5. **Claude Decision**: Choose to search OR answer directly
6. **If Search Needed**:
   - Tool Manager executes tool (CourseSearchTool or CourseOutlineTool)
   - Vector Store performs semantic search:
     - Fuzzy match course name in `course_catalog` collection
     - Search content in `course_content` with filters
   - Returns formatted results to Claude
   - Claude generates final answer with context
7. **Response Assembly**:
   - Answer + sources returned to user
   - Conversation saved to session history
   - Sources include lesson links for attribution

## Tool System Architecture

The system uses Anthropic's tool calling (function calling) pattern:

**Available Tools**:
1. `search_course_content` - Semantic search with optional course/lesson filters
2. `get_course_outline` - Retrieve course metadata and lesson structure

**Tool Manager** (`search_tools.py`):
- Abstract `Tool` base class defines interface
- Each tool provides:
  - `get_tool_definition()` - JSON schema for Claude API
  - `execute(**kwargs)` - Implementation logic
- ToolManager registers tools and routes execution

**AI Autonomy**:
- Claude decides when to search (not hardcoded)
- Principle: Maximum 1 search per query
- Tool results fed back to Claude for final synthesis

## Frontend-Backend Contract

**Query Flow** (`/api/query`):
```json
Request: {
  "query": "user question",
  "session_id": "optional_session_123"
}

Response: {
  "answer": "AI-generated response",
  "sources": ["Source 1", {"text": "Source 2", "link": "url"}],
  "session_id": "session_123"
}
```

**Sources Format**:
- Can be simple strings OR objects with `{text, link}`
- Links point to specific lessons when available
- Frontend renders markdown and makes links clickable

## Adding New Course Documents

1. Place `.txt` file in `docs/` folder with required format
2. Restart server (documents loaded on startup in `app.py:109`)
3. System checks existing courses by title to avoid duplicates
4. Each course creates two database entries:
   - Metadata in `course_catalog` (for course name resolution)
   - Chunks in `course_content` (for semantic search)

To force re-indexing: `rm -rf backend/chroma_db && ./run.sh`