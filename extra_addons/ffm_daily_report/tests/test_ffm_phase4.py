# -*- coding: utf-8 -*-
import base64
import json
from datetime import date
from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import ValidationError, AccessError
from odoo.tools import mute_logger

# Minimal valid JPEG bytes (magic bytes \xff\xd8\xff\xe0)
TINY_JPEG_BYTES = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00' + b'\x01' * 64 + b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
VALID_JPEG_B64 = base64.b64encode(TINY_JPEG_BYTES).decode('utf-8')


class TestFFMPhase4Models(TransactionCase):

    def setUp(self):
        super().setUp()
        self.DailyExpense = self.env['ffm.daily.expense']
        self.DailyReport = self.env['ffm.daily.report']
        self.Employee = self.env['hr.employee']
        self.Users = self.env['res.users']
        self.Attachment = self.env['ir.attachment']

        # Security groups
        self.grp_fp = self.env.ref('field_force_management.group_ffm_field_person')
        self.grp_asm = self.env.ref('field_force_management.group_ffm_asm')
        self.grp_nsm = self.env.ref('field_force_management.group_ffm_nsm')
        self.grp_director = self.env.ref('field_force_management.group_ffm_director')
        self.grp_admin = self.env.ref('field_force_management.group_ffm_admin')

        # Users
        self.user_fp1 = self.Users.create({
            'name': 'Phase4 FP1 User',
            'login': 'phase4_fp1_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.user_fp2 = self.Users.create({
            'name': 'Phase4 FP2 User',
            'login': 'phase4_fp2_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.user_asm = self.Users.create({
            'name': 'Phase4 ASM User',
            'login': 'phase4_asm_user',
            'groups_id': [(6, 0, [self.grp_asm.id])],
        })
        self.user_nsm = self.Users.create({
            'name': 'Phase4 NSM User',
            'login': 'phase4_nsm_user',
            'groups_id': [(6, 0, [self.grp_nsm.id])],
        })
        self.user_director = self.Users.create({
            'name': 'Phase4 Director User',
            'login': 'phase4_director_user',
            'groups_id': [(6, 0, [self.grp_director.id])],
        })

        # Hierarchy
        self.emp_asm = self.Employee.create({
            'name': 'Phase4 ASM Employee',
            'user_id': self.user_asm.id,
        })
        self.emp_fp1 = self.Employee.create({
            'name': 'Phase4 FP1 Employee',
            'user_id': self.user_fp1.id,
            'parent_id': self.emp_asm.id,
        })
        self.emp_fp2 = self.Employee.create({
            'name': 'Phase4 FP2 Employee',
            'user_id': self.user_fp2.id,
        })

    def test_01_at_least_one_amount_required(self):
        """Test validation: at least one amount > 0 is required, and non-negative constraint."""
        # 1. All amounts zero raises ValidationError
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': date.today(),
            })

        # 2. Negative amount raises ValidationError
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': date.today(),
                'promotion': -100.0,
            })

        # 3. Valid single non-voucher category succeeds and computes total
        exp = self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': date.today(),
            'promotion': 250.0,
            'stationery': 150.0,
        })
        self.assertTrue(exp.id)
        self.assertEqual(exp.total_amount, 400.0)

    def test_02_voucher_required_for_the_four_categories(self):
        """Vouchers are required for Entertainment, Courier, Photocopy, and Hotel Rent when amount > 0."""
        today = date.today()

        # Entertainment without voucher -> Error
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': today,
                'entertainment': 300.0,
            })

        # Courier without voucher -> Error
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': today,
                'courier': 120.0,
            })

        # Photocopy without voucher -> Error
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': today,
                'photocopy': 80.0,
            })

        # Hotel rent without voucher -> Error
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': today,
                'hotel_rent': 1500.0,
            })

        # With vouchers provided -> Success
        exp = self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
            'entertainment': 300.0,
            'voucher_entertainment': VALID_JPEG_B64,
            'courier': 120.0,
            'voucher_courier': VALID_JPEG_B64,
            'photocopy': 80.0,
            'voucher_photocopy': VALID_JPEG_B64,
            'hotel_rent': 1500.0,
            'voucher_hotel_rent': VALID_JPEG_B64,
        })
        self.assertTrue(exp.id)
        self.assertEqual(exp.total_amount, 2000.0)

    def test_03_voucher_file_type_and_size_limits(self):
        """Only JPEG, PNG, WebP <= 5 MB allowed as vouchers."""
        today = date.today()

        # 1. Plain text / PDF magic bytes rejected
        fake_pdf = base64.b64encode(b'%PDF-1.4 header contents').decode('utf-8')
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': today,
                'entertainment': 200.0,
                'voucher_entertainment': fake_pdf,
            })

        # 2. File exceeding 5 MB rejected
        large_bytes = b'\xff\xd8\xff\xe0' + b'X' * (6 * 1024 * 1024)
        large_b64 = base64.b64encode(large_bytes).decode('utf-8')
        with self.assertRaises(ValidationError):
            self.DailyExpense.create({
                'employee_id': self.emp_fp1.id,
                'date': today,
                'entertainment': 200.0,
                'voucher_entertainment': large_b64,
            })

        # 3. Valid PNG magic bytes accepted
        png_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        png_b64 = base64.b64encode(png_bytes).decode('utf-8')
        exp = self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
            'courier': 150.0,
            'voucher_courier': png_b64,
        })
        self.assertTrue(exp.id)

    def test_04_idempotency_client_uuid(self):
        """Duplicate client_uuid raises IntegrityError."""
        uuid_token = 'expense-uuid-test-9999'
        exp1 = self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': date.today(),
            'promotion': 500.0,
            'client_uuid': uuid_token,
        })
        self.assertTrue(exp1.id)

        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'):
                self.DailyExpense.create({
                    'employee_id': self.emp_fp1.id,
                    'date': date.today(),
                    'promotion': 500.0,
                    'client_uuid': uuid_token,
                })

    def test_05_record_rule_visibility(self):
        """Marketer sees own expenses, manager sees subordinate expenses, higher roles see all."""
        today = date.today()

        exp_fp1 = self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
            'promotion': 100.0,
        })
        exp_fp2 = self.DailyExpense.create({
            'employee_id': self.emp_fp2.id,
            'date': today,
            'promotion': 200.0,
        })

        # 1. FP1 sees own only
        fp1_records = self.DailyExpense.with_user(self.user_fp1).search([])
        self.assertIn(exp_fp1, fp1_records)
        self.assertNotIn(exp_fp2, fp1_records)

        # 2. FP2 sees own only
        fp2_records = self.DailyExpense.with_user(self.user_fp2).search([])
        self.assertIn(exp_fp2, fp2_records)
        self.assertNotIn(exp_fp1, fp2_records)

        # 3. ASM sees subordinate FP1's expense, but NOT FP2
        asm_records = self.DailyExpense.with_user(self.user_asm).search([])
        self.assertIn(exp_fp1, asm_records)
        self.assertNotIn(exp_fp2, asm_records)

        # 4. NSM sees both
        nsm_records = self.DailyExpense.with_user(self.user_nsm).search([])
        self.assertIn(exp_fp1, nsm_records)
        self.assertIn(exp_fp2, nsm_records)

        # 5. Director sees both
        dir_records = self.DailyExpense.with_user(self.user_director).search([])
        self.assertIn(exp_fp1, dir_records)
        self.assertIn(exp_fp2, dir_records)

    def test_06_attachment_security(self):
        """Attachments linked to an expense inherit read security: unauthorized users cannot read them."""
        today = date.today()
        exp_fp1 = self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
            'entertainment': 300.0,
            'voucher_entertainment': VALID_JPEG_B64,
            'voucher_entertainment_filename': 'ent_receipt.jpg',
        })

        # Find the ir.attachment created by attachment=True
        attachment = self.Attachment.sudo().search([
            ('res_model', '=', 'ffm.daily.expense'),
            ('res_id', '=', exp_fp1.id),
            ('res_field', '=', 'voucher_entertainment')
        ], limit=1)
        self.assertTrue(attachment, "Attachment record should exist for binary field with attachment=True")

        # 1. FP1 can read own voucher attachment
        att_fp1 = attachment.with_user(self.user_fp1)
        self.assertTrue(att_fp1.datas)

        # 2. Manager (ASM) can read subordinate's voucher attachment
        att_asm = attachment.with_user(self.user_asm)
        self.assertTrue(att_asm.datas)

        # 3. Unrelated FP2 CANNOT read FP1's voucher attachment (AccessError raised by ir.attachment.check)
        att_fp2 = attachment.with_user(self.user_fp2)
        with self.assertRaises(AccessError):
            att_fp2.read(['datas'])

    def test_07_daily_report_linking_and_totals(self):
        """Daily expense links to today's daily report and updates total_expense_tk."""
        today = date.today()
        report = self.DailyReport.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
        })

        exp = self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
            'carrying': 350.0,
            'banking': 150.0,
        })
        self.assertEqual(exp.daily_report_id.id, report.id, "Should auto-link to today's daily report")

        report.invalidate_cache()
        self.assertEqual(report.total_expense_tk, 500.0)


