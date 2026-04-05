#!/bin/bash
# DDNS 服务备份脚本
set -e

BACKUP_DIR="/var/backups/ddns"
DB_PATH="/var/lib/ddns-heartbeat/ddns.db"
CONFIG_PATH="/etc/ddns-heartbeat/server.json5"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

usage() {
    echo "Usage: $0 {backup|restore|list}"
    echo "  backup  - Create backup"
    echo "  restore - Restore from backup"
    echo "  list    - List available backups"
    exit 1
}

do_backup() {
    echo "Creating backup..."
    mkdir -p "$BACKUP_DIR"
    
    # 备份 SQLite 数据库
    sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/db-$TIMESTAMP.sqlite'"
    
    # 备份配置文件
    cp "$CONFIG_PATH" "$BACKUP_DIR/config-$TIMESTAMP.json5"
    
    # 保留 30 天备份
    find "$BACKUP_DIR" -name "*.sqlite" -mtime +30 -delete
    find "$BACKUP_DIR" -name "*.json5" -mtime +30 -delete
    
    echo "Backup created: $BACKUP_DIR/db-$TIMESTAMP.sqlite"
}

do_restore() {
    if [ -z "$1" ]; then
        echo "Error: Please specify backup timestamp (e.g., 20260405_120000)"
        exit 1
    fi
    
    BACKUP_TS="$1"
    
    # 恢复前先备份当前状态
    echo "Creating pre-restore backup..."
    do_backup
    
    echo "Stopping ddns-server service..."
    systemctl stop ddns-server
    
    echo "Restoring SQLite database..."
    sqlite3 "$DB_PATH" ".restore '$BACKUP_DIR/db-$BACKUP_TS.sqlite'"
    
    echo "Restoring configuration..."
    cp "$BACKUP_DIR/config-$BACKUP_TS.json5" "$CONFIG_PATH"
    
    echo "Starting ddns-server service..."
    systemctl start ddns-server
    
    echo "Verifying service..."
    sleep 2
    curl -k https://localhost:8989/health && echo "Restore successful!" || echo "Restore failed!"
}

do_list() {
    echo "Available backups:"
    ls -la "$BACKUP_DIR"/*.sqlite 2>/dev/null | awk '{print $9}' | sed 's|.*/db-||;s|\.sqlite||'
}

# 权限检查
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

case "$1" in
    backup) do_backup ;;
    restore) do_restore "$2" ;;
    list) do_list ;;
    *) usage ;;
esac
