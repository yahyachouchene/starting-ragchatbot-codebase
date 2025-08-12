#!/bin/bash
# Run all code quality checks

set -e  # Exit on first error

echo "🚀 Running comprehensive code quality checks..."
echo "=================================================="

echo ""
echo "1️⃣  Checking code formatting..."
./scripts/lint.sh

echo ""
echo "2️⃣  Running type checks..."
./scripts/typecheck.sh

echo ""
echo "🎉 All quality checks passed!"