#!/bin/sh
# 每天備份 coaching.db，保留最近 14 天，用 cron 排程執行（見
# spec/cloud_deployment.md）。只備份 coaching.db 本身——那三個 .txt/
# .json 都是設定/狀態檔，不是會累積、遺失了會痛的業務資料。
#
# 這是「VPS 本機端」的備份，本身還是跟資料庫放在同一台主機、同一顆硬碟；
# 定期把 backups/ 目錄整個下載回本機電腦，才是真正防得住「這台 VPS
# 本身掛掉」的異地備份，不能只做這一步就以為夠了。

set -eu

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$APP_DIR/backups"
RETENTION_DAYS=14

mkdir -p "$BACKUP_DIR"
cp "$APP_DIR/coaching.db" "$BACKUP_DIR/coaching_$(date +%Y%m%d_%H%M%S).db"

find "$BACKUP_DIR" -name 'coaching_*.db' -mtime "+$RETENTION_DAYS" -delete
