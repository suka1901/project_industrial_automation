#!/usr/bin/env bash
# Builds ina700-pi.tar.gz for the Raspberry Pi. Tests first; no build if they
# fail, because a bundle from a failing tree looks exactly like a good one.
set -euo pipefail
cd "$(dirname "$0")"

echo "Running the tests..."
( cd pi && python3 -m pytest -q )

echo
echo "Building ina700-pi.tar.gz..."
tar -czf ina700-pi.tar.gz \
    --exclude='__pycache__' --exclude='.pytest_cache' \
    --exclude='*.pyc' --exclude='*.log' \
    pi \
    model/best_ncnn_model \
    model/dataset/yolo/val/images \
    model/dataset/yolo/val/labels \
    model/dataset/yolo/data.yaml \
    LAB.md

echo
printf "  ina700-pi.tar.gz   %s   junk files: %s\n" \
    "$(du -h ina700-pi.tar.gz | cut -f1)" \
    "$(tar -tzf ina700-pi.tar.gz | grep -cE '__pycache__|pytest_cache|\.pyc$|\.log$')"
