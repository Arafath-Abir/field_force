import base64
from datetime import datetime, date, timedelta
import json
import math
import pytz
import logging

from odoo import http, fields, _
from odoo.http import request, Response
from odoo.addons.web.controllers.main import Home
from odoo.exceptions import UserError, ValidationError
import werkzeug.utils
import re

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

_logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

def _clean_base64_image(data_str):
    if not data_str or not isinstance(data_str, str):
        return False
    data_str = data_str.strip()
    if not data_str:
        return False
    if ',' in data_str and 'data:' in data_str[:25]:
        data_str = data_str.split(',', 1)[1]
    return data_str

def _check_and_validate_voucher(binary_b64, field_label):
    if not binary_b64:
        raise ValidationError(_('%s: Voucher image is required.') % field_label)
    try:
        raw_bytes = base64.b64decode(binary_b64)
    except Exception:
        raise ValidationError(_('%s: Invalid binary image data.') % field_label)

    if len(raw_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(_('%s: File size cannot exceed 5MB.') % field_label)

    is_jpeg = raw_bytes.startswith(b'\xff\xd8\xff')
    is_png = raw_bytes.startswith(b'\x89PNG\r\n\x1a\n')
    is_webp = raw_bytes[:4] == b'RIFF' and len(raw_bytes) > 12 and raw_bytes[8:12] == b'WEBP'

    if not (is_jpeg or is_png or is_webp):
        raise ValidationError(_('%s: Only image files (JPEG, PNG, WebP) are allowed.') % field_label)

TRANSPORT_MODES = [
    ('bus', 'Bus'),
    ('rickshaw', 'Rickshaw / Van'),
    ('auto_cng', 'Auto / CNG'),
    ('motorcycle', 'Motorcycle'),
    ('uber_pathao', 'Uber / Pathao'),
    ('on_foot', 'On Foot'),
    ('train', 'Train'),
    ('launch', 'Launch / Ferry'),
    ('others', 'Others'),
]

DOCTOR_GRADES = [
    ('a_plus', 'A+'),
    ('a', 'A'),
    ('b', 'B'),
    ('c', 'C'),
]

class FFMHome(Home):
    def _login_redirect(self, uid, redirect=None):
        if uid:
            request.uid = uid
            user = request.env['res.users'].sudo().browse(uid)
            if user.exists():
                is_admin = (user._is_admin() or
                            user.has_group('field_force_management.group_ffm_admin') or
                            user.has_group('base.group_system'))
                is_manager = user.has_group('field_force_management.group_ffm_nsm') and not is_admin
                is_rsm = user.has_group('field_force_management.group_ffm_rsm') and not (is_admin or is_manager)
                is_asm = user.has_group('field_force_management.group_ffm_asm') and not (is_admin or is_manager or is_rsm)
                is_fp = not (is_admin or is_manager or is_rsm or is_asm)

                # Management-only roles (NSM, MM, Admin) land directly on the Manager Panel
                if is_admin or is_manager:
                    return '/ff/manager'
                elif is_rsm or is_asm or is_fp:
                    return '/ff'
        return super(FFMHome, self)._login_redirect(uid, redirect=redirect)

    @http.route('/web', type='http', auth="none")
    def web_client(self, s_action=None, **kw):
        if request.session.uid:
            request.uid = request.session.uid
            user = request.env['res.users'].sudo().browse(request.session.uid)
            if user.exists():
                is_admin = (user._is_admin() or
                            user.has_group('field_force_management.group_ffm_admin') or
                            user.has_group('base.group_system'))
                is_manager = user.has_group('field_force_management.group_ffm_nsm') and not is_admin
                is_rsm = user.has_group('field_force_management.group_ffm_rsm') and not (is_admin or is_manager)
                is_asm = user.has_group('field_force_management.group_ffm_asm') and not (is_admin or is_manager or is_rsm)
                is_fp = not (is_admin or is_manager or is_rsm or is_asm)

                if is_admin or is_manager:
                    if not kw.get('backend'):
                        return werkzeug.utils.redirect('/ff/manager', 303)
                elif is_rsm or is_asm or is_fp:
                    return werkzeug.utils.redirect('/ff', 303)
        return super(FFMHome, self).web_client(s_action=s_action, **kw)


class FFMController(http.Controller):

    def _get_dhaka_date_and_time(self):
        tz = pytz.timezone('Asia/Dhaka')
        now = datetime.now(tz)
        return now.date(), now.strftime('%I:%M %p')

    def _get_live_location(self, payload):
        """Validate the device GPS fix sent with every field form; None when missing or invalid."""
        try:
            lat = float(payload.get('latitude'))
            lon = float(payload.get('longitude'))
        except (TypeError, ValueError):
            return None
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0) or (lat == 0.0 and lon == 0.0):
            return None
        try:
            accuracy = float(payload.get('gps_accuracy') or 0.0)
        except (TypeError, ValueError):
            accuracy = 0.0
        return {'latitude': lat, 'longitude': lon, 'gps_accuracy': accuracy}

    # ── Team scope, filters and org tree (shared by Manager Panel and Report Cards) ──
    ROLE_ORDER = {'rsm': 0, 'asm': 1, 'fp': 2, 'manager': 3}

    def _ffm_team(self, ctx):
        """Active field force people the current user supervises (never includes the user)."""
        Emp = request.env['hr.employee'].sudo()
        employee = ctx.get('employee')
        if ctx.get('is_super_admin') or ctx.get('is_manager'):
            return Emp.search([('active', '=', True), ('ffm_role', 'in', ('rsm', 'asm', 'fp'))], order='name')
        if (ctx.get('is_rsm') or ctx.get('is_asm')) and employee:
            return Emp.search([
                ('active', '=', True),
                ('id', 'child_of', employee.id),
                ('id', '!=', employee.id),
            ], order='name')
        return Emp.browse([])

    def _ffm_scope_options(self, ctx, team):
        """Territories / RSMs / ASMs the user may filter reports by."""
        Emp = request.env['hr.employee'].sudo()
        employee = ctx.get('employee')
        is_mgmt = ctx.get('is_super_admin') or ctx.get('is_manager')
        if is_mgmt:
            territories = request.env['territory.territory'].sudo().search([], order='name')
        else:
            people = team | (employee or Emp.browse([]))
            territories = people.mapped('ffm_territory_ids').sorted('name')
        rsms = team.filtered(lambda e: e.ffm_role == 'rsm') if is_mgmt else Emp.browse([])
        asms = team.filtered(lambda e: e.ffm_role == 'asm') if (is_mgmt or ctx.get('is_rsm')) else Emp.browse([])
        return territories, rsms, asms

    def _ffm_people_json(self, team):
        """Existing people the user can open a report for (name search picker)."""
        role_label = {'rsm': 'RSM', 'asm': 'ASM', 'fp': 'Field Person', 'manager': 'Manager'}
        return json.dumps([{
            'id': e.id,
            'name': e.name or '',
            'role': role_label.get(e.ffm_role, ''),
            'territories': ', '.join(e.ffm_territory_ids.mapped('name')),
        } for e in team])

    def _ffm_org_tree(self, team, viewer=None):
        """Reporting tree built from parent_id: RSM → ASM → Field Person."""
        nodes = team
        if viewer and viewer.ffm_role in ('rsm', 'asm'):
            nodes = nodes | viewer
        ids = set(nodes.ids)
        children = {}
        roots = []
        ordered = nodes.sorted(lambda e: (self.ROLE_ORDER.get(e.ffm_role, 9), (e.name or '').lower()))
        for emp in ordered:
            if emp.parent_id.id in ids:
                children.setdefault(emp.parent_id.id, []).append(emp)
            else:
                roots.append(emp)

        def build(emp, depth):
            kids = children.get(emp.id, []) if depth < 5 else []
            return {'emp': emp, 'children': [build(k, depth + 1) for k in kids]}

        return [build(r, 0) for r in roots]

    def _generate_report_pdf(self, report):
        """Render report to PDF using Odoo actions or resilient xhtml2pdf fallback."""
        try:
            pdf_content, _ = request.env.ref('ffm_daily_report.action_report_ffm_daily_report_pdf').sudo()._render_qweb_pdf(report.ids)
            return pdf_content
        except Exception:
            from xhtml2pdf import pisa
            import io
            import re
            html = request.env['ir.qweb']._render('ffm_daily_report.report_daily_report_pdf_document', {'docs': report})
            if isinstance(html, bytes):
                html = html.decode('utf-8')
            cleaned = re.sub(r'<link[^>]*rel=[\"\']stylesheet[\"\'][^>]*>', '', html, flags=re.IGNORECASE)
            cleaned = re.sub(r'<script[^>]*>.*?</script>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
            out = io.BytesIO()
            pisa.CreatePDF(cleaned, dest=out)
            return out.getvalue()

    def _generate_statement_pdf(self, statement):
        """Render monthly statement to PDF using Odoo actions or resilient xhtml2pdf fallback."""
        try:
            pdf_content, _ = request.env.ref('ffm_daily_report.action_report_ffm_expense_statement_pdf').sudo()._render_qweb_pdf(statement.ids)
            return pdf_content
        except Exception:
            from xhtml2pdf import pisa
            import io
            import re
            html = request.env['ir.qweb']._render('ffm_daily_report.report_expense_statement_pdf_document', {'docs': statement})
            if isinstance(html, bytes):
                html = html.decode('utf-8')
            cleaned = re.sub(r'<link[^>]*rel=[\"\']stylesheet[\"\'][^>]*>', '', html, flags=re.IGNORECASE)
            cleaned = re.sub(r'<script[^>]*>.*?</script>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
            out = io.BytesIO()
            pisa.CreatePDF(cleaned, dest=out)
            return out.getvalue()

    APPROVAL_PARAM = 'ffm_daily_report.approval_enabled'

    def _approval_enabled(self):
        """Approval workflow switch (Manager Panel). Off unless explicitly turned on."""
        return request.env['ir.config_parameter'].sudo().get_param(self.APPROVAL_PARAM, default='0') == '1'

    def _get_app_context(self):
        user = request.env.user
        employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        territory = user.territory_id if hasattr(user, 'territory_id') else False
        app_name = request.env['ir.config_parameter'].sudo().get_param('ffm.app_name', default='Newtec FFM')
        
        is_super_admin = (user._is_admin() or user.has_group('field_force_management.group_ffm_admin') or user.has_group('base.group_system'))
        is_manager = user.has_group('field_force_management.group_ffm_nsm') and not is_super_admin
        is_rsm = user.has_group('field_force_management.group_ffm_rsm') and not (is_super_admin or is_manager)
        is_asm = user.has_group('field_force_management.group_ffm_asm') and not (is_super_admin or is_manager or is_rsm)
        is_fp = not (is_super_admin or is_manager or is_rsm or is_asm)

        is_management_only = is_super_admin or is_manager
        has_field_operations = not is_management_only

        if is_super_admin:
            panel_title = 'Super Admin Panel'
            role_badge = 'Super Admin'
        elif is_manager:
            panel_title = 'Manager Panel'
            role_badge = 'Manager'
        elif is_rsm:
            panel_title = 'RSM Panel'
            role_badge = 'RSM'
        elif is_asm:
            panel_title = 'ASM Panel'
            role_badge = 'ASM'
        else:
            panel_title = 'Field Person Portal'
            role_badge = 'Field Person'

        # Hierarchy and territory resolution for current user
        Emp = request.env['hr.employee'].sudo()
        territories = employee.ffm_territory_ids if employee else request.env['territory.territory'].browse([])
        if not territories and territory:
            territories = territory
        territory_names = ', '.join(territories.mapped('name')) if territories else ''
        depot_list = [d for d in set(territories.mapped('branch_id.name') + [employee.branch_id.name if employee and employee.branch_id else False]) if d]
        if not depot_list and employee:
            child_depots = employee.child_ids.mapped('branch_id.name') + employee.child_ids.mapped('ffm_territory_ids.branch_id.name')
            depot_list = [d for d in set(child_depots) if d]
        depot_names = ', '.join(sorted(depot_list)) if depot_list else (employee.branch_id.name if employee and employee.branch_id else '')
        if not depot_names:
            first_depot = request.env['aam.branch'].sudo().search([], limit=1)
            depot_names = first_depot.name if first_depot else 'Main Depot'

        designation = employee.job_id.name if employee and employee.job_id else ('Area Sales Manager (ASM)' if is_asm else ('Regional Sales Manager (RSM)' if is_rsm else ('Field Marketer' if is_fp else role_badge)))

        asm_employee = False
        rsm_employee = False
        asm_name = ''
        rsm_name = ''
        asm_subordinate_fps = Emp.browse([])
        rsm_hierarchy_asms = []
        rsm_direct_fps = Emp.browse([])

        if is_fp and employee:
            p = employee.parent_id
            if p:
                if p.ffm_role == 'asm':
                    asm_employee = p
                    if p.parent_id and p.parent_id.ffm_role == 'rsm':
                        rsm_employee = p.parent_id
                elif p.ffm_role == 'rsm':
                    rsm_employee = p
            if not asm_employee and territories:
                asm_employee = territories.mapped('asm_ids')[:1]
            if not rsm_employee and territories:
                rsm_employee = territories.mapped('rsm_ids')[:1]
            if not rsm_employee and asm_employee and asm_employee.parent_id and asm_employee.parent_id.ffm_role == 'rsm':
                rsm_employee = asm_employee.parent_id

            asm_name = asm_employee.name if asm_employee else ''
            rsm_name = rsm_employee.name if rsm_employee else 'Marketing Manager/Head Office'

        elif is_asm and employee:
            p = employee.parent_id
            if p and p.ffm_role == 'rsm':
                rsm_employee = p
            elif territories:
                rsm_employee = territories.mapped('rsm_ids')[:1]
            rsm_name = rsm_employee.name if rsm_employee else 'Marketing Manager/Head Office'

            # Field persons under this ASM
            direct_fps = Emp.search([('parent_id', '=', employee.id), ('ffm_role', '=', 'fp'), ('active', '=', True)], order='name')
            terr_fps = territories.mapped('fp_ids').filtered('active') if territories else Emp.browse([])
            asm_subordinate_fps = (direct_fps | terr_fps).sorted('name')

        elif is_rsm and employee:
            rsm_name = 'Marketing Manager/Head Office'
            direct_asms = Emp.search([('parent_id', '=', employee.id), ('ffm_role', '=', 'asm'), ('active', '=', True)], order='name')
            terr_asms = territories.mapped('asm_ids').filtered('active') if territories else Emp.browse([])
            all_asms = (direct_asms | terr_asms).sorted('name')
            all_asm_fps_set = set()

            for asm_rec in all_asms:
                sub_fps = Emp.search([('parent_id', '=', asm_rec.id), ('ffm_role', '=', 'fp'), ('active', '=', True)], order='name') | asm_rec.ffm_territory_ids.mapped('fp_ids').filtered('active')
                sub_fps = sub_fps.sorted('name')
                all_asm_fps_set.update(sub_fps.ids)
                rsm_hierarchy_asms.append({
                    'asm': asm_rec,
                    'fps': sub_fps,
                })
            # Any FP directly reporting to RSM without an ASM
            rsm_direct_fps = Emp.search([('parent_id', '=', employee.id), ('ffm_role', '=', 'fp'), ('active', '=', True), ('id', 'not in', list(all_asm_fps_set))], order='name')
        else:
            rsm_name = 'Marketing Manager/Head Office'

        all_depots = request.env['aam.branch'].sudo().search([], order='name')

        return {
            'user': user,
            'user_name': user.name,
            'employee': employee,
            'territory': territory,
            'territories': territories,
            'territory_names': territory_names,
            'depot_names': depot_names,
            'all_depots': all_depots,
            'asm_employee': asm_employee,
            'rsm_employee': rsm_employee,
            'asm_name': asm_name,
            'rsm_name': rsm_name,
            'asm_subordinate_fps': asm_subordinate_fps,
            'rsm_hierarchy_asms': rsm_hierarchy_asms,
            'rsm_direct_fps': rsm_direct_fps,
            'app_name': app_name,
            'is_super_admin': is_super_admin,
            'is_manager': is_manager,
            'is_rsm': is_rsm,
            'is_asm': is_asm,
            'is_fp': is_fp,
            'is_management_only': is_management_only,
            'has_field_operations': has_field_operations,
            'panel_title': panel_title,
            'role_badge': role_badge,
            'designation': designation,
            'approval_enabled': self._approval_enabled(),
        }

    # ── 1. Dashboard ────────────────────────────────────────────────────────
    @http.route('/ff', type='http', auth='user')
    def ff_dashboard(self, **kw):
        """Field activities start page with field tiles for operational staff (FP, ASM, RSM).
        Management-only roles (NSM, MM, Admin) have no field visits/attendance, so they
        are redirected directly to /ff/manager.
        """
        ctx = self._get_app_context()
        if ctx.get('is_management_only'):
            return werkzeug.utils.redirect('/ff/manager', 303)

        user = request.env.user
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        attendance_today = False
        today_report = False
        if employee:
            attendance_today = request.env['ffm.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)
            today_report = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)

        # Manager status and subordinate metrics for ASM / RSM / Manager
        is_super_admin = ctx.get('is_super_admin', False)
        is_manager = ctx.get('is_manager', False)
        is_rsm = ctx.get('is_rsm', False)
        is_asm = ctx.get('is_asm', False)
        is_supervisor = is_super_admin or is_manager or is_rsm or is_asm

        subordinates = request.env['hr.employee'].browse([])
        if (is_super_admin or is_manager) and employee:
            subordinates = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
                ('id', '!=', employee.id)
            ], order='name')
        elif is_rsm and employee:
            subordinates = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
                ('id', 'child_of', employee.id),
                ('id', '!=', employee.id)
            ], order='name')
        elif is_asm and employee:
            subordinates = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
                ('parent_id', '=', employee.id)
            ], order='name')

        sub_ids = subordinates.ids
        pending_reports_count = 0
        present_count = 0
        if sub_ids:
            approvable_sub_ids = sub_ids

            pending_reports_count = request.env['ffm.daily.report'].sudo().search_count([
                ('employee_id', 'in', approvable_sub_ids),
                ('state', '=', 'submitted')
            ])
            present_count = len(request.env['ffm.attendance'].sudo().search([
                ('employee_id', 'in', sub_ids),
                ('date', '=', today_date)
            ]).mapped('employee_id.id'))

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'attendance_today': bool(attendance_today),
            'today_report': today_report,
            'is_supervisor': is_supervisor,
            'is_super_admin': is_super_admin,
            'is_manager': is_manager,
            'is_asm': is_asm,
            'is_rsm': is_rsm,
            'is_fp': ctx.get('is_fp', False),
            'sub_count': len(subordinates),
            'pending_reports_count': pending_reports_count,
            'present_count': present_count,
        })
        return request.render('ffm_daily_report.ff_dashboard', ctx)

    # ── 2. Attendance ───────────────────────────────────────────────────────
    @http.route('/ff/attendance', type='http', auth='user')
    def ff_attendance(self, **kw):
        ctx = self._get_app_context()
        if ctx.get('is_management_only'):
            return werkzeug.utils.redirect('/ff/manager', 303)
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        attendance = False
        reporting_time_str = ''
        if employee:
            attendance = request.env['ffm.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)
            if attendance and attendance.reporting_time:
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
        try:
            attendance = request.env['ffm.attendance'].submit_attendance(payload)
            return {
                'status': 'success',
                'attendance_id': attendance.id,
                'message': _('Attendance recorded successfully.'),
            }
        except Exception as exc:
            return {
                'status': 'error',
                'message': str(exc),
            }

    # ── 3. Daily Report Header ──────────────────────────────────────────────
    @http.route('/ff/report/daily', type='http', auth='user')
    def ff_daily_report(self, **kw):
        """View or initialize today's daily report (strictly current date)."""
        ctx = self._get_app_context()
        if ctx.get('is_management_only'):
            return werkzeug.utils.redirect('/ff/manager', 303)
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        report = False
        if employee:
            report = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)

        places = request.env['ffm.place'].sudo().search([('active', '=', True)], limit=150, order='name asc')
        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'today_date': today_date,
            'report': report,
            'places': places,
        })
        return request.render('ffm_daily_report.ff_daily_report', ctx)

    @http.route('/ff/report/daily/init', type='json', auth='user', methods=['POST'])
    def ff_daily_report_init(self, **payload):
        """Initialize today's daily report with required working_place_id."""
        try:
            working_place_id = payload.get('working_place_id')
            if not working_place_id:
                return {'status': 'error', 'message': _('Working Place selection is required.')}

            report = request.env['ffm.daily.report'].get_or_create_today_report(
                working_place_id=int(working_place_id)
            )
            return {
                'status': 'success',
                'report_id': report.id,
                'message': _('Daily report initialized successfully.'),
            }
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/report/daily/submit', type='json', auth='user', methods=['POST'])
    def ff_daily_report_submit(self, **payload):
        """Final submit today's daily report."""
        try:
            today_date, _now_time = self._get_dhaka_date_and_time()
            user = request.env.user
            employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            report = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)
            if not report:
                return {'status': 'error', 'message': _('No daily report found for today.')}
            if not self._approval_enabled():
                return {'status': 'error', 'message': _('Approval system is turned off.')}
            if report.state != 'draft':
                return {'status': 'error', 'message': _('Report has already been submitted.')}
            report.action_submit()
            return {'status': 'success', 'message': _('Daily report submitted successfully.')}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    # ── 4. Chemist Visit ────────────────────────────────────────────────────
    @http.route('/ff/visit/chemist', type='http', auth='user')
    def ff_visit_chemist(self, **kw):
        ctx = self._get_app_context()
        if ctx.get('is_management_only'):
            return werkzeug.utils.redirect('/ff/manager', 303)
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        report = request.env['ffm.daily.report'].get_or_create_today_report()

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'report': report,
            'transport_modes': TRANSPORT_MODES,
        })
        return request.render('ffm_daily_report.ff_visit_chemist', ctx)

    @http.route('/ff/visit/chemist/submit', type='json', auth='user', methods=['POST'])
    def ff_visit_chemist_submit(self, **payload):
        try:
            client_uuid = (payload.get('client_uuid') or '').strip()
            if client_uuid:
                existing = request.env['ffm.chemist.visit'].sudo().search([('client_uuid', '=', client_uuid)], limit=1)
                if existing:
                    return {'status': 'success', 'visit_id': existing.id, 'message': _('Chemist visit already saved.')}

            location = self._get_live_location(payload)
            if not location:
                return {'status': 'error', 'message': _('Live location is required. Please turn on GPS / location and try again.')}

            chemist_id = payload.get('chemist_id')
            chemist_name_manual = (payload.get('chemist_name_manual') or '').strip()
            if not chemist_id and not chemist_name_manual:
                return {'status': 'error', 'message': _('Select a chemist or enter manual name.')}

            try:
                order_tk = float(payload.get('order_tk') or 0)
                sale_tk = float(payload.get('sale_tk') or 0)
                coll_tk = float(payload.get('coll_tk') or 0)
            except (ValueError, TypeError):
                return {'status': 'error', 'message': _('Order, sale, and collection must be numeric.')}

            if order_tk < 0 or sale_tk < 0 or coll_tk < 0:
                return {'status': 'error', 'message': _('Amount cannot be negative.')}

            if not (order_tk.is_integer() and sale_tk.is_integer() and coll_tk.is_integer()):
                return {'status': 'error', 'message': _('Amount must be a whole number.')}

            # Journey validation for Chemist visit (required)
            mode = (payload.get('mode') or '').strip()
            try:
                fare_tk = float(payload.get('fare_tk') or 0.0)
            except (ValueError, TypeError):
                fare_tk = 0.0

            if not mode:
                return {'status': 'error', 'message': _('Mode of journey is required.')}

            report = request.env['ffm.daily.report'].get_or_create_today_report()

            # Create Chemist Visit line
            visit = request.env['ffm.chemist.visit'].sudo().create({
                'report_id': report.id,
                'chemist_id': int(chemist_id) if chemist_id else False,
                'chemist_name_manual': chemist_name_manual or False,
                'order_tk': order_tk,
                'sale_tk': sale_tk,
                'coll_tk': coll_tk,
                'note': (payload.get('note') or '').strip(),
                'client_uuid': client_uuid or False,
                **location,
            })

            # Create Travel Leg
            travel_log = report.travel_log_ids[:1]
            if not travel_log:
                travel_log = request.env['ffm.travel.log'].sudo().create({
                    'daily_report_id': report.id,
                    'employee_id': report.employee_id.id,
                    'date': report.date,
                })

            # Only mode + T.A. bill are collected; places fall back to the working place
            def_place = report.working_place_id or request.env['ffm.place'].sudo().search([], limit=1)
            p_from = p_to = def_place.id if def_place else False

            if p_from and p_to:
                request.env['ffm.travel.journey'].sudo().with_context(ffm_manual_fare=True).create({
                    'travel_log_id': travel_log.id,
                    'place_from_id': p_from,
                    'place_to_id': p_to,
                    'mode': mode,
                    'other_mode': (payload.get('other_mode') or '').strip(),
                    'distance_km': 0.0,
                    'fare_tk': fare_tk,
                    'chemist_visit_id': visit.id,
                    'client_uuid': f"{client_uuid}_leg" if client_uuid else False,
                })

            return {
                'status': 'success',
                'visit_id': visit.id,
                'message': _('Chemist visit and journey details saved successfully.'),
            }
        except Exception as exc:
            _logger.exception("Error submitting chemist visit")
            return {'status': 'error', 'message': str(exc)}

    # ── 5. Doctor Visit ─────────────────────────────────────────────────────
    @http.route('/ff/visit/doctor', type='http', auth='user')
    def ff_visit_doctor(self, **kw):
        ctx = self._get_app_context()
        if ctx.get('is_management_only'):
            return werkzeug.utils.redirect('/ff/manager', 303)
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        report = request.env['ffm.daily.report'].get_or_create_today_report()

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'report': report,
            'transport_modes': TRANSPORT_MODES,
            'doctor_grades': DOCTOR_GRADES,
        })
        return request.render('ffm_daily_report.ff_visit_doctor', ctx)

    @http.route('/ff/visit/doctor/submit', type='json', auth='user', methods=['POST'])
    def ff_visit_doctor_submit(self, **payload):
        try:
            client_uuid = (payload.get('client_uuid') or '').strip()
            if client_uuid:
                existing = request.env['ffm.prescriber.visit'].sudo().search([('client_uuid', '=', client_uuid)], limit=1)
                if existing:
                    return {'status': 'success', 'visit_id': existing.id, 'message': _('Doctor visit already saved.')}

            location = self._get_live_location(payload)
            if not location:
                return {'status': 'error', 'message': _('Live location is required. Please turn on GPS / location and try again.')}

            doctor_id = payload.get('doctor_id')
            prescriber_name_manual = (payload.get('prescriber_name_manual') or '').strip()
            if not doctor_id and not prescriber_name_manual:
                return {'status': 'error', 'message': _('Select a doctor or enter manual name.')}

            mobile = (payload.get('mobile') or '').strip()
            mailing_address = (payload.get('mailing_address') or '').strip()
            product_discussion = (payload.get('product_discussion') or '').strip()
            sample = (payload.get('sample') or '').strip()
            grade = (payload.get('grade') or '').strip()

            if not product_discussion or not sample or not grade:
                return {'status': 'error', 'message': _('Product discussion, sample/gift, and grade are required.')}

            # Journey validation for Doctor visit
            mode = (payload.get('mode') or '').strip()
            try:
                fare_tk = float(payload.get('fare_tk') or 0.0)
            except (ValueError, TypeError):
                fare_tk = 0.0

            if not mode:
                return {'status': 'error', 'message': _('Mode of journey is required.')}

            report = request.env['ffm.daily.report'].get_or_create_today_report()

            visit = request.env['ffm.prescriber.visit'].sudo().create({
                'report_id': report.id,
                'prescriber_id': int(doctor_id) if doctor_id else False,
                'prescriber_name_manual': prescriber_name_manual or False,
                'mobile': mobile,
                'mailing_address': mailing_address,
                'product_discussion': product_discussion,
                'sample': sample,
                'grade': grade,
                'client_uuid': client_uuid or False,
                **location,
            })

            # Create Travel Leg
            travel_log = report.travel_log_ids[:1]
            if not travel_log:
                travel_log = request.env['ffm.travel.log'].sudo().create({
                    'daily_report_id': report.id,
                    'employee_id': report.employee_id.id,
                    'date': report.date,
                })

            # Only mode + T.A. bill are collected; places fall back to the working place
            def_place = report.working_place_id or request.env['ffm.place'].sudo().search([], limit=1)
            p_from = p_to = def_place.id if def_place else False

            if p_from and p_to:
                request.env['ffm.travel.journey'].sudo().with_context(ffm_manual_fare=True).create({
                    'travel_log_id': travel_log.id,
                    'place_from_id': p_from,
                    'place_to_id': p_to,
                    'mode': mode,
                    'other_mode': (payload.get('other_mode') or '').strip(),
                    'distance_km': 0.0,
                    'fare_tk': fare_tk,
                    'prescriber_visit_id': visit.id,
                    'client_uuid': f"{client_uuid}_leg" if client_uuid else False,
                })

            return {
                'status': 'success',
                'visit_id': visit.id,
                'message': _('Doctor visit and journey details saved successfully.'),
            }
        except Exception as exc:
            _logger.exception("Error submitting doctor visit")
            return {'status': 'error', 'message': str(exc)}

    # ── 6. Farm / Others Visit ──────────────────────────────────────────────
    @http.route('/ff/visit/farm', type='http', auth='user')
    def ff_visit_farm(self, **kw):
        ctx = self._get_app_context()
        if ctx.get('is_management_only'):
            return werkzeug.utils.redirect('/ff/manager', 303)
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        report = request.env['ffm.daily.report'].get_or_create_today_report()

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'report': report,
            'transport_modes': TRANSPORT_MODES,
        })
        return request.render('ffm_daily_report.ff_visit_farm', ctx)

    @http.route('/ff/visit/farm/submit', type='json', auth='user', methods=['POST'])
    def ff_visit_farm_submit(self, **payload):
        try:
            client_uuid = (payload.get('client_uuid') or '').strip()
            if client_uuid:
                existing = request.env['ffm.farm.visit'].sudo().search([('client_uuid', '=', client_uuid)], limit=1)
                if existing:
                    return {'status': 'success', 'visit_id': existing.id, 'message': _('Farm visit already saved.')}

            location = self._get_live_location(payload)
            if not location:
                return {'status': 'error', 'message': _('Live location is required. Please turn on GPS / location and try again.')}

            mode = (payload.get('mode') or '').strip()
            if not mode:
                return {'status': 'error', 'message': _('Mode of journey is required.')}

            farm_name = (payload.get('farm_name') or '').strip()
            if not farm_name:
                return {'status': 'error', 'message': _('Farm or institution name is required.')}

            broiler = (payload.get('broiler') or '').strip()
            layer = (payload.get('layer') or '').strip()
            sonali = (payload.get('sonali') or '').strip()
            cattle = (payload.get('cattle') or '').strip()
            aqua = (payload.get('aqua') or '').strip()
            bird_raw = payload.get('bird_count')
            if not broiler or not layer or not sonali or not cattle or not aqua or bird_raw is None or str(bird_raw).strip() == '':
                return {'status': 'error', 'message': _('All Livestock & Capacity Breakdown fields are required.')}

            try:
                bird_count = int(bird_raw)
            except (ValueError, TypeError):
                return {'status': 'error', 'message': _('Animal/bird count must be a number.')}

            if bird_count < 0:
                return {'status': 'error', 'message': _('Animal/bird count cannot be negative.')}

            report = request.env['ffm.daily.report'].get_or_create_today_report()

            visit = request.env['ffm.farm.visit'].sudo().create({
                'report_id': report.id,
                'farm_name': farm_name,
                'address': (payload.get('address') or '').strip(),
                'broiler': broiler,
                'layer': layer,
                'sonali': sonali,
                'cattle': cattle,
                'aqua': aqua,
                'bird_count': bird_count,
                'note': (payload.get('note') or '').strip(),
                'client_uuid': client_uuid or False,
                **location,
            })

            # Journey leg (mode of journey + T.A. bill for vehicle)
            if mode:
                travel_log = report.travel_log_ids[:1]
                if not travel_log:
                    travel_log = request.env['ffm.travel.log'].sudo().create({
                        'daily_report_id': report.id,
                        'employee_id': report.employee_id.id,
                        'date': report.date,
                    })

                fare_tk = float(payload.get('fare_tk', 0) or 0.0)

                # Only mode + T.A. bill are collected; places fall back to the working place
                def_place = report.working_place_id or request.env['ffm.place'].sudo().search([], limit=1)
                p_from = p_to = def_place.id if def_place else False

                if p_from and p_to:
                    request.env['ffm.travel.journey'].sudo().with_context(ffm_manual_fare=True).create({
                        'travel_log_id': travel_log.id,
                        'place_from_id': p_from,
                        'place_to_id': p_to,
                        'mode': mode,
                        'other_mode': (payload.get('other_mode') or '').strip(),
                        'distance_km': 0.0,
                        'fare_tk': fare_tk,
                        'farm_visit_id': visit.id,
                        'client_uuid': f"{client_uuid}_leg" if client_uuid else False,
                    })

            return {
                'status': 'success',
                'visit_id': visit.id,
                'message': _('Farm visit saved successfully.'),
            }
        except Exception as exc:
            _logger.exception("Error submitting farm visit")
            return {'status': 'error', 'message': str(exc)}

    # ── 7. Daily Expense (Phase 4) ──────────────────────────────────────────
    @http.route('/ff/expense', type='http', auth='user')
    def ff_daily_expense_page(self, **kw):
        """Marketer Daily Expense form and today's submitted expenses."""
        ctx = self._get_app_context()
        if ctx.get('is_management_only'):
            return werkzeug.utils.redirect('/ff/manager', 303)
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        today_expenses = []
        day_expense_total = 0.0
        if employee:
            today_expenses = request.env['ffm.daily.expense'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], order='id desc')
            day_expense_total = sum(today_expenses.mapped('total_amount'))

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'today_expenses': today_expenses,
            'day_expense_total': day_expense_total,
        })
        return request.render('ffm_daily_report.ff_daily_expense', ctx)

    @http.route('/ff/expense/submit', type='json', auth='user', methods=['POST'])
    def ff_expense_submit(self, **payload):
        try:
            client_uuid = (payload.get('client_uuid') or '').strip()
            if client_uuid:
                existing = request.env['ffm.daily.expense'].sudo().search([('client_uuid', '=', client_uuid)], limit=1)
                if existing:
                    return {
                        'status': 'success',
                        'expense_id': existing.id,
                        'message': _('Daily expense already saved.')
                    }

            location = self._get_live_location(payload)
            if not location:
                return {'status': 'error', 'message': _('Live location is required. Please turn on GPS / location and try again.')}

            user = request.env.user
            employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            if not employee:
                return {'status': 'error', 'message': _('No employee record found for current user.')}

            today_date, _now_time = self._get_dhaka_date_and_time()

            try:
                entertainment = float(payload.get('entertainment') or 0.0)
                courier = float(payload.get('courier') or 0.0)
                photocopy = float(payload.get('photocopy') or 0.0)
                promotion = float(payload.get('promotion') or 0.0)
                stationery = float(payload.get('stationery') or 0.0)
                carrying = float(payload.get('carrying') or 0.0)
                banking = float(payload.get('banking') or 0.0)
                hotel_rent = float(payload.get('hotel_rent') or 0.0)
                bike = float(payload.get('bike') or 0.0)
            except (ValueError, TypeError):
                return {'status': 'error', 'message': _('Expense amounts must be valid numbers.')}

            amounts = [entertainment, courier, photocopy, promotion, stationery, carrying, banking, hotel_rent, bike]
            if any(val < 0 for val in amounts):
                return {'status': 'error', 'message': _('Expense amount cannot be negative.')}

            if sum(amounts) <= 0:
                return {'status': 'error', 'message': _('At least one expense category must be greater than zero.')}

            # Clean vouchers; they are optional but validated when attached
            v_entertainment = _clean_base64_image(payload.get('voucher_entertainment'))
            v_courier = _clean_base64_image(payload.get('voucher_courier'))
            v_photocopy = _clean_base64_image(payload.get('voucher_photocopy'))
            v_hotel_rent = _clean_base64_image(payload.get('voucher_hotel_rent'))

            if entertainment > 0 and v_entertainment:
                _check_and_validate_voucher(v_entertainment, _('Entertainment Voucher'))

            if courier > 0 and v_courier:
                _check_and_validate_voucher(v_courier, _('Courier Voucher'))

            if photocopy > 0 and v_photocopy:
                _check_and_validate_voucher(v_photocopy, _('Photocopy Voucher'))

            if hotel_rent > 0 and v_hotel_rent:
                _check_and_validate_voucher(v_hotel_rent, _('Hotel Rent Voucher'))

            # Search today's report if any
            report = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)

            vals = {
                'employee_id': employee.id,
                'date': today_date,
                'daily_report_id': report.id if report else False,
                'entertainment': entertainment,
                'courier': courier,
                'photocopy': photocopy,
                'promotion': promotion,
                'stationery': stationery,
                'carrying': carrying,
                'banking': banking,
                'hotel_rent': hotel_rent,
                'bike': bike,
                'note': (payload.get('note') or '').strip(),
                'client_uuid': client_uuid or False,
                **location,
                'voucher_entertainment': v_entertainment or False,
                'voucher_entertainment_filename': 'voucher_entertainment.jpg' if v_entertainment else False,
                'voucher_courier': v_courier or False,
                'voucher_courier_filename': 'voucher_courier.jpg' if v_courier else False,
                'voucher_photocopy': v_photocopy or False,
                'voucher_photocopy_filename': 'voucher_photocopy.jpg' if v_photocopy else False,
                'voucher_hotel_rent': v_hotel_rent or False,
                'voucher_hotel_rent_filename': 'voucher_hotel_rent.jpg' if v_hotel_rent else False,
            }

            expense = request.env['ffm.daily.expense'].sudo().create(vals)

            return {
                'status': 'success',
                'expense_id': expense.id,
                'message': _('Daily expense and vouchers saved successfully.'),
            }
        except ValidationError as ve:
            return {'status': 'error', 'message': ve.name or str(ve)}
        except Exception as exc:
            _logger.exception("Error submitting daily expense")
            return {'status': 'error', 'message': str(exc)}

    # ── 8. Today's Entries (Redirected to Report Cards) ────────────────────
    @http.route('/ff/entries/today', type='http', auth='user')
    def ff_entries_today(self, **kw):
        """Redirect legacy today's entries directly to Report Cards."""
        date_param = kw.get('date')
        if date_param:
            return werkzeug.utils.redirect(f'/ff/report/cards?date={date_param}')
        return werkzeug.utils.redirect('/ff/report/cards')

    # ── 8. Daily & Monthly Report Cards (Phase 5) ───────────────────────────
    @http.route('/ff/report/cards', type='http', auth='user')
    def ff_report_cards(self, **kw):
        """Daily & Monthly Report Cards with role scoping, team attendance, search and pagination."""
        ctx = self._get_app_context()
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']
        user = request.env.user

        is_super_admin = ctx.get('is_super_admin', False)
        is_manager = ctx.get('is_manager', False)
        is_rsm = ctx.get('is_rsm', False)
        is_asm = ctx.get('is_asm', False)
        is_fp = ctx.get('is_fp', False)

        search_query = (kw.get('search') or '').strip()

        # 1. Mode determination
        if is_fp:
            # Field Person is strictly daily report for current calendar date (no past/future reports)
            mode = 'daily'
            query_date = today_date
            date_start = today_date
            date_end = today_date
            period_label = today_date.strftime('%d %B, %Y')
        else:
            mode = kw.get('mode') or 'daily'  # 'daily' or 'monthly'

            # 2. Date / Period calculations
            if mode == 'daily':
                date_str = kw.get('date')
                if date_str:
                    try:
                        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        query_date = today_date
                else:
                    query_date = today_date
                date_start = query_date
                date_end = query_date
                period_label = query_date.strftime('%d %B, %Y')
            else:
                # Monthly mode
                period = kw.get('period') or 'current'  # 'current', 'last_30_days', 'prev'
                if period == 'last_30_days':
                    date_start = today_date - timedelta(days=30)
                    date_end = today_date
                    period_label = f"Last 30 Days ({date_start.strftime('%d %b')} - {date_end.strftime('%d %b, %Y')})"
                elif period == 'prev':
                    first_this_month = today_date.replace(day=1)
                    last_prev_month = first_this_month - timedelta(days=1)
                    date_start = last_prev_month.replace(day=1)
                    date_end = last_prev_month
                    period_label = date_start.strftime('%B, %Y')
                else:
                    date_start = today_date.replace(day=1)
                    date_end = today_date
                    period_label = date_start.strftime('%B, %Y')

        # 3. Subordinates strictly by hierarchy
        if is_super_admin or is_manager:
            # Manager Panel: all active field personnel across company
            all_active = request.env['hr.employee'].sudo().search([('active', '=', True)], order='name asc')
            subordinates = all_active.filtered(lambda e: e.user_id != user)
        elif is_rsm and employee:
            # RSM: all ASMs under him + Field Persons under those ASMs
            subordinates = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
                ('id', 'child_of', employee.id),
                ('id', '!=', employee.id)
            ], order='name asc')
        elif is_asm and employee:
            # ASM: Field Persons directly reporting to him
            subordinates = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
                ('parent_id', '=', employee.id)
            ], order='name asc')
        else:
            # Field Person: No subordinates
            subordinates = request.env['hr.employee'].sudo().browse([])
        subordinates = subordinates.filtered(lambda e: e.ffm_role in ('rsm', 'asm', 'fp'))

        # Filter subordinates by search query if present
        filtered_subordinates = subordinates
        if search_query:
            filtered_subordinates = subordinates.filtered(
                lambda e: search_query.lower() in (e.name or '').lower() or
                          search_query.lower() in (e.job_id.name or '').lower() or
                          search_query.lower() in (e.hq or '').lower()
            )

        # Territory / RSM / ASM scope filters (team overview and attendance views)
        Emp = request.env['hr.employee'].sudo()
        scope_ctx = dict(ctx, is_super_admin=is_super_admin, is_manager=is_manager, is_rsm=is_rsm, is_asm=is_asm)
        ff_team = subordinates.filtered(lambda e: e.ffm_role in ('rsm', 'asm', 'fp'))
        scope_territories, scope_rsms, scope_asms = self._ffm_scope_options(scope_ctx, ff_team)

        def _pick(recs, key):
            try:
                rid = int(kw.get(key) or 0)
            except (TypeError, ValueError):
                rid = 0
            return recs.filtered(lambda r: r.id == rid)[:1]

        sel_territory = _pick(scope_territories, 'territory_id')
        sel_rsm = _pick(scope_rsms, 'rsm_id')
        sel_asm = _pick(scope_asms, 'asm_id')
        if sel_territory:
            filtered_subordinates = filtered_subordinates & sel_territory.member_ids
        for head in (sel_rsm, sel_asm):
            if head:
                branch = Emp.search([('id', 'child_of', head.id)])
                filtered_subordinates = filtered_subordinates & branch
        scope_parts = [label for label in (
            sel_territory and _('Territory: %s') % sel_territory.name,
            sel_rsm and _('RSM: %s') % sel_rsm.name,
            sel_asm and _('ASM: %s') % sel_asm.name,
        ) if label]

        # 4. Target Employee selection
        target_employee = employee
        report_type = kw.get('report_type')
        if not report_type:
            report_type = 'team' if ctx.get('is_management_only') else 'personal'

        if is_fp:
            # Field Person can ONLY view their own report card
            target_employee = employee
            report_type = 'personal'
        else:
            target_emp_id = kw.get('employee_id')
            if target_emp_id:
                try:
                    target_emp_id_int = int(target_emp_id)
                except (ValueError, TypeError):
                    target_emp_id_int = employee.id if employee else 0

                if employee and target_emp_id_int == employee.id and not ctx.get('is_management_only'):
                    target_employee = employee
                    report_type = 'personal'
                else:
                    found = subordinates.filtered(lambda e: e.id == target_emp_id_int)
                    if found:
                        target_employee = found[0]
                        report_type = 'individual'
                    elif ctx.get('is_management_only'):
                        report_type = 'team'
                    else:
                        target_employee = employee
                        report_type = 'personal'
            elif kw.get('view') == 'team' or report_type in ('team', 'asm', 'rsm') or ctx.get('is_management_only'):
                report_type = 'team'
            elif report_type == 'attendance':
                target_employee = employee
            else:
                target_employee = employee
                report_type = 'personal'

        # Pagination setup
        page = max(1, int(kw.get('page') or 1))
        limit = 15

        # Output collections
        attendance_summary = {}
        target_report = False
        report_state = 'none'
        single_day_attendance = False
        chemist_visits = []
        doctor_visits = []
        farm_visits = []
        journey_legs = []
        daily_expenses = []
        team_members_data = []
        day_rows = []
        present_days = 0
        period_days = (date_end - date_start).days + 1

        total_order = 0.0
        total_sale = 0.0
        total_coll = 0.0
        total_fare = 0.0
        total_distance = 0.0
        total_expense = 0.0
        total_chemists_count = 0
        total_doctors_count = 0
        total_farms_count = 0
        total_pages = 1
        total_items = 0

        # ── Scenario A: Team Overview (ASM / RSM / Manager Panel) ─────────────
        if report_type == 'team' and not is_fp:
            emp_ids = filtered_subordinates.ids
            reports = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', '>=', date_start),
                ('date', '<=', date_end),
            ], order='date desc')

            # Attendance: today's record in daily mode, present-day count in monthly mode
            attendances = request.env['ffm.attendance'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', '>=', date_start),
                ('date', '<=', date_end),
            ])
            att_map = {}
            present_days_map = {}
            for att in attendances:
                eid = att.employee_id.id
                present_days_map[eid] = present_days_map.get(eid, 0) + 1
                if att.date == date_start:
                    att_map[eid] = att

            # Map metrics per subordinate
            emp_metrics = {}
            for emp in filtered_subordinates:
                emp_metrics[emp.id] = {
                    'employee': emp,
                    'attendance': att_map.get(emp.id, False),
                    'present_days': present_days_map.get(emp.id, 0),
                    'reports_count': 0,
                    'order': 0.0,
                    'sale': 0.0,
                    'coll': 0.0,
                    'chemists': 0,
                    'doctors': 0,
                    'farms': 0,
                    'distance': 0.0,
                    'fare': 0.0,
                    'expense': 0.0,
                    'latest_state': False,
                }

            for rep in reports:
                eid = rep.employee_id.id
                if eid in emp_metrics:
                    m = emp_metrics[eid]
                    m['reports_count'] += 1
                    if not m['latest_state']:
                        m['latest_state'] = rep.state
                    m['order'] += rep.total_order_tk
                    m['sale'] += rep.total_sale_tk
                    m['coll'] += rep.total_coll_tk
                    m['chemists'] += rep.total_chemist_visited
                    m['doctors'] += rep.total_prescriber_visited
                    m['farms'] += rep.total_farm_visited
                    m['expense'] += rep.total_expense_tk
                    tl = rep.travel_log_ids[:1]
                    if tl:
                        m['distance'] += tl.total_distance_km
                        m['fare'] += tl.total_fare_tk

                total_order += rep.total_order_tk
                total_sale += rep.total_sale_tk
                total_coll += rep.total_coll_tk
                total_chemists_count += rep.total_chemist_visited
                total_doctors_count += rep.total_prescriber_visited
                total_farms_count += rep.total_farm_visited
                total_expense += rep.total_expense_tk
                tl = rep.travel_log_ids[:1]
                if tl:
                    total_distance += tl.total_distance_km
                    total_fare += tl.total_fare_tk

            all_team_list = list(emp_metrics.values())
            total_items = len(all_team_list)
            total_pages = max(1, math.ceil(total_items / limit))
            team_members_data = all_team_list[(page - 1) * limit : page * limit]

        # ── Scenario Attendance: Territory Attendance ──────────────────────────
        elif report_type == 'attendance' and not is_fp:
            present_records = request.env['ffm.attendance'].sudo().search([
                ('employee_id', 'in', filtered_subordinates.ids),
                ('date', '=', date_start)
            ])
            present_map = {a.employee_id.id: a for a in present_records}
            present_list = [{'employee': a.employee_id, 'attendance': a} for a in present_records]
            absent_list = [{'employee': e} for e in filtered_subordinates if e.id not in present_map]
            attendance_summary = {
                'total_strength': len(filtered_subordinates),
                'present_count': len(present_list),
                'absent_count': len(absent_list),
                'present_list': present_list,
                'absent_list': absent_list,
            }

        # ── Scenario B: Individual / Personal Report (Latest Live Data) ───────
        else:
            if target_employee:
                if mode == 'daily':
                    # Single day attendance
                    single_day_attendance = request.env['ffm.attendance'].sudo().search([
                        ('employee_id', '=', target_employee.id),
                        ('date', '=', date_start)
                    ], limit=1)

                    # Single day report
                    target_report = request.env['ffm.daily.report'].sudo().search([
                        ('employee_id', '=', target_employee.id),
                        ('date', '=', date_start)
                    ], limit=1)

                    if target_report:
                        report_state = target_report.state
                        chemist_visits = list(target_report.chemist_visit_ids)
                        doctor_visits = list(target_report.prescriber_visit_ids)
                        farm_visits = list(target_report.farm_visit_ids)
                        journey_legs = list(target_report.travel_log_ids.mapped('journey_ids'))

                        total_order = sum(c.order_tk for c in chemist_visits)
                        total_sale = sum(c.sale_tk for c in chemist_visits)
                        total_coll = sum(c.coll_tk for c in chemist_visits)
                        total_distance = sum(j.distance_km for j in journey_legs)
                        total_fare = sum(j.fare_tk for j in journey_legs)
                    else:
                        report_state = 'pending' if single_day_attendance else 'none'

                    daily_expenses = list(request.env['ffm.daily.expense'].sudo().search([
                        ('employee_id', '=', target_employee.id),
                        ('date', '=', date_start)
                    ], order='id desc'))
                    total_expense = sum(e.total_amount for e in daily_expenses)

                else:
                    # Monthly mode
                    monthly_reports = request.env['ffm.daily.report'].sudo().search([
                        ('employee_id', '=', target_employee.id),
                        ('date', '>=', date_start),
                        ('date', '<=', date_end),
                    ], order='date desc, id desc')

                    for rep in monthly_reports:
                        chem_list = list(rep.chemist_visit_ids)
                        doc_list = list(rep.prescriber_visit_ids)
                        farm_list = list(rep.farm_visit_ids)
                        legs_list = list(rep.travel_log_ids.mapped('journey_ids'))

                        chemist_visits.extend(chem_list)
                        doctor_visits.extend(doc_list)
                        farm_visits.extend(farm_list)
                        journey_legs.extend(legs_list)

                        total_order += (sum(c.order_tk for c in chem_list) or rep.total_order_tk)
                        total_sale += (sum(c.sale_tk for c in chem_list) or rep.total_sale_tk)
                        total_coll += (sum(c.coll_tk for c in chem_list) or rep.total_coll_tk)
                        total_distance += sum(j.distance_km for j in legs_list)
                        total_fare += sum(j.fare_tk for j in legs_list)

                    if monthly_reports:
                        report_state = monthly_reports[0].state
                    else:
                        report_state = 'none'

                    daily_expenses = list(request.env['ffm.daily.expense'].sudo().search([
                        ('employee_id', '=', target_employee.id),
                        ('date', '>=', date_start),
                        ('date', '<=', date_end),
                    ], order='date desc, id desc'))
                    total_expense = sum(e.total_amount for e in daily_expenses)

                    # Day-by-day summary (newest first) so the month reads like a set of daily cards
                    month_att = request.env['ffm.attendance'].sudo().search([
                        ('employee_id', '=', target_employee.id),
                        ('date', '>=', date_start),
                        ('date', '<=', date_end),
                    ])
                    att_by_day = {a.date: a for a in month_att}
                    present_days = len(att_by_day)
                    rep_by_day = {r.date: r for r in monthly_reports}
                    exp_by_day = {}
                    for e in daily_expenses:
                        exp_by_day[e.date] = exp_by_day.get(e.date, 0.0) + e.total_amount
                    day = date_end
                    while day >= date_start:
                        r = rep_by_day.get(day)
                        chem = r.chemist_visit_ids if r else []
                        day_rows.append({
                            'date': day,
                            'attendance': att_by_day.get(day, False),
                            'chemists': len(chem),
                            'doctors': len(r.prescriber_visit_ids) if r else 0,
                            'farms': len(r.farm_visit_ids) if r else 0,
                            'order': sum(c.order_tk for c in chem),
                            'sale': sum(c.sale_tk for c in chem),
                            'coll': sum(c.coll_tk for c in chem),
                            'expense': exp_by_day.get(day, 0.0),
                        })
                        day -= timedelta(days=1)

                total_chemists_count = len(chemist_visits)
                total_doctors_count = len(doctor_visits)
                total_farms_count = len(farm_visits)

        # Doctor grades count
        grade_counts = {'a_plus': 0, 'a': 0, 'b': 0, 'c': 0}
        for d in doctor_visits:
            if d.grade in grade_counts:
                grade_counts[d.grade] += 1

        target_territory_name = False
        if target_employee and target_employee.ffm_territory_ids:
            target_territory_name = ', '.join(target_employee.ffm_territory_ids.mapped('name'))
        if target_employee and not target_territory_name:
            if hasattr(target_employee, 'user_id') and target_employee.user_id and hasattr(target_employee.user_id, 'territory_id') and target_employee.user_id.territory_id:
                target_territory_name = target_employee.user_id.territory_id.name
            if not target_territory_name:
                terr_rec = request.env['territory.territory'].sudo().search([('field_person_id', '=', target_employee.id)], limit=1)
                if terr_rec:
                    target_territory_name = terr_rec.name
            if not target_territory_name and target_report and target_report.territory_id:
                target_territory_name = target_report.territory_id.name
            if not target_territory_name and target_employee.hq:
                target_territory_name = target_employee.hq

        # Own report for today is submitted from the Report Card (no separate Daily Report screen)
        my_today_report = False
        if employee and ctx.get('has_field_operations'):
            my_today_report = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', today_date)
            ], limit=1)

        ctx.update({
            'period': kw.get('period') or 'current',
            'scope_territories': scope_territories,
            'scope_rsms': scope_rsms,
            'scope_asms': scope_asms,
            'sel_territory_id': sel_territory.id or False,
            'sel_rsm_id': sel_rsm.id or False,
            'sel_asm_id': sel_asm.id or False,
            'scope_label': ' • '.join(scope_parts),
            'people_json': self._ffm_people_json(ff_team),
            'mode': mode,
            'report_type': report_type,
            'day_rows': day_rows,
            'period_month': '%02d' % date_start.month,
            'period_year': date_start.year,
            'present_days': present_days,
            'period_days': period_days,
            'query_date': str(date_start),
            'period_label': period_label,
            'allowed_subordinates': subordinates,
            'filtered_subordinates': filtered_subordinates,
            'search_query': search_query,
            'target_employee': target_employee,
            'target_territory_name': target_territory_name,
            'target_report': target_report,
            'report_state': report_state,
            'single_day_attendance': single_day_attendance,
            'my_today_report': my_today_report,
            'team_members_data': team_members_data,
            'chemist_visits': chemist_visits,
            'doctor_visits': doctor_visits,
            'farm_visits': farm_visits,
            'journey_legs': journey_legs,
            'daily_expenses': daily_expenses,
            'grade_counts': grade_counts,
            'total_order': total_order,
            'total_sale': total_sale,
            'total_coll': total_coll,
            'total_fare': total_fare,
            'total_distance': total_distance,
            'total_expense': total_expense,
            'total_chemists_count': total_chemists_count,
            'total_doctors_count': total_doctors_count,
            'total_farms_count': total_farms_count,
            'page': page,
            'total_pages': total_pages,
            'total_items': total_items,
            'has_prev': page > 1,
            'has_next': page < total_pages,
        })
        return request.render('ffm_daily_report.ff_report_cards', ctx)

    @http.route('/ff/report/daily/pdf', type='http', auth='user')
    def ff_report_daily_pdf(self, **kw):
        """Direct stream download of Daily Report PDF with hierarchy scoping and auto-initialization."""
        user = request.env.user
        employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        
        is_super_admin = (user._is_admin() or user.has_group('field_force_management.group_ffm_admin') or user.has_group('base.group_system'))
        is_manager = user.has_group('field_force_management.group_ffm_nsm')
        is_rsm = user.has_group('field_force_management.group_ffm_rsm')
        is_asm = user.has_group('field_force_management.group_ffm_asm')
        is_fp = not (is_super_admin or is_manager or is_rsm or is_asm)

        report = False
        today_date, _ = self._get_dhaka_date_and_time()

        if kw.get('report_id'):
            try:
                report = request.env['ffm.daily.report'].sudo().browse(int(kw['report_id']))
                if is_fp and report:
                    if report.date != today_date or report.employee_id.id != (employee.id if employee else False):
                        return request.not_found()
            except (ValueError, TypeError):
                report = False
        else:
            if is_fp:
                # Field Person can only download own report for current calendar date
                target_emp_id = employee.id if employee else False
                q_date = today_date
            else:
                if kw.get('employee_id'):
                    try:
                        target_emp_id = int(kw['employee_id'])
                    except (ValueError, TypeError):
                        target_emp_id = employee.id if employee else False
                elif employee:
                    target_emp_id = employee.id
                else:
                    target_emp_id = False

                query_date_str = kw.get('date')
                if query_date_str:
                    try:
                        q_date = datetime.strptime(query_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        q_date = today_date
                else:
                    q_date = today_date

            if target_emp_id:
                report = request.env['ffm.daily.report'].sudo().search([
                    ('employee_id', '=', target_emp_id),
                    ('date', '=', q_date)
                ], limit=1)

                if not report:
                    # Auto-initialize a draft daily report so PDF can be rendered with attendance and 'PENDING' status
                    report = request.env['ffm.daily.report'].sudo().create({
                        'employee_id': target_emp_id,
                        'date': q_date,
                        'state': 'draft',
                    })

        if not report or not report.exists():
            return request.not_found()

        # Permission check based on hierarchy
        allowed = False
        if is_super_admin or is_manager:
            # Manager panel / Super Admin: any report
            allowed = True
        elif is_rsm and employee:
            # RSM: self, ASMs under him, or Field Persons under those ASMs
            rsm_subs = request.env['hr.employee'].sudo().search([('id', 'child_of', employee.id)]).ids
            allowed = (report.employee_id.id in rsm_subs or report.employee_id.id == employee.id)
        elif is_asm and employee:
            # ASM: self or direct Field Persons
            asm_subs = request.env['hr.employee'].sudo().search([('parent_id', '=', employee.id)]).ids
            allowed = (report.employee_id.id in asm_subs or report.employee_id.id == employee.id)
        else:
            # Field Person: strictly own report for any calendar date
            allowed = bool(employee and report.employee_id.id == employee.id)

        if not allowed:
            return Response("Forbidden: Access Denied", status=403)

        pdf_content = self._generate_report_pdf(report)
        emp_clean_name = (report.employee_id.name or 'Staff').replace(' ', '_').replace('/', '_')
        pdf_filename = f"Daily_Report_{emp_clean_name}_{report.date}.pdf"
        return Response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{pdf_filename}"'),
            ]
        )

    # ── 8b. Monthly Expense Statement Portal Routes ─────────────────────────
    @http.route('/ff/statement', type='http', auth='user')
    def ff_statement(self, **kw):
        """View monthly expense statement (Supervisors/Managers only; Field Person blocked)."""
        ctx = self._get_app_context()
        if ctx.get('is_fp'):
            return werkzeug.utils.redirect('/ff')

        employee = ctx['employee']
        today_date, _ = self._get_dhaka_date_and_time()

        selected_month = kw.get('month') or f"{today_date.month:02d}"
        try:
            selected_year = int(kw.get('year') or today_date.year)
        except (ValueError, TypeError):
            selected_year = today_date.year

        statement = False
        if employee:
            statement = request.env['ffm.expense.statement'].sudo().search([
                ('employee_id', '=', employee.id),
                ('month', '=', selected_month),
                ('year', '=', selected_year),
            ], limit=1)

        ctx.update({
            'selected_month': selected_month,
            'selected_year': selected_year,
            'statement': statement,
        })
        return request.render('ffm_daily_report.ff_statement', ctx)

    @http.route('/ff/statement/generate', type='http', auth='user', methods=['POST'], csrf=False)
    def ff_statement_generate(self, **kw):
        """Generate or refresh monthly expense statement for the selected period."""
        ctx = self._get_app_context()
        if ctx.get('is_fp'):
            return werkzeug.utils.redirect('/ff')

        employee = ctx['employee']
        if not employee:
            return werkzeug.utils.redirect('/ff')

        today_date, _ = self._get_dhaka_date_and_time()
        selected_month = kw.get('month') or f"{today_date.month:02d}"
        try:
            selected_year = int(kw.get('year') or today_date.year)
        except (ValueError, TypeError):
            selected_year = today_date.year

        statement = request.env['ffm.expense.statement'].sudo().search([
            ('employee_id', '=', employee.id),
            ('month', '=', selected_month),
            ('year', '=', selected_year),
        ], limit=1)

        if not statement:
            statement = request.env['ffm.expense.statement'].sudo().create({
                'employee_id': employee.id,
                'month': selected_month,
                'year': selected_year,
                'state': 'draft',
            })

        if statement.state in ('draft', 'rejected'):
            statement.sudo().action_generate_or_refresh()

        return werkzeug.utils.redirect(f"/ff/statement?month={selected_month}&year={selected_year}")

    @http.route('/ff/statement/submit', type='http', auth='user', methods=['POST'], csrf=False)
    def ff_statement_submit(self, **kw):
        """Submit the statement for superior approval."""
        ctx = self._get_app_context()
        if ctx.get('is_fp'):
            return werkzeug.utils.redirect('/ff')
        if not ctx['approval_enabled']:
            return werkzeug.utils.redirect('/ff/statement')

        employee = ctx['employee']
        statement_id = kw.get('statement_id')
        remarks = kw.get('remarks')

        if statement_id and employee:
            statement = request.env['ffm.expense.statement'].sudo().browse(int(statement_id))
            if statement.exists() and statement.employee_id == employee:
                if remarks is not None:
                    statement.sudo().write({'remarks': remarks.strip()})
                statement.sudo().action_submit()
                return werkzeug.utils.redirect(f"/ff/statement?month={statement.month}&year={statement.year}")

        return werkzeug.utils.redirect('/ff/statement')

    @http.route('/ff/statement/pdf', type='http', auth='user')
    def ff_statement_pdf(self, **kw):
        """Download Monthly Expense Statement PDF in clean table format."""
        user = request.env.user
        is_super_admin = (user._is_admin() or user.has_group('field_force_management.group_ffm_admin') or user.has_group('base.group_system'))
        is_manager = user.has_group('field_force_management.group_ffm_nsm')
        is_rsm = user.has_group('field_force_management.group_ffm_rsm')
        is_asm = user.has_group('field_force_management.group_ffm_asm')
        is_fp = not (is_super_admin or is_manager or is_rsm or is_asm)

        if is_fp:
            # Field Person cannot download monthly expense statement PDF
            return werkzeug.utils.redirect('/ff')

        employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        today_date, _ = self._get_dhaka_date_and_time()

        statement = False
        if kw.get('statement_id'):
            try:
                statement = request.env['ffm.expense.statement'].sudo().browse(int(kw['statement_id']))
            except (ValueError, TypeError):
                statement = False
        elif kw.get('employee_id'):
            target_emp_id = int(kw.get('employee_id'))
            selected_month = kw.get('month') or f"{today_date.month:02d}"
            try:
                selected_year = int(kw.get('year') or today_date.year)
            except (ValueError, TypeError):
                selected_year = today_date.year
            statement = request.env['ffm.expense.statement'].sudo().search([
                ('employee_id', '=', target_emp_id),
                ('month', '=', selected_month),
                ('year', '=', selected_year),
            ], limit=1)
        else:
            selected_month = kw.get('month') or f"{today_date.month:02d}"
            try:
                selected_year = int(kw.get('year') or today_date.year)
            except (ValueError, TypeError):
                selected_year = today_date.year
            if employee:
                statement = request.env['ffm.expense.statement'].sudo().search([
                    ('employee_id', '=', employee.id),
                    ('month', '=', selected_month),
                    ('year', '=', selected_year),
                ], limit=1)

        if not statement or not statement.exists():
            return request.not_found()

        # Hierarchy permission check
        allowed = False
        if is_super_admin or is_manager:
            allowed = True
        elif is_rsm and employee:
            sub_ids = request.env['hr.employee'].sudo().search([('id', 'child_of', employee.id)]).ids
            allowed = (statement.employee_id.id in sub_ids or statement.employee_id.id == employee.id)
        elif is_asm and employee:
            allowed = (statement.employee_id.parent_id.id == employee.id or statement.employee_id.id == employee.id)
        else:
            allowed = (employee and statement.employee_id.id == employee.id)

        if not allowed:
            return Response("Forbidden: Access Denied", status=403)

        pdf_content = self._generate_statement_pdf(statement)
        emp_clean_name = (statement.employee_id.name or 'Staff').replace(' ', '_').replace('/', '_')
        pdf_filename = f"Monthly_Statement_{emp_clean_name}_{statement.year}_{statement.month}.pdf"
        return Response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{pdf_filename}"'),
            ]
        )

    # ── 9. Rapid Local Places & Customers API ───────────────────────────────
    @http.route('/ff/api/places/search', type='json', auth='user', methods=['POST'])
    def ff_api_places_search(self, **kw):
        """Search local ffm.place database only. No external API call."""
        term = (kw.get('term') or '').strip()
        domain = [('active', '=', True)]
        if term:
            domain.append(('name', 'ilike', term))
        places = request.env['ffm.place'].sudo().search(domain, limit=25, order='name asc')
        return {
            'status': 'success',
            'results': [{'id': p.id, 'name': p.name} for p in places]
        }

    @http.route('/ff/api/customers/search', type='json', auth='user', methods=['POST'])
    def ff_api_customers_search(self, **kw):
        """Search active chemists or doctors in customer.information."""
        c_type = kw.get('type') or 'chemist'
        term = (kw.get('term') or '').strip()
        domain = [('active', '=', True), ('type', '=', c_type)]
        if term:
            domain.append(('name', 'ilike', term))
        customers = request.env['customer.information'].sudo().search(domain, limit=25, order='name asc')
        return {
            'status': 'success',
            'results': [
                {
                    'id': c.id,
                    'name': c.name,
                    'address': c.address or '',
                    'mobile': c.mobile or '',
                    'grade': c.grade if hasattr(c, 'grade') else '',
                }
                for c in customers
            ]
        }

    @http.route('/ff/api/journey/calculate', type='json', auth='user', methods=['POST'])
    def ff_api_journey_calculate(self, **kw):
        """Calculate road distance and slab fare between two places with safe fallback."""
        try:
            place_from_id = kw.get('place_from_id')
            place_to_id = kw.get('place_to_id')
            mode = kw.get('mode') or 'motorcycle'

            if not place_from_id or not place_to_id:
                return {'status': 'error', 'message': _('Please select starting and destination places.')}

            p_from = request.env['ffm.place'].sudo().browse(int(place_from_id))
            p_to = request.env['ffm.place'].sudo().browse(int(place_to_id))

            if not p_from.exists() or not p_to.exists():
                return {'status': 'error', 'message': _('Place not found.')}

            route = p_from.compute_route_to(p_to, mode=mode)
            dist = route.get('distance_km', 0.0)
            fare = request.env['ffm.fare.config'].get_fare(mode, dist) if mode and dist else 0.0

            return {
                'status': 'success',
                'distance_km': round(dist, 2),
                'fare_tk': round(fare, 2),
                'source': route.get('source', 'fallback')
            }
        except Exception as exc:
            _logger.exception("Journey distance calculation error")
            return {
                'status': 'success',
                'distance_km': 0.0,
                'fare_tk': 0.0,
                'source': 'fallback',
            }

    # ── 8c. Manager Panel (ASM & RSM Monitoring & Approvals) ─────────────────
    @http.route('/ff/manager', type='http', auth='user')
    def ff_manager_dashboard(self, **kw):
        """Manager Panel for ASM and RSM.
        Dedicated solely to Monitoring, Review, and Approvals.
        NO visit/expense data entry forms.
        """
        user = request.env.user
        is_manager = (user.has_group('field_force_management.group_ffm_asm') or
                      user.has_group('field_force_management.group_ffm_rsm') or
                      user.has_group('field_force_management.group_ffm_nsm') or
                      user.has_group('field_force_management.group_ffm_admin') or
                      request.env.is_admin())
        if not is_manager:
            return werkzeug.utils.redirect('/ff')

        ctx = self._get_app_context()
        today_date, now_time_str = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        is_super_admin = (request.env.is_admin() or
                          user.has_group('field_force_management.group_ffm_admin') or
                          user.has_group('base.group_system'))
        is_manager = user.has_group('field_force_management.group_ffm_nsm') and not is_super_admin
        # Management roles assign territories, people, logins and the reporting hierarchy
        is_management = is_super_admin or is_manager
        is_rsm = user.has_group('field_force_management.group_ffm_rsm') and not (is_super_admin or is_manager)
        is_asm = user.has_group('field_force_management.group_ffm_asm') and not (is_super_admin or is_manager or is_rsm)

        if is_super_admin:
            role_badge = 'Super Admin'
            panel_title = 'Super Admin Panel'
        elif is_manager:
            role_badge = 'Manager'
            panel_title = 'Manager Panel'
        elif is_rsm:
            role_badge = 'Regional Sales Manager (RSM)'
            panel_title = 'RSM Panel'
        elif is_asm:
            role_badge = 'Area Sales Manager (ASM)'
            panel_title = 'ASM Panel'
        else:
            role_badge = 'Field Person'
            panel_title = 'Field Person Portal'

        if is_super_admin or is_manager:
            # Nationwide: all active subordinates in field force hierarchy
            all_active_emps = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
            ], order='name')
            subordinates = all_active_emps.filtered(
                lambda e: (e.user_id != user and not (e.user_id and e.user_id.login == 'admin'))
            )
            approvable_subordinates = subordinates
        elif is_rsm and employee:
            subordinates = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
                ('id', 'child_of', employee.id),
                ('id', '!=', employee.id)
            ], order='name')
            approvable_subordinates = subordinates
        elif is_asm and employee:
            subordinates = request.env['hr.employee'].sudo().search([
                ('active', '=', True),
                ('parent_id', '=', employee.id)
            ], order='name')
            approvable_subordinates = subordinates
        else:
            subordinates = request.env['hr.employee'].browse([])
            approvable_subordinates = request.env['hr.employee'].browse([])

        sub_ids = subordinates.ids
        approvable_sub_ids = approvable_subordinates.ids

        # Admin Management Data (Employees, Roles, Territories, Branches)
        emp_role_map = {}
        if is_management:
            for emp in subordinates:
                u = emp.user_id
                jname = (emp.job_id.name or '').lower()
                if (u and u.has_group('field_force_management.group_ffm_rsm')) or 'rsm' in jname or 'regional' in jname:
                    emp_role_map[emp.id] = {'code': 'rsm', 'label': 'RSM'}
                elif (u and u.has_group('field_force_management.group_ffm_asm')) or 'asm' in jname or 'area' in jname:
                    emp_role_map[emp.id] = {'code': 'asm', 'label': 'ASM'}
                else:
                    emp_role_map[emp.id] = {'code': 'fp', 'label': 'Field Person'}
            all_employees = subordinates
            manager_employees = subordinates.filtered(
                lambda e: emp_role_map.get(e.id, {}).get('code') in ('rsm', 'asm')
            )
            all_territories = request.env['territory.territory'].sudo().search([], order='name')
            all_branches = request.env['aam.branch'].sudo().search([], order='name')
        else:
            all_employees = request.env['hr.employee'].browse([])
            manager_employees = request.env['hr.employee'].browse([])
            all_territories = request.env['territory.territory'].browse([])
            all_branches = request.env['aam.branch'].browse([])

        # 1. Team Attendance Today & Recent
        att_records = request.env['ffm.attendance'].sudo().search([
            ('employee_id', 'in', sub_ids),
            ('date', '=', today_date)
        ], order='reporting_time desc')
        present_emp_ids = att_records.mapped('employee_id.id')
        absent_employees = subordinates.filtered(lambda e: e.id not in present_emp_ids)

        # 2. Daily Reports (Pending Approval, Today & Recent History)
        pending_reports = request.env['ffm.daily.report'].sudo().search([
            ('employee_id', 'in', approvable_sub_ids),
            ('state', '=', 'submitted')
        ], order='date desc, id desc')
        today_reports = request.env['ffm.daily.report'].sudo().search([
            ('employee_id', 'in', sub_ids),
            ('date', '=', today_date)
        ], order='id desc')
        all_recent_reports = request.env['ffm.daily.report'].sudo().search([
            ('employee_id', 'in', sub_ids)
        ], order='date desc, id desc', limit=50)

        # 3. Customer & Field Visits Today & Recent
        chemist_visits = request.env['ffm.chemist.visit'].sudo().search([
            ('report_id.employee_id', 'in', sub_ids),
        ], order='id desc', limit=50)
        doctor_visits = request.env['ffm.prescriber.visit'].sudo().search([
            ('report_id.employee_id', 'in', sub_ids),
        ], order='id desc', limit=50)
        farm_visits = request.env['ffm.farm.visit'].sudo().search([
            ('report_id.employee_id', 'in', sub_ids),
        ], order='id desc', limit=50)

        # 4. Daily Expenses Submitted
        team_expenses = request.env['ffm.daily.expense'].sudo().search([
            ('employee_id', 'in', sub_ids),
        ], order='date desc, id desc', limit=50)

        # 5. Monthly Statements
        submitted_statements = request.env['ffm.expense.statement'].sudo().search([
            ('employee_id', 'in', approvable_sub_ids),
            ('state', '=', 'submitted')
        ], order='year desc, month desc, id desc')
        all_team_statements = request.env['ffm.expense.statement'].sudo().search([
            ('employee_id', 'in', sub_ids)
        ], order='year desc, month desc, id desc', limit=50)

        # Aggregate Metrics (Today or Overall)
        total_order_today = sum(today_reports.mapped('total_order_tk')) if today_reports else sum(chemist_visits.mapped('order_tk'))
        total_sale_today = sum(today_reports.mapped('total_sale_tk')) if today_reports else sum(chemist_visits.mapped('sale_tk'))
        total_coll_today = sum(today_reports.mapped('total_coll_tk')) if today_reports else sum(chemist_visits.mapped('coll_tk'))
        total_expense_today = sum(team_expenses.mapped('total_amount'))

        # Team hierarchy, territories and report filter options
        scope_ctx = dict(ctx, is_super_admin=is_super_admin, is_manager=is_manager, is_rsm=is_rsm, is_asm=is_asm)
        team = self._ffm_team(scope_ctx)
        scope_territories, scope_rsms, scope_asms = self._ffm_scope_options(scope_ctx, team)
        if is_management:
            my_territories = scope_territories
        else:
            my_territories = (team | (employee or team.browse([]))).mapped('ffm_territory_ids').sorted('name')

        default_tab = 'approvals' if ctx['approval_enabled'] else 'activity'
        tab = kw.get('tab', default_tab)
        valid_tabs = (['approvals'] if ctx['approval_enabled'] else []) + ['activity', 'reports', 'team'] + (['territories'] if is_management else [])
        if tab in ('attendance', 'visits', 'expenses'):
            tab = 'activity'
        elif tab == 'statements':
            tab = default_tab
        elif tab not in valid_tabs:
            tab = default_tab

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'now_time_str': now_time_str,
            'panel_title': panel_title,
            'role_badge': role_badge,
            'is_asm': is_asm,
            'is_rsm': is_rsm,
            'is_manager': is_manager,
            'is_super_admin': is_super_admin,
            'is_admin': is_super_admin,
            'can_manage_system': is_management,
            'is_management': is_management,
            'team_people': team,
            'org_roots': self._ffm_org_tree(team, employee),
            'my_territories': my_territories,
            'visible_member_ids': None if is_management else (team.ids + ([employee.id] if employee else [])),
            'scope_territories': scope_territories,
            'scope_rsms': scope_rsms,
            'scope_asms': scope_asms,
            'people_json': self._ffm_people_json(team),
            'rsm_options': team.filtered(lambda e: e.ffm_role == 'rsm') if is_management else team.browse([]),
            'asm_options': team.filtered(lambda e: e.ffm_role == 'asm') if is_management else team.browse([]),
            'today_iso': str(today_date),
            'subordinates': subordinates,
            'sub_count': len(subordinates),
            'all_employees': all_employees,
            'manager_employees': manager_employees,
            'emp_role_map': emp_role_map,
            'all_territories': all_territories,
            'all_branches': all_branches,
            'present_count': len(present_emp_ids),
            'absent_count': len(absent_employees),
            'present_records': att_records,
            'absent_employees': absent_employees,
            'pending_reports': pending_reports,
            'today_reports': today_reports,
            'all_recent_reports': all_recent_reports,
            'chemist_visits': chemist_visits,
            'doctor_visits': doctor_visits,
            'farm_visits': farm_visits,
            'team_expenses': team_expenses,
            'submitted_statements': submitted_statements,
            'all_team_statements': all_team_statements,
            'total_order_today': total_order_today,
            'total_sale_today': total_sale_today,
            'total_coll_today': total_coll_today,
            'total_expense_today': total_expense_today,
            'active_tab': tab,
        })
        return request.render('ffm_daily_report.ff_manager_dashboard', ctx)

    @http.route('/ff/manager/report/approve', type='json', auth='user', methods=['POST'])
    def ff_manager_report_approve(self, report_id, **kw):
        if not self._approval_enabled():
            return {'status': 'error', 'message': _('Approval system is turned off.')}
        user = request.env.user
        report = request.env['ffm.daily.report'].sudo().browse(int(report_id))
        if not report.exists():
            return {'status': 'error', 'message': _('Report not found.')}
        if not report.with_user(user)._can_approve_or_reject():
            return {'status': 'error', 'message': _('You do not have permission to approve this report.')}
        try:
            report.sudo().action_approve()
            return {'status': 'success', 'message': _('Daily report approved successfully.')}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/manager/report/reject', type='json', auth='user', methods=['POST'])
    def ff_manager_report_reject(self, report_id, reason=None, **kw):
        if not self._approval_enabled():
            return {'status': 'error', 'message': _('Approval system is turned off.')}
        user = request.env.user
        report = request.env['ffm.daily.report'].sudo().browse(int(report_id))
        if not report.exists():
            return {'status': 'error', 'message': _('Report not found.')}
        if not report.with_user(user)._can_approve_or_reject():
            return {'status': 'error', 'message': _('You do not have permission to reject this report.')}
        try:
            if reason:
                report.sudo().message_post(body=_("Report rejected by %s. Reason: %s") % (user.name, reason))
            report.sudo().action_reject()
            return {'status': 'success', 'message': _('Daily report rejected.')}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/manager/statement/check', type='json', auth='user', methods=['POST'])
    def ff_manager_statement_check(self, statement_id, **kw):
        if not self._approval_enabled():
            return {'status': 'error', 'message': _('Approval system is turned off.')}
        user = request.env.user
        stmt = request.env['ffm.expense.statement'].sudo().browse(int(statement_id))
        if not stmt.exists():
            return {'status': 'error', 'message': _('Statement not found.')}
        try:
            stmt.with_user(user).action_check()
            return {'status': 'success', 'message': _('Monthly statement verified and checked.')}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/manager/approval/toggle', type='json', auth='user', methods=['POST'])
    def ff_manager_approval_toggle(self, enabled=False, **kw):
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Only Manager or Super Admin can change the approval setting.')}
        request.env['ir.config_parameter'].sudo().set_param(self.APPROVAL_PARAM, '1' if enabled else '0')
        return {
            'status': 'success',
            'enabled': bool(enabled),
            'message': _('Approval system turned on.') if enabled else _('Approval system turned off.'),
        }

    # ── 8d. System Admin CRUD, Password Reset & Demo Seeding ─────────────────
    def _is_ffm_admin_user(self):
        user = request.env.user
        return bool(
            request.env.is_admin() or
            user.has_group('field_force_management.group_ffm_admin') or
            user.has_group('base.group_system') or
            user.has_group('field_force_management.group_ffm_nsm')
        )

    def _ffm_id_list(self, values):
        ids = []
        for v in values or []:
            try:
                ids.append(int(v))
            except (TypeError, ValueError):
                continue
        return ids

    @http.route('/ff/admin/employee/save', type='json', auth='user', methods=['POST'])
    def ff_admin_employee_save(self, name='', role='fp', email='', password='',
                               emp_id=None, parent_id=None, territory_ids=None, branch_id=None,
                               hq='', phone='', login='', **kw):
        """Create / update an RSM, ASM or Field Person together with the login they sign in with."""
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only management can manage personnel.')}
        name = (name or '').strip()
        email = (email or login or '').strip().lower()
        password = password or ''
        role = (role or 'fp').strip().lower()
        if not name:
            return {'status': 'error', 'message': _('Full name is required.')}
        if role not in ('rsm', 'asm', 'fp'):
            return {'status': 'error', 'message': _('Invalid role selected.')}

        role_meta = {
            'rsm': ('field_force_management.group_ffm_rsm', 'Regional Sales Manager (RSM)'),
            'asm': ('field_force_management.group_ffm_asm', 'Area Sales Manager (ASM)'),
            'fp': ('field_force_management.group_ffm_field_person', 'Field Person'),
        }
        group_xmlid, job_title = role_meta[role]
        try:
            Employee = request.env['hr.employee'].sudo()
            Users = request.env['res.users'].sudo().with_context(active_test=False)
            Territory = request.env['territory.territory'].sudo()

            emp = Employee.browse(int(emp_id)) if emp_id else Employee.browse([])
            if emp_id and not emp.exists():
                return {'status': 'error', 'message': _('Personnel record not found.')}
            user_rec = emp.user_id if emp else Users.browse([])

            # Login credentials: email is the login; a password is required for new accounts
            if not email and not user_rec:
                return {'status': 'error', 'message': _('Email (login) is required.')}
            login_changed = bool(email) and (not user_rec or email != (user_rec.login or '').lower())
            if login_changed and not EMAIL_RE.match(email):
                return {'status': 'error', 'message': _('Please enter a valid email address for the login.')}
            if login_changed:
                clash = Users.search([('login', '=ilike', email)], limit=1)
                if clash and clash != user_rec:
                    return {'status': 'error', 'message': _('Another account already uses the login "%s".') % email}
            if not user_rec and len(password) < 6:
                return {'status': 'error', 'message': _('Password must be at least 6 characters for a new account.')}
            if password and len(password) < 6:
                return {'status': 'error', 'message': _('Password must be at least 6 characters.')}

            # Reporting line: Field Person → ASM (or RSM), ASM → RSM, RSM → none
            parent = Employee.browse(int(parent_id)) if parent_id else Employee.browse([])
            allowed_parent = {'fp': ('asm', 'rsm'), 'asm': ('rsm',), 'rsm': ()}[role]
            if parent:
                if not parent.exists() or parent.ffm_role not in allowed_parent:
                    return {'status': 'error', 'message': _('%s can only report to: %s.') % (
                        dict(fp='Field Person', asm='ASM', rsm='RSM')[role],
                        ', '.join(r.upper() for r in allowed_parent) or _('nobody (top of field force)'))}
                if emp and parent == emp:
                    return {'status': 'error', 'message': _('A person cannot report to themselves.')}

            territories = Territory.browse(self._ffm_id_list(territory_ids)).exists()
            if not territories:
                return {'status': 'error', 'message': _('Please select at least one territory for this person.')}

            Job = request.env['hr.job'].sudo()
            job = Job.search([('name', '=', job_title)], limit=1) or Job.create({'name': job_title})
            role_group = request.env.ref(group_xmlid)
            grp_internal = request.env.ref('base.group_user')

            user_vals = {
                'name': name,
                'active': True,
                'groups_id': [(6, 0, [grp_internal.id, role_group.id])],
                'territory_id': territories[:1].id or False,
            }
            if email:
                user_vals.update({'login': email, 'email': email})
            if password:
                user_vals['password'] = password
            if user_rec:
                user_rec.write(user_vals)
            else:
                user_vals.setdefault('tz', 'Asia/Dhaka')
                user_rec = Users.create(user_vals)

            old_territories = emp.ffm_territory_ids if emp else Territory.browse([])
            emp_vals = {
                'name': name,
                'job_id': job.id,
                'parent_id': parent.id or False,
                'branch_id': int(branch_id) if branch_id else False,
                'hq': (hq or '').strip(),
                'mobile_phone': (phone or '').strip(),
                'ffm_phone': (phone or '').strip(),
                'user_id': user_rec.id,
                'work_email': user_rec.login,
                'ffm_territory_ids': [(6, 0, territories.ids)],
                'active': True,
            }
            if not emp:
                # Creating a user may already have created a linked employee
                emp = Employee.search([('user_id', '=', user_rec.id)], limit=1)
            if emp:
                emp.write(emp_vals)
            else:
                emp = Employee.create(emp_vals)

            (old_territories | territories)._sync_legacy_links()
            return {
                'status': 'success',
                'message': _('%s (%s) saved. Login: %s') % (emp.name, job_title, user_rec.login),
                'emp_id': emp.id,
            }
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/admin/employee/reset_password', type='json', auth='user', methods=['POST'])
    def ff_admin_employee_reset_password(self, emp_id, new_password='', **kw):
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only System Administrators can reset passwords.')}
        new_password = (new_password or '').strip()
        if not new_password:
            return {'status': 'error', 'message': _('Please provide a non-empty new password.')}
        emp = request.env['hr.employee'].sudo().browse(int(emp_id))
        if not emp.exists() or not emp.user_id:
            return {'status': 'error', 'message': _('Linked user account not found for this employee.')}
        try:
            emp.user_id.sudo().write({'password': new_password})
            return {
                'status': 'success',
                'message': _('Password updated successfully for %s (login: %s).') % (emp.name, emp.user_id.login),
            }
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/admin/employee/delete', type='json', auth='user', methods=['POST'])
    def ff_admin_employee_delete(self, emp_id, **kw):
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only System Administrators can remove personnel.')}
        emp = request.env['hr.employee'].sudo().browse(int(emp_id))
        if not emp.exists():
            return {'status': 'error', 'message': _('Personnel record not found.')}
        try:
            emp_name = emp.name
            linked_user = emp.user_id
            emp.sudo().write({'active': False})
            if linked_user and linked_user.id != request.env.user.id:
                linked_user.sudo().write({'active': False})
            # Territories keep pointing at an active ASM / Field Person
            emp.ffm_territory_ids._sync_legacy_links()
            return {
                'status': 'success',
                'message': _('Personnel "%s" deactivated and removed from active roster.') % emp_name,
            }
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/admin/territory/save', type='json', auth='user', methods=['POST'])
    def ff_admin_territory_save(self, name='', territory_id=None, branch_id=None, member_ids=None, **kw):
        """Create / update a territory and the RSMs, ASMs and Field Persons assigned to it."""
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only management can manage territories.')}
        name = (name or '').strip()
        if not name:
            return {'status': 'error', 'message': _('Territory name is required.')}
        if not branch_id:
            return {'status': 'error', 'message': _('Please select a Depot for this territory.')}
        try:
            Territory = request.env['territory.territory'].sudo()
            members = request.env['hr.employee'].sudo().browse(self._ffm_id_list(member_ids)).exists()
            vals = {
                'name': name,
                'branch_id': int(branch_id) if branch_id else False,
                'member_ids': [(6, 0, members.ids)],
            }
            if territory_id:
                rec = Territory.browse(int(territory_id))
                if not rec.exists():
                    return {'status': 'error', 'message': _('Territory not found.')}
                rec.write(vals)
            else:
                rec = Territory.create(vals)
            rec._sync_legacy_links()
            # Users without a primary territory get this one (attendance / report territory)
            for emp in members.filtered(lambda e: e.user_id and not e.user_id.territory_id):
                emp.user_id.write({'territory_id': rec.id})
            return {
                'status': 'success',
                'message': _('Territory "%s" saved with %d people.') % (rec.name, len(members)),
                'territory_id': rec.id,
            }
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/admin/territory/delete', type='json', auth='user', methods=['POST'])
    def ff_admin_territory_delete(self, territory_id, **kw):
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only System Administrators can delete territories.')}
        rec = request.env['territory.territory'].sudo().browse(int(territory_id))
        if not rec.exists():
            return {'status': 'error', 'message': _('Territory not found.')}
        try:
            t_name = rec.name
            rec.unlink()
            return {'status': 'success', 'message': _('Territory "%s" deleted successfully.') % t_name}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/admin/branch/save', type='json', auth='user', methods=['POST'])
    def ff_admin_branch_save(self, name='', code='', branch_id=None, **kw):
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only System Administrators can manage branches.')}
        name = (name or '').strip()
        code = (code or '').strip()
        if not name:
            return {'status': 'error', 'message': _('Branch name is required.')}
        try:
            Branch = request.env['aam.branch'].sudo()
            vals = {'name': name, 'code': code}
            if branch_id:
                rec = Branch.browse(int(branch_id))
                if not rec.exists():
                    return {'status': 'error', 'message': _('Branch not found.')}
                rec.write(vals)
            else:
                rec = Branch.create(vals)
            return {
                'status': 'success',
                'message': _('Branch "%s" saved successfully.') % rec.name,
                'branch_id': rec.id,
            }
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/admin/branch/delete', type='json', auth='user', methods=['POST'])
    def ff_admin_branch_delete(self, branch_id, **kw):
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only System Administrators can delete branches.')}
        rec = request.env['aam.branch'].sudo().browse(int(branch_id))
        if not rec.exists():
            return {'status': 'error', 'message': _('Branch not found.')}
        try:
            b_name = rec.name
            rec.unlink()
            return {'status': 'success', 'message': _('Branch "%s" deleted successfully.') % b_name}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    @http.route('/ff/admin/seed_demo', type='json', auth='user', methods=['POST'])
    def ff_admin_seed_demo(self, **kw):
        if not self._is_ffm_admin_user():
            return {'status': 'error', 'message': _('Access Denied: Only System Administrators can seed demo data.')}
        try:
            wiz = request.env['ffm.seed.demo.wizard'].sudo().create({})
            wiz.action_seed_demo_data()
            return {
                'status': 'success',
                'message': _('Demo data seeded successfully across RSM, ASM, and Field Person panels!'),
            }
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    # ── 9. Manifest ─────────────────────────────────────────────────────────
    @http.route('/ff/manifest.json', type='http', auth='none', methods=['GET'])
    def ff_manifest(self):
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
