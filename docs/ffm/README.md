# Newtec Pharmaceuticals Limited — Field Force Management (FFM)
## Complete Technical Architecture & System Documentation (Phases 1–7)

### 1. Executive Summary & System Overview
The Newtec Field Force Management (FFM) system is an enterprise-grade field force automation and expense management platform built within **Odoo 14 Community** (Python 3.9, PostgreSQL 15). It supports **500+ daily field representatives (Medical Information Officers / Field Persons)** across Bangladesh, handling daily attendance with GPS verification, chemist and doctor visits, farm interactions, travel and journey logging, daily operational expenses with photo vouchers, monthly expense statement generation and multi-tier approval workflows, and managerial analytics.

The platform provides two primary user interfaces:
1. **Marketer Mobile Shell (`/ff`)**: A lightweight, mobile-first responsive web application (PWA-compatible) engineered without heavy backend assets, optimized for 3G/4G field mobile devices (360px–420px viewports), featuring client UUID idempotency, double-tap guards, and offline drafts.
2. **Backend Management Console**: Odoo standard backend tailored for Area Sales Managers (ASM), Regional Sales Managers (RSM), Divisional Sales Managers (DSM), National Sales Managers / Marketing Managers (NSM/MM), Directors, and Accounts personnel.

---

### 2. Multi-Phase Architecture Breakdown

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Newtec FFM Multi-Phase Architecture                      │
└─────────────────────────────────────────────────────────────────────────────┘
  │
  ├─ Phase 1: Stabilization & Guardrails
  │    • Visit line domains (chemist & doctor customer info filtering)
  │    • Dead wizard cleanup and legacy import isolation
  │    • Direct superior approval guard on Daily Reports
  │    • Disabling chatter tracking on high-volume transactional models
  │    • Routing abstraction with non-blocking failover & local cache
  │
  ├─ Phase 2: Core Foundation & /ff Mobile Shell
  │    • Designation-wise Allowance Rates (DA per day, motorcycle monthly)
  │    • Centralized App Settings & ffm.audit.log immutable auditing
  │    • Lightweight /ff mobile UI shell (no web.assets_backend overhead)
  │    • ffm.attendance with SQL unique (employee_id, date) & Dhaka tz locking
  │
  ├─ Phase 3: Daily Field Visits & Journey Log
  │    • Get-or-create today's ffm.daily.report with mandatory Working Place
  │    • Chemist Shop Visit (Sales, Orders, Collections)
  │    • Doctor Visit (Discussion, Sample, Grade A+/A/B/C)
  │    • Farm & Other Visit (Broiler, Layer, Sonali, Cattle, Aqua, Bird Count)
  │    • Journey Slab Fare Calculation engine with local ffm.place routing
  │
  ├─ Phase 4: Daily Expenses & Voucher Attachments
  │    • ffm.daily.expense (9 voucher heads: entertainment, courier, etc.)
  │    • Client-side image compression (JPEG 1280px, ~0.7 quality)
  │    • Server-side magic-byte inspection (JPEG, PNG, WebP) & 5MB cap
  │    • Strict ir.attachment record rules tied to parent expense visibility
  │
  ├─ Phase 5: Reporting Cards & Managerial Analytics
  │    • /ff Daily & Monthly report cards (Personal, Territory Attendance)
  │    • Read-only SQL view models (_auto = False) for high performance
  │    • Pivot, graph, and drill-down views (RSM -> ASM -> FP)
  │    • Memory-efficient chunked Excel & PDF exports
  │
  ├─ Phase 6: Monthly Expense Statement & Workflow
  │    • ffm.expense.statement & ffm.expense.statement.line breakdown
  │    • 6-stage lifecycle: Draft -> Submitted -> Checked -> Approved -> Paid
  │    • Reject Wizard with mandatory reason (ffm.expense.statement.reject.wizard)
  │    • Automated DA and TA aggregation with designation rate engine
  │    • Bengali-compatible PDF statement rendering
  │
  └─ Phase 7: Hardening, Performance Proof & Verification
       • Mobile touch targets (>= 44px) and input sizing (16px, iOS zoom prevention)
       • High-scale seed script (500 employees, 12 months operations, 250k+ records)
       • PostgreSQL EXPLAIN ANALYZE validation (<300ms submits, <1s reports)
       • End-to-end unit and HTTP integration test suite
