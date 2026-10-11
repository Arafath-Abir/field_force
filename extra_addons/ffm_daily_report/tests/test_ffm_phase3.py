# -*- coding: utf-8 -*-
import json
from datetime import date
from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import ValidationError, UserError
from odoo.tools import mute_logger


class TestFFMPhase3Models(TransactionCase):

    def setUp(self):
        super().setUp()
        self.DailyReport = self.env['ffm.daily.report']
        self.ChemistVisit = self.env['ffm.chemist.visit']
        self.PrescriberVisit = self.env['ffm.prescriber.visit']
        self.FarmVisit = self.env['ffm.farm.visit']
        self.TravelLog = self.env['ffm.travel.log']
        self.TravelJourney = self.env['ffm.travel.journey']
        self.Place = self.env['ffm.place']
        self.Customer = self.env['customer.information']
        self.FareConfig = self.env['ffm.fare.config']
        self.Employee = self.env['hr.employee']
        self.Users = self.env['res.users']

        self.grp_fp = self.env.ref('field_force_management.group_ffm_field_person')

        # Create demo user and employee
        self.user_fp = self.Users.create({
            'name': 'Phase3 FP User',
            'login': 'phase3_fp_user',
            'groups_id': [(6, 0, [self.grp_fp.id])],
        })
        self.emp_fp = self.Employee.create({
            'name': 'Phase3 FP Employee',
            'user_id': self.user_fp.id,
        })

        # Create places
        self.place_from = self.Place.create({
            'name': 'Dhanmondi HQ Phase3',
            'lat': 23.7461,
            'lng': 90.3742,
            'active': True,
        })
        self.place_to = self.Place.create({
            'name': 'Mirpur Area Phase3',
            'lat': 23.8223,
            'lng': 90.3654,
            'active': True,
        })

        # Create customer records
        self.cust_chemist = self.Customer.create({
            'name': 'Lazz Pharma Dhanmondi',
            'type': 'chemist',
            'address': 'Dhanmondi, Dhaka',
            'active': True,
        })
        self.cust_doctor = self.Customer.create({
            'name': 'Dr. K. M. Rahman',
            'type': 'doctor',
            'address': 'Mirpur-10, Dhaka',
            'active': True,
        })

        # Create today's report
        self.report = self.DailyReport.get_or_create_today_report(
            employee_id=self.emp_fp.id,
            working_place_id=self.place_from.id
        )

    def test_01_chemist_visit_amount_validations(self):
        """Test whole number and non-negative constraints on Chemist Visit."""
        # Negative amount
        with self.assertRaises(ValidationError):
            self.ChemistVisit.create({
                'report_id': self.report.id,
                'chemist_id': self.cust_chemist.id,
                'order_tk': -500.0,
                'sale_tk': 0.0,
                'coll_tk': 0.0,
            })

        # Non-integer float amount
        with self.assertRaises(ValidationError):
            self.ChemistVisit.create({
                'report_id': self.report.id,
                'chemist_id': self.cust_chemist.id,
                'order_tk': 500.75,
                'sale_tk': 0.0,
                'coll_tk': 0.0,
            })

        # Valid whole numbers
        visit = self.ChemistVisit.create({
            'report_id': self.report.id,
            'chemist_id': self.cust_chemist.id,
            'order_tk': 1500.0,
            'sale_tk': 1200.0,
            'coll_tk': 1000.0,
        })
        self.assertTrue(visit.id)
        self.assertEqual(visit.order_tk, 1500.0)

    def test_02_manual_name_fallback_chemist_and_doctor(self):
        """Test fallback to manual name when customer is not pre-registered."""
        # Chemist: Neither selected nor manual name provided
        with self.assertRaises(ValidationError):
            self.ChemistVisit.create({
                'report_id': self.report.id,
                'chemist_id': False,
                'chemist_name_manual': '',
                'order_tk': 100.0,
                'sale_tk': 100.0,
                'coll_tk': 100.0,
            })

        # Chemist: Manual name only
        chem_manual = self.ChemistVisit.create({
            'report_id': self.report.id,
            'chemist_id': False,
            'chemist_name_manual': 'Local Unlisted Medical Store',
            'order_tk': 200.0,
            'sale_tk': 200.0,
            'coll_tk': 200.0,
        })
        self.assertTrue(chem_manual.id)
        self.assertEqual(chem_manual.chemist_name_manual, 'Local Unlisted Medical Store')

        # Doctor: Neither selected nor manual name provided
        with self.assertRaises(ValidationError):
            self.PrescriberVisit.create({
                'report_id': self.report.id,
                'prescriber_id': False,
                'prescriber_name_manual': '',
                'product_discussion': 'Discussion',
                'sample': 'Sample',
                'grade': 'a',
            })

        # Doctor: Manual name only
        doc_manual = self.PrescriberVisit.create({
            'report_id': self.report.id,
            'prescriber_id': False,
            'prescriber_name_manual': 'Dr. Unlisted Specialist',
            'product_discussion': 'Antibiotic Discussion',
            'sample': '1 Sample Box',
            'grade': 'b',
        })
        self.assertTrue(doc_manual.id)
        self.assertEqual(doc_manual.prescriber_name_manual, 'Dr. Unlisted Specialist')

    def test_03a_idempotency_chemist_client_uuid(self):
        """Verify unique client_uuid SQL constraint on Chemist Visit."""
        uuid_chem = 'client-uuid-chem-001'
        self.ChemistVisit.create({
            'report_id': self.report.id,
            'chemist_id': self.cust_chemist.id,
            'order_tk': 100.0,
            'sale_tk': 100.0,
            'coll_tk': 100.0,
            'client_uuid': uuid_chem,
        })
        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'):
                self.ChemistVisit.create({
                    'report_id': self.report.id,
                    'chemist_id': self.cust_chemist.id,
                    'order_tk': 200.0,
                    'sale_tk': 200.0,
                    'coll_tk': 200.0,
                    'client_uuid': uuid_chem,
                })

    def test_03b_idempotency_farm_client_uuid(self):
        """Verify unique client_uuid SQL constraint on Farm Visit."""
        uuid_farm = 'client-uuid-farm-001'
        self.FarmVisit.create({
            'report_id': self.report.id,
            'farm_name': 'Newtec Pioneer Agro',
            'bird_count': 1200,
            'client_uuid': uuid_farm,
        })
        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'):
                self.FarmVisit.create({
                    'report_id': self.report.id,
                    'farm_name': 'Duplicate Agro',
                    'client_uuid': uuid_farm,
                })

    def test_04_journey_leg_creation_and_nullable_link(self):
        """Verify journey leg linking to visits and ondelete='set null' behavior."""
        travel_log = self.report.travel_log_ids[:1]
        self.assertTrue(travel_log)

        chem_visit = self.ChemistVisit.create({
            'report_id': self.report.id,
            'chemist_id': self.cust_chemist.id,
            'order_tk': 500.0,
            'sale_tk': 500.0,
            'coll_tk': 500.0,
        })

        # Create leg linked to chemist visit with manual fare override
        leg = self.TravelJourney.create({
            'travel_log_id': travel_log.id,
            'place_from_id': self.place_from.id,
            'place_to_id': self.place_to.id,
            'mode': 'motorcycle',
            'distance_km': 12.5,
            'fare_tk': 150.0,  # Manual override
            'chemist_visit_id': chem_visit.id,
        })
        self.assertTrue(leg.id)
        self.assertEqual(leg.chemist_visit_id.id, chem_visit.id)
        self.assertEqual(leg.fare_tk, 150.0)

        # Unlink chemist visit: journey leg must NOT be deleted, link set to null
        chem_visit.unlink()
        self.assertTrue(leg.exists())
        self.assertFalse(leg.chemist_visit_id)

    def test_05a_farm_visit_bird_count_validation(self):
        """Verify bird_count negative validation."""
        with self.assertRaises(ValidationError):
            self.FarmVisit.create({
                'report_id': self.report.id,
                'farm_name': 'Invalid Bird Count Farm',
                'bird_count': -10,
            })

    def test_05b_farm_visit_and_summary_totals(self):
        """Verify Daily Report compute totals across all visit types."""
        # Add valid farm visit
        self.FarmVisit.create({
            'report_id': self.report.id,
            'farm_name': 'Sonar Bangla Agro Farm',
            'broiler': '2 Sheds',
            'bird_count': 5000,
        })

        # Add chemist visits
        self.ChemistVisit.create({
            'report_id': self.report.id,
            'chemist_name_manual': 'Shop 1',
            'order_tk': 2000.0,
            'sale_tk': 1500.0,
            'coll_tk': 1000.0,
        })
        self.ChemistVisit.create({
            'report_id': self.report.id,
            'chemist_name_manual': 'Shop 2',
            'order_tk': 3000.0,
            'sale_tk': 2500.0,
            'coll_tk': 2000.0,
        })

        # Add doctor visit
        self.PrescriberVisit.create({
            'report_id': self.report.id,
            'prescriber_name_manual': 'Dr. Test',
            'product_discussion': 'Discussion',
            'sample': 'Sample',
            'grade': 'a_plus',
        })

        # Re-compute / check stored totals on Daily Report
        self.report.invalidate_cache()
        self.report._compute_chemist_totals()
        self.report._compute_prescriber_totals()
        self.report._compute_farm_totals()

        self.assertEqual(self.report.total_order_tk, 5000.0)
        self.assertEqual(self.report.total_sale_tk, 4000.0)
        self.assertEqual(self.report.total_coll_tk, 3000.0)
        self.assertEqual(self.report.total_chemist_visited, 2)
        self.assertEqual(self.report.total_prescriber_visited, 1)
        self.assertEqual(self.report.total_farm_visited, 1)


