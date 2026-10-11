# -*- coding: utf-8 -*-
from datetime import date
from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError
from odoo.tools import mute_logger


class TestFFMDailyReport(TransactionCase):

    def setUp(self):
        super().setUp()
        self.DailyReport = self.env['ffm.daily.report']
        self.Employee = self.env['hr.employee']
        self.Users = self.env['res.users']

        # Security groups
        self.grp_fp = self.env.ref('field_force_management.group_ffm_field_person')
        self.grp_asm = self.env.ref('field_force_management.group_ffm_asm')
        self.grp_rsm = self.env.ref('field_force_management.group_ffm_rsm')
        self.grp_dsm = self.env.ref('field_force_management.group_ffm_dsm')
        self.grp_nsm = self.env.ref('field_force_management.group_ffm_nsm')
        self.grp_director = self.env.ref('field_force_management.group_ffm_director')
        self.grp_admin = self.env.ref('field_force_management.group_ffm_admin')

        # Create Users
        self.user_director = self.Users.create({
            'name': 'Test Director User',
            'login': 'test_director_user',
            'groups_id': [(6, 0, [self.grp_director.id])],
        })
        self.user_nsm = self.Users.create({
            'name': 'Test NSM User',
            'login': 'test_nsm_user',
            'groups_id': [(6, 0, [self.grp_nsm.id])],
        })
        self.user_asm = self.Users.create({
            'name': 'Test ASM User',
            'login': 'test_asm_user',
            'groups_id': [(6, 0, [self.grp_asm.id])],
        })
        self.user_other_asm = self.Users.create({
            'name': 'Other ASM User',
            'login': 'test_other_asm_user',
            'groups_id': [(6, 0, [self.grp_asm.id])],
        })
        self.user_fp1 = self.Users.create({
            'name': 'Test Field Person 1',
            'login': 'test_fp1_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.user_fp2 = self.Users.create({
            'name': 'Test Field Person 2',
            'login': 'test_fp2_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })

        # Create Employees with hierarchy
        # ASM Employee
        self.emp_asm = self.Employee.create({
            'name': 'ASM Employee',
            'user_id': self.user_asm.id,
        })
        self.emp_other_asm = self.Employee.create({
            'name': 'Other ASM Employee',
            'user_id': self.user_other_asm.id,
        })
        # FP1 reports to ASM
        self.emp_fp1 = self.Employee.create({
            'name': 'Field Person 1 Employee',
            'user_id': self.user_fp1.id,
            'parent_id': self.emp_asm.id,
        })
        # FP2 reports to Other ASM
        self.emp_fp2 = self.Employee.create({
            'name': 'Field Person 2 Employee',
            'user_id': self.user_fp2.id,
            'parent_id': self.emp_other_asm.id,
        })

    def test_01_unique_daily_report_constraint(self):
        """Verify that only one daily report can be created per employee per date."""
        today = date.today()
        report1 = self.DailyReport.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
        })
        self.assertTrue(report1.id)

        # Attempt to create duplicate report on same date for same employee
        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'):
                self.DailyReport.create({
                    'employee_id': self.emp_fp1.id,
                    'date': today,
                })

    def test_02_approval_rules(self):
        """Verify direct manager or higher authority approval enforcement."""
        report = self.DailyReport.create({
            'employee_id': self.emp_fp1.id,
            'date': date.today(),
        })
        report.action_submit()
        self.assertEqual(report.state, 'submitted')

        # 1. Field person cannot approve
        with self.assertRaises(UserError):
            report.with_user(self.user_fp1).action_approve()

        # 2. Other ASM (not direct manager) cannot approve
        with self.assertRaises(UserError):
            report.with_user(self.user_other_asm).action_approve()

        # 3. Direct manager (user_asm) CAN approve
        report.with_user(self.user_asm).action_approve()
        self.assertEqual(report.state, 'approved')

        # Reset to draft and test higher authority
        report.action_reset_draft()
        report.action_submit()

        # 4. NSM (higher role) CAN approve
        report.with_user(self.user_nsm).action_approve()
        self.assertEqual(report.state, 'approved')

        # Reset to draft and test Director
        report.action_reset_draft()
        report.action_submit()

        # 5. Director (higher role) CAN approve
        report.with_user(self.user_director).action_approve()
        self.assertEqual(report.state, 'approved')

    def test_03_record_rule_visibility(self):
        """Verify record rule visibility: FP own only, ASM direct reports, NSM/Director all."""
        today = date.today()
        report_fp1 = self.DailyReport.create({
            'employee_id': self.emp_fp1.id,
            'date': today,
        })
        report_fp2 = self.DailyReport.create({
            'employee_id': self.emp_fp2.id,
            'date': today,
        })
        report_asm = self.DailyReport.create({
            'employee_id': self.emp_asm.id,
            'date': today,
        })

        # Field Person 1 sees only own report
        fp1_reports = self.DailyReport.with_user(self.user_fp1).search([])
        self.assertIn(report_fp1, fp1_reports)
        self.assertNotIn(report_fp2, fp1_reports)
        self.assertNotIn(report_asm, fp1_reports)

        # ASM sees own report + FP1 report (direct report), but NOT FP2
        asm_reports = self.DailyReport.with_user(self.user_asm).search([])
        self.assertIn(report_fp1, asm_reports)
        self.assertIn(report_asm, asm_reports)
        self.assertNotIn(report_fp2, asm_reports)

        # NSM sees ALL reports
        nsm_reports = self.DailyReport.with_user(self.user_nsm).search([])
        self.assertIn(report_fp1, nsm_reports)
        self.assertIn(report_fp2, nsm_reports)
        self.assertIn(report_asm, nsm_reports)

        # Director sees ALL reports
        director_reports = self.DailyReport.with_user(self.user_director).search([])
        self.assertIn(report_fp1, director_reports)
        self.assertIn(report_fp2, director_reports)
        self.assertIn(report_asm, director_reports)
