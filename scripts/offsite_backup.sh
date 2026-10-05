#!/bin/sh
# 異地備份：把 scripts/backup_db.sh 每天產生在 backups/ 的資料庫備份，再上傳一份到
# Cloudflare R2（見 spec/cloud_deployment.md「異地備份」）。主機本身的 backups/ 跟
# Vultr 快照都在同一家公司，帳號或主機出事會一起不見，所以要另外存一份在別處。
#
# 用 rclone 上傳，R2 的金鑰放在主機上的 rclone 設定檔（不進版控）。上傳失敗時用
# Discord 通知，不要默默失敗——備份壞掉通常要等到真的需要還原時才會發現。
# 用 cron 排在 backup_db.sh 之後執行。

set -u

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${OFFSITE_REMOTE:-r2:coaching-backup/db}"
KEEP_DAYS=30

notify_failure() {
    url=$(head -n 1 "$APP_DIR/discord_webhook_url.txt" 2>/dev/null) || return 0
    [ -n "$url" ] || return 0
    curl -s -H "Content-Type: application/json" \
        -d "{\"content\": \"❌ 異地備份失敗：$1，請檢查主機上的 rclone 設定\"}" "$url" >/dev/null
}

if ! command -v rclone >/dev/null 2>&1; then
    notify_failure "主機上找不到 rclone"
    exit 1
fi

# 只上傳最近 3 天內產生的備份檔（已經在 R2 上的不會重傳）
if ! rclone copy "$APP_DIR/backups" "$REMOTE" --include "coaching_*.db" --max-age 72h; then
    notify_failure "上傳到 $REMOTE 失敗"
    exit 1
fi

# R2 上保留 30 天，比主機上的 14 天長
if ! rclone delete "$REMOTE" --include "coaching_*.db" --min-age "${KEEP_DAYS}d"; then
    notify_failure "清理 R2 上超過 ${KEEP_DAYS} 天的舊備份失敗"
fi
