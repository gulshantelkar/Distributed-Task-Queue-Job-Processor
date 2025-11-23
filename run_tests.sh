#!/bin/bash
# Script to run tests in Docker

set -e

echo "🧪 Running tests in Docker..."
echo ""

# Check if Docker containers are running
if ! docker compose ps | grep -q "taskqueue_web.*Up"; then
    echo "❌ Error: Docker containers are not running!"
    echo "Please start the containers first with: docker compose up -d"
    exit 1
fi

# Run tests
echo "Running test suite..."
docker compose exec web python manage.py test --verbosity=2

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed!"
else
    echo ""
    echo "❌ Some tests failed!"
    exit 1
fi

