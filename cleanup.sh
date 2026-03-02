#!/usr/bin/env bash

echo "Cleaning up temporary repositories in /tmp..."
rm -rf /tmp/repgen_*

echo "Cleaning up results directory..."
rm -rf ./repgen_results/*

echo "Cleaning up Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +

echo "Cleanup complete!"
