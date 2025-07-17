#!/bin/bash
# RefServer Docker Build and Push Script
# Builds Docker image with version tag and latest, then pushes to Docker Hub

set -e  # Exit on any error

# Configuration
DOCKER_USERNAME="honestjung"
IMAGE_NAME="refserverlite"

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Read version from VERSION file
VERSION_FILE="$PROJECT_ROOT/VERSION"
if [ -f "$VERSION_FILE" ]; then
    VERSION=$(cat "$VERSION_FILE" | tr -d '\n\r ')
    echo -e "${BLUE}📋 Version read from VERSION file: ${VERSION}${NC}"
else
    echo -e "${RED}❌ VERSION file not found at: $VERSION_FILE${NC}"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 RefServer Docker Build and Push Script${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Project root already set above

echo -e "${YELLOW}📁 Project root: ${PROJECT_ROOT}${NC}"
echo -e "${YELLOW}🏷️  Building image: ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}${NC}"
echo ""

# Change to project root directory
cd "$PROJECT_ROOT"

# Build Docker image with both version and latest tags
echo -e "${BLUE}🔨 Building Docker image...${NC}"
docker build \
    -t "${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}" \
    -t "${DOCKER_USERNAME}/${IMAGE_NAME}:latest" \
    .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Docker image built successfully!${NC}"
else
    echo -e "${RED}❌ Docker build failed!${NC}"
    exit 1
fi

echo ""

# Check if user is logged in to Docker Hub
echo -e "${BLUE}🔐 Checking Docker Hub authentication...${NC}"
if ! docker info | grep -q "Username"; then
    echo -e "${YELLOW}⚠️  Not logged in to Docker Hub. Please log in:${NC}"
    docker login
fi

echo ""

# Push both tags to Docker Hub
echo -e "${BLUE}📤 Pushing to Docker Hub...${NC}"

echo -e "${YELLOW}Pushing ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}...${NC}"
docker push "${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"

echo -e "${YELLOW}Pushing ${DOCKER_USERNAME}/${IMAGE_NAME}:latest...${NC}"
docker push "${DOCKER_USERNAME}/${IMAGE_NAME}:latest"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}🎉 Successfully built and pushed Docker images!${NC}"
    echo ""
    echo -e "${GREEN}📋 Images pushed:${NC}"
    echo -e "   • ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"
    echo -e "   • ${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
    echo ""
    echo -e "${BLUE}🚀 Usage:${NC}"
    echo -e "   docker pull ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"
    echo -e "   docker pull ${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
    echo ""
else
    echo -e "${RED}❌ Docker push failed!${NC}"
    exit 1
fi