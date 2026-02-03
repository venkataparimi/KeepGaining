#!/bin/bash
# Database Backup Script for KeepGaining
# Runs daily via Docker container

set -e

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
BACKUP_FILE="${BACKUP_DIR}/keepgaining_backup_${DATE}.sql.gz"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}

echo "Starting database backup at $(date)"

# Create backup directory if it doesn't exist
mkdir -p ${BACKUP_DIR}

# Perform backup
PGPASSWORD=${POSTGRES_PASSWORD} pg_dump \
    -h ${POSTGRES_HOST} \
    -U ${POSTGRES_USER} \
    -d ${POSTGRES_DB} \
    --format=custom \
    --compress=9 \
    --verbose \
    | gzip > ${BACKUP_FILE}

if [ $? -eq 0 ]; then
    echo "Backup completed successfully: ${BACKUP_FILE}"
    
    # Get file size
    SIZE=$(du -h ${BACKUP_FILE} | cut -f1)
    echo "Backup size: ${SIZE}"
    
    # Delete old backups
    echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
    find ${BACKUP_DIR} -name "keepgaining_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
    
    echo "Backup process completed at $(date)"
else
    echo "ERROR: Backup failed at $(date)" >&2
    exit 1
fi
