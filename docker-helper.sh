#!/bin/bash
# ============================================================================
# Docker Helper Script for API Lifecycle Service
# Provides convenient commands for managing Docker containers
# ============================================================================

set -e

COMPOSE_FILE="Docker/docker-compose.yml"
COMPOSE_DEV_FILE="Docker/docker-compose.dev.yml"
PROJECT_NAME="api-lifecycle-service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Command functions
cmd_start() {
    print_header "Starting Services (Production)"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME up -d
    print_success "Services started successfully"
    cmd_status
}

cmd_start_dev() {
    print_header "Starting Services (Development)"
    docker-compose -f $COMPOSE_DEV_FILE -p "${PROJECT_NAME}-dev" up -d
    print_success "Development services started successfully"
    docker-compose -f $COMPOSE_DEV_FILE -p "${PROJECT_NAME}-dev" ps
}

cmd_stop() {
    print_header "Stopping Services"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME stop
    print_success "Services stopped successfully"
}

cmd_down() {
    print_header "Removing Services"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down
    print_success "Services removed successfully"
}

cmd_restart() {
    print_header "Restarting Services"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME restart
    print_success "Services restarted successfully"
}

cmd_logs() {
    SERVICE=${1:-app}
    print_header "Showing logs for: $SERVICE"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f $SERVICE
}

cmd_status() {
    print_header "Service Status"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME ps
}

cmd_build() {
    print_header "Building Docker Image"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME build --no-cache
    print_success "Build completed successfully"
}

cmd_shell() {
    SERVICE=${1:-app}
    print_header "Opening shell in: $SERVICE"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME exec $SERVICE /bin/sh
}

cmd_db_shell() {
    print_header "Opening PostgreSQL shell"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME exec postgres psql -U apiuser -d api_lifecycle_db
}

cmd_redis_cli() {
    print_header "Opening Redis CLI"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME exec redis redis-cli
}

cmd_clean() {
    print_header "Cleaning up Docker resources"
    read -p "This will remove all containers, volumes, and images. Continue? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down -v
        docker system prune -f
        print_success "Cleanup completed"
    else
        print_warning "Cleanup cancelled"
    fi
}

cmd_health() {
    print_header "Health Check"
    
    echo "Checking services..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME ps
    
    echo ""
    echo "Checking application health..."
    curl -s http://localhost:8000/health | jq . || echo "Application not responding"
    
    echo ""
    echo "Checking PostgreSQL..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME exec -T postgres pg_isready -U apiuser || echo "PostgreSQL not ready"
    
    echo ""
    echo "Checking Redis..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME exec -T redis redis-cli ping || echo "Redis not responding"
}

cmd_migrate() {
    print_header "Running Database Migrations"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME exec app alembic upgrade head
    print_success "Migrations completed"
}

cmd_test() {
    print_header "Running Tests"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME exec app pytest tests/ -v
}

cmd_help() {
    print_header "Docker Helper Commands"
    cat << EOF

Usage: ./docker-helper.sh [command]

Available commands:

  Production Commands:
    start       - Start all services (production)
    stop        - Stop all services
    down        - Stop and remove all containers
    restart     - Restart all services
    build       - Rebuild Docker images
    
  Development Commands:
    start-dev   - Start services in development mode (with hot reload)
    
  Monitoring Commands:
    status      - Show status of all services
    logs [svc]  - Show logs (default: app, or specify: postgres, redis)
    health      - Run health checks on all services
    
  Shell Access:
    shell [svc] - Open shell in container (default: app)
    db-shell    - Open PostgreSQL shell
    redis-cli   - Open Redis CLI
    
  Maintenance Commands:
    migrate     - Run database migrations
    test        - Run test suite
    clean       - Remove all containers, volumes, and images
    
  Help:
    help        - Show this help message

Examples:
  ./docker-helper.sh start
  ./docker-helper.sh logs app
  ./docker-helper.sh shell
  ./docker-helper.sh health

EOF
}

# Main command dispatcher
case "${1:-help}" in
    start)
        cmd_start
        ;;
    start-dev)
        cmd_start_dev
        ;;
    stop)
        cmd_stop
        ;;
    down)
        cmd_down
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs ${2:-app}
        ;;
    status)
        cmd_status
        ;;
    build)
        cmd_build
        ;;
    shell)
        cmd_shell ${2:-app}
        ;;
    db-shell)
        cmd_db_shell
        ;;
    redis-cli)
        cmd_redis_cli
        ;;
    clean)
        cmd_clean
        ;;
    health)
        cmd_health
        ;;
    migrate)
        cmd_migrate
        ;;
    test)
        cmd_test
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        print_error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
