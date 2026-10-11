# Newtec FFM — Production Deployment and Hardening Guide
## Linux (Ubuntu 22.04 LTS), Nginx Reverse Proxy, SSL, and High-Concurrency Workers

---

### 1. Architectural Topology

```
             Mobile Marketers (/ff) & Web Users (HTTPS)
                                │
                                ▼
                   ┌─────────────────────────┐
                   │   Nginx (Port 443 TLS)  │
                   │   Rate Limiting & Proxy │
                   └────────────┬────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              │                                   │
              ▼                                   ▼
    ┌──────────────────┐                ┌──────────────────┐
    │  Odoo Gunicorn   │                │  Odoo Gevent     │
    │  Workers (8069)  │                │  Longpoll (8072) │
    └─────────┬────────┘                └─────────┬────────┘
              │                                   │
              └─────────────────┬─────────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │  PostgreSQL 15 Database │
                   │  Tuned Buffer Cache     │
                   └─────────────────────────┘
```

---

### 2. Single-Threaded Development vs. Production Multi-Worker Model

> [!IMPORTANT]
> The local development environment runs on Windows, where Python and Odoo run in a **single-threaded, non-forking process (`workers = 0`)**. Windows development cannot leverage pre-fork Gunicorn workers or gevent longpolling. In production Linux environments, running multi-worker mode (`workers = 4` to `8`) with Nginx TLS reverse proxying is mandatory to handle 500+ concurrent field agents.

---

### 3. Server Hardware & PostgreSQL Optimization

Recommended minimum server specifications:
- **CPU**: 4 to 8 vCPU cores
- **RAM**: 16 GB DDR4/DDR5
- **Disk**: 100+ GB NVMe SSD (high IOPS for bulk visits and audit logging)

#### PostgreSQL 15 `postgresql.conf` Tuning
```ini
# Memory Configuration for 16 GB RAM Host
shared_buffers = 4GB
effective_cache_size = 12GB
maintenance_work_mem = 1GB
work_mem = 64MB
wal_buffers = 16MB
min_wal_size = 1GB
max_wal_size = 4GB
checkpoint_completion_target = 0.9

# Connection Settings
max_connections = 120
listen_addresses = '127.0.0.1'
```

---

### 4. Production Odoo Configuration (`/etc/odoo/odoo.conf`)

```ini
[options]
admin_passwd = $2b$12$STRONG_HASHED_ADMIN_PASSWORD
db_host = 127.0.0.1
db_port = 5432
db_user = openpg
db_password = STRONG_DB_SECRET
db_name = ffm_prod
dbfilter = ^ffm_prod$
list_db = False

# Addons paths
addons_path = /opt/odoo/odoo/addons,/opt/odoo/addons,/opt/odoo/custom/field_force_management/extra_addons

# Multi-Worker Process Model
workers = 5
max_cron_threads = 2
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_request = 8192
limit_time_cpu = 120
limit_time_real = 240

# Network & Proxy
xmlrpc_port = 8069
longpolling_port = 8072
proxy_mode = True
log_level = info
logfile = /var/log/odoo/odoo-server.log
```

---

### 5. Systemd Service Unit (`/etc/systemd/system/odoo.service`)

```ini
[Unit]
Description=Newtec Odoo 14 Field Force Management
Requires=postgresql.service
After=network.target postgresql.service

[Service]
Type=simple
User=odoo
Group=odoo
ExecStart=/opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin -c /etc/odoo/odoo.conf
StandardOutput=journal+console
StandardError=journal+console
Restart=always
RestartSec=5
KillMode=mixed

[Install]
WantedBy=multi-user.target
```

Reload and enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now odoo
```

---

### 6. Nginx Reverse Proxy with TLS & HTML5 Geolocation Requirement

> [!CAUTION]
> Modern web browsers (Google Chrome, Apple Safari, Samsung Internet) **strictly block HTML5 Geolocation (`navigator.geolocation`)** on insecure connections (`http://`), except for `localhost`. Because daily field attendance requires verified GPS coordinates, **HTTPS (TLS 1.2 / 1.3) is an absolute operational requirement** for production.

Create `/etc/nginx/sites-available/ffm.conf`:

```nginx
# Rate limiting zone: max 15 requests/sec per IP, burst 30
limit_req_zone $binary_remote_addr zone=ffm_req_limit:10m rate=15r/s;

upstream odoo_backend {
    server 127.0.0.1:8069;
}

upstream odoo_chat {
    server 127.0.0.1:8072;
}

server {
    listen 80;
    server_name ffm.newtecpharma.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ffm.newtecpharma.com;

    # SSL Certificates (Let's Encrypt or Corporate Cert)
    ssl_certificate /etc/letsencrypt/live/ffm.newtecpharma.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ffm.newtecpharma.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Maximum upload size for compressed voucher attachments
    client_max_body_size 10M;

    # Proxy headers
    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;

    # Rate limiting applied to API and submit routes
    location /ff/ {
        limit_req zone=ffm_req_limit burst=30 nodelay;
        proxy_pass http://odoo_backend;
    }

    location /longpolling {
        proxy_pass http://odoo_chat;
    }

    location / {
        proxy_pass http://odoo_backend;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_cache_valid 200 60m;
        proxy_buffering on;
        expires 864000;
        proxy_pass http://odoo_backend;
    }

    gzip on;
    gzip_types text/css text/less text/plain text/xml application/xml application/json application/javascript;
}
```

Enable site and reload:
```bash
sudo ln -s /etc/nginx/sites-available/ffm.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

### 7. Automated Backups & Monitoring

1. **Daily Database Backup Cron (`/etc/cron.daily/ffm_backup.sh`)**:
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/odoo_ffm"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
pg_dump -U openpg -h 127.0.0.1 -F c -b -v -f "$BACKUP_DIR/ffm_prod_$DATE.dump" ffm_prod
# Retain last 14 days
find "$BACKUP_DIR" -type f -name "*.dump" -mtime +14 -delete
```

2. **Filestore Backup**:
Sync `/var/lib/odoo/.local/share/Odoo/filestore/ffm_prod` to secure secondary storage using `rsync` or cloud storage buckets.
