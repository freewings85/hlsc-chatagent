#!/bin/bash
set -e

cd "$(dirname "$0")/.."

docker buildx build -f docker/Dockerfile.server -t chatagent_server:1.0.0 .
docker buildx build -f docker/Dockerfile.web -t chatagent_web:1.0.0 web/

echo "构建完成: chatagent_server:1.0.0, chatagent_web:1.0.0"
