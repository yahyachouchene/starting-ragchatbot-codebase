#!/bin/bash
# Format Python code using Black and isort

echo "🔧 Formatting Python code with Black..."
uv run black .

echo "📚 Sorting imports with isort..."
uv run isort .

echo "✅ Code formatting complete!"