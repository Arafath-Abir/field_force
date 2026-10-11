# -*- coding: utf-8 -*-
from datetime import datetime
import json
import pytz

from odoo import http, fields, _
from odoo.http import request, Response
from odoo.addons.web.controllers.main import Home

class FFMHome(Home):
    def _login_redirect(self, uid, redirect=None):
        if not redirect and uid:
            user = request.env['res.users'].browse(uid)
            if user.has_group('field_force_management.group_ffm_field_person') and not user.has_group('field_force_management.group_ffm_asm') and not user.has_group('field_force_management.group_ffm_admin'):
                return '/ff'
        return super(FFMHome, self)._login_redirect(uid, redirect=redirect)

    @http.route()
    def web_client(self, s_action=None, **kw):
        if request.session.uid and not request.env.is_admin():
            user = request.env.user
            if user.has_group('field_force_management.group_ffm_field_person') and not user.has_group('field_force_management.group_ffm_asm') and not user.has_group('field_force_management.group_ffm_admin'):
                return request.redirect('/ff')
        return super(FFMHome, self).web_client(s_action=s_action, **kw)


class FFMController(http.Controller):

    def _get_dhaka_date_and_time(self):
        tz = pytz.timezone('Asia/Dhaka')
        now = datetime.now(tz)
        return now.date(), now.strftime('%I:%M %p')

    def _get_app_context(self):
        user = request.env.user
        employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        territory = user.territory_id if hasattr(user, 'territory_id') else False
        app_name = request.env['ir.config_parameter'].sudo().get_param('ffm.app_name', default='Newtec FFM')
        return {
            'user': user,
            'user_name': user.name,
            'employee': employee,
            'territory': territory,
            'app_name': app_name,
        }

    @http.route('/ff', type='http', auth='user')
    def ff_dashboard(self, **kw):
        """Marketer mobile start page with the 8 tiles."""
        ctx = self._get_app_context()
        today_date, _ = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        attendance_today = False
        if employee:
            attendance_today = request.env['ffm.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'attendance_today': bool(attendance_today),
        })
        return request.render('ffm_daily_report.ff_dashboard', ctx)

    @http.route('/ff/attendance', type='http', auth='user')
    def ff_attendance(self, **kw):
        """Attendance screen: shows current status or GPS capture submission."""
        ctx = self._get_app_context()
        today_date, _ = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        attendance = False
        reporting_time_str = ''
        if employee:
            attendance = request.env['ffm.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)
            if attendance and attendance.reporting_time:
                # Format reporting time in Dhaka timezone
                tz = pytz.timezone('Asia/Dhaka')
                utc_dt = pytz.utc.localize(attendance.reporting_time)
                dhaka_dt = utc_dt.astimezone(tz)
                reporting_time_str = dhaka_dt.strftime('%I:%M %p')

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'attendance': attendance,
            'reporting_time_str': reporting_time_str,
        })
        return request.render('ffm_daily_report.ff_attendance', ctx)

    @http.route('/ff/attendance/submit', type='json', auth='user', methods=['POST'])
    def ff_attendance_submit(self, **payload):
        """JSON endpoint to record attendance with GPS verification and idempotency."""
        try:
            attendance = request.env['ffm.attendance'].submit_attendance(payload)
            return {
                'status': 'success',
                'attendance_id': attendance.id,
                'message': _('হাজিরা সফলভাবে নিশ্চিত হয়েছে। (Attendance recorded successfully)'),
            }
        except Exception as exc:
            return {
                'status': 'error',
                'message': str(exc),
            }

    @http.route('/ff/manifest.json', type='http', auth='none', methods=['GET'])
    def ff_manifest(self):
        """Serve PWA web app manifest."""
        manifest_data = {
            'name': 'Newtec FFM - Field Force Management',
            'short_name': 'Newtec FFM',
            'start_url': '/ff',
            'display': 'standalone',
            'background_color': '#f4f6f8',
            'theme_color': '#107c41',
            'icons': [
                {
                    'src': '/field_force_management/static/src/description/icon.png',
                    'sizes': '192x192',
                    'type': 'image/png'
                }
            ]
        }
        return Response(
            json.dumps(manifest_data),
            content_type='application/manifest+json;charset=utf-8'
        )
