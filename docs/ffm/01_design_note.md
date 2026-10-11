# Design Note 01: System Architecture & Technical Specifications
**Project:** Field Force Management (FFM) — Daily Report & Monthly Expense System  
**Client:** Newtec Pharmaceuticals Limited  
**Target Environment:** Odoo 14.0 Community, Python 3.9, PostgreSQL 15, Windows / Linux  
**Branch:** `feature/ffm-daily-report`  
**Date:** October 2026  

---

## 1. System Overview & Architectural Strategy

### 1.1 Objective & Scale
The primary objective is to implement an enterprise-grade Field Force Management system for Newtec Pharmaceuticals Limited, supporting **~500 active field users** daily. Each field user generates **10–15 visit, travel, and expense transactions per working day** across 26 working days a month (~150,000–200,000 transaction rows monthly).

### 1.2 Modular Architecture
All new features reside in a dedicated module **`ffm_daily_report`**, ensuring clean decoupling from core modules while fixing baseline defects in existing modules:
* **`field_force_management`**: Base operational models (`ffm.daily.report`, `ffm.travel.log`, `ffm.place`, `ffm.fare.config`).
* **`aam_branch_management`**: Master organizational structure (`aam.branch`, `territory.territory`).
* **`customer_management`**: Master stakeholder database (`customer.information` with chemists, doctors, and institutions).
* **`ffm_daily_report` (New)**: Marketer `/ff` web application, Geolocation Attendance (`ffm.attendance`), Farm Visits (`ffm.farm.visit`), Daily Expenses (`ffm.daily.expense`), Monthly Expense Statement (`ffm.expense.statement`), Allowance Rates (`ffm.allowance.rate`), Audit Trail (`ffm.audit.log`), and High-Performance SQL Reporting views.

```
+-------------------------------------------------------------+
|                     ffm_daily_report                        |
|   (/ff Web Portal, Attendance, Farm Visits, Daily Expense,   |
|     Monthly Statements, Allowance Rates, Audit Logging)     |
+-------------------------------------------------------------+
           |                    |                     |
           v                    v                     v
+-----------------------+ +--------------------+ +------------+
| field_force_management| |customer_management | | aam_branch |
+-----------------------+ +--------------------+ +------------+
           \                    |                     /
            +-------------------+--------------------+
                                |
                                v
               +---------------------------------+
               |    Odoo 14 Core (hr, mail, base)|
               +---------------------------------+
```

---

## 2. Complete Model Catalog & Entity Relationships

### 2.1 Reused and Extended Models
1. **`ffm.daily.report` (Daily Report Header)**
   * **Role:** Central aggregation point per employee per calendar date.
   * **Key Fields:** `employee_id` (M2O `hr.employee`), `date` (Date, locked to `Asia/Dhaka`), `territory_id` (M2O `territory.territory`), `working_place` (Char/M2O `ffm.place`), `state` (`draft`, `submitted`, `approved`, `rejected`), `total_order_tk`, `total_sale_tk`, `total_coll_tk`, `total_chemist_visited`, `total_prescriber_visited`.
   * **Constraint:** Unique `(employee_id, date)`.
   * **Tracking:** `tracking=False` (no chatter bloat).

2. **`ffm.chemist.visit` (Chemist Visit Lines)**
   * **Parent:** `report_id` (M2O `ffm.daily.report`, ondelete `cascade`).
   * **Key Fields:** `chemist_id` (M2O `customer.information`, domain `type='chemist'`), `chemist_name_manual` (Char, fallback), `order_tk` (Float, non-negative whole integer), `sale_tk` (Float), `coll_tk` (Float), `note` (Char).
   * **Validation:** Either `chemist_id` or `chemist_name_manual` required.

3. **`ffm.prescriber.visit` (Doctor / Prescriber Visit Lines)**
   * **Parent:** `report_id` (M2O `ffm.daily.report`, ondelete `cascade`).
   * **Key Fields:** `prescriber_id` (M2O `customer.information`, domain `type='doctor'`), `prescriber_name_manual` (Char, fallback), `mailing_address` (related Text), `product_discussion` (Char), `sample` (Char: sample, cash, gift), `grade` (Selection: `a_plus`, `a`, `b`, `c`).
   * **Validation:** Either `prescriber_id` or `prescriber_name_manual` required.

4. **`ffm.travel.log` & `ffm.travel.journey` (Travel Logs & Journey Legs)**
   * **Log Header:** `daily_report_id` (M2O `ffm.daily.report`), `employee_id`, `date`, `total_distance_km`, `total_fare_tk`, `state` (`draft`, `confirmed`).
   * **Legs:** `travel_log_id`, `place_from_id` (M2O `ffm.place`), `place_to_id` (M2O `ffm.place`), `mode` (Selection: bus, rickshaw, auto_cng, motorcycle, etc.), `distance_km` (editable Float), `fare_tk` (editable Float, manual TA bill support), `route_info` (Char).
   * **Cross-Linkage:** Nullable visit links on `ffm.travel.journey`:
     * `chemist_visit_id` (M2O `ffm.chemist.visit`, nullable)
     * `doctor_visit_id` (M2O `ffm.prescriber.visit`, nullable)
     * `farm_visit_id` (M2O `ffm.farm.visit`, nullable)

### 2.2 New Models Built in `ffm_daily_report`
1. **`ffm.attendance` (Daily Marketer Attendance)**
   * **Purpose:** Single daily check-in with GPS verification.
   * **Fields:**
     * `employee_id` (M2O `hr.employee`, required, indexed)
     * `date` (Date, required, indexed)
     * `reporting_time` (Datetime, server timestamp at submit)
     * `name` (Char, snapshot of employee name)
     * `designation` (Char, snapshot of job title)
     * `territory_id` (M2O `territory.territory`, snapshot)
     * `latitude` (Float, digits=(12, 7), required)
     * `longitude` (Float, digits=(12, 7), required)
     * `accuracy` (Float, required, radius in meters)
     * `mode_of_journey` (Char, manual text entry)
     * `client_uuid` (Char, unique, idempotency token)
   * **Constraint:** Unique `(employee_id, date)`.
   * **Security:** Marketers can only create (no edit, no delete).

2. **`ffm.farm.visit` (Farm & Institutional Visits)**
   * **Parent:** `report_id` (M2O `ffm.daily.report`, ondelete `cascade`).
   * **Fields:**
     * `farm_name` (Char, required)
     * `address` (Text)
     * `broiler` (Char)
     * `layer` (Char)
     * `sonali` (Char)
     * `cattle` (Char)
     * `aqua` (Char)
     * `bird_count` (Integer, non-negative)
     * `note` (Char)

3. **`ffm.daily.expense` (Daily Operational Field Expenses)**
   * **Linkage:** `daily_report_id` (M2O `ffm.daily.report`, ondelete `cascade`), `employee_id`, `date`.
   * **Expense Amounts:**
     * `entertainment` (Float, voucher mandatory)
     * `courier` (Float, voucher mandatory)
     * `photocopy` (Float, voucher mandatory)
     * `hotel_rent` (Float, voucher mandatory)
     * `promotion` (Float)
     * `stationery` (Float)
     * `carrying` (Float)
     * `banking` (Float)
     * `bike_maintenance` (Float)
     * `total_amount` (Float, computed & stored)
   * **Validation:** At least one expense amount must be greater than zero.

4. **`ffm.allowance.rate` (Allowance Rates by Designation)**
   * **Fields:**
     * `job_id` (M2O `hr.job`, required, unique)
     * `da_per_day` (Float, Daily Allowance rate)
     * `motorcycle_maintenance_per_month` (Float, fixed monthly bike allowance)
     * `active` (Boolean)

