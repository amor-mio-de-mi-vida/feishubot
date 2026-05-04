#!/usr/bin/env bash
# Install a weekly cron job: every Monday at 09:00 CST (01:00 UTC)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3 || command -v python)"
LOG="$SCRIPT_DIR/weekly_report.log"

CRON_LINE="0 1 * * 1 cd $SCRIPT_DIR && $PYTHON main.py >> $LOG 2>&1"

# Check if already installed
(crontab -l 2>/dev/null | grep -qF "feishubot") && {
    echo "Cron job already installed. Current crontab:"
    crontab -l | grep feishubot
    exit 0
}

# Append to existing crontab
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
echo "Cron job installed:"
echo "  $CRON_LINE"
echo "Logs will be written to: $LOG"
