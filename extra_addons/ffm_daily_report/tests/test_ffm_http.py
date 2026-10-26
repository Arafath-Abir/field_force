# -*- coding: utf-8 -*-
import json
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.exceptions import AccessError

@tagged('-at_install', 'post_install')
class TestFFMHttp(HttpCase):

    def setUp(self):
        super(TestFFMHttp, self).setUp()
        self.env['ir.http']._clear_routing_map()
        # These flows exercise the approval workflow, which is off by default
        self.env['ir.config_parameter'].sudo().set_param('ffm_daily_report.approval_enabled', '1')

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

    def test_02_manager_panel_and_redirection(self):
        """Test manager redirection: Field Person -> /ff, ASM/RSM -> /ff/manager, and manager panel rendering."""
        # 1. Field person cannot access manager panel -> redirected to /ff
        self.authenticate('ffm_fp_demo', 'Demo12345!')
        res_fp_mgr = self.url_open('/ff/manager')
        self.assertEqual(res_fp_mgr.status_code, 200)
        self.assertIn(b'Daily Attendance', res_fp_mgr.content)

        # 2. ASM accessing /ff loads /ff with all 8 field activity tiles AND manager supervision banner
        self.authenticate('ffm_asm_demo', 'Demo12345!')
        res_asm_dash = self.url_open('/ff')
        self.assertEqual(res_asm_dash.status_code, 200)
        self.assertIn(b'Daily Attendance', res_asm_dash.content)
        self.assertIn(b'Chemist Visit', res_asm_dash.content)
        self.assertIn(b'Doctor Visit', res_asm_dash.content)
        self.assertIn(b'Farm Visit', res_asm_dash.content)
        self.assertIn(b'Daily Expense', res_asm_dash.content)
        self.assertIn(b'Monthly Statement', res_asm_dash.content)
        self.assertIn(b'Report Cards', res_asm_dash.content)
        self.assertIn(b'Area Team Approvals & Monitor', res_asm_dash.content)

        # ASM accessing /ff/manager directly
        res_asm_mgr = self.url_open('/ff/manager')
        self.assertEqual(res_asm_mgr.status_code, 200)
        self.assertIn(b'Pending Reports', res_asm_mgr.content)
        self.assertIn(b'My Field Activities', res_asm_mgr.content)
        self.assertNotIn(b'Team & Passwords', res_asm_mgr.content)
        self.assertNotIn(b'Territories & Branches', res_asm_mgr.content)

        # 3. RSM accessing /ff has 8 tiles and RSM banner, and /ff/manager works
        self.authenticate('ffm_rsm_demo', 'Demo12345!')
        res_rsm_dash = self.url_open('/ff')
        self.assertEqual(res_rsm_dash.status_code, 200)
        self.assertIn(b'Daily Attendance', res_rsm_dash.content)
        self.assertIn(b'Regional Team Approvals & Monitor', res_rsm_dash.content)

        res_rsm_mgr = self.url_open('/ff/manager')
        self.assertEqual(res_rsm_mgr.status_code, 200)
        self.assertIn(b'Regional Sales Manager (RSM)', res_rsm_mgr.content)
        self.assertIn(b'My Field Activities', res_rsm_mgr.content)
        self.assertNotIn(b'Team & Passwords', res_rsm_mgr.content)

        # 4. RSM and FP hitting /web get redirected to /ff without 500 error
        res_rsm_web = self.url_open('/web')
        self.assertEqual(res_rsm_web.status_code, 200)
        self.assertIn(b'Daily Attendance', res_rsm_web.content)

        self.authenticate('ffm_fp_demo', 'Demo12345!')
        res_fp_web = self.url_open('/web')
        self.assertEqual(res_fp_web.status_code, 200)
        self.assertIn(b'Daily Attendance', res_fp_web.content)

        # 5. Main Admin and FFM System Admin accessing /web get redirected to the custom Manager & Admin Panel (/ff/manager)
        self.authenticate('ffm_admin_demo', 'Demo12345!')
        res_ffm_admin_web = self.url_open('/web')
        self.assertEqual(res_ffm_admin_web.status_code, 200)
        self.assertIn(b'System Administrator (Main Admin)', res_ffm_admin_web.content)
        self.assertIn(b'Team & Passwords', res_ffm_admin_web.content)
        self.assertIn(b'Territories & Branches', res_ffm_admin_web.content)
        self.assertIn(b'Seed Demo Data', res_ffm_admin_web.content)

        self.authenticate('admin', 'admin')
        res_admin_web = self.url_open('/web')
        self.assertEqual(res_admin_web.status_code, 200)
        self.assertIn(b'System Administrator (Main Admin)', res_admin_web.content)
        self.assertIn(b'Team & Passwords', res_admin_web.content)

        # 6. Admin can still access raw Odoo ERP backend via /web?backend=1
        res_admin_backend = self.url_open('/web?backend=1')
        self.assertEqual(res_admin_backend.status_code, 200)
        self.assertIn(b'odoo.session_info', res_admin_backend.content)

    def test_03_change_password_and_seed_wizards(self):
        """Test admin change password wizard, demo seeding wizard, and /ff/admin JSON endpoints."""
        # 1. Test Seed Demo Wizard
        seed_wiz = self.env['ffm.seed.demo.wizard'].create({})
        seed_res = seed_wiz.action_seed_demo_data()
        self.assertEqual(seed_res.get('type'), 'ir.actions.client')

        # 2. Test Change Password Wizard on an employee
        emp = self.env['hr.employee'].search([('user_id.login', '=', 'ffm_fp_demo')], limit=1)
        self.assertTrue(emp)

        pwd_wiz = self.env['ffm.change.password.wizard'].with_context(
            active_model='hr.employee',
            active_id=emp.id
        ).create({
            'new_password': 'UpdatedPass123!',
            'confirm_password': 'UpdatedPass123!',
        })
        pwd_res = pwd_wiz.action_apply_password()
        self.assertEqual(pwd_res.get('type'), 'ir.actions.client')

        # Authenticate with new password
        self.authenticate('ffm_fp_demo', 'UpdatedPass123!')
        res = self.url_open('/ff')
        self.assertEqual(res.status_code, 200)

        # Restore password via /ff/admin/employee/reset_password endpoint as ffm_admin_demo
        self.authenticate('ffm_admin_demo', 'Demo12345!')
        import json
        resp_pwd = self.url_open(
            '/ff/admin/employee/reset_password',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'emp_id': emp.id, 'new_password': 'Demo12345!'}}),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(resp_pwd.status_code, 200)
        self.assertEqual(json.loads(resp_pwd.content.decode())['result']['status'], 'success')

        # Test creating & deleting a territory via /ff/admin/territory/save & delete
        resp_terr = self.url_open(
            '/ff/admin/territory/save',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'name': 'Admin Panel Test Territory'}}),
            headers={'Content-Type': 'application/json'}
        )
        terr_res = json.loads(resp_terr.content.decode())['result']
        self.assertEqual(terr_res['status'], 'success')
        terr_id = terr_res['territory_id']

        resp_terr_del = self.url_open(
            '/ff/admin/territory/delete',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'territory_id': terr_id}}),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(json.loads(resp_terr_del.content.decode())['result']['status'], 'success')

        self.authenticate('ffm_fp_demo', 'Demo12345!')

    def test_04_security_restrictions_for_non_admins(self):
        """Ensure ASM, RSM, Field Persons CANNOT perform employee/territory CRUD or password resets."""
        import json
        user_asm = self.env['res.users'].search([('login', '=', 'ffm_asm_demo')], limit=1)
        emp_fp = self.env['hr.employee'].search([('user_id.login', '=', 'ffm_fp_demo')], limit=1)
        self.assertTrue(user_asm)
        self.assertTrue(emp_fp)

        # 1. ASM cannot call action_open_change_password_wizard
        with self.assertRaises(AccessError):
            emp_fp.with_user(user_asm).action_open_change_password_wizard()

        # 2. ASM cannot instantiate or run ffm.change.password.wizard
        with self.assertRaises(AccessError):
            self.env['ffm.change.password.wizard'].with_user(user_asm).with_context(
                active_model='hr.employee',
                active_id=emp_fp.id
            ).default_get(['employee_id', 'user_id'])

        # 3. ASM cannot create or unlink territories
        with self.assertRaises(AccessError):
            self.env['territory.territory'].with_user(user_asm).create({
                'name': 'Unauthorized Territory by ASM',
            })

        # 4. ASM cannot create new employees
        with self.assertRaises(AccessError):
            self.env['hr.employee'].with_user(user_asm).create({
                'name': 'Unauthorized Employee by ASM',
            })

        # 5. ASM calling /ff/admin/* JSON endpoints gets Access Denied
        self.authenticate('ffm_asm_demo', 'Demo12345!')
        for endpoint, payload in [
            ('/ff/admin/employee/save', {'name': 'Hack Emp', 'login': 'hack_emp'}),
            ('/ff/admin/employee/reset_password', {'emp_id': emp_fp.id, 'new_password': 'hacked'}),
            ('/ff/admin/territory/save', {'name': 'Hack Territory'}),
            ('/ff/admin/branch/save', {'name': 'Hack Branch'}),
        ]:
            resp = self.url_open(
                endpoint,
                data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': payload}),
                headers={'Content-Type': 'application/json'}
            )
            res_data = json.loads(resp.content.decode()).get('result', {})
            self.assertEqual(res_data.get('status'), 'error')
            self.assertIn('Access Denied', res_data.get('message', ''))

    def test_05_hierarchy_approval_isolation(self):
        """Verify that ASM only approves FP reports, RSM only approves ASM reports, and Admin approves all."""
        from datetime import date, timedelta
        test_date = date.today() - timedelta(days=25)

        emp_fp = self.env['hr.employee'].search([('user_id.login', '=', 'ffm_fp_demo')], limit=1)
        emp_asm = self.env['hr.employee'].search([('user_id.login', '=', 'ffm_asm_demo')], limit=1)
        emp_rsm = self.env['hr.employee'].search([('user_id.login', '=', 'ffm_rsm_demo')], limit=1)
        self.assertTrue(emp_fp and emp_asm and emp_rsm)

        # Clean any existing reports on test_date
        self.env['ffm.daily.report'].search([
            ('employee_id', 'in', [emp_fp.id, emp_asm.id]),
            ('date', '=', test_date)
        ]).unlink()

        # 1. FP submits daily report
        rep_fp = self.env['ffm.daily.report'].create({
            'employee_id': emp_fp.id,
            'date': test_date,
            'state': 'submitted',
        })

        # 2. ASM submits daily report
        rep_asm = self.env['ffm.daily.report'].create({
            'employee_id': emp_asm.id,
            'date': test_date,
            'state': 'submitted',
        })

        # Test A: RSM logs into /ff/manager
        # In RSM's dashboard, rep_asm should appear, rep_fp should NOT appear
        self.authenticate('ffm_rsm_demo', 'Demo12345!')
        res_rsm = self.url_open('/ff/manager?tab=approvals')
        self.assertEqual(res_rsm.status_code, 200)
        self.assertIn(emp_asm.name.encode('utf-8'), res_rsm.content)

        # RSM tries to approve FP's report directly -> Denied with clean message
        resp_rsm_fp = self.url_open(
            '/ff/manager/report/approve',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'report_id': rep_fp.id}}),
            headers={'Content-Type': 'application/json'}
        )
        res_data = json.loads(resp_rsm_fp.content.decode()).get('result', {})
        self.assertEqual(res_data.get('status'), 'error')
        self.assertIn('permission', res_data.get('message', '').lower())

        # RSM approves ASM's report -> Success
        resp_rsm_asm = self.url_open(
            '/ff/manager/report/approve',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'report_id': rep_asm.id}}),
            headers={'Content-Type': 'application/json'}
        )
        res_data_asm = json.loads(resp_rsm_asm.content.decode()).get('result', {})
        self.assertEqual(res_data_asm.get('status'), 'success')
        self.assertEqual(rep_asm.state, 'approved')

        # Test B: ASM logs into /ff/manager
        # In ASM's dashboard, rep_fp should appear
        self.authenticate('ffm_asm_demo', 'Demo12345!')
        res_asm = self.url_open('/ff/manager?tab=approvals')
        self.assertEqual(res_asm.status_code, 200)
        self.assertIn(emp_fp.name.encode('utf-8'), res_asm.content)

        # ASM approves FP's report -> Success
        resp_asm_fp = self.url_open(
            '/ff/manager/report/approve',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'report_id': rep_fp.id}}),
            headers={'Content-Type': 'application/json'}
        )
        res_data_fp = json.loads(resp_asm_fp.content.decode()).get('result', {})
        self.assertEqual(res_data_fp.get('status'), 'success')
        self.assertEqual(rep_fp.state, 'approved')

    def test_approval_switch_off_hides_and_blocks_approvals(self):
        """With the approval switch off there is no Approvals tab and approve is refused."""
        self.env['ir.config_parameter'].sudo().set_param('ffm_daily_report.approval_enabled', '0')
        emp_fp = self.env['hr.employee'].search([('user_id.login', '=', 'ffm_fp_demo')], limit=1)
        report = self.env['ffm.daily.report'].create({
            'employee_id': emp_fp.id,
            'date': '2019-03-03',
            'state': 'submitted',
        })

        self.authenticate('ffm_asm_demo', 'Demo12345!')
        res = self.url_open('/ff/manager?tab=approvals')
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(b'id="tab-approvals"', res.content)
        self.assertNotIn(b'Pending Reports', res.content)

        resp = self.url_open(
            '/ff/manager/report/approve',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'report_id': report.id}}),
            headers={'Content-Type': 'application/json'}
        )
        result = json.loads(resp.content.decode()).get('result', {})
        self.assertEqual(result.get('status'), 'error')
        self.assertEqual(report.state, 'submitted')

        # Only Manager / Super Admin may flip the switch
        resp_toggle = self.url_open(
            '/ff/manager/approval/toggle',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'enabled': True}}),
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(json.loads(resp_toggle.content.decode()).get('result', {}).get('status'), 'error')