5. **`ffm.expense.statement` (Monthly Expense Statement)**
   * **Header:** `employee_id`, `month_year` (Char, format `YYYY-MM`), `job_id`, `hq` (Char), `state` (`draft`, `submitted`, `checked`, `approved`, `paid`, `rejected`), `total_daily_allowance`, `total_travel_allowance`, `total_other_expense`, `grand_total`.
   * **Tracking:** Inherits `mail.thread` for formal multi-tier audit trail.
   * **Constraint:** Unique `(employee_id, month_year)`.
   * **Lines (`ffm.expense.statement.line`):**
     * One row per active day from `ffm.daily.report`: `date`, `visited_places`, `travel_allowance` (sum of day's fares), `daily_allowance` (from `ffm.allowance.rate`), `day_total`.

6. **`ffm.audit.log` (Tamper-Evident System Audit Trail)**
   * **Fields:** `user_id` (M2O `res.users`), `action` (create, write, unlink, approve, reject, pay, export), `model_name` (Char), `res_id` (Integer), `old_values` (Text/JSON), `new_values` (Text/JSON), `timestamp` (Datetime). Read-only for Admin.

---

## 3. Security Architecture & Role-Based Access Matrix

### 3.1 Groups Hierarchy
```
Admin (group_ffm_admin)
  ├── Director (group_ffm_director) [Peer to NSM]
  └── NSM / MM (group_ffm_nsm)
        └── DSM (group_ffm_dsm)
              └── RSM (group_ffm_rsm)
                    └── ASM (group_ffm_asm)
                          └── Field Person (group_ffm_field_person)
Accounts (group_ffm_accounts) [Standalone role for financial verification]
```

### 3.2 Access Rights & Record Visibility Matrix

| Model | Field Person | ASM / RSM / DSM | NSM / Director / Admin | Accounts |
| :--- | :--- | :--- | :--- | :--- |
| **`ffm.attendance`** | Create / Read Own (Locked upon submit) | Read Own + Direct Reports (Subtree if enabled) | Full Read / Export | Read Only |
| **`ffm.daily.report`** | Create / Write Draft Own | Read & Approve Subordinates | Full Read / Write / Approve | Read Only |
| **`ffm.chemist.visit`** | Create / Write Draft Own | Read Subordinates | Full Access | Read Only |
| **`ffm.prescriber.visit`**| Create / Write Draft Own | Read Subordinates | Full Access | Read Only |
| **`ffm.farm.visit`** | Create / Write Draft Own | Read Subordinates | Full Access | Read Only |
| **`ffm.travel.log`** | Create / Write Draft Own | Read Subordinates | Full Access | Read (Confirmed) |
| **`ffm.daily.expense`** | Create / Write Draft Own | Read Subordinates | Full Access | Read (Vouchers) |
| **`ffm.expense.statement`**| Create / Submit Own | Check (Review) Subordinates | Full Approval Authority | Verify & Pay |
| **`ffm.allowance.rate`** | No Access | No Access | Full Configuration | Read Only |
| **`ffm.audit.log`** | No Access | No Access | Read Only (Admin) | No Access |

---

## 4. Marketer Web Portal (`/ff`) Route Architecture

### 4.1 Technology Stack
* Pure QWeb template rendered by Odoo HTTP controller (`auth='user'`).
* **Isolated lightweight asset bundle:** Does **NOT** inherit `web.assets_backend`. Loads only custom vanilla CSS (grid/flexbox, touch targets >= 44px, inputs 16px) and a minimal JS runtime (~25 KB total payload).
* Offline Resilience: Draft forms preserved in browser `localStorage`.
* Idempotency: Every POST payload carries a client-generated UUID (`client_uuid`).

### 4.2 Endpoint Specifications

| Route | Method | Purpose & Guard Rails |
| :--- | :--- | :--- |
| `/ff` | `GET` | Home tile dashboard. Redirects non-authenticated users to login; restricts to `group_ffm_field_person`. |
| `/ff/attendance` | `GET / POST` | Attendance screen. POST validates GPS coordinates, accuracy, and enforces single daily submission in `Asia/Dhaka`. |
| `/ff/report/daily` | `GET / POST` | Daily report header. Auto-resolves or creates today's report for the session employee. |
| `/ff/visit/chemist` | `GET / POST` | Inline Chemist visit logging with attached travel leg. |
| `/ff/visit/doctor` | `GET / POST` | Inline Doctor visit logging with grade, discussion, and travel leg. |
| `/ff/visit/farm` | `GET / POST` | Farm & institutional visit logging. |
| `/ff/expense/daily` | `GET / POST` | Daily expense logging with client-side canvas compressed voucher upload (max 1280px JPEG, ~0.7 quality). |
| `/ff/report-card/daily` | `GET` | Daily operational summary card (personal, ASM, RSM, territory attendance). |
| `/ff/report-card/monthly` | `GET` | Monthly rolling 30-day performance card with printable QWeb PDF trigger. |
| `/ff/statement/monthly` | `GET / POST` | Monthly expense statement generation, review, comment, and submission. |
| `/ff/api/places/search` | `GET` | Rapid place search: queries local `ffm.place` first; optional 3-second external Geoapify lookup. |

---

## 5. Design Decisions & Context Harmonization

1. **Hierarchy Traversal:**
   The employee hierarchy uses `hr.employee.parent_id`. To avoid Odoo domain recursion overhead on large datasets, the setting `ffm.subtree_visibility` defaults to `False` (direct reports check via `parent_id.user_id = user.id`), switching to PostgreSQL hierarchical index-assisted `child_of` only when explicitly toggled on by Super Admin.
2. **Provider Isolation:**
   Geoapify API calls are placed behind a clean provider abstraction (`RoutingProviderBase`). External lookups are decoupled from `name_search`, `create`, `write`, and `onchange`, ensuring user typing and database transactions remain instantaneous even during network loss.
3. **High-Volume Data Preservation:**
   To guarantee system responsiveness under bursts of morning attendance and evening report submissions, `mail.thread` and chatter tracking are stripped from visit lines, attendance, and travel logs, preserving disk space and eliminating database connection contention.
4. **Bengali Typography in PDF Reports:**
   wkhtmltopdf 0.12.6 lacks modern HarfBuzz shaping on Windows. The module includes an explicit `@font-face` declaration for licensed Unicode Bengali fonts (`Kalpurush` / `Noto Sans Bengali`) in report stylesheets, ensuring conjuncts (*যুক্তবর্ণ*) render cleanly across both Windows development machines and production Linux environments.
