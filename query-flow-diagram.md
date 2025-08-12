# Query Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant Frontend as Frontend<br/>(script.js)
    participant API as FastAPI<br/>(app.py)
    participant RAG as RAG System<br/>(rag_system.py)
    participant Session as Session Manager<br/>(session_manager.py)
    participant AI as AI Generator<br/>(ai_generator.py)
    participant Tools as Tool Manager<br/>(search_tools.py)
    participant Vector as Vector Store<br/>(vector_store.py)
    participant Claude as Anthropic Claude<br/>(API)

    User->>Frontend: Types query & clicks send
    Frontend->>Frontend: Disable input, show loading
    Frontend->>API: POST /api/query<br/>{"query": "...", "session_id": "..."}
    
    API->>API: Parse QueryRequest
    API->>RAG: rag_system.query(query, session_id)
    
    RAG->>Session: get_conversation_history(session_id)
    Session-->>RAG: Previous messages context
    
    RAG->>AI: generate_response(query, history, tools, tool_manager)
    
    AI->>Claude: First API call<br/>System prompt + query + tools
    Claude-->>AI: Response with tool_use decision
    
    alt Claude decides to use search tool
        AI->>Tools: execute_tool("search_course_content", params)
        Tools->>Vector: search(query, course_name, lesson_number)
        
        Vector->>Vector: Resolve course name via similarity
        Vector->>Vector: Query ChromaDB with filters
        Vector-->>Tools: SearchResults with documents & metadata
        
        Tools->>Tools: Format results with course/lesson headers
        Tools-->>AI: Formatted search results string
        
        AI->>Claude: Second API call<br/>Tool results + original context
        Claude-->>AI: Final response text
    else Claude uses existing knowledge
        Claude-->>AI: Direct response text
    end
    
    AI-->>RAG: Generated response
    RAG->>Tools: get_last_sources()
    Tools-->>RAG: Source list for UI
    RAG->>Session: add_exchange(session_id, query, response)
    RAG-->>API: (response, sources)
    
    API->>API: Build QueryResponse object
    API-->>Frontend: {"answer": "...", "sources": [...], "session_id": "..."}
    
    Frontend->>Frontend: Remove loading, parse markdown
    Frontend->>Frontend: Display response + sources
    Frontend->>Frontend: Re-enable input
    Frontend-->>User: Show response with sources
```

## Flow Summary

### 1. **User Interaction**
- User enters query in chat interface
- Frontend disables input and shows loading animation

### 2. **API Request**
- POST to `/api/query` with JSON payload
- Session ID included for conversation continuity

### 3. **RAG Orchestration**
- Retrieve conversation history for context
- Pass query to AI generator with available tools

### 4. **AI Processing**
- Claude analyzes query and decides whether to search
- If search needed: executes course search tool
- If no search: uses existing knowledge

### 5. **Vector Search** (if triggered)
- Resolve course names via semantic similarity
- Query ChromaDB with course/lesson filters
- Format results with contextual headers

### 6. **Response Generation**
- Claude generates final response using search results
- Sources tracked and extracted for UI display
- Session updated with query/response pair

### 7. **Frontend Display**
- Parse markdown response for rich formatting
- Show sources in collapsible section
- Re-enable input for next query

## Key Components

- **Session Management**: Maintains conversation context
- **Tool Orchestration**: AI decides when to search vs. use knowledge  
- **Vector Search**: Semantic similarity for course/content matching
- **Source Attribution**: Track and display result origins
- **Error Handling**: Graceful fallbacks throughout the flow