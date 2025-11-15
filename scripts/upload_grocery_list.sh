#!/bin/bash

set -e

echo "📄 Generating and uploading grocery list..."

cd "$(dirname "$0")/.."

cd assets && python upload_grocery_list.py

echo ""
echo "✅ Done!"
