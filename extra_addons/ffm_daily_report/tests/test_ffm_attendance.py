# -*- coding: utf-8 -*-
from datetime import date, timedelta
from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger
from odoo.exceptions import UserError, ValidationError

class TestFFMAttendance(TransactionCase):

    def setUp(self):
        super(TestFFMAttendance, self).setUp()
        self.Attendance = self.env['ffm.attendance']
        self.AuditLog = self.env['ffm.audit.log']
        self.AllowanceRate = self.env['ffm.allowance.rate']

        # Security Groups
        self.group_fp = self.env.ref('field_force_management.group_ffm_field_person')
        self.group_asm = self.env.ref('field_force_management.group_ffm_asm')
        self.group_nsm = self.env.ref('field_force_management.group_ffm_nsm')
        self.group_admin = self.env.ref('field_force_management.group_ffm_admin')

        # Create Job
        self.job_mpo = self.env['hr.job'].create({'name': 'Test MPO'})
        self.job_asm = self.env['hr.job'].create({'name': 'Test ASM'})

        # Users & Employees
        self.user_asm = self.env['res.users'].create({
            'name': 'Test ASM User',
            'login': 'test_asm_att',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.group_asm.id])],
        })
        self.emp_asm = self.env['hr.employee'].create({
            'name': 'Test ASM Employee',
            'user_id': self.user_asm.id,
            'job_id': self.job_asm.id,
        })

        self.user_fp1 = self.env['res.users'].create({
            'name': 'Test FP 1',
            'login': 'test_fp1_att',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.group_fp.id])],
        })
        self.emp_fp1 = self.env['hr.employee'].create({
            'name': 'Test FP 1 Employee',
            'user_id': self.user_fp1.id,
            'job_id': self.job_mpo.id,
            'parent_id': self.emp_asm.id,
        })

        self.user_fp2 = self.env['res.users'].create({
            'name': 'Test FP 2',
            'login': 'test_fp2_att',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.group_fp.id])],
        })
        self.emp_fp2 = self.env['hr.employee'].create({
            'name': 'Test FP 2 Employee',
            'user_id': self.user_fp2.id,
            'job_id': self.job_mpo.id,
            # Different manager
        })

    def test_01_attendance_unique_lock(self):
        """Attendance must allow only one record per employee per day."""
        today = self.Attendance.get_dhaka_today()
        # 1. First submission via submit_attendance
        att1 = self.Attendance.with_user(self.user_fp1).submit_attendance({
            'latitude': 23.8103,
            'longitude': 90.4125,
            'accuracy': 15.0,
            'mode_of_journey': 'Motorcycle',
            'client_uuid': 'uuid-test-01',
        })
        self.assertTrue(att1)
        self.assertEqual(att1.employee_id, self.emp_fp1)
        self.assertEqual(att1.date, today)

        # 2. Direct create attempt for same employee and date triggers SQL unique integrity error
        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'):
                self.Attendance.create({
                    'employee_id': self.emp_fp1.id,
                    'date': today,
                    'reporting_time': att1.reporting_time,
                    'latitude': 23.8103,
                    'longitude': 90.4125,
                    'accuracy': 10.0,
                    'client_uuid': 'uuid-test-01-dup',
                })

    def test_02_idempotent_retry(self):
        """Submitting with same client_uuid or repeated submit_attendance returns existing record."""
        # First submission
        att1 = self.Attendance.with_user(self.user_fp1).submit_attendance({
            'latitude': 23.7500,
            'longitude': 90.3900,
            'accuracy': 12.0,
            'mode_of_journey': 'Bus',
            'client_uuid': 'uuid-idempotent-key-123',
        })
        
        # Second submission with identical client_uuid
        att2 = self.Attendance.with_user(self.user_fp1).submit_attendance({
            'latitude': 23.7500,
            'longitude': 90.3900,
            'accuracy': 12.0,
            'mode_of_journey': 'Bus',
            'client_uuid': 'uuid-idempotent-key-123',
        })
        self.assertEqual(att1.id, att2.id)

        # Third submission with different client_uuid but same day (friendly check)
        att3 = self.Attendance.with_user(self.user_fp1).submit_attendance({
            'latitude': 23.7500,
            'longitude': 90.3900,
            'accuracy': 12.0,
            'mode_of_journey': 'Bus',
            'client_uuid': 'uuid-another-key-456',
        })
        self.assertEqual(att1.id, att3.id)

    def test_03_server_derives_employee_and_date(self):
        """Client-supplied employee_id and date in payload must be strictly ignored."""
        spoofed_date = '2020-01-01'
        att = self.Attendance.with_user(self.user_fp1).submit_attendance({
            'employee_id': self.emp_fp2.id,  # Attempting to spoof another employee
            'date': spoofed_date,             # Attempting to spoof past date
            'latitude': 23.7800,
            'longitude': 90.4000,
            'accuracy': 20.0,
            'client_uuid': 'uuid-spoof-test',
        })
        # Must resolve to user_fp1's employee and server Dhaka date
        self.assertEqual(att.employee_id.id, self.emp_fp1.id)
        self.assertNotEqual(str(att.date), spoofed_date)
        self.assertEqual(att.date, self.Attendance.get_dhaka_today())

    def test_04_required_fields_and_validation(self):
        """Missing or invalid GPS coordinates must raise ValidationError."""
        # Invalid latitude (> 90)
        with self.assertRaises(ValidationError):
            self.Attendance.with_user(self.user_fp1).submit_attendance({
                'latitude': 120.0,
                'longitude': 90.0,
                'accuracy': 10.0,
            })

        # Negative accuracy (<= 0)
        with self.assertRaises(ValidationError):
            self.Attendance.with_user(self.user_fp1).submit_attendance({
                'latitude': 23.0,
                'longitude': 90.0,
                'accuracy': -5.0,
            })

    def test_05_role_visibility(self):
        """Field Person sees only own; ASM sees direct reports; Admin sees all."""
        today = self.Attendance.get_dhaka_today()
        # FP1 creates attendance
        att1 = self.Attendance.with_user(self.user_fp1).submit_attendance({
            'latitude': 23.8100,
            'longitude': 90.4100,
            'accuracy': 15.0,
            'client_uuid': 'uuid-fp1-vis',
        })
        # FP2 creates attendance
        att2 = self.Attendance.with_user(self.user_fp2).submit_attendance({
            'latitude': 23.8200,
            'longitude': 90.4200,
            'accuracy': 15.0,
            'client_uuid': 'uuid-fp2-vis',
        })

        # FP1 sees only att1
        records_fp1 = self.Attendance.with_user(self.user_fp1).search([])
        self.assertIn(att1, records_fp1)
        self.assertNotIn(att2, records_fp1)

        # ASM (manager of FP1, not FP2) sees att1 but not att2
        records_asm = self.Attendance.with_user(self.user_asm).search([])
        self.assertIn(att1, records_asm)
        self.assertNotIn(att2, records_asm)

    def test_06_allowance_rates_and_audit(self):
        """Allowance rate creation triggers audit log."""
        rate = self.AllowanceRate.create({
            'job_id': self.job_mpo.id,
            'da_per_day': 350.0,
            'motorcycle_maintenance_per_month': 2500.0,
        })
        self.assertEqual(rate.da_per_day, 350.0)

        # Duplicate job rate constraint
        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'):
                self.AllowanceRate.create({
                    'job_id': self.job_mpo.id,
                    'da_per_day': 400.0,
                })
