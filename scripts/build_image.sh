#!/bin/bash
# RefServer Docker Build Script (Local only)
# Builds Docker image with version tag and latest

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
    echo "📋 Version: $VERSION (from VERSION file)"
else
    echo "❌ VERSION file not found at: $VERSION_FILE"
    exit 1
fi

echo "🐳 Building RefServer Docker Image..."
echo "======================================"

# Project root already set above

# Change to project root
cd "$PROJECT_ROOT"

echo "📁 Building from: $PROJECT_ROOT"
echo "🏷️  Image tags: ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}, ${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
echo ""

# Build image
docker build \
    -t "${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}" \
    -t "${DOCKER_USERNAME}/${IMAGE_NAME}:latest" \
    .

echo ""
echo "✅ Docker image built successfully!"
echo ""
echo "🚀 To run locally:"
echo "   docker run -d -p 8060:8000 ${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
echo ""
echo "📤 To push to Docker Hub:"
echo "   ./scripts/build_and_push.sh"