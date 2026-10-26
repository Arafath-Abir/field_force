#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/seed_today_and_future.py
------------------------------
Seeds demo data for today (2026-10-22) and the next 3 days (2026-10-23, 2026-10-24, 2026-10-25)
across all Field Force Management models:
  - Users & Credentials activation (sets unified password '123456')
  - Realistic Customers (Chemists & Doctors)
  - Attendance (Checked in with GPS coordinates & times)
  - Daily Reports (Draft, Submitted, Approved states)
  - Chemist / Pharmacy Visits (Orders, Sales, Collections, Notes)
  - Doctor / Prescriber Visits (Discussions, Samples, Grades)
  - Farm & Institutional Visits (Bird counts, Sheds, Notes)
  - Travel Logs & Journey Legs (Real Places, Distances, Fares)
  - Daily Expenses (Entertainment, Courier, Photocopy, Bike, Hotel Rent, Vouchers)
  - Monthly Expense Statements for October 2026 (Refreshed Daily Breakdown Lines)
  - Bulk operational data across all 475+ field employees
"""

import os
import sys
import base64
from datetime import date, datetime, timedelta
import pytz

# Add odoo core to path
sys.path.insert(0, '/Users/arafathabir/Code/ERP/Odoo/odoo-core')

import odoo
from odoo import api, fields, SUPERUSER_ID

TINY_JPEG_BYTES = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00'
    + b'\x01' * 64
    + b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
)
VALID_JPEG_B64 = base64.b64encode(TINY_JPEG_BYTES).decode('utf-8')


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def init_odoo_env():
    conf_path = '/Users/arafathabir/Downloads/field_force_management/odoo.conf'
    odoo.tools.config.parse_config(['-c', conf_path, '-d', 'field_force_db'])
    odoo.modules.initialize_sys_path()
    registry = odoo.registry('field_force_db')
    return registry


def activate_and_set_credentials(env):
    """Ensure all demo users are active and set password to '123456'."""
    log("1/6 Activating and verifying demo users & credentials...")
    User = env['res.users'].with_context(active_test=False).sudo()
    Emp = env['hr.employee'].with_context(active_test=False).sudo()

    user_configs = [
        ('admin', 'Mitchell Admin'),
        ('ffm_admin_demo', 'System Admin (FFM Admin)'),
        ('ffm_nsm_demo', 'Jahangir Alam (NSM)'),
        ('ffm_rsm_demo', 'Md. Karimul Islam (RSM)'),
        ('ffm_asm_demo', 'Md. Nazmul Huda (ASM)'),
        ('ffm_asm_dhaka', 'Tariqul Alam (ASM)'),
        ('ffm_fp_demo', 'Abdur Rahim (MPO)'),
        ('ffm_fp_sherpur', 'Shafiqul Islam (MPO)'),
        ('ffm_fp_dhaka', 'Monir Hossain (MPO)'),
        ('ffm_fp_demo2', 'Kamrul Islam (FP-2)'),
    ]

    for login, name in user_configs:
        u = User.search([('login', '=', login)], limit=1)
        if u:
            u.write({'active': True, 'password': '123456'})
            emp = Emp.search([('user_id', '=', u.id)], limit=1)
            if emp:
                emp.write({'active': True})
            log(f"  [OK] User '{login}' activated with password '123456'.")
        else:
            log(f"  [WARN] User '{login}' not found.")


def seed_customers_and_doctors(env):
    """Seed realistic Chemist shops and Doctors."""
    log("2/6 Seeding realistic Chemists and Doctors...")
    Cust = env['customer.information'].sudo()
    Emp = env['hr.employee'].with_context(active_test=False).sudo()
    
    emp_fp_bogura = Emp.search([('user_id.login', '=', 'ffm_fp_demo')], limit=1)
    emp_fp_sherpur = Emp.search([('user_id.login', '=', 'ffm_fp_sherpur')], limit=1)
    emp_fp_dhaka = Emp.search([('user_id.login', '=', 'ffm_fp_dhaka')], limit=1)

    chemists = [
        ('Popular Pharmacy (Bogura Sadar)', 'College Road, Bogura', '01711223344', emp_fp_bogura.id if emp_fp_bogura else False, 'Bogura Sadar'),
        ('Bismillah Drug House (Sherpur)', 'Main Market, Sherpur, Bogura', '01722334455', emp_fp_sherpur.id if emp_fp_sherpur else False, 'Sherpur'),
        ('Medina Pharmacy (Bogura)', 'Thana Road, Bogura Sadar', '01733445566', emp_fp_bogura.id if emp_fp_bogura else False, 'Bogura Sadar'),
        ('Care & Cure Medicine Corner (Mirpur)', 'Section 10, Mirpur, Dhaka', '01811223344', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Mirpur'),
        ('Al-Madina Pharma (Mirpur-1)', 'Mukto Bangla Complex, Mirpur-1', '01822334455', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Mirpur'),
        ('Square Medicine Corner (Dhanmondi)', 'Road 27, Dhanmondi, Dhaka', '01833445566', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Dhanmondi'),
        ('Green Life Pharmacy (Uttara)', 'Sector 3, Uttara, Dhaka', '01911223344', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Uttara'),
        ('Central Pharmacy (Chittagong)', 'GEC Circle, Chittagong', '01922334455', False, 'Chittagong Sadar'),
        ('Labaid Drug House (Rajshahi)', 'Zero Point, Shaheb Bazar, Rajshahi', '01933445566', False, 'Rajshahi Sadar'),
        ('Standard Pharmacy (Tejgaon)', 'Tejgaon I/A, Dhaka', '01944556677', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Tejgaon'),
    ]

    for name, addr, mob, fp_id, terr in chemists:
        c = Cust.search([('name', '=', name)], limit=1)
        if not c:
            Cust.create({
                'name': name,
                'type': 'chemist',
                'address': addr,
                'mobile': mob,
                'field_person_id': fp_id,
                'territory': terr,
                'state': 'confirmed',
                'active': True
            })

    doctors = [
        ('Dr. Rafiqul Islam (MBBS)', 'Modern Hospital Chamber, Bogura', '01712334455', emp_fp_bogura.id if emp_fp_bogura else False, 'Bogura Sadar'),
        ('Dr. Selim Reza (MBBS, DCH - Pediatrician)', 'Popular Diagnostic Center, Bogura', '01713445566', emp_fp_bogura.id if emp_fp_bogura else False, 'Bogura Sadar'),
        ('Dr. Nusrat Jahan (MBBS, FCPS - Gynae)', 'Mirpur General Hospital, Dhaka', '01812334455', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Mirpur'),
        ('Dr. Mahmud Hasan (MBBS, MD - Cardiology)', 'National Heart Foundation, Mirpur', '01813445566', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Mirpur'),
        ('Dr. Tariqul Islam (MBBS, MS - Ortho)', 'Ibn Sina Diagnostic, Dhanmondi', '01814556677', emp_fp_dhaka.id if emp_fp_dhaka else False, 'Dhanmondi'),
        ('Dr. Farhana Akter (MBBS - General)', 'Sherpur Upazila Health Complex', '01714556677', emp_fp_sherpur.id if emp_fp_sherpur else False, 'Sherpur'),
    ]

    for name, addr, mob, fp_id, terr in doctors:
        d = Cust.search([('name', '=', name)], limit=1)
        if not d:
            Cust.create({
                'name': name,
                'type': 'doctor',
                'address': addr,
                'mobile': mob,
                'field_person_id': fp_id,
                'territory': terr,
                'state': 'confirmed',
                'active': True
            })
    log("  [OK] Realistic Chemists and Doctors ready.")


def seed_primary_demo_fp_data(env):
    """Seed rich realistic data for the primary demo field persons across today and next 3 days."""
    log("3/6 Seeding detailed data for primary demo Field Persons (Today + next 3 days)...")
    Emp = env['hr.employee'].with_context(active_test=False).sudo()
    Att = env['ffm.attendance'].sudo()
    Report = env['ffm.daily.report'].sudo()
    ChemVisit = env['ffm.chemist.visit'].sudo()
    DocVisit = env['ffm.prescriber.visit'].sudo()
    FarmVisit = env['ffm.farm.visit'].sudo()
    TLog = env['ffm.travel.log'].sudo()
    TJourney = env['ffm.travel.journey'].sudo()
    DailyExp = env['ffm.daily.expense'].sudo()
    Place = env['ffm.place'].sudo()
    Cust = env['customer.information'].sudo()

    # Places
    p_bogura = Place.search([('name', '=', 'Bogura Sadar')], limit=1) or Place.search([('name', 'ilike', 'Bogura')], limit=1) or Place.search([], limit=1)
    p_shajahan = Place.search([('name', '=', 'Shajahanpur')], limit=1) or Place.search([('name', 'ilike', 'Shajahanpur')], limit=1) or p_bogura
    p_sherpur = Place.search([('name', '=', 'Sherpur Bus Stand')], limit=1) or Place.search([('name', 'ilike', 'Sherpur')], limit=1) or p_bogura
    p_mirpur = Place.search([('name', 'ilike', 'Mirpur')], limit=1) or p_bogura
    p_dhanmondi = Place.search([('name', 'ilike', 'Dhanmondi')], limit=1) or p_bogura
    p_uttara = Place.search([('name', 'ilike', 'Uttara')], limit=1) or p_bogura

    # Employees
    emp_fp1 = Emp.search([('user_id.login', '=', 'ffm_fp_demo')], limit=1)
    emp_fp2 = Emp.search([('user_id.login', '=', 'ffm_fp_sherpur')], limit=1)
    emp_fp3 = Emp.search([('user_id.login', '=', 'ffm_fp_dhaka')], limit=1)
    emp_fp4 = Emp.search([('user_id.login', '=', 'ffm_fp_demo2')], limit=1)

    chemists = Cust.search([('type', '=', 'chemist')])
    doctors = Cust.search([('type', '=', 'doctor')])

    c_popular = Cust.search([('name', 'ilike', 'Popular Pharmacy')], limit=1) or chemists[0]
    c_bismillah = Cust.search([('name', 'ilike', 'Bismillah Drug')], limit=1) or chemists[min(1, len(chemists)-1)]
    c_medina = Cust.search([('name', 'ilike', 'Medina Pharmacy')], limit=1) or chemists[min(2, len(chemists)-1)]
    c_mirpur = Cust.search([('name', 'ilike', 'Care & Cure')], limit=1) or chemists[min(3, len(chemists)-1)]

    d_rafiq = Cust.search([('name', 'ilike', 'Dr. Rafiqul')], limit=1) or doctors[0]
    d_selim = Cust.search([('name', 'ilike', 'Dr. Selim')], limit=1) or doctors[min(1, len(doctors)-1)]
    d_nusrat = Cust.search([('name', 'ilike', 'Dr. Nusrat')], limit=1) or doctors[min(2, len(doctors)-1)]

    # Dates: Today (2026-10-22) + next 3 days (2026-10-23, 2026-10-24, 2026-10-25)
    base_date = date(2026, 10, 22)
    target_dates = [base_date + timedelta(days=i) for i in range(4)]

    for idx, target_date in enumerate(target_dates):
        date_str = target_date.strftime('%Y-%m-%d')
        is_today = (idx == 0)

        # ----------------------------------------------------
        # 1. Abdur Rahim (ffm_fp_demo) - Bogura Sadar
        # ----------------------------------------------------
        if emp_fp1:
            # Attendance
            att1 = Att.search([('employee_id', '=', emp_fp1.id), ('date', '=', target_date)], limit=1)
            if not att1:
                att_time = datetime.combine(target_date, datetime.min.time()).replace(hour=9, minute=12 + idx * 3)
                Att.create({
                    'employee_id': emp_fp1.id,
                    'date': target_date,
                    'reporting_time': att_time,
                    'latitude': 24.8465 + idx * 0.002,
                    'longitude': 89.3777 + idx * 0.002,
                    'accuracy': 10.5,
                    'mode_of_journey': 'motorcycle',
                    'client_uuid': f'seed_att_fp1_{date_str}',
                    'state': 'submitted',
                })

            # Daily Report
            rep_state = 'submitted' if is_today else ('approved' if idx == 1 else 'draft')
            rep1 = Report.search([('employee_id', '=', emp_fp1.id), ('date', '=', target_date)], limit=1)
            if not rep1:
                rep1 = Report.create({
                    'employee_id': emp_fp1.id,
                    'date': target_date,
                    'working_place_id': p_bogura.id,
                    'state': rep_state,
                    'note': f'Field operations for {date_str}. Visited core key prescribers and high-volume chemist counters.'
                })
            else:
                rep1.write({'state': rep_state, 'working_place_id': p_bogura.id})

            # Chemist visits
            if not rep1.chemist_visit_ids:
                ChemVisit.create({
                    'report_id': rep1.id,
                    'chemist_id': c_popular.id,
                    'order_tk': 25000.0 + idx * 2000,
                    'sale_tk': 20000.0 + idx * 1000,
                    'coll_tk': 15000.0 + idx * 1500,
                    'note': 'Order booked for Amoxil & Calcium batch. Cheque received.',
                })
                ChemVisit.create({
                    'report_id': rep1.id,
                    'chemist_id': c_bismillah.id,
                    'order_tk': 18000.0 + idx * 1000,
                    'sale_tk': 14000.0,
                    'coll_tk': 10000.0,
                    'note': 'Cash collected Tk 10,000. Shelf stock checked.',
                })
                ChemVisit.create({
                    'report_id': rep1.id,
                    'chemist_id': c_medina.id,
                    'order_tk': 22000.0,
                    'sale_tk': 18000.0,
                    'coll_tk': 12000.0,
                    'note': 'New product brochure given to dispenser.',
                })

            # Doctor visit
            if not rep1.prescriber_visit_ids:
                DocVisit.create({
                    'report_id': rep1.id,
                    'prescriber_id': d_rafiq.id,
                    'mobile': '01712334455',
                    'mailing_address': 'Modern Hospital Chamber',
                    'product_discussion': 'Discussed Newtec Brand Cardio portfolio & Cipro line.',
                    'sample': '2 Packs sample given with promotional literature.',
                    'grade': 'a_plus',
                })
                DocVisit.create({
                    'report_id': rep1.id,
                    'prescriber_id': d_selim.id,
                    'mobile': '01713445566',
                    'mailing_address': 'Popular Diagnostic Center',
                    'product_discussion': 'Discussed Pediatric antibiotic dry syrup.',
                    'sample': 'Sample Kit & Pens.',
                    'grade': 'a',
                })

            # Farm visit
            if not rep1.farm_visit_ids:
                FarmVisit.create({
                    'report_id': rep1.id,
                    'farm_name': f'Green Valley Agro Poultry Farm - Lot {idx+1}',
                    'address': 'Shajahanpur, Bogura',
                    'broiler': '3 Sheds',
                    'bird_count': 5000 + idx * 500,
                    'note': 'Advised on seasonal electrolyte and feed additive mix.',
                    'client_uuid': f'seed_fv_fp1_{date_str}',
                })

            # Travel Log & Journeys
            tlog1 = TLog.search([('employee_id', '=', emp_fp1.id), ('date', '=', target_date)], limit=1)
            if not tlog1:
                tlog1 = TLog.create({
                    'daily_report_id': rep1.id,
                    'employee_id': emp_fp1.id,
                    'date': target_date,
                    'state': 'confirmed',
                })
            if not tlog1.journey_ids:
                TJourney.create({
                    'travel_log_id': tlog1.id,
                    'place_from_id': p_bogura.id,
                    'place_to_id': p_shajahan.id,
                    'mode': 'motorcycle',
                    'distance_km': 12.0,
                    'fare_tk': 60.0,
                })
                TJourney.create({
                    'travel_log_id': tlog1.id,
                    'place_from_id': p_shajahan.id,
                    'place_to_id': p_sherpur.id,
                    'mode': 'motorcycle',
                    'distance_km': 16.0,
                    'fare_tk': 80.0,
                })

            # Daily Expense
            exp1 = DailyExp.search([('employee_id', '=', emp_fp1.id), ('date', '=', target_date)], limit=1)
            if not exp1:
                DailyExp.create({
                    'employee_id': emp_fp1.id,
                    'date': target_date,
                    'daily_report_id': rep1.id,
                    'entertainment': 250.0 + idx * 50,
                    'courier': 120.0,
                    'photocopy': 60.0,
                    'bike': 100.0,
                    'voucher_entertainment': VALID_JPEG_B64,
                    'voucher_entertainment_filename': 'entertainment_slip.jpg',
                    'voucher_courier': VALID_JPEG_B64,
                    'voucher_courier_filename': 'courier_slip.jpg',
                    'voucher_photocopy': VALID_JPEG_B64,
                    'voucher_photocopy_filename': 'photocopy_slip.jpg',
                    'note': 'Refreshment with chemist association & document courier dispatch.',
                    'client_uuid': f'seed_exp_fp1_{date_str}',
                })

        # ----------------------------------------------------
        # 2. Shafiqul Islam (ffm_fp_sherpur) - Sherpur
        # ----------------------------------------------------
        if emp_fp2:
            # Attendance
            att2 = Att.search([('employee_id', '=', emp_fp2.id), ('date', '=', target_date)], limit=1)
            if not att2:
                att_time = datetime.combine(target_date, datetime.min.time()).replace(hour=9, minute=25)
                Att.create({
                    'employee_id': emp_fp2.id,
                    'date': target_date,
                    'reporting_time': att_time,
                    'latitude': 24.6766,
                    'longitude': 89.4182,
                    'accuracy': 14.0,
                    'mode_of_journey': 'bus',
                    'client_uuid': f'seed_att_fp2_{date_str}',
                    'state': 'submitted',
                })

            # Daily Report (approved)
            rep2 = Report.search([('employee_id', '=', emp_fp2.id), ('date', '=', target_date)], limit=1)
            if not rep2:
                rep2 = Report.create({
                    'employee_id': emp_fp2.id,
                    'date': target_date,
                    'working_place_id': p_sherpur.id,
                    'state': 'approved',
                    'note': 'Sherpur market coverage completed.'
                })
            if not rep2.chemist_visit_ids:
                ChemVisit.create({
                    'report_id': rep2.id,
                    'chemist_id': c_bismillah.id,
                    'order_tk': 20000.0,
                    'sale_tk': 16000.0,
                    'coll_tk': 12000.0,
                    'note': 'Order taken and payment collected.',
                })
            if not rep2.prescriber_visit_ids:
                DocVisit.create({
                    'report_id': rep2.id,
                    'prescriber_name_manual': 'Dr. Farhana Akter',
                    'product_discussion': 'General medicine lineup presentation.',
                    'sample': 'Samples provided.',
                    'grade': 'b',
                })
            tlog2 = TLog.search([('employee_id', '=', emp_fp2.id), ('date', '=', target_date)], limit=1)
            if not tlog2:
                tlog2 = TLog.create({
                    'daily_report_id': rep2.id,
                    'employee_id': emp_fp2.id,
                    'date': target_date,
                    'state': 'confirmed',
                })
            if not tlog2.journey_ids:
                TJourney.create({
                    'travel_log_id': tlog2.id,
                    'place_from_id': p_sherpur.id,
                    'place_to_id': p_bogura.id,
                    'mode': 'bus',
                    'distance_km': 28.0,
                    'fare_tk': 80.0,
                })
            exp2 = DailyExp.search([('employee_id', '=', emp_fp2.id), ('date', '=', target_date)], limit=1)
            if not exp2:
                DailyExp.create({
                    'employee_id': emp_fp2.id,
                    'date': target_date,
                    'daily_report_id': rep2.id,
                    'entertainment': 150.0,
                    'photocopy': 40.0,
                    'voucher_entertainment': VALID_JPEG_B64,
                    'voucher_entertainment_filename': 'voucher_ent_fp2.jpg',
                    'voucher_photocopy': VALID_JPEG_B64,
                    'voucher_photocopy_filename': 'voucher_photo_fp2.jpg',
                    'client_uuid': f'seed_exp_fp2_{date_str}',
                })

        # ----------------------------------------------------
        # 3. Monir Hossain (ffm_fp_dhaka) - Mirpur Dhaka
        # ----------------------------------------------------
        if emp_fp3:
            # Attendance
            att3 = Att.search([('employee_id', '=', emp_fp3.id), ('date', '=', target_date)], limit=1)
            if not att3:
                att_time = datetime.combine(target_date, datetime.min.time()).replace(hour=9, minute=5)
                Att.create({
                    'employee_id': emp_fp3.id,
                    'date': target_date,
                    'reporting_time': att_time,
                    'latitude': 23.8071,
                    'longitude': 90.3686,
                    'accuracy': 12.0,
                    'mode_of_journey': 'motorcycle',
                    'client_uuid': f'seed_att_fp3_{date_str}',
                    'state': 'submitted',
                })

            # Daily Report (draft on today, submitted on others)
            rep3_state = 'draft' if is_today else 'submitted'
            rep3 = Report.search([('employee_id', '=', emp_fp3.id), ('date', '=', target_date)], limit=1)
            if not rep3:
                rep3 = Report.create({
                    'employee_id': emp_fp3.id,
                    'date': target_date,
                    'working_place_id': p_mirpur.id,
                    'state': rep3_state,
                    'note': 'Mirpur & Dhanmondi territory scheduled visits.'
                })
            if not rep3.chemist_visit_ids:
                ChemVisit.create({
                    'report_id': rep3.id,
                    'chemist_id': c_mirpur.id,
                    'order_tk': 30000.0,
                    'sale_tk': 25000.0,
                    'coll_tk': 20000.0,
                    'note': 'Order booked for hospital supply pharmacy.',
                })
            if not rep3.prescriber_visit_ids:
                DocVisit.create({
                    'report_id': rep3.id,
                    'prescriber_id': d_nusrat.id,
                    'product_discussion': 'Prescription generation campaign for Gynae products.',
                    'sample': 'Full promotional sample kit.',
                    'grade': 'a_plus',
                })
            tlog3 = TLog.search([('employee_id', '=', emp_fp3.id), ('date', '=', target_date)], limit=1)
            if not tlog3:
                tlog3 = TLog.create({
                    'daily_report_id': rep3.id,
                    'employee_id': emp_fp3.id,
                    'date': target_date,
                    'state': 'confirmed',
                })
            if not tlog3.journey_ids:
                TJourney.create({
                    'travel_log_id': tlog3.id,
                    'place_from_id': p_mirpur.id,
                    'place_to_id': p_dhanmondi.id,
                    'mode': 'motorcycle',
                    'distance_km': 8.5,
                    'fare_tk': 50.0,
                })
            exp3 = DailyExp.search([('employee_id', '=', emp_fp3.id), ('date', '=', target_date)], limit=1)
            if not exp3:
                DailyExp.create({
                    'employee_id': emp_fp3.id,
                    'date': target_date,
                    'daily_report_id': rep3.id,
                    'entertainment': 200.0,
                    'bike': 120.0,
                    'voucher_entertainment': VALID_JPEG_B64,
                    'voucher_entertainment_filename': 'voucher_ent_fp3.jpg',
                    'client_uuid': f'seed_exp_fp3_{date_str}',
                })

        # ----------------------------------------------------
        # 4. Kamrul Islam (ffm_fp_demo2) - Left absent today for absent monitor!
        # ----------------------------------------------------
        if emp_fp4 and not is_today:
            att4 = Att.search([('employee_id', '=', emp_fp4.id), ('date', '=', target_date)], limit=1)
            if not att4:
                att_time = datetime.combine(target_date, datetime.min.time()).replace(hour=9, minute=30)
                Att.create({
                    'employee_id': emp_fp4.id,
                    'date': target_date,
                    'reporting_time': att_time,
                    'latitude': 23.75,
                    'longitude': 90.38,
                    'accuracy': 15.0,
                    'mode_of_journey': 'motorcycle',
                    'client_uuid': f'seed_att_fp4_{date_str}',
                    'state': 'submitted',
                })
            rep4 = Report.search([('employee_id', '=', emp_fp4.id), ('date', '=', target_date)], limit=1)
            if not rep4:
                rep4 = Report.create({
                    'employee_id': emp_fp4.id,
                    'date': target_date,
                    'working_place_id': p_dhanmondi.id,
                    'state': 'submitted',
                })
                ChemVisit.create({
                    'report_id': rep4.id,
                    'chemist_id': c_popular.id,
                    'order_tk': 12000.0,
                    'sale_tk': 10000.0,
                    'coll_tk': 8000.0,
                })

    log("  [OK] Primary demo FPs data seeded for 2026-10-22 to 2026-10-25.")


def seed_bulk_nationwide_data(env):
    """Seed fast high-volume data for all 475+ field persons for 2026-10-22 to 2026-10-25."""
    log("4/6 Bulk Seeding nationwide operational data for all field employees (2026-10-22 to 2026-10-25)...")
    cr = env.cr

    # Get active field employees
    cr.execute("SELECT id FROM hr_employee WHERE active = true AND name LIKE 'Seed FP %' LIMIT 500;")
    fp_ids = [r[0] for r in cr.fetchall()]
    if not fp_ids:
        cr.execute("SELECT id FROM hr_employee WHERE active = true LIMIT 500;")
        fp_ids = [r[0] for r in cr.fetchall()]

    cr.execute("SELECT id FROM ffm_place LIMIT 20;")
    place_ids = [r[0] for r in cr.fetchall()]
    p1 = place_ids[0] if len(place_ids) > 0 else 1
    p2 = place_ids[1] if len(place_ids) > 1 else p1

    log(f"  Targeting {len(fp_ids)} field employees over 4 upcoming dates...")

    # 1. Attendance for target dates
    cr.execute("""
        WITH target_dates AS (
            SELECT '2026-10-22'::date + (n || ' days')::interval AS op_date
            FROM generate_series(0, 3) n
        ),
        target_emps AS (
            SELECT id AS emp_id FROM hr_employee WHERE active = true AND id = ANY(%s)
        )
        INSERT INTO ffm_attendance (employee_id, date, reporting_time, latitude, longitude, accuracy, mode_of_journey, state, client_uuid)
        SELECT
            e.emp_id,
            d.op_date::date,
            d.op_date + time '09:15:00',
            23.7500000 + (e.emp_id %% 100) * 0.001,
            90.3800000 + (e.emp_id %% 100) * 0.001,
            12.5,
            CASE (e.emp_id %% 3) WHEN 0 THEN 'motorcycle' WHEN 1 THEN 'bus' ELSE 'rickshaw' END,
            'submitted',
            'perf-att-' || e.emp_id || '-' || d.op_date::date
        FROM target_emps e
        CROSS JOIN target_dates d
        ON CONFLICT (employee_id, date) DO NOTHING;
    """, [fp_ids])
    att_cnt = cr.rowcount
    log(f"  [OK] Bulk ffm_attendance seeded: {att_cnt} rows.")

    # 2. Daily Reports
    cr.execute("""
        WITH target_dates AS (
            SELECT '2026-10-22'::date + (n || ' days')::interval AS op_date
            FROM generate_series(0, 3) n
        ),
        target_emps AS (
            SELECT id AS emp_id FROM hr_employee WHERE active = true AND id = ANY(%s)
        )
        INSERT INTO ffm_daily_report (employee_id, date, working_place_id, state)
        SELECT
            e.emp_id,
            d.op_date::date,
            %s,
            CASE (e.emp_id %% 4) WHEN 0 THEN 'approved' WHEN 1 THEN 'submitted' WHEN 2 THEN 'approved' ELSE 'submitted' END
        FROM target_emps e
        CROSS JOIN target_dates d
        ON CONFLICT (employee_id, date) DO NOTHING;
    """, [fp_ids, p1])
    dr_cnt = cr.rowcount
    log(f"  [OK] Bulk ffm_daily_report seeded: {dr_cnt} rows.")

    # 3. Chemist Visits
    cr.execute("""
        WITH recent_reports AS (
            SELECT id, employee_id, date FROM ffm_daily_report
            WHERE employee_id = ANY(%s) AND date >= '2026-10-22'
        )
        INSERT INTO ffm_chemist_visit (report_id, chemist_name_manual, order_tk, sale_tk, coll_tk, client_uuid)
        SELECT
            r.id,
            'Chemist Pharmacy ' || (r.id %% 50),
            ROUND((10000 + (r.id %% 25) * 1000)::numeric, 0),
            ROUND((8000 + (r.id %% 20) * 1000)::numeric, 0),
            ROUND((6000 + (r.id %% 15) * 1000)::numeric, 0),
            'bulk-cv-' || r.id
        FROM recent_reports r
        ON CONFLICT (client_uuid) DO NOTHING;
    """, [fp_ids])
    cv_cnt = cr.rowcount
    log(f"  [OK] Bulk ffm_chemist_visit seeded: {cv_cnt} rows.")

    # 4. Doctor Visits
    cr.execute("""
        WITH recent_reports AS (
            SELECT id, employee_id, date FROM ffm_daily_report
            WHERE employee_id = ANY(%s) AND date >= '2026-10-22'
        )
        INSERT INTO ffm_prescriber_visit (report_id, prescriber_name_manual, product_discussion, sample, grade, client_uuid)
        SELECT
            r.id,
            'Dr. Consultant ' || (r.id %% 40),
            'Core therapeutic prescription discussion',
            'Sample gift pack and literature',
            CASE (r.id %% 4) WHEN 0 THEN 'a_plus' WHEN 1 THEN 'a' WHEN 2 THEN 'b' ELSE 'c' END,
            'bulk-pv-' || r.id
        FROM recent_reports r
        ON CONFLICT (client_uuid) DO NOTHING;
    """, [fp_ids])
    pv_cnt = cr.rowcount
    log(f"  [OK] Bulk ffm_prescriber_visit seeded: {pv_cnt} rows.")

    # 5. Farm Visits
    cr.execute("""
        WITH recent_reports AS (
            SELECT id, employee_id, date FROM ffm_daily_report
            WHERE employee_id = ANY(%s) AND date >= '2026-10-22' AND (id %% 2 = 0)
        )
        INSERT INTO ffm_farm_visit (report_id, farm_name, bird_count, note, client_uuid)
        SELECT
            r.id,
            'Agro Farm ' || (r.id %% 30),
            2000 + (r.id %% 50) * 50,
            'Routine biosecurity and feed supplement consultation.',
            'bulk-fv-' || r.id
        FROM recent_reports r
        ON CONFLICT (client_uuid) DO NOTHING;
    """, [fp_ids])
    fv_cnt = cr.rowcount
    log(f"  [OK] Bulk ffm_farm_visit seeded: {fv_cnt} rows.")

    # 6. Travel Logs & Journeys
    cr.execute("""
        WITH recent_reports AS (
            SELECT id, employee_id, date FROM ffm_daily_report
            WHERE employee_id = ANY(%s) AND date >= '2026-10-22'
              AND id NOT IN (SELECT daily_report_id FROM ffm_travel_log WHERE daily_report_id IS NOT NULL)
        )
        INSERT INTO ffm_travel_log (daily_report_id, employee_id, date, state)
        SELECT r.id, r.employee_id, r.date, 'confirmed'
        FROM recent_reports r;
    """, [fp_ids])

    cr.execute("""
        WITH t_logs AS (
            SELECT tl.id, tl.daily_report_id FROM ffm_travel_log tl
            WHERE tl.employee_id = ANY(%s) AND tl.date >= '2026-10-22'
        )
        INSERT INTO ffm_travel_journey (travel_log_id, place_from_id, place_to_id, mode, distance_km, fare_tk, client_uuid)
        SELECT
            tl.id,
            %s,
            %s,
            'motorcycle',
            14.5,
            72.0,
            'bulk-tj-' || tl.id
        FROM t_logs tl
        ON CONFLICT (client_uuid) DO NOTHING;
    """, [fp_ids, p1, p2])
    log("  [OK] Bulk ffm_travel_log & ffm_travel_journey populated.")

    # 7. Daily Expenses
    cr.execute("""
        WITH recent_reports AS (
            SELECT id, employee_id, date FROM ffm_daily_report
            WHERE employee_id = ANY(%s) AND date >= '2026-10-22'
        )
        INSERT INTO ffm_daily_expense (employee_id, date, daily_report_id, entertainment, courier, photocopy, hotel_rent, bike, total_amount, client_uuid)
        SELECT
            r.employee_id,
            r.date,
            r.id,
            180.0,
            60.0,
            40.0,
            0.0,
            100.0,
            380.0,
            'bulk-de-' || r.employee_id || '-' || r.date
        FROM recent_reports r
        ON CONFLICT (client_uuid) DO NOTHING;
    """, [fp_ids])
    log("  [OK] Bulk ffm_daily_expense populated.")


def refresh_monthly_statements(env):
    """Generate and refresh October 2026 expense statements for all active employees."""
    log("5/6 Refreshing October 2026 Expense Statements for demo employees...")
    Statement = env['ffm.expense.statement'].sudo()
    Emp = env['hr.employee'].with_context(active_test=False).sudo()

    demo_emps = Emp.search([('user_id.login', 'in', ['ffm_fp_demo', 'ffm_fp_sherpur', 'ffm_fp_dhaka'])])
    for emp in demo_emps:
        stmt = Statement.search([
            ('employee_id', '=', emp.id),
            ('month', '=', '10'),
            ('year', '=', 2026),
        ], limit=1)
        if not stmt:
            stmt = Statement.create({
                'employee_id': emp.id,
                'month': '10',
                'year': 2026,
                'state': 'draft',
            })
        try:
            stmt.action_generate_or_refresh()
            if stmt.state == 'draft':
                stmt.write({'remarks': 'October 2026 monthly statement generated with all visits, TA/DA and expenses.'})
            log(f"  [OK] Statement for {emp.name}: Grand Total = {stmt.grand_total:,.2f} Tk ({len(stmt.line_ids)} daily lines)")
        except Exception as e:
            log(f"  [WARN] Statement generate error for {emp.name}: {e}")


def verify_summary(env):
    """Print verification statistics."""
    log("6/6 Verifying data seeding across all target dates...")
    cr = env.cr

    queries = [
        ("Total Attendance (2026-10-22 to 2026-10-25)", "SELECT count(*) FROM ffm_attendance WHERE date BETWEEN '2026-10-22' AND '2026-10-25'"),
        ("Total Daily Reports (2026-10-22 to 2026-10-25)", "SELECT count(*) FROM ffm_daily_report WHERE date BETWEEN '2026-10-22' AND '2026-10-25'"),
        ("Chemist Visits on these reports", "SELECT count(*) FROM ffm_chemist_visit cv JOIN ffm_daily_report dr ON cv.report_id = dr.id WHERE dr.date BETWEEN '2026-10-22' AND '2026-10-25'"),
        ("Doctor Visits on these reports", "SELECT count(*) FROM ffm_prescriber_visit pv JOIN ffm_daily_report dr ON pv.report_id = dr.id WHERE dr.date BETWEEN '2026-10-22' AND '2026-10-25'"),
        ("Farm Visits on these reports", "SELECT count(*) FROM ffm_farm_visit fv JOIN ffm_daily_report dr ON fv.report_id = dr.id WHERE dr.date BETWEEN '2026-10-22' AND '2026-10-25'"),
        ("Travel Logs (2026-10-22 to 2026-10-25)", "SELECT count(*) FROM ffm_travel_log WHERE date BETWEEN '2026-10-22' AND '2026-10-25'"),
        ("Daily Expenses (2026-10-22 to 2026-10-25)", "SELECT count(*) FROM ffm_daily_expense WHERE date BETWEEN '2026-10-22' AND '2026-10-25'"),
        ("Analysis View Count (2026-10-22 to 2026-10-25)", "SELECT count(*) FROM ffm_daily_report_analysis WHERE date BETWEEN '2026-10-22' AND '2026-10-25'"),
    ]

    for label, q in queries:
        cr.execute(q)
        cnt = cur_val = cr.fetchone()[0]
        log(f"  * {label:50}: {cnt}")


def main():
    log("==================================================================")
    log("Starting Field Force Demo Seeding: Today (2026-10-22) + Next 3 Days")
    log("==================================================================")

    registry = init_odoo_env()
    with registry.cursor() as cr:
        with api.Environment.manage():
            env = api.Environment(cr, SUPERUSER_ID, {})

            # Step 1: Users & credentials
            activate_and_set_credentials(env)

            # Step 2: Realistic Chemist & Doctors
            seed_customers_and_doctors(env)

            # Step 3: Detailed primary demo FPs
            seed_primary_demo_fp_data(env)

            # Step 4: Bulk nationwide operational data
            seed_bulk_nationwide_data(env)

            # Step 5: Refresh statements
            refresh_monthly_statements(env)

            # Commit all changes
            cr.commit()

            # Step 6: Verify
            verify_summary(env)

    log("==================================================================")
    log("SUCCESS: All demo data seeded and credentials confirmed!")
    log("==================================================================")


if __name__ == '__main__':
    main()
