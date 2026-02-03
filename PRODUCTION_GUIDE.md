# Production Deployment Guide

This guide covers deploying KeepGaining to a production environment using Docker.

## Prerequisites

- Docker 24.0+ and Docker Compose 2.20+
- 4GB+ RAM, 20GB+ disk space
- Linux server (Ubuntu 22.04 LTS recommended)
- Domain name (optional, for SSL)

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/your-org/keepgaining.git
cd keepgaining
```

### 2. Configure Environment

Create `.env.prod` file:

```bash
# Database
DB_USER=keepgaining
DB_PASSWORD=your_strong_password_here
DB_NAME=keepgaining
DATABASE_URL=postgresql+asyncpg://keepgaining:your_strong_password_here@db:5432/keepgaining

# Security
SECRET_KEY=your_secret_key_min_32_chars_here
REDIS_PASSWORD=your_redis_password_here

# API Keys
FYERS_API_ID=your_fyers_api_id
FYERS_SECRET_KEY=your_fyers_secret_key
UPSTOX_API_KEY=your_upstox_api_key
UPSTOX_API_SECRET=your_upstox_api_secret

# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
NEXT_PUBLIC_API_URL=https://api.your-domain.com
```

### 3. Deploy

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

## Architecture

```
┌─────────────┐
│   Nginx     │  Port 80/443 (Reverse Proxy)
└──────┬──────┘
       │
       ├─────► Frontend (Next.js)  Port 3000
       │
       ├─────► Backend (FastAPI)   Port 8000
       │
       └─────► Database (TimescaleDB) Port 5432
                Redis (Cache)        Port 6379
```

## Service Configuration

### Backend (FastAPI)

- **Image**: Python 3.12 slim
- **Workers**: 4 (configurable)
- **Resources**: 1-2 CPU, 1-2GB RAM
- **Health Check**: HTTP GET /health every 30s

### Frontend (Next.js)

- **Image**: Node 20 Alpine
- **Mode**: Production SSR
- **Resources**: 0.5-1 CPU, 512MB-1GB RAM
- **Health Check**: HTTP GET /api/health every 30s

### Database (TimescaleDB)

- **Image**: TimescaleDB Latest (PostgreSQL 15)
- **Resources**: 1-2 CPU, 2-4GB RAM
- **Backups**: Daily automated backups with 30-day retention
- **Volume**: Persistent storage at `/var/lib/postgresql/data`

### Redis (Cache & Pub/Sub)

- **Image**: Redis 7 Alpine
- **Memory**: 512MB with LRU eviction
- **Persistence**: AOF + RDB snapshots
- **Volume**: Persistent storage at `/data`

### Nginx (Reverse Proxy)

- **Features**: 
  - Rate limiting (10 req/s API, 50 req/s general)
  - Gzip compression
  - WebSocket support
  - SSL/TLS ready (uncomment in config)
  - Security headers

## SSL/TLS Configuration

### Using Let's Encrypt

1. Install certbot:
```bash
sudo apt-get install certbot
```

2. Generate certificates:
```bash
sudo certbot certonly --standalone -d your-domain.com -d api.your-domain.com
```

3. Copy certificates:
```bash
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/key.pem
```

4. Uncomment SSL configuration in `nginx/nginx.conf`

5. Restart Nginx:
```bash
docker-compose -f docker-compose.prod.yml restart nginx
```

## Backup & Restore

### Automated Backups

Backups run daily at midnight and are stored in `./backups/` with 30-day retention.

### Manual Backup

```bash
docker-compose -f docker-compose.prod.yml exec db pg_dump \
  -U keepgaining keepgaining | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore from Backup

```bash
gunzip < backup_20240101.sql.gz | docker-compose -f docker-compose.prod.yml exec -T db \
  psql -U keepgaining keepgaining
```

## Monitoring

### View Logs

```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f backend

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail=100
```

### Service Health

```bash
# Check all services
docker-compose -f docker-compose.prod.yml ps

# Check specific service
docker-compose -f docker-compose.prod.yml exec backend python -c "import requests; print(requests.get('http://localhost:8000/health').json())"
```

### Resource Usage

```bash
# CPU and Memory
docker stats

# Disk usage
docker system df
```

## Maintenance

### Update Application

```bash
git pull origin main
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d
```

### Scale Services

```bash
# Scale backend to 3 instances
docker-compose -f docker-compose.prod.yml up -d --scale backend=3
```

### Clean Up

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Full cleanup
docker system prune -a --volumes
```

## Security Best Practices

1. **Change Default Passwords**: Never use default passwords in production
2. **Use SSL/TLS**: Always enable HTTPS for production
3. **Firewall Rules**: Only expose ports 80 and 443 to the internet
4. **Regular Updates**: Keep Docker images and dependencies updated
5. **Secrets Management**: Use Docker secrets or environment files (never commit secrets)
6. **Rate Limiting**: Configure appropriate rate limits in Nginx
7. **Monitoring**: Set up alerts for service failures and resource exhaustion

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs backend

# Check resource usage
docker stats

# Verify environment variables
docker-compose -f docker-compose.prod.yml config
```

### Database Connection Issues

```bash
# Test database connection
docker-compose -f docker-compose.prod.yml exec db psql -U keepgaining -d keepgaining -c "SELECT 1;"

# Check database logs
docker-compose -f docker-compose.prod.yml logs db
```

### Redis Connection Issues

```bash
# Test Redis connection
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# Check Redis stats
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO
```

### Out of Memory

1. Increase Docker memory limits in `docker-compose.prod.yml`
2. Scale down worker processes
3. Enable Redis memory limits and eviction

### High CPU Usage

1. Check for infinite loops in logs
2. Reduce number of workers
3. Implement better caching strategies

## Performance Optimization

### Database

```sql
-- Create indexes on frequently queried columns
CREATE INDEX idx_trades_timestamp ON trades(timestamp);
CREATE INDEX idx_positions_symbol ON positions(symbol);

-- Enable query timing
ALTER DATABASE keepgaining SET log_min_duration_statement = 1000;
```

### Redis

```bash
# Monitor slow queries
docker-compose -f docker-compose.prod.yml exec redis redis-cli SLOWLOG GET 10

# Check memory usage
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory
```

### Application

- Enable HTTP/2 in Nginx (requires SSL)
- Use CDN for static assets
- Implement application-level caching
- Optimize database queries

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/keepgaining/issues
- Documentation: https://docs.keepgaining.com
- Email: support@keepgaining.com
