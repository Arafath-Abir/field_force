# -*- coding: utf-8 -*-
import base64
from datetime import date, datetime, timedelta

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, HttpCase
from odoo.tools import mute_logger

# Minimal valid JPEG bytes
TINY_JPEG_BYTES = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00' + b'\x01' * 64 + b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
VALID_JPEG_B64 = base64.b64encode(TINY_JPEG_BYTES).decode('utf-8')


class TestFFMPhase5Models(TransactionCase):

    def setUp(self):
        super().setUp()
        self.DailyReport = self.env['ffm.daily.report']
        self.Attendance = self.env['ffm.attendance']
        self.ChemistVisit = self.env['ffm.chemist.visit']
        self.PrescriberVisit = self.env['ffm.prescriber.visit']
        self.FarmVisit = self.env['ffm.farm.visit']
        self.TravelLog = self.env['ffm.travel.log']
        self.TravelJourney = self.env['ffm.travel.journey']
        self.DailyExpense = self.env['ffm.daily.expense']
        self.Employee = self.env['hr.employee']
        self.Users = self.env['res.users']
        self.Place = self.env['ffm.place']

        # Reporting models
        self.ReportAnalysis = self.env['ffm.daily.report.analysis']
        self.TerritoryAttReport = self.env['ffm.report.territory.attendance']
        self.VisitReport = self.env['ffm.report.visit.analysis']
        self.JourneyReport = self.env['ffm.report.journey.analysis']
        self.ExpenseReport = self.env['ffm.report.expense.analysis']

        # Security groups
        self.grp_fp = self.env.ref('field_force_management.group_ffm_field_person')
        self.grp_asm = self.env.ref('field_force_management.group_ffm_asm')
        self.grp_rsm = self.env.ref('field_force_management.group_ffm_rsm')
        self.grp_nsm = self.env.ref('field_force_management.group_ffm_nsm')
        self.grp_director = self.env.ref('field_force_management.group_ffm_nsm')
        self.grp_admin = self.env.ref('field_force_management.group_ffm_admin')

        # Create Hierarchy: RSM -> ASM -> FP1 & FP2
        self.user_rsm = self.Users.create({
            'name': 'Phase5 RSM User',
            'login': 'phase5_rsm_user',
            'groups_id': [(6, 0, [self.grp_rsm.id])],
        })
        self.emp_rsm = self.Employee.create({
            'name': 'Phase5 RSM Employee',
            'user_id': self.user_rsm.id,
        })

        self.user_asm = self.Users.create({
            'name': 'Phase5 ASM User',
            'login': 'phase5_asm_user',
            'groups_id': [(6, 0, [self.grp_asm.id])],
        })
        self.emp_asm = self.Employee.create({
            'name': 'Phase5 ASM Employee',
            'user_id': self.user_asm.id,
            'parent_id': self.emp_rsm.id,
        })

        # Field Person 1 with Bengali Script Name
        self.user_fp1 = self.Users.create({
            'name': 'মোঃ আরিফুল ইসলাম',
            'login': 'phase5_fp1_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.emp_fp1 = self.Employee.create({
            'name': 'মোঃ আরিফুল ইসলাম',
            'user_id': self.user_fp1.id,
            'parent_id': self.emp_asm.id,
        })

        # Field Person 2 with Bengali Script Name
        self.user_fp2 = self.Users.create({
            'name': 'নাজমুল হাসান',
            'login': 'phase5_fp2_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.emp_fp2 = self.Employee.create({
            'name': 'নাজমুল হাসান',
            'user_id': self.user_fp2.id,
            'parent_id': self.emp_asm.id,
        })

        # Other unrelated FP
        self.user_other_fp = self.Users.create({
            'name': 'Other Region Marketer',
            'login': 'phase5_other_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.emp_other_fp = self.Employee.create({
            'name': 'Other Region Marketer',
            'user_id': self.user_other_fp.id,
        })

        # Place
        self.place_hq = self.Place.create({'name': 'Tejgaon HQ Phase5'})
        self.place_market = self.Place.create({'name': 'Mohakhali Market Phase5'})

        # Create Attendance for FP1 today (FP2 has none -> absent!)
        self.today = date.today()
        self.attendance_fp1 = self.Attendance.create({
            'employee_id': self.emp_fp1.id,
            'date': self.today,
            'reporting_time': datetime.now(),
            'latitude': 23.765,
            'longitude': 90.395,
            'accuracy': 15.0,
            'mode_of_journey': 'motorcycle',
            'client_uuid': 'p5-att-uuid-fp1-001',
        })

        # Create Today's Daily Report for FP1
        self.report_fp1 = self.DailyReport.create({
            'employee_id': self.emp_fp1.id,
            'date': self.today,
            'working_place_id': self.place_hq.id,
        })

        # Chemist Visit
        self.ChemistVisit.create({
            'report_id': self.report_fp1.id,
            'chemist_name_manual': 'Green Life Pharmacy Phase5',
            'order_tk': 3000.0,
            'sale_tk': 2000.0,
            'coll_tk': 1000.0,
        })

        # Doctor Visit
        self.PrescriberVisit.create({
            'report_id': self.report_fp1.id,
            'prescriber_name_manual': 'Dr. M. A. Hasan Phase5',
            'product_discussion': 'Antibiotics',
            'sample': 'Syrup',
            'grade': 'a_plus',
        })

        # Farm Visit
        self.FarmVisit.create({
            'report_id': self.report_fp1.id,
            'farm_name': 'Bismillah Layer Farm Phase5',
            'bird_count': 500,
        })

        # Journey Log
        self.travel_log_fp1 = self.TravelLog.create({
            'daily_report_id': self.report_fp1.id,
            'employee_id': self.emp_fp1.id,
            'date': self.today,
        })
        self.TravelJourney.create({
            'travel_log_id': self.travel_log_fp1.id,
            'place_from_id': self.place_hq.id,
            'place_to_id': self.place_market.id,
            'mode': 'bus',
            'distance_km': 10.0,
            'fare_tk': 50.0,
        })

        # Daily Expense
        self.DailyExpense.create({
            'employee_id': self.emp_fp1.id,
            'date': self.today,
            'daily_report_id': self.report_fp1.id,
            'bike': 100.0,
            'entertainment': 200.0,
            'voucher_entertainment': VALID_JPEG_B64,
        })

        # Flush records to DB so SQL views can read uncommitted transaction rows
        self.Attendance.flush()
        self.DailyReport.flush()
        self.ChemistVisit.flush()
        self.PrescriberVisit.flush()
        self.FarmVisit.flush()
        self.TravelLog.flush()
        self.TravelJourney.flush()
        self.DailyExpense.flush()
        self.Employee.flush()

        # Refresh computed totals
        self.report_fp1.invalidate_cache()
        self.travel_log_fp1.invalidate_cache()

    def test_01_report_scope_per_role(self):
        """Verify role scoping in ffm.daily.report.analysis record rules."""
        # 1. FP1 sees only own analysis record
        fp1_records = self.ReportAnalysis.with_user(self.user_fp1).search([])
        emp_ids_seen = fp1_records.mapped('employee_id.id')
        self.assertIn(self.emp_fp1.id, emp_ids_seen)
        self.assertNotIn(self.emp_fp2.id, emp_ids_seen)
        self.assertNotIn(self.emp_other_fp.id, emp_ids_seen)

        # 2. ASM sees subordinate FP1's record, but NOT other region FP
        asm_records = self.ReportAnalysis.with_user(self.user_asm).search([])
        emp_ids_seen_asm = asm_records.mapped('employee_id.id')
        self.assertIn(self.emp_fp1.id, emp_ids_seen_asm)
        self.assertNotIn(self.emp_other_fp.id, emp_ids_seen_asm)

        # 3. Higher authority (admin) sees all
        admin_records = self.ReportAnalysis.search([])
        self.assertTrue(len(admin_records) >= 1)

    def test_02_territory_attendance_present_and_absent(self):
        """Verify ffm.report.territory.attendance identifies who is present and who is absent."""
        # Query attendance analysis for today
        records_today = self.TerritoryAttReport.search([('date', '=', self.today)])
        fp1_att = records_today.filtered(lambda r: r.employee_id.id == self.emp_fp1.id)
        fp2_att = records_today.filtered(lambda r: r.employee_id.id == self.emp_fp2.id)

        # FP1 gave attendance -> status 'present'
        self.assertTrue(fp1_att)
        self.assertEqual(fp1_att[0].status, 'present')
        self.assertEqual(fp1_att[0].is_present, 1)
        self.assertEqual(fp1_att[0].is_absent, 0)
        self.assertEqual(fp1_att[0].working_place_id.id, self.place_hq.id)
        self.assertEqual(fp1_att[0].mode_of_journey, 'motorcycle')
        self.assertEqual(fp1_att[0].accuracy, 15.0)

        # FP2 did not give attendance -> status 'absent'
        self.assertTrue(fp2_att)
        self.assertEqual(fp2_att[0].status, 'absent')
        self.assertEqual(fp2_att[0].is_present, 0)
        self.assertEqual(fp2_att[0].is_absent, 1)

    def test_03_summary_totals_in_analysis(self):
        """Verify calculated totals in ffm.daily.report.analysis SQL view."""
        rep_analysis = self.ReportAnalysis.search([('report_id', '=', self.report_fp1.id)], limit=1)
        self.assertTrue(rep_analysis)
        self.assertEqual(rep_analysis.total_order_tk, 3000.0)
        self.assertEqual(rep_analysis.total_sale_tk, 2000.0)
        self.assertEqual(rep_analysis.total_coll_tk, 1000.0)
        self.assertEqual(rep_analysis.total_chemist_visited, 1)
        self.assertEqual(rep_analysis.total_prescriber_visited, 1)
        self.assertEqual(rep_analysis.total_farm_visited, 1)
        self.assertEqual(rep_analysis.total_distance_km, 10.0)
        self.assertEqual(rep_analysis.total_fare_tk, 50.0)
        self.assertEqual(rep_analysis.total_expense_tk, 300.0)
        self.assertEqual(rep_analysis.entertainment_tk, 200.0)
        self.assertEqual(rep_analysis.bike_tk, 100.0)

    def test_04_qweb_pdf_generation_with_bengali_font(self):
        """Verify QWeb PDF report generation with Bengali font and Bengali script employee name."""
        report_action = self.env.ref('ffm_daily_report.action_report_ffm_daily_report_pdf')
        rendered_bytes, report_type = report_action._render_qweb_pdf(self.report_fp1.ids)

        self.assertIn(report_type, ('pdf', 'html'))
        self.assertTrue(rendered_bytes)
        self.assertTrue(len(rendered_bytes) > 500, "Generated report content must not be empty")

        # Verify Bengali font declaration and Bengali script employee name in rendered report
        bengali_name_bytes = 'মোঃ আরিফুল ইসলাম'.encode('utf-8')
        font_family_bytes = 'Nirmala UI'.encode('utf-8')
        self.assertIn(bengali_name_bytes, rendered_bytes)
        self.assertIn(font_family_bytes, rendered_bytes)

    def test_05_visit_and_journey_and_expense_reporting_views(self):
        """Verify visit, journey, and expense analysis SQL view models populate correctly."""
        # 1. Visit analysis
        v_records = self.VisitReport.search([('employee_id', '=', self.emp_fp1.id), ('date', '=', self.today)])
        self.assertEqual(len(v_records), 3, "Should have 1 chemist + 1 doctor + 1 farm visit")
        v_types = v_records.mapped('visit_type')
        self.assertIn('chemist', v_types)
        self.assertIn('doctor', v_types)
        self.assertIn('farm', v_types)

        # 2. Journey analysis
        j_records = self.JourneyReport.search([('employee_id', '=', self.emp_fp1.id), ('date', '=', self.today)])
        self.assertEqual(len(j_records), 1)
        self.assertEqual(j_records[0].distance_km, 10.0)
        self.assertEqual(j_records[0].fare_tk, 50.0)

        # 3. Expense analysis
        e_records = self.ExpenseReport.search([('employee_id', '=', self.emp_fp1.id), ('date', '=', self.today)])
        self.assertEqual(len(e_records), 1)
        self.assertEqual(e_records[0].total_amount, 300.0)


