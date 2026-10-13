#!/usr/bin/env bash
# Run Field Force Management on macOS / Linux
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PYTHON="/Users/arafathabir/Code/ERP/Odoo/.venv/bin/python3"
ODOO_BIN="/Users/arafathabir/Code/ERP/Odoo/odoo-core/odoo-bin"

echo "======================================================"
echo "Starting Field Force Management Project (Odoo 14)"
echo "======================================================"
echo "URL: http://localhost:8069"
echo "Mobile Shell: http://localhost:8069/ff"
echo "Backend: http://localhost:8069/web/login"
echo "Database: field_force_db"
echo "======================================================"

"$PYTHON" "$ODOO_BIN" -c "$DIR/odoo.conf" -d field_force_db