@tagged('-at_install', 'post_install')
class TestFFMPhase4Http(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.http']._clear_routing_map()

    def test_01_http_expense_workflow(self):
        """Test /ff/expense page, JSON submission, voucher enforcement, idempotency, and summary view."""
        self.env['ffm.daily.expense'].sudo().search([('client_uuid', '=', 'http-expense-uuid-demo-777')]).unlink()

        # 1. Authenticate with demo marketer
        self.authenticate('ffm_fp_demo', 'Demo12345!')

        # 2. GET /ff/expense
        res_page = self.url_open('/ff/expense')
        self.assertEqual(res_page.status_code, 200)
        self.assertIn('Daily Expense', res_page.content.decode('utf-8'))

        # 3. Submit expense without required voucher -> Should return error
        err_payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'entertainment': 400.0,
                'note': 'Tea and biscuits with chemist',
                'latitude': 23.7461,
                'longitude': 90.3742,
                'gps_accuracy': 12.0,
            }
        }
        res_err = self.url_open(
            '/ff/expense/submit',
            data=json.dumps(err_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_err.status_code, 200)
        data_err = res_err.json().get('result', {})
        self.assertEqual(data_err.get('status'), 'error')
        self.assertIn('voucher image is required', data_err.get('message', ''))

        # 4. Submit valid expense with voucher and client_uuid
        uuid_token = 'http-expense-uuid-demo-777'
        valid_payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'entertainment': 400.0,
                'voucher_entertainment': 'data:image/jpeg;base64,' + VALID_JPEG_B64,
                'carrying': 200.0,
                'note': 'Sample delivery carrying and tea',
                'client_uuid': uuid_token,
                'latitude': 23.7461,
                'longitude': 90.3742,
                'gps_accuracy': 12.0,
            }
        }
        res_ok = self.url_open(
            '/ff/expense/submit',
            data=json.dumps(valid_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_ok.status_code, 200)
        data_ok = res_ok.json().get('result', {})
        self.assertEqual(data_ok.get('status'), 'success')
        expense_id = data_ok.get('expense_id')
        self.assertTrue(expense_id)

        # 5. Idempotent retry with same client_uuid
        res_retry = self.url_open(
            '/ff/expense/submit',
            data=json.dumps(valid_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_retry.status_code, 200)
        data_retry = res_retry.json().get('result', {})
        self.assertEqual(data_retry.get('status'), 'success')
        self.assertEqual(data_retry.get('expense_id'), expense_id)

        # 6. Check /ff/entries/today page displays the expense
        res_entries = self.url_open('/ff/entries/today')
        self.assertEqual(res_entries.status_code, 200)
        entries_content = res_entries.content.decode('utf-8')
        self.assertIn('Daily Expense', entries_content)
        self.assertIn('600', entries_content)
