# -*- coding: utf-8 -*-
import json
from odoo.tests import tagged
from odoo.tests.common import HttpCase

@tagged('-at_install', 'post_install')
class TestFFMHttp(HttpCase):

    def setUp(self):
        super(TestFFMHttp, self).setUp()
        self.env['ir.http']._clear_routing_map()

    def test_01_http_dashboard_and_attendance_submit(self):
        """Test marketer mobile shell access and JSON attendance submission via HttpCase."""
        # 1. Authenticate with demo marketer user created in demo_data.xml
        self.authenticate('ffm_fp_demo', 'Demo12345!')

        # 2. GET /ff dashboard
        res_dash = self.url_open('/ff')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Newtec FFM', res_dash.content)

        # 3. GET /ff/attendance page
        res_att = self.url_open('/ff/attendance')
        self.assertEqual(res_att.status_code, 200)

        # 4. POST /ff/attendance/submit via JSON-RPC
        json_payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'latitude': 23.8103,
                'longitude': 90.4125,
                'accuracy': 15.0,
                'mode_of_journey': 'Motorcycle',
                'client_uuid': 'http-test-token-999',
            }
        }
        res_post = self.url_open(
            '/ff/attendance/submit',
            data=json.dumps(json_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_post.status_code, 200)
        data = res_post.json()
        result = data.get('result', {})
        self.assertEqual(result.get('status'), 'success')
        self.assertTrue(result.get('attendance_id'))

        # 5. Retry POST with same client_uuid (Idempotency over HTTP)
        res_post2 = self.url_open(
            '/ff/attendance/submit',
            data=json.dumps(json_payload),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(res_post2.status_code, 200)
        data2 = res_post2.json()
        result2 = data2.get('result', {})
        self.assertEqual(result2.get('status'), 'success')
        self.assertEqual(result2.get('attendance_id'), result.get('attendance_id'))