```

---

### 3. Core Models & Schema Reference

| Model | Table | Description | Key Security / Rules |
| :--- | :--- | :--- | :--- |
| `ffm.attendance` | `ffm_attendance` | Daily attendance timestamps, GPS coords, accuracy | Marketers cannot edit/delete; unique `(employee_id, date)` |
| `ffm.daily.report` | `ffm_daily_report` | Parent daily report header linking working place | Direct manager or NSM/Admin approval |
| `ffm.chemist.visit` | `ffm_chemist_visit` | Chemist calls, sales, order, collection | Subtree visibility; client UUID idempotency |
| `ffm.prescriber.visit`| `ffm_prescriber_visit` | Doctor calls, product discussions, samples | Subtree visibility; client UUID idempotency |
| `ffm.farm.visit` | `ffm_farm_visit` | Farm calls, animal/bird counts | Subtree visibility; client UUID idempotency |
| `ffm.travel.log` | `ffm_travel_log` | Daily travel log parent | Linked to daily report |
| `ffm.travel.journey` | `ffm_travel_journey` | Journey legs between places, slab fares | Linked to travel log |
| `ffm.daily.expense` | `ffm_daily_expense` | 9 expense heads, linked vouchers | Subtree visibility; attachment security |
| `ffm.allowance.rate`| `ffm_allowance_rate` | DA per day & motorcycle maintenance by job | Admin manage, employees read |
| `ffm.expense.statement`| `ffm_expense_statement` | Monthly statement, approvals, grand totals | 6-state workflow, subtree & Accounts rules |
| `ffm.expense.statement.line`| `ffm_expense_statement_line` | Daily TA + DA breakdown rows | Follows parent statement permissions |
| `ffm.audit.log` | `ffm_audit_log` | Immutable security audit trail | Read-only for Admin |

---

### 4. Security & Role Permissions Matrix

| Role | Attendance | Visits & Expenses | Daily Report Approval | Statement Approval | Statement Payment | Manager Reports |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Field Person** | Create (Own) | Create (Own) | Read (Own) | Submit (Own) | No | Personal Card |
| **ASM** | Subtree View | Subtree View | Approve Direct Subtree | Check Subtree | No | Territory & Subtree |
| **RSM / DSM** | Subtree View | Subtree View | Approve Subtree | Check Subtree | No | Regional Drill-down |
| **NSM / MM** | All View | All View | Approve All | Approve All | No | Full Analytical Views |
| **Director** | All View | All View | Approve All | Approve All | No | Full Analytical Views |
| **Accounts** | Read All | Read All | Read All | Read All | Mark as Paid | Expense Statements |
| **Admin** | Full Access | Full Access | Full Access | Full Access | Full Access | Full Access |

---

### 5. Repository Structure
```
field_force_management/
├── docs/
│   └── ffm/
│       ├── README.md                     # System architecture & summary
│       ├── INSTALL_AND_UPGRADE.md        # Installation & deployment steps
│       ├── USER_GUIDE.md                 # Role-based operating manual
│       ├── DEPLOYMENT.md                 # Production Nginx, Linux, Workers guide
│       └── PHONE_TESTING_GUIDE.md        # Mobile responsive & GPS test guide
├── extra_addons/
│   ├── field_force_management/          # Core base module (places, fares, customer info)
│   └── ffm_daily_report/                # Newtec FFM extension module (Phases 1–7)
│       ├── controllers/main.py           # Web shell & API routes (/ff/*)
│       ├── models/                       # Data models & business logic
│       ├── report/                       # QWeb PDF reports (Daily & Statement)
│       ├── security/                     # ir.model.access.csv & record rules
│       ├── static/                       # Mobile CSS, JS, manifest, icons
│       ├── tests/                        # Automated unit & integration tests
│       ├── views/                        # Backend XML views & menus
│       └── wizards/                      # Rejection wizard (ffm.expense.statement.reject.wizard)
├── tools/
│   └── seed_ff_data.py                   # High-scale seed script & performance benchmark
└── odoo.conf.example                     # Sanitized configuration template
```
