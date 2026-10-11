# Newtec FFM — Installation and Upgrade Guide
## Odoo 14 Community Edition (Python 3.9 + PostgreSQL 15)

---

### 1. Prerequisites and System Requirements

- **Operating System**: Windows (Development) or Linux Ubuntu 22.04 LTS (Production)
- **Python**: Python 3.9.x (ensure virtual environment is active if applicable)
- **PostgreSQL**: PostgreSQL 15.x
- **Odoo Version**: Odoo 14.0 Community Edition
- **PDF Engine**: `wkhtmltopdf` 0.12.5 or 0.12.6 with patched qt
- **Bengali Fonts**: `SolaimanLipi` or `fonts-beng` / `fonts-noto-bengali` installed on the host OS for proper PDF rendering.

---

### 2. Configuration File Setup

Copy `odoo.conf.example` to `odoo.conf` and update paths and credentials:

```ini
[options]
admin_passwd = <STRONG_MASTER_PASSWORD>
db_host = localhost
db_port = 5432
db_user = openpg
db_password = <DB_PASSWORD>
addons_path = D:\Software\Odoo\odoo\odoo\addons,D:\Software\Odoo\odoo\addons,D:\Software\field_force_management\extra_addons
http_port = 8069
```

> [!WARNING]
> Never commit `odoo.conf` containing real passwords or Geoapify API keys to version control. Maintain only `odoo.conf.example` in git.

---

### 3. Fresh Installation Procedure

#### Step 1: Create PostgreSQL Database
```powershell
# Windows PowerShell
& "C:\Program Files\PostgreSQL\15\bin\createdb.exe" -U openpg -h localhost -E UTF8 ffm_prod
```
```bash
# Linux
sudo -u postgres createdb -O openpg -E UTF8 ffm_prod
```

#### Step 2: Initialize Base Odoo Modules and FFM
```powershell
py -3.9 "D:\Software\Odoo\odoo\odoo-bin" -c "odoo.conf" -d ffm_prod -i base,web,hr,account,mail -i field_force_management,ffm_daily_report --stop-after-init
```

---

### 4. Zero-Downtime Safe Upgrade Procedure

When deploying new code or model updates, execute an in-place module upgrade with `-u ffm_daily_report`. This maintains all existing transactional data (attendance, daily reports, visits, expenses, and statements) and automatically creates missing columns, database indexes, and access rights.

```powershell
# Windows
py -3.9 "D:\Software\Odoo\odoo\odoo-bin" -c "odoo.conf" -d ffm_prod -u ffm_daily_report --stop-after-init
```
```bash
# Linux (Production)
python3 odoo-bin -c /etc/odoo/odoo.conf -d ffm_prod -u ffm_daily_report --stop-after-init
```

---

### 5. Post-Installation Configuration Checklist

1. **System Allowance Rates (`ffm.allowance.rate`)**:
   - Navigate to: **Field Force Management > Configuration > Allowance Rates**.
   - Create entries for each designation (e.g. `Medical Information Officer`: DA Tk 250/day, Motorcycle Maintenance Tk 1,500/month; `Area Sales Manager`: DA Tk 350/day, etc.).

2. **Fare Configuration (`ffm.fare.config`)**:
   - Navigate to: **Field Force Management > Configuration > Fare Slabs**.
   - Ensure slab fares exist for transport modes: `motorcycle`, `bus`, `cng`, `rickshaw`, `train`, `walking`.

3. **Territory and Working Places (`ffm.place`)**:
   - Navigate to: **Field Force Management > Master Data > Places**.
   - Import or add key company branches, market hubs, upazilas, and headquarters with latitude and longitude.

4. **Employee Setup & Organization Hierarchy**:
   - In **Employees (`hr.employee`)**, ensure each field worker has:
     - Linked Odoo Login User (`user_id`).
     - Designation (`job_id`).
     - Branch / HQ (`branch_id`).
     - Direct Manager (`parent_id`) pointing to their immediate supervisor (Field Person -> ASM -> RSM -> NSM).
     - Security group assigned in **Settings > Users & Companies > Users**.

5. **App Settings (`res.config.settings`)**:
   - Navigate to: **Field Force Management > Settings**.
   - Verify App Title (`Newtec FFM`), Travel Auto Bill toggle (default unchecked), and Hierarchy Scope switch.

---

### 6. Verification & Automated Test Run

To verify installation integrity on a test database:
```powershell
py -3.9 "D:\Software\Odoo\odoo\odoo-bin" -c "odoo.conf" -d ffm_test -u ffm_daily_report --test-enable --test-tags=/ffm_daily_report --stop-after-init
```
Expected result: **0 failed, 0 errors**.
