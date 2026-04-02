#!/usr/bin/env bash
set -euo pipefail

echo "Checking legal-search API..."
cd legal-search/api
npm ci
npm run check

echo "Checking legal-search frontend..."
cd ../frontend
npm ci
npm run check
npm run build
npm run openapi:lint
npm run openapi:check