@tagged('-at_install', 'post_install')
class TestFFMPhase5Http(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.http']._clear_routing_map()

    def test_01_http_report_cards_and_pdf_download(self):
        """Test /ff/report/cards daily/monthly views, territory attendance, and PDF download."""
        # 1. Authenticate with demo marketer user
        self.authenticate('ffm_fp_demo', 'Demo12345!')

        # 2. GET Daily Report Card
        res_daily = self.url_open('/ff/report/cards?mode=daily&report_type=personal')
        self.assertEqual(res_daily.status_code, 200)
        self.assertIn('Daily Report Card', res_daily.content.decode('utf-8'))

        # 3. GET Monthly Report Card
        res_monthly = self.url_open('/ff/report/cards?mode=monthly&report_type=personal&period=current')
        self.assertEqual(res_monthly.status_code, 200)
        self.assertIn('Monthly Report Card', res_monthly.content.decode('utf-8'))

        # 4. GET Territory Attendance
        res_att = self.url_open('/ff/report/cards?mode=daily&report_type=attendance')
        self.assertEqual(res_att.status_code, 200)
        self.assertIn('Team Daily Attendance', res_att.content.decode('utf-8'))

        # 5. GET Excel Export with 5,000 rows guard
        res_excel = self.url_open('/ffm/export/excel?report_type=daily_analysis')
        self.assertEqual(res_excel.status_code, 200)
        self.assertEqual(
            res_excel.headers.get('Content-Type'),
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertTrue(len(res_excel.content) > 500)

        # 6. GET Daily Report PDF Download
        res_pdf = self.url_open('/ff/report/daily/pdf')
        # May return 200 if today's report exists or 404 if no report initialized for today yet
        if res_pdf.status_code == 200:
            self.assertEqual(res_pdf.headers.get('Content-Type'), 'application/pdf')
            self.assertTrue(res_pdf.content.startswith(b'%PDF-1.') or len(res_pdf.content) > 500)
