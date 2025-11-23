#!/bin/bash

# Setup script for Task Queue system
# This script helps set up the development environment

set -e

echo "🚀 Task Queue Setup Script"
echo "=========================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Found Python $python_version"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"
echo ""

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp env_template.txt .env
    echo "✓ .env file created"
    echo "⚠️  Please edit .env file with your database credentials"
else
    echo "✓ .env file already exists"
fi
echo ""

# Check if PostgreSQL is running
echo "Checking PostgreSQL connection..."
if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo "✓ PostgreSQL is running"
    
    # Run migrations
    echo ""
    echo "Running database migrations..."
    python manage.py migrate
    echo "✓ Migrations completed"
    
    # Create superuser prompt
    echo ""
    read -p "Do you want to create a Django superuser? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python manage.py createsuperuser
    fi
    
    # Create tenant prompt
    echo ""
    read -p "Do you want to create a test tenant? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python manage.py shell <<EOF
from tenants.models import Tenant
import sys

try:
    tenant = Tenant.objects.create(
        name="Test Company",
        email="test@example.com",
        max_concurrent_jobs=5,
        max_jobs_per_minute=10,
        max_jobs_per_hour=100
    )
    print("\n✓ Test tenant created successfully!")
    print(f"\nAPI Key: {tenant.api_key}")
    print("\n⚠️  Save this API key! You'll need it to submit jobs.")
except Exception as e:
    print(f"\n✗ Error creating tenant: {e}")
    sys.exit(1)
EOF
    fi
else
    echo "⚠️  PostgreSQL is not running"
    echo ""
    echo "Options:"
    echo "1. Start PostgreSQL locally"
    echo "2. Use Docker: docker-compose up -d db"
    echo "3. Update .env with remote database credentials"
    echo ""
    echo "After PostgreSQL is running, run: python manage.py migrate"
fi

echo ""
echo "=========================="
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Start the web server: python manage.py runserver"
echo "2. Start a worker: python manage.py run_worker"
echo "3. Open dashboard: http://localhost:8000"
echo "4. Or use Docker: docker-compose up"
echo ""
echo "For more information, see README.md"

