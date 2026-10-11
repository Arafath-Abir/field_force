import base64
from datetime import date
from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import UserError, AccessError
from odoo.tools import mute_logger

TINY_JPEG_BYTES = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00' + b'\x01' * 64 + b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
VALID_JPEG_B64 = base64.b64encode(TINY_JPEG_BYTES).decode('utf-8')


class TestFFMStatementModels(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Statement = self.env['ffm.expense.statement']
        self.StatementLine = self.env['ffm.expense.statement.line']
        self.RejectWizard = self.env['ffm.expense.statement.reject.wizard']
        self.AllowanceRate = self.env['ffm.allowance.rate']
        self.DailyReport = self.env['ffm.daily.report']
        self.TravelLog = self.env['ffm.travel.log']
        self.TravelJourney = self.env['ffm.travel.journey']
        self.DailyExpense = self.env['ffm.daily.expense']
        self.Employee = self.env['hr.employee']
        self.Users = self.env['res.users']
        self.Job = self.env['hr.job']
        self.Place = self.env['ffm.place']
        self.AuditLog = self.env['ffm.audit.log']

        # Security groups
        self.grp_fp = self.env.ref('field_force_management.group_ffm_field_person')
        self.grp_asm = self.env.ref('field_force_management.group_ffm_asm')
        self.grp_rsm = self.env.ref('field_force_management.group_ffm_rsm')
        self.grp_nsm = self.env.ref('field_force_management.group_ffm_nsm')
        self.grp_admin = self.env.ref('field_force_management.group_ffm_admin')
        self.grp_accounts = self.env.ref('field_force_management.group_ffm_accounts')

        # Create Job & Allowance rate
        self.job_mio = self.Job.create({'name': 'Test Medical Information Officer'})
        self.rate = self.AllowanceRate.create({
            'job_id': self.job_mio.id,
            'da_per_day': 250.0,
            'motorcycle_maintenance_per_month': 1500.0,
            'active': True,
        })

        # Create hierarchy: NSM -> RSM -> ASM -> FP1 & FP2
        self.user_nsm = self.Users.create({
            'name': 'Stmt NSM User',
            'login': 'stmt_nsm_user',
            'email': 'stmt_nsm@example.com',
            'groups_id': [(6, 0, [self.grp_nsm.id])],
        })
        self.emp_nsm = self.Employee.create({
            'name': 'Stmt NSM Employee',
            'user_id': self.user_nsm.id,
        })

        self.user_asm = self.Users.create({
            'name': 'Stmt ASM User',
            'login': 'stmt_asm_user',
            'email': 'stmt_asm@example.com',
            'groups_id': [(6, 0, [self.grp_asm.id])],
        })
        self.emp_asm = self.Employee.create({
            'name': 'Stmt ASM Employee',
            'user_id': self.user_asm.id,
            'parent_id': self.emp_nsm.id,
        })

        self.user_fp1 = self.Users.create({
            'name': 'Stmt FP1 User',
            'login': 'stmt_fp1_user',
            'email': 'stmt_fp1@example.com',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.emp_fp1 = self.Employee.create({
            'name': 'Stmt FP1 Employee',
            'user_id': self.user_fp1.id,
            'job_id': self.job_mio.id,
            'parent_id': self.emp_asm.id,
        })

        self.user_fp2 = self.Users.create({
            'name': 'Stmt FP2 User',
            'login': 'stmt_fp2_user',
            'email': 'stmt_fp2@example.com',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.emp_fp2 = self.Employee.create({
            'name': 'Stmt FP2 Employee',
            'user_id': self.user_fp2.id,
            'job_id': self.job_mio.id,
            'parent_id': self.emp_asm.id,
        })

        self.user_accounts = self.Users.create({
            'name': 'Stmt Accounts User',
            'login': 'stmt_accounts_user',
            'email': 'stmt_accounts@example.com',
            'groups_id': [(6, 0, [self.grp_accounts.id])],
        })

        # Places
        self.place_a = self.Place.create({'name': 'Stmt Place Mohakhali', 'active': True})
        self.place_b = self.Place.create({'name': 'Stmt Place Uttara', 'active': True})

    def test_01_statement_generation_and_totals(self):
        """Verify monthly expense statement line generation, calculations, DA, TA, and other expenses."""
        target_month = '05'
        target_year = 2026

        # Create 3 daily reports for FP1 in May 2026
        rep1 = self.DailyReport.sudo().create({
            'employee_id': self.emp_fp1.id,
            'date': date(2026, 5, 2),
            'working_place_id': self.place_a.id,
        })
        # Add travel log with journey for rep1
        tlog1 = self.TravelLog.sudo().create({
            'daily_report_id': rep1.id,
            'employee_id': self.emp_fp1.id,
            'date': rep1.date,
        })
        self.TravelJourney.sudo().create({
            'travel_log_id': tlog1.id,
            'place_from_id': self.place_a.id,
            'place_to_id': self.place_b.id,
            'mode': 'motorcycle',
            'distance_km': 12.0,
            'fare_tk': 120.0,
        })

        rep2 = self.DailyReport.sudo().create({
            'employee_id': self.emp_fp1.id,
            'date': date(2026, 5, 5),
            'working_place_id': self.place_b.id,
        })
        tlog2 = self.TravelLog.sudo().create({
            'daily_report_id': rep2.id,
            'employee_id': self.emp_fp1.id,
            'date': rep2.date,
        })
        self.TravelJourney.sudo().create({
            'travel_log_id': tlog2.id,
            'place_from_id': self.place_b.id,
            'place_to_id': self.place_a.id,
            'mode': 'bus',
            'distance_km': 10.0,
            'fare_tk': 80.0,
        })

        rep3 = self.DailyReport.sudo().create({
            'employee_id': self.emp_fp1.id,
            'date': date(2026, 5, 10),
            'working_place_id': self.place_a.id,
        })

        # Create daily expense for FP1 in May 2026
        self.DailyExpense.sudo().create({
            'employee_id': self.emp_fp1.id,
            'date': date(2026, 5, 2),
            'entertainment': 300.0,
            'voucher_entertainment': VALID_JPEG_B64,
            'voucher_entertainment_filename': 'voucher_entertainment.jpg',
            'courier': 150.0,
            'voucher_courier': VALID_JPEG_B64,
            'voucher_courier_filename': 'voucher_courier.jpg',
            'carrying': 50.0,
        })

        # Create statement
        stmt = self.Statement.sudo().create({
            'employee_id': self.emp_fp1.id,
            'month': target_month,
            'year': target_year,
            'state': 'draft',
        })

        # Generate / Refresh
        stmt.action_generate_or_refresh()

        # Check daily lines
        self.assertEqual(len(stmt.line_ids), 3, "Should generate exactly 3 daily breakdown lines.")
        self.assertEqual(stmt.total_daily_ta, 200.0, "TA should be 120 + 80 = 200 Tk.")
        self.assertEqual(stmt.total_daily_da, 750.0, "DA should be 3 * 250 = 750 Tk.")
        self.assertEqual(stmt.total_daily_table, 950.0, "Daily table total should be 200 + 750 = 950 Tk.")

        # Check other expenses
        self.assertEqual(stmt.other_entertainment, 300.0)
        self.assertEqual(stmt.other_courier, 150.0)
        self.assertEqual(stmt.other_carrying, 50.0)
        self.assertEqual(stmt.motorcycle_maintenance, 1500.0, "Should match designation allowance rate.")

        expected_other = 300.0 + 150.0 + 50.0 + 1500.0
        self.assertEqual(stmt.total_other_expenses, expected_other)

        # Check grand total
        expected_grand = 950.0 + expected_other
        self.assertEqual(stmt.grand_total, expected_grand)

        # Test clear error when employee has no job_id
        emp_no_job = self.Employee.create({'name': 'Test No Job Emp', 'job_id': False})
        stmt_no_job = self.Statement.sudo().create({
            'employee_id': emp_no_job.id,
            'month': '09',
            'year': 2026,
        })
        with self.assertRaises(UserError):
            stmt_no_job.action_generate_or_refresh()

        # Test clear error when job has no allowance rate configured
        job_no_rate = self.Job.create({'name': 'Job Without Rate'})
        emp_no_rate = self.Employee.create({'name': 'Test No Rate Emp', 'job_id': job_no_rate.id})
        stmt_no_rate = self.Statement.sudo().create({
            'employee_id': emp_no_rate.id,
            'month': '09',
            'year': 2026,
        })
        with self.assertRaises(UserError):
            stmt_no_rate.action_generate_or_refresh()

        # Test unique constraint (employee, month, year)
        with mute_logger('odoo.sql_db'):
            with self.assertRaises(IntegrityError):
                with self.cr.savepoint():
                    self.Statement.sudo().create({
                        'employee_id': self.emp_fp1.id,
                        'month': target_month,
                        'year': target_year,
                    })

    def test_02_statement_workflow_full_lifecycle(self):
        """Test complete workflow: draft -> submitted -> checked -> approved -> paid with audit logs."""
        stmt = self.Statement.sudo().create({
            'employee_id': self.emp_fp1.id,
            'month': '06',
            'year': 2026,
            'other_entertainment': 200.0,
        })

        # Step 1: Submit as employee FP1
        stmt_as_fp1 = stmt.with_user(self.user_fp1)
        stmt_as_fp1.action_submit()
        self.assertEqual(stmt.state, 'submitted')
        self.assertEqual(stmt.submitted_by, self.user_fp1)
        self.assertTrue(stmt.submitted_date)

        # Verify non-manager cannot check
        with self.assertRaises((UserError, AccessError)):
            stmt.with_user(self.user_fp2).action_check()

        # Step 2: Check as direct superior ASM
        stmt_as_asm = stmt.with_user(self.user_asm)
        stmt_as_asm.action_check()
        self.assertEqual(stmt.state, 'checked')
        self.assertEqual(stmt.checked_by, self.user_asm)
        self.assertTrue(stmt.checked_date)

        # Verify ASM cannot approve (only NSM, Director, Admin can approve)
        with self.assertRaises((UserError, AccessError)):
            stmt_as_asm.action_approve()

        # Step 3: Approve as NSM
        stmt_as_nsm = stmt.with_user(self.user_nsm)
        stmt_as_nsm.action_approve()
        self.assertEqual(stmt.state, 'approved')
        self.assertEqual(stmt.approved_by, self.user_nsm)
        self.assertTrue(stmt.approved_date)

        # Verify marketer cannot pay
        with self.assertRaises((UserError, AccessError)):
            stmt.with_user(self.user_fp1).action_pay()

        # Step 4: Pay as Accounts
        stmt_as_acc = stmt.with_user(self.user_accounts)
        stmt_as_acc.action_pay()
        self.assertEqual(stmt.state, 'paid')
        self.assertEqual(stmt.paid_by, self.user_accounts)
        self.assertTrue(stmt.paid_date)

        # Verify audit logs created for all actions
        audit_actions = self.AuditLog.search([
            ('model_name', '=', 'ffm.expense.statement'),
            ('res_id', '=', stmt.id),
        ]).mapped('action')
        self.assertIn('submit', audit_actions)
        self.assertIn('check', audit_actions)
        self.assertIn('approve', audit_actions)
        self.assertIn('pay', audit_actions)

    def test_03_statement_reject_wizard(self):
        """Test rejection wizard: submitted/checked -> rejected with mandatory reason and re-submit."""
        stmt = self.Statement.sudo().create({
            'employee_id': self.emp_fp1.id,
            'month': '07',
            'year': 2026,
            'other_entertainment': 100.0,
        })
        stmt.action_submit()
        self.assertEqual(stmt.state, 'submitted')

        # Rejection wizard without reason -> error
        with self.assertRaises(UserError):
            self.RejectWizard.create({
                'statement_id': stmt.id,
                'reason': '   ',
            }).action_reject()

        # Rejection wizard with valid reason
        wizard = self.RejectWizard.create({
            'statement_id': stmt.id,
            'reason': 'Voucher image for entertainment is blurry. Please re-upload.',
        })
        wizard.action_reject()

        self.assertEqual(stmt.state, 'rejected')
        self.assertIn('blurry', stmt.rejection_reason)

        # Audit log has reject action
        reject_log = self.AuditLog.search([
            ('model_name', '=', 'ffm.expense.statement'),
            ('res_id', '=', stmt.id),
            ('action', '=', 'reject'),
        ], limit=1)
        self.assertTrue(reject_log)

        # From rejected, employee can re-submit
        stmt.action_submit()
        self.assertEqual(stmt.state, 'submitted')
        self.assertFalse(stmt.rejection_reason, "Rejection reason should be cleared upon resubmission.")

    def test_04_record_rules_visibility(self):
        """Test record rules: FP can only see own statements, ASM sees subtree, NSM/Admin sees all."""
        stmt_fp1 = self.Statement.sudo().create({
            'employee_id': self.emp_fp1.id,
            'month': '08',
            'year': 2026,
        })
        stmt_fp2 = self.Statement.sudo().create({
            'employee_id': self.emp_fp2.id,
            'month': '08',
            'year': 2026,
        })

        # FP1 view
        fp1_visible = self.Statement.with_user(self.user_fp1).search([])
        self.assertIn(stmt_fp1, fp1_visible)
        self.assertNotIn(stmt_fp2, fp1_visible, "FP1 must not see FP2's statement.")

        # ASM view (both FP1 and FP2 are in ASM subtree)
        asm_visible = self.Statement.with_user(self.user_asm).search([])
        self.assertIn(stmt_fp1, asm_visible)
        self.assertIn(stmt_fp2, asm_visible)

        # NSM view (sees all)
        nsm_visible = self.Statement.with_user(self.user_nsm).search([])
        self.assertIn(stmt_fp1, nsm_visible)
        self.assertIn(stmt_fp2, nsm_visible)

        # Accounts view: sees only approved and paid statements
        stmt_fp1.write({'state': 'approved'})
        acc_visible = self.Statement.with_user(self.user_accounts).search([])
        self.assertIn(stmt_fp1, acc_visible)
        self.assertNotIn(stmt_fp2, acc_visible, "Accounts must not see draft/submitted statements.")

    def test_05_skip_check_step_for_top_level_user(self):
        """Top-level employees without a parent_id skip the 'submitted' check step directly to 'checked'."""
        self.emp_nsm.job_id = self.job_mio.id
        stmt_top = self.Statement.sudo().create({
            'employee_id': self.emp_nsm.id,
            'month': '11',
            'year': 2026,
            'other_entertainment': 150.0,
        })
        self.assertFalse(self.emp_nsm.parent_id, "Top level user must have no manager.")

        # Submit as top level user
        stmt_top.with_user(self.user_nsm).action_submit()
        self.assertEqual(stmt_top.state, 'checked', "Top-level statement must skip check and transition directly to checked.")
        self.assertEqual(stmt_top.submitted_by, self.user_nsm)
        self.assertEqual(stmt_top.checked_by, self.user_nsm)


@tagged('-at_install', 'post_install')
class TestFFMStatementHttp(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.http']._clear_routing_map()

    def test_01_http_statement_routes(self):
        """Test portal /ff/statement page, statement generation, submit, and PDF export."""
        self.authenticate('ffm_fp_demo', 'Demo12345!')

        # 1. GET /ff/statement
        res_page = self.url_open('/ff/statement')
        self.assertEqual(res_page.status_code, 200)
        self.assertIn('মাসিক খরচের বিবরণী', res_page.content.decode('utf-8'))

        # 2. POST /ff/statement/generate
        res_gen = self.url_open(
            '/ff/statement/generate',
            data={'month': '10', 'year': '2026'},
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        self.assertEqual(res_gen.status_code, 200)

        # Find the statement
        demo_emp = self.env['hr.employee'].search([('user_id.login', '=', 'ffm_fp_demo')], limit=1)
        self.assertTrue(demo_emp)
        stmt = self.env['ffm.expense.statement'].sudo().search([
            ('employee_id', '=', demo_emp.id),
            ('month', '=', '10'),
            ('year', '=', 2026),
        ], limit=1)
        self.assertTrue(stmt, "Statement should be created via /ff/statement/generate route.")

        # Ensure it has some amount or line to allow submit
        stmt.sudo().write({'other_entertainment': 100.0})
        self.env.cr.commit()

        # 3. POST /ff/statement/submit
        res_sub = self.url_open(
            '/ff/statement/submit',
            data={'statement_id': str(stmt.id), 'remarks': 'October Monthly Bill'},
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        self.assertEqual(res_sub.status_code, 200)
        stmt.invalidate_cache()
        self.assertEqual(stmt.state, 'submitted', "Statement should transition to submitted state.")

        # 4. GET /ff/statement/pdf
        res_pdf = self.url_open(f'/ff/statement/pdf?month=10&year=2026')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.headers.get('Content-Type'), 'application/pdf')
        self.assertTrue(len(res_pdf.content) > 1000, "PDF content should be generated.")
