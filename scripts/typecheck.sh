#!/bin/bash
# Run type checking with mypy

echo "🔧 Running type checking with mypy..."
uv run mypy backend/ --exclude backend/tests/ --exclude backend/test_pipeline_architecture.py

echo "✅ Type checking complete!"