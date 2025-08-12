#!/bin/bash
# Run code quality checks

echo "🔍 Running flake8 linting..."
uv run flake8 . --statistics

echo "🧹 Checking import sorting..."
uv run isort . --check-only --diff

echo "🎨 Checking code formatting..."
uv run black . --check --diff

echo "✅ Linting complete!"