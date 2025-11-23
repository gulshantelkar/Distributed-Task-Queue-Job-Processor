# Makefile for Task Queue Project

.PHONY: help install migrate run worker test clean docker-up docker-down

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements.txt

migrate:  ## Run database migrations
	python manage.py migrate

makemigrations:  ## Create new migrations
	python manage.py makemigrations

createsuperuser:  ## Create Django superuser
	python manage.py createsuperuser

collectstatic:  ## Collect static files
	python manage.py collectstatic --noinput

run:  ## Run development server
	python manage.py runserver

channels:  ## Run Channels/Daphne server
	daphne -b 127.0.0.1 -p 8001 taskqueue.asgi:application

worker:  ## Run a worker
	python manage.py run_worker

worker-multi:  ## Run 3 workers
	python manage.py run_worker --worker-id worker-1 & \
	python manage.py run_worker --worker-id worker-2 & \
	python manage.py run_worker --worker-id worker-3

shell:  ## Open Django shell
	python manage.py shell

test:  ## Run tests
	python manage.py test

clean:  ## Clean Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".DS_Store" -delete

docker-build:  ## Build Docker images
	docker-compose build

docker-up:  ## Start all services with Docker
	docker-compose up

docker-up-d:  ## Start all services with Docker (detached)
	docker-compose up -d

docker-down:  ## Stop all Docker services
	docker-compose down

docker-logs:  ## View Docker logs
	docker-compose logs -f

docker-shell:  ## Open shell in web container
	docker-compose exec web python manage.py shell

docker-migrate:  ## Run migrations in Docker
	docker-compose exec web python manage.py migrate

docker-createsuperuser:  ## Create superuser in Docker
	docker-compose exec web python manage.py createsuperuser

docker-restart:  ## Restart Docker services
	docker-compose restart

docker-clean:  ## Remove Docker containers and volumes
	docker-compose down -v

docker-test:  ## Run tests in Docker
	docker compose exec web python manage.py test --verbosity=2

docker-test-fast:  ## Run tests in Docker (less verbose)
	docker compose exec web python manage.py test

docker-test-coverage:  ## Run tests with coverage report in Docker
	docker compose exec web python manage.py test --verbosity=2 --parallel

setup:  ## Initial setup (install + migrate)
	make install
	make migrate

dev:  ## Start development environment (server + worker)
	@echo "Starting development environment..."
	@echo "Starting web server..."
	python manage.py runserver & \
	echo "Starting worker..." && \
	python manage.py run_worker

