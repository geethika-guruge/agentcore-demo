#!/bin/bash

set -e

echo "🧪 Testing agent with grocery list..."

cd "$(dirname "$0")/../agentcore/runtime"

agentcore invoke '{
    "grocery_items": [
        "Grocery List",
        "2 Full Cream Milk",
        "1 Bread",
        "12 Eggs",
        "5 Apples",
        "1 kg Chicken",
        "2 kg Rice",
        "6 Tomatoes",
        "500g Cheese",
        "1 Butter",
        "1 Coffee"
    ]
}'
