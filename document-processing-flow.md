# Document Processing Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INPUT: Course Document                          │
│                              (*.txt file)                               │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Read File Content    │
                    │  (UTF-8 encoding)      │
                    └────────────┬───────────┘
                                 │
                                 ▼
        ┌────────────────────────────────────────────────────────┐
        │           METADATA EXTRACTION (Lines 1-4)              │
        │  ┌──────────────────────────────────────────────────┐  │
        │  │ Regex Parse:                                     │  │
        │  │  • Course Title: [name]                          │  │
        │  │  • Course Link: [url]                            │  │
        │  │  • Course Instructor: [instructor]               │  │
        │  └──────────────────────────────────────────────────┘  │
        └────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │ Course Object  │
                        │  - title       │
                        │  - link        │
                        │  - instructor  │
                        │  - lessons: [] │
                        └────────┬───────┘
                                 │
                                 ▼
        ┌────────────────────────────────────────────────────────┐
        │         LESSON PARSING (Remaining Content)             │
        │  ┌──────────────────────────────────────────────────┐  │
        │  │ For each "Lesson N: [title]" marker:            │  │
        │  │  1. Extract lesson number & title               │  │
        │  │  2. Check for optional "Lesson Link:"           │  │
        │  │  3. Accumulate content until next lesson        │  │
        │  │  4. Create Lesson object                        │  │
        │  └──────────────────────────────────────────────────┘  │
        └────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   TEXT CHUNKING        │
                    │  (per lesson content)  │
                    └────────────┬───────────┘
                                 │
                ┌────────────────┴────────────────┐
                │                                 │
                ▼                                 ▼
    ┌───────────────────────┐       ┌───────────────────────┐
    │ Sentence Splitting    │       │   Chunk Building      │
    │ • Regex-based         │──────▶│ • Max: 800 chars      │
    │ • Handles abbrev.     │       │ • Overlap: 100 chars  │
    │ • Preserve boundaries │       │ • Sentence-aware      │
    └───────────────────────┘       └───────────┬───────────┘
                                                │
                                                ▼
                                    ┌───────────────────────┐
                                    │  Add Context Prefix   │
                                    │ First chunk:          │
                                    │  "Lesson N content:"  │
                                    │ Later chunks:         │
                                    │  "Course X Lesson N"  │
                                    └───────────┬───────────┘
                                                │
                                                ▼
        ┌───────────────────────────────────────────────────────┐
        │              CREATE COURSE CHUNKS                     │
        │  ┌─────────────────────────────────────────────────┐  │
        │  │ CourseChunk {                                   │  │
        │  │   content: "Course X Lesson N content: ..."    │  │
        │  │   course_title: "Building Towards..."          │  │
        │  │   lesson_number: 0                             │  │
        │  │   chunk_index: 0, 1, 2...                      │  │
        │  │ }                                               │  │
        │  └─────────────────────────────────────────────────┘  │
        └────────────────────────┬──────────────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                │                                 │
                ▼                                 ▼
    ┌───────────────────────┐       ┌───────────────────────────┐
    │  ChromaDB Collection  │       │   ChromaDB Collection     │
    │  "course_catalog"     │       │   "course_content"        │
    │                       │       │                           │
    │  • Course metadata    │       │  • Chunk content          │
    │  • Title              │       │  • Course title (filter)  │
    │  • Instructor         │       │  • Lesson # (filter)      │
    │  • Links              │       │  • Chunk index            │
    │  • Lesson list        │       │  • Vector embeddings      │
    └───────────────────────┘       └───────────────────────────┘
                                                │
                                                ▼
                                    ┌───────────────────────┐
                                    │   READY FOR SEARCH    │
                                    │  Semantic retrieval   │
                                    │  with metadata        │
                                    │  filtering            │
                                    └───────────────────────┘
```

## Key Processing Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| Chunk Size | 800 chars | Balance context vs precision |
| Chunk Overlap | 100 chars | Maintain continuity |
| Sentence Splitting | Regex-based | Preserve semantic boundaries |
| Context Prefix | `"Course X Lesson N content:"` | Enhance retrieval accuracy |
| Collections | 2 (catalog + content) | Separate metadata from searchable text |

## Example Transformation

**Input:**
```
Course Title: Building Towards Computer Use
Course Instructor: Colt Steele

Lesson 0: Introduction
Welcome to the course. This is a 800-character lesson...
```

**Output:**
```
Course {
  title: "Building Towards Computer Use"
  instructor: "Colt Steele"
  lessons: [Lesson(0, "Introduction")]
}

CourseChunk {
  content: "Course Building Towards Computer Use Lesson 0 content: Welcome to..."
  course_title: "Building Towards Computer Use"
  lesson_number: 0
  chunk_index: 0
}
```
