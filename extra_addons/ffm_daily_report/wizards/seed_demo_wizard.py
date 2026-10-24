# -*- coding: utf-8 -*-
import base64
from datetime import datetime, date, timedelta
import pytz
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TINY_JPEG_BYTES = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00' + b'\x01' * 64 + b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
VALID_JPEG_B64 = base64.b64encode(TINY_JPEG_BYTES).decode('utf-8')

class FFMSeedDemoWizard(models.TransientModel):
    _name = 'ffm.seed.demo.wizard'
    _description = 'Seed Demo Data for Field Force Testing'

    include_attendance = fields.Boolean(string='Seed Today Attendance', default=True)
    include_visits = fields.Boolean(string='Seed Today Visits & Daily Report', default=True)
    include_expenses = fields.Boolean(string='Seed Daily Expenses & Vouchers', default=True)
    include_statements = fields.Boolean(string='Seed Monthly Statements', default=True)

    def action_seed_demo_data(self):
        self.ensure_one()
        env = self.env
        tz = pytz.timezone('Asia/Dhaka')
        today_date = datetime.now(tz).date()

        # 1. Security Groups
        grp_admin = env.ref('field_force_management.group_ffm_admin', raise_if_not_found=False)
        grp_rsm = env.ref('field_force_management.group_ffm_rsm', raise_if_not_found=False)
        grp_asm = env.ref('field_force_management.group_ffm_asm', raise_if_not_found=False)
        grp_fp = env.ref('field_force_management.group_ffm_field_person', raise_if_not_found=False)
        grp_internal = env.ref('base.group_user')

        # 2. Branches
        Branch = env['aam.branch'].sudo()
        b_bogura = Branch.search([('name', '=', 'Bogura Branch')], limit=1)
        if not b_bogura:
            b_bogura = Branch.create({'name': 'Bogura Branch', 'code': 'BOG-01'})
        b_dhaka = Branch.search([('name', '=', 'Dhaka Branch')], limit=1)
        if not b_dhaka:
            b_dhaka = Branch.create({'name': 'Dhaka Branch', 'code': 'DHK-01'})

        # 3. Job Positions & Allowance Rates
        Job = env['hr.job'].sudo()
        Rate = env['ffm.allowance.rate'].sudo()

        job_rsm = env.ref('ffm_daily_report.job_demo_rsm', raise_if_not_found=False) or Job.search([('name', 'ilike', 'Regional')], limit=1) or Job.create({'name': 'Regional Sales Manager'})
        job_asm = env.ref('ffm_daily_report.job_demo_asm', raise_if_not_found=False) or Job.search([('name', 'ilike', 'Area')], limit=1) or Job.create({'name': 'Area Sales Manager'})
        job_fp = env.ref('ffm_daily_report.job_demo_mpo', raise_if_not_found=False) or Job.search(['|', ('name', 'ilike', 'Medical'), ('name', 'ilike', 'Field')], limit=1) or Job.create({'name': 'Medical Promotion Officer'})

        # Ensure active allowance rates exist for each job
        for j, da, moto in [(job_rsm, 700.0, 4500.0), (job_asm, 500.0, 3500.0), (job_fp, 350.0, 2500.0)]:
            if not Rate.search([('job_id', '=', j.id)], limit=1):
                Rate.create({'job_id': j.id, 'da_per_day': da, 'motorcycle_maintenance_per_month': moto, 'active': True})

        # Helper to create/update user & employee
        def _get_or_create_user_emp(login, name, job, groups, hq, branch, parent=False):
            User = env['res.users'].sudo()
            Emp = env['hr.employee'].sudo()

            user = User.search([('login', '=', login)], limit=1)
            if not user:
                user = User.create({
                    'name': name,
                    'login': login,
                    'password': 'Demo12345!',
                    'email': f'{login}@newtec.com',
                    'tz': 'Asia/Dhaka',
                    'groups_id': [(6, 0, [grp_internal.id] + [g.id for g in groups if g])],
                    'branch_id': branch.id if branch else False,
                })
            else:
                user.write({
                    'tz': 'Asia/Dhaka',
                    'groups_id': [(4, g.id) for g in groups if g],
                    'branch_id': branch.id if branch else False,
                })

            emp = Emp.search([('user_id', '=', user.id)], limit=1)
            if not emp:
                emp = Emp.create({
                    'name': name,
                    'user_id': user.id,
                    'job_id': job.id if job else False,
                    'hq': hq,
                    'branch_id': branch.id if branch else False,
                    'parent_id': parent.id if parent else False,
                    'work_email': user.email,
                    'mobile_phone': '01711002233',
                })
            else:
                emp_vals = {
                    'branch_id': branch.id if branch else False,
                    'parent_id': parent.id if parent else False,
                }
                if not emp.job_id or emp.job_id.name == 'Field Person / MPO':
                    emp_vals['job_id'] = job.id
                if not emp.hq:
                    emp_vals['hq'] = hq
                emp.write(emp_vals)
            return user, emp

        # Hierarchy: RSM -> ASM Bogura -> FPs
        _u_rsm, emp_rsm = _get_or_create_user_emp('ffm_rsm_demo', 'Md. Karimul Islam (RSM)', job_rsm, [grp_rsm], 'Rajshahi Division', b_bogura)
        _u_asm, emp_asm = _get_or_create_user_emp('ffm_asm_demo', 'Md. Nazmul Huda (ASM)', job_asm, [grp_asm], 'Bogura Area', b_bogura, parent=emp_rsm)
        _u_asm_dhk, emp_asm_dhk = _get_or_create_user_emp('ffm_asm_dhaka', 'Tariqul Alam (ASM)', job_asm, [grp_asm], 'Dhaka Area', b_dhaka, parent=emp_rsm)

        _u_fp1, emp_fp1 = _get_or_create_user_emp('ffm_fp_demo', 'Abdur Rahim (MPO)', job_fp, [grp_fp], 'Bogura Sadar', b_bogura, parent=emp_asm)
        _u_fp2, emp_fp2 = _get_or_create_user_emp('ffm_fp_sherpur', 'Shafiqul Islam (MPO)', job_fp, [grp_fp], 'Sherpur Upazila', b_bogura, parent=emp_asm)
        _u_fp3, emp_fp3 = _get_or_create_user_emp('ffm_fp_dhaka', 'Monir Hossain (MPO)', job_fp, [grp_fp], 'Mirpur Zone', b_dhaka, parent=emp_asm_dhk)

        # 4. Territories
        Territory = env['territory.territory'].sudo()
        def _get_or_create_territory(name, branch, fp, mgr):
            t = Territory.search([('name', '=', name)], limit=1)
            if not t:
                t = Territory.create({
                    'name': name,
                    'branch_id': branch.id,
                    'field_person_id': fp.id,
                    'manager_id': mgr.id,
                })
            else:
                t.write({
                    'branch_id': branch.id,
                    'field_person_id': fp.id,
                    'manager_id': mgr.id,
                })
            return t

        t_bogura = _get_or_create_territory('Bogura Sadar Territory', b_bogura, emp_fp1, emp_asm)
        t_sherpur = _get_or_create_territory('Sherpur Upazila Territory', b_bogura, emp_fp2, emp_asm)
        t_mirpur = _get_or_create_territory('Mirpur Zone Territory', b_dhaka, emp_fp3, emp_asm_dhk)

        # 5. Places
        Place = env['ffm.place'].sudo()
        def _get_or_create_place(name, lat=0.0, lng=0.0):
            p = Place.search([('name', '=', name)], limit=1)
            if not p:
                p = Place.create({'name': name, 'lat': lat, 'lng': lng, 'active': True})
            return p

        p_bogura = _get_or_create_place('Bogura Sadar', 24.8465, 89.3777)
        p_shajahan = _get_or_create_place('Shajahanpur', 24.7645, 89.3942)
        p_sherpur = _get_or_create_place('Sherpur Bus Stand', 24.6766, 89.4182)
        p_mirpur = _get_or_create_place('Mirpur-10 Circle', 23.8071, 90.3686)

        # 6. Customers (Chemists & Doctors)
        CustInfo = env['customer.information'].sudo()
        c1 = CustInfo.search([('name', 'ilike', 'Popular Pharmacy')], limit=1)
        if not c1:
            c1 = CustInfo.create({
                'name': 'Popular Pharmacy (Bogura Sadar)',
                'type': 'chemist',
                'address': 'College Road, Bogura',
                'field_person_id': emp_fp1.id,
                'state': 'confirmed',
            })
        c2 = CustInfo.search([('name', 'ilike', 'Bismillah Drug House')], limit=1)
        if not c2:
            c2 = CustInfo.create({
                'name': 'Bismillah Drug House (Sherpur)',
                'type': 'chemist',
                'address': 'Main Market, Sherpur',
                'field_person_id': emp_fp1.id,
                'state': 'confirmed',
            })

        d1 = CustInfo.search([('name', 'ilike', 'Dr. Rafiqul Islam')], limit=1)
        if not d1:
            d1 = CustInfo.create({
                'name': 'Dr. Rafiqul Islam (MBBS)',
                'type': 'doctor',
                'address': 'Chamber: Modern Hospital, Bogura',
                'mobile': '01712334455',
                'field_person_id': emp_fp1.id,
                'state': 'confirmed',
            })

        # 7. Today Attendance
        if self.include_attendance:
            Att = env['ffm.attendance'].sudo()
            # FP 1 Present
            att1 = Att.search([('employee_id', '=', emp_fp1.id), ('date', '=', today_date)], limit=1)
            if not att1:
                Att.create({
                    'employee_id': emp_fp1.id,
                    'date': today_date,
                    'reporting_time': fields.Datetime.now(),
                    'latitude': 24.8465,
                    'longitude': 89.3777,
                    'accuracy': 10.0,
                    'mode_of_journey': 'Motorcycle',
                    'client_uuid': f'demo_att_fp1_{today_date}',
                    'state': 'submitted',
                })
            # FP 2 Present
            att2 = Att.search([('employee_id', '=', emp_fp2.id), ('date', '=', today_date)], limit=1)
            if not att2:
                Att.create({
                    'employee_id': emp_fp2.id,
                    'date': today_date,
                    'reporting_time': fields.Datetime.now(),
                    'latitude': 24.6766,
                    'longitude': 89.4182,
                    'accuracy': 15.0,
                    'mode_of_journey': 'Bus',
                    'client_uuid': f'demo_att_fp2_{today_date}',
                    'state': 'submitted',
                })
            # FP 3 (Dhaka) left absent so the absent monitor shows data!

        # 8. Today Daily Reports and Visits
        if self.include_visits:
            Report = env['ffm.daily.report'].sudo()
            # FP 1 Submitted Report
            rep1 = Report.search([('employee_id', '=', emp_fp1.id), ('date', '=', today_date)], limit=1)
            if not rep1:
                rep1 = Report.create({
                    'employee_id': emp_fp1.id,
                    'date': today_date,
                    'working_place_id': p_bogura.id,
                    'state': 'draft',
                })
            # Add Chemist Visits
            ChemVisit = env['ffm.chemist.visit'].sudo()
            if not rep1.chemist_visit_ids:
                ChemVisit.create({
                    'report_id': rep1.id,
                    'chemist_id': c1.id,
                    'order_tk': 25000,
                    'sale_tk': 20000,
                    'coll_tk': 15000,
                    'note': 'Order booked for Antibiotic batch. Cheque collection next week.',
                })
                ChemVisit.create({
                    'report_id': rep1.id,
                    'chemist_id': c2.id,
                    'order_tk': 15000,
                    'sale_tk': 12000,
                    'coll_tk': 8000,
                    'note': 'Cash collected Tk 8,000.',
                })
            # Add Doctor Visit
            DocVisit = env['ffm.prescriber.visit'].sudo()
            if not rep1.prescriber_visit_ids:
                DocVisit.create({
                    'report_id': rep1.id,
                    'prescriber_id': d1.id,
                    'mobile': '01712334455',
                    'mailing_address': 'Modern Hospital Chamber',
                    'product_discussion': 'Discussed Newtec Brand Amoxil & Calcium supplements.',
                    'sample': '2 Packs sample given with promotional literature.',
                    'grade': 'a_plus',
                })
            # Add Farm Visit
            FarmVisit = env['ffm.farm.visit'].sudo()
            if not rep1.farm_visit_ids:
                FarmVisit.create({
                    'report_id': rep1.id,
                    'farm_name': 'Green Valley Agro Poultry Farm',
                    'address': 'Shajahanpur, Bogura',
                    'broiler': '2 Sheds',
                    'bird_count': 4500,
                    'note': 'Advised on seasonal electrolyte & vitamin balance in summer.',
                })
            # Add Travel Log
            TLog = env['ffm.travel.log'].sudo()
            tlog1 = rep1.travel_log_ids[:1]
            if not tlog1:
                tlog1 = TLog.create({
                    'daily_report_id': rep1.id,
                    'employee_id': emp_fp1.id,
                    'date': today_date,
                })
            TJourney = env['ffm.travel.journey'].sudo()
            if not tlog1.journey_ids:
                TJourney.create({
                    'travel_log_id': tlog1.id,
                    'place_from_id': p_bogura.id,
                    'place_to_id': p_shajahan.id,
                    'mode': 'motorcycle',
                    'distance_km': 12.0,
                    'fare_tk': 60.0,
                })
            # Move report to submitted so manager can approve/reject
            if rep1.state == 'draft':
                rep1.action_submit()

        # 9. Daily Expenses
        if self.include_expenses:
            DailyExp = env['ffm.daily.expense'].sudo()
            exp1 = DailyExp.search([('employee_id', '=', emp_fp1.id), ('date', '=', today_date)], limit=1)
            if not exp1:
                DailyExp.create({
                    'employee_id': emp_fp1.id,
                    'date': today_date,
                    'daily_report_id': rep1.id if 'rep1' in locals() and rep1 else False,
                    'entertainment': 250.0,
                    'courier': 120.0,
                    'photocopy': 60.0,
                    'voucher_entertainment': VALID_JPEG_B64,
                    'voucher_entertainment_filename': 'voucher_entertainment.jpg',
                    'voucher_courier': VALID_JPEG_B64,
                    'voucher_courier_filename': 'voucher_courier.jpg',
                    'voucher_photocopy': VALID_JPEG_B64,
                    'voucher_photocopy_filename': 'voucher_photocopy.jpg',
                    'note': 'Tea with chemist association & dispatching monthly forms via courier.',
                    'client_uuid': f'demo_exp_fp1_{today_date}',
                })

        # 10. Monthly Expense Statement
        if self.include_statements:
            Statement = env['ffm.expense.statement'].sudo()
            cur_month_str = today_date.strftime('%m')
            cur_year_int = today_date.year
            stmt1 = Statement.search([
                ('employee_id', '=', emp_fp1.id),
                ('month', '=', cur_month_str),
                ('year', '=', cur_year_int)
            ], limit=1)
            if not stmt1:
                stmt1 = Statement.create({
                    'employee_id': emp_fp1.id,
                    'month': cur_month_str,
                    'year': cur_year_int,
                })
                stmt1.action_generate()
                # Set demo lines if empty
                if not stmt1.line_ids:
                    env['ffm.expense.statement.line'].sudo().create({
                        'statement_id': stmt1.id,
                        'date': today_date,
                        'visited_places': 'Bogura Sadar - Shajahanpur',
                        'ta_amount': 180.0,
                        'da_amount': 250.0,
                    })
                stmt1.write({
                    'other_entertainment': 450.0,
                    'other_courier': 220.0,
                    'other_photocopy': 120.0,
                    'remarks': 'Submitted for monthly verification and reimbursement.',
                })
                if stmt1.state == 'draft':
                    stmt1.action_submit()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Demo Data Seeded Successfully"),
                'message': _("Sample RSM, ASMs, Field Persons, Territories, Attendance, Visits, Expenses & Statements seeded!"),
                'type': 'success',
                'sticky': False,
            }
        }