@tagged('-at_install', 'post_install')
class TestFFMPhase3Http(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.http']._clear_routing_map()

    def test_01_http_visit_submission_and_entries_today(self):
        """Test HTTP JSON endpoints for chemist, doctor, and farm visits, and today's summary view."""
        # 1. Authenticate with demo marketer user created in demo_data.xml
        self.authenticate('ffm_fp_demo', 'Demo12345!')

        # 2. Initialize today's report
        place = self.env['ffm.place'].sudo().search([('active', '=', True)], limit=1)
        if not place:
            place = self.env['ffm.place'].sudo().create({'name': 'Test Thana Dhaka'})

        init_payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'working_place_id': place.id,
            }
        }
        res_init = self.url_open(
            '/ff/report/daily/init',
            data=json.dumps(init_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_init.status_code, 200)
        init_data = res_init.json().get('result', {})
        self.assertEqual(init_data.get('status'), 'success')

        # 3. Submit Chemist Visit with Journey Leg
        chem_payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'chemist_name_manual': 'Green Life Pharmacy HTTP Test',
                'order_tk': 4500,
                'sale_tk': 3500,
                'coll_tk': 2000,
                'note': 'Order taken for next week delivery',
                'place_from_id': place.id,
                'place_to_id': place.id,
                'mode': 'bus',
                'distance_km': 8.5,
                'fare_tk': 40.0,
                'client_uuid': 'http-test-chem-uuid-101',
            }
        }
        res_chem = self.url_open(
            '/ff/visit/chemist/submit',
            data=json.dumps(chem_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_chem.status_code, 200)
        chem_res = res_chem.json().get('result', {})
        self.assertEqual(chem_res.get('status'), 'success')
        visit_id = chem_res.get('visit_id')
        self.assertTrue(visit_id)

        # 4. Idempotency test: submit same chemist visit client_uuid again
        res_chem_retry = self.url_open(
            '/ff/visit/chemist/submit',
            data=json.dumps(chem_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_chem_retry.status_code, 200)
        chem_res_retry = res_chem_retry.json().get('result', {})
        self.assertEqual(chem_res_retry.get('status'), 'success')
        self.assertEqual(chem_res_retry.get('visit_id'), visit_id)

        # 5. Submit Doctor Visit
        doc_payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'prescriber_name_manual': 'Dr. M. S. Alam HTTP Test',
                'mobile': '01711000000',
                'mailing_address': 'Room 204, Test Diagnostic Center',
                'product_discussion': 'Antibiotic and Vitamin Syrups',
                'sample': '2 Sample Strips',
                'grade': 'a',
                'place_from_id': place.id,
                'place_to_id': place.id,
                'mode': 'rickshaw',
                'distance_km': 2.0,
                'fare_tk': 30.0,
                'client_uuid': 'http-test-doc-uuid-201',
            }
        }
        res_doc = self.url_open(
            '/ff/visit/doctor/submit',
            data=json.dumps(doc_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_doc.status_code, 200)
        doc_res = res_doc.json().get('result', {})
        self.assertEqual(doc_res.get('status'), 'success')

        # 6. Submit Farm Visit
        farm_payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'farm_name': 'Baraka Layer Farm HTTP Test',
                'address': 'Dhanmondi Lake View',
                'layer': '4000 birds',
                'bird_count': 4000,
                'note': 'Good feedback on feed quality',
                'mode': 'on_foot',
                'client_uuid': 'http-test-farm-uuid-301',
            }
        }
        res_farm = self.url_open(
            '/ff/visit/farm/submit',
            data=json.dumps(farm_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_farm.status_code, 200)
        farm_res = res_farm.json().get('result', {})
        self.assertEqual(farm_res.get('status'), 'success')

        # 7. GET /ff/entries/today and check rendered summary
        res_entries = self.url_open('/ff/entries/today')
        self.assertEqual(res_entries.status_code, 200)
        content = res_entries.content.decode('utf-8')
        self.assertIn('Green Life Pharmacy HTTP Test', content)
        self.assertIn('Dr. M. S. Alam HTTP Test', content)
        self.assertIn('Baraka Layer Farm HTTP Test', content)
