#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "Usage:"
echo "  ./run.sh          — run once and send to Feishu"
echo "  ./run.sh dry      — run once, print report, skip Feishu"
echo "  ./run.sh schedule — run now then every Monday 09:00 CST"
echo ""

case "${1:-}" in
  dry)      python main.py --dry-run ;;
  schedule) python main.py --schedule ;;
  *)        python main.py ;;
esac
