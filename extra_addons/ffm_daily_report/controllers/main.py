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
        raise ValidationError(_('%s: ভাউচারের ছবি আবশ্যক।') % field_label)
    try:
        raw_bytes = base64.b64decode(binary_b64)
    except Exception:
        raise ValidationError(_('%s: ছবির বাইনারি ডেটা সঠিক নয়।') % field_label)

    if len(raw_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(_('%s: ফাইলের আকার ৫ মেগাবাইটের বেশি হতে পারবে না।') % field_label)

    is_jpeg = raw_bytes.startswith(b'\xff\xd8\xff')
    is_png = raw_bytes.startswith(b'\x89PNG\r\n\x1a\n')
    is_webp = raw_bytes[:4] == b'RIFF' and len(raw_bytes) > 12 and raw_bytes[8:12] == b'WEBP'

    if not (is_jpeg or is_png or is_webp):
        raise ValidationError(_('%s: শুধুমাত্র ছবি ফাইল (JPEG, PNG, WebP) গ্রহণযোগ্য।') % field_label)

TRANSPORT_MODES = [
    ('bus', 'Bus (বাস)'),
    ('rickshaw', 'Rickshaw (রিকশা/ভ্যান)'),
    ('auto_cng', 'Auto / CNG (সিএনজি/অটো)'),
    ('motorcycle', 'Motorcycle (মোটরসাইকেল)'),
    ('uber_pathao', 'Uber / Pathao'),
    ('on_foot', 'On Foot (হেঁটে)'),
    ('train', 'Train (ট্রেন)'),
    ('launch', 'Launch / Ferry (লঞ্চ/নৌকা)'),
    ('others', 'Others (অন্যান্য)'),
]

DOCTOR_GRADES = [
    ('a_plus', 'A+'),
    ('a', 'A'),
    ('b', 'B'),
    ('c', 'C'),
]

class FFMHome(Home):
    def _login_redirect(self, uid, redirect=None):
        if not redirect and uid:
            user = request.env['res.users'].browse(uid)
            if user.has_group('field_force_management.group_ffm_field_person') and not user.has_group('field_force_management.group_ffm_asm') and not user.has_group('field_force_management.group_ffm_admin'):
                return '/ff'
        return super(FFMHome, self)._login_redirect(uid, redirect=redirect)

    @http.route('/web', type='http', auth="none")
    def web_client(self, s_action=None, **kw):
        if request.session.uid and not request.env.is_admin():
            user = request.env.user
            if user.has_group('field_force_management.group_ffm_field_person') and not user.has_group('field_force_management.group_ffm_asm') and not user.has_group('field_force_management.group_ffm_admin'):
                return werkzeug.utils.redirect('/ff')
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

    # ── 1. Dashboard ────────────────────────────────────────────────────────
    @http.route('/ff', type='http', auth='user')
    def ff_dashboard(self, **kw):
        """Marketer mobile start page with the 8 tiles."""
        ctx = self._get_app_context()
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

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'attendance_today': bool(attendance_today),
            'today_report': today_report,
        })
        return request.render('ffm_daily_report.ff_dashboard', ctx)

    # ── 2. Attendance ───────────────────────────────────────────────────────
    @http.route('/ff/attendance', type='http', auth='user')
    def ff_attendance(self, **kw):
        ctx = self._get_app_context()
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
                'message': _('হাজিরা সফলভাবে নিশ্চিত হয়েছে। (Attendance recorded successfully)'),
            }
        except Exception as exc:
            return {
                'status': 'error',
                'message': str(exc),
            }

    # ── 3. Daily Report Header ──────────────────────────────────────────────
    @http.route('/ff/report/daily', type='http', auth='user')
    def ff_daily_report(self, **kw):
        """View or initialize today's daily report."""
        ctx = self._get_app_context()
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
                return {'status': 'error', 'message': _('কর্মক্ষেত্র (Working Place) নির্বাচন করা আবশ্যক।')}

            report = request.env['ffm.daily.report'].get_or_create_today_report(
                working_place_id=int(working_place_id)
            )
            return {
                'status': 'success',
                'report_id': report.id,
                'message': _('আজকের রিপোর্ট সফলভাবে শুরু হয়েছে।'),
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
                return {'status': 'error', 'message': _('আজকের কোনো রিপোর্ট পাওয়া যায়নি।')}
            if report.state != 'draft':
                return {'status': 'error', 'message': _('রিপোর্টটি ইতিমধ্যে জমা দেওয়া হয়েছে।')}
            report.action_submit()
            return {'status': 'success', 'message': _('আজকের রিপোর্ট সফলভাবে সাবমিট করা হয়েছে।')}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    # ── 4. Chemist Visit ────────────────────────────────────────────────────
    @http.route('/ff/visit/chemist', type='http', auth='user')
    def ff_visit_chemist(self, **kw):
        ctx = self._get_app_context()
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        report = request.env['ffm.daily.report'].get_or_create_today_report()
        places = request.env['ffm.place'].sudo().search([('active', '=', True)], limit=150, order='name asc')

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'report': report,
            'places': places,
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
                    return {'status': 'success', 'visit_id': existing.id, 'message': _('কেমিস্ট ভিজিট ইতিমধ্যে সংরক্ষিত আছে।')}

            chemist_id = payload.get('chemist_id')
            chemist_name_manual = (payload.get('chemist_name_manual') or '').strip()
            if not chemist_id and not chemist_name_manual:
                return {'status': 'error', 'message': _('কেমিস্ট নির্বাচন করুন অথবা ম্যানুয়াল নাম লিখুন।')}

            try:
                order_tk = float(payload.get('order_tk', 0))
                sale_tk = float(payload.get('sale_tk', 0))
                coll_tk = float(payload.get('coll_tk', 0))
            except (ValueError, TypeError):
                return {'status': 'error', 'message': _('অর্ডার, সেল এবং কালেকশন সংখ্যায় হতে হবে।')}

            if order_tk < 0 or sale_tk < 0 or coll_tk < 0:
                return {'status': 'error', 'message': _('টাকার পরিমাণ ঋণাত্মক হতে পারবে না।')}

            if not (order_tk.is_integer() and sale_tk.is_integer() and coll_tk.is_integer()):
                return {'status': 'error', 'message': _('টাকার পরিমাণ পূর্ণসংখ্যা (Whole Number) হতে হবে।')}

            # Journey validation for Chemist visit (required)
            mode = (payload.get('mode') or '').strip()
            try:
                fare_tk = float(payload.get('fare_tk', 0))
            except (ValueError, TypeError):
                fare_tk = 0.0

            if not mode:
                return {'status': 'error', 'message': _('ভ্রমণের মাধ্যম (Mode of Journey) নির্বাচন করা আবশ্যক।')}

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
            })

            # Create Travel Leg
            travel_log = report.travel_log_ids[:1]
            if not travel_log:
                travel_log = request.env['ffm.travel.log'].sudo().create({
                    'daily_report_id': report.id,
                    'employee_id': report.employee_id.id,
                    'date': report.date,
                })

            place_from_id = payload.get('place_from_id')
            place_to_id = payload.get('place_to_id')
            distance_km = float(payload.get('distance_km', 0) or 0.0)

            # Fallback to report working place or default first place
            def_place = report.working_place_id or request.env['ffm.place'].sudo().search([], limit=1)
            p_from = int(place_from_id) if place_from_id else (def_place.id if def_place else False)
            p_to = int(place_to_id) if place_to_id else (def_place.id if def_place else False)

            if p_from and p_to:
                request.env['ffm.travel.journey'].sudo().create({
                    'travel_log_id': travel_log.id,
                    'place_from_id': p_from,
                    'place_to_id': p_to,
                    'mode': mode,
                    'other_mode': (payload.get('other_mode') or '').strip(),
                    'distance_km': distance_km,
                    'fare_tk': fare_tk,
                    'chemist_visit_id': visit.id,
                    'client_uuid': f"{client_uuid}_leg" if client_uuid else False,
                })

            return {
                'status': 'success',
                'visit_id': visit.id,
                'message': _('কেমিস্ট ভিজিট ও ভ্রমণ তথ্য সফলভাবে সংরক্ষিত হয়েছে।'),
            }
        except Exception as exc:
            _logger.exception("Error submitting chemist visit")
            return {'status': 'error', 'message': str(exc)}

    # ── 5. Doctor Visit ─────────────────────────────────────────────────────
    @http.route('/ff/visit/doctor', type='http', auth='user')
    def ff_visit_doctor(self, **kw):
        ctx = self._get_app_context()
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        report = request.env['ffm.daily.report'].get_or_create_today_report()
        places = request.env['ffm.place'].sudo().search([('active', '=', True)], limit=150, order='name asc')

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'report': report,
            'places': places,
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
                    return {'status': 'success', 'visit_id': existing.id, 'message': _('ডাক্তার ভিজিট ইতিমধ্যে সংরক্ষিত আছে।')}

            doctor_id = payload.get('doctor_id')
            prescriber_name_manual = (payload.get('prescriber_name_manual') or '').strip()
            if not doctor_id and not prescriber_name_manual:
                return {'status': 'error', 'message': _('ডাক্তার নির্বাচন করুন অথবা ম্যানুয়াল নাম লিখুন।')}

            mobile = (payload.get('mobile') or '').strip()
            mailing_address = (payload.get('mailing_address') or '').strip()
            product_discussion = (payload.get('product_discussion') or '').strip()
            sample = (payload.get('sample') or '').strip()
            grade = (payload.get('grade') or '').strip()

            if not product_discussion or not sample or not grade:
                return {'status': 'error', 'message': _('প্রোডাক্ট আলোচনা, স্যাম্পল/উপহার এবং গ্রেড নির্বাচন করা আবশ্যক।')}

            # Journey validation for Doctor visit
            mode = (payload.get('mode') or '').strip()
            try:
                fare_tk = float(payload.get('fare_tk', 0))
            except (ValueError, TypeError):
                fare_tk = 0.0

            if not mode:
                return {'status': 'error', 'message': _('ভ্রমণের মাধ্যম (Mode of Journey) নির্বাচন করা আবশ্যক।')}

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
            })

            # Create Travel Leg
            travel_log = report.travel_log_ids[:1]
            if not travel_log:
                travel_log = request.env['ffm.travel.log'].sudo().create({
                    'daily_report_id': report.id,
                    'employee_id': report.employee_id.id,
                    'date': report.date,
                })

            place_from_id = payload.get('place_from_id')
            place_to_id = payload.get('place_to_id')
            distance_km = float(payload.get('distance_km', 0) or 0.0)

            def_place = report.working_place_id or request.env['ffm.place'].sudo().search([], limit=1)
            p_from = int(place_from_id) if place_from_id else (def_place.id if def_place else False)
            p_to = int(place_to_id) if place_to_id else (def_place.id if def_place else False)

            if p_from and p_to:
                request.env['ffm.travel.journey'].sudo().create({
                    'travel_log_id': travel_log.id,
                    'place_from_id': p_from,
                    'place_to_id': p_to,
                    'mode': mode,
                    'other_mode': (payload.get('other_mode') or '').strip(),
                    'distance_km': distance_km,
                    'fare_tk': fare_tk,
                    'prescriber_visit_id': visit.id,
                    'client_uuid': f"{client_uuid}_leg" if client_uuid else False,
                })

            return {
                'status': 'success',
                'visit_id': visit.id,
                'message': _('ডাক্তার ভিজিট ও ভ্রমণ তথ্য সফলভাবে সংরক্ষিত হয়েছে।'),
            }
        except Exception as exc:
            _logger.exception("Error submitting doctor visit")
            return {'status': 'error', 'message': str(exc)}

    # ── 6. Farm / Others Visit ──────────────────────────────────────────────
    @http.route('/ff/visit/farm', type='http', auth='user')
    def ff_visit_farm(self, **kw):
        ctx = self._get_app_context()
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        report = request.env['ffm.daily.report'].get_or_create_today_report()
        places = request.env['ffm.place'].sudo().search([('active', '=', True)], limit=150, order='name asc')

        ctx.update({
            'today_str': today_date.strftime('%d %B, %Y'),
            'report': report,
            'places': places,
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
                    return {'status': 'success', 'visit_id': existing.id, 'message': _('খামার ভিজিট ইতিমধ্যে সংরক্ষিত আছে।')}

            farm_name = (payload.get('farm_name') or '').strip()
            if not farm_name:
                return {'status': 'error', 'message': _('খামার বা প্রতিষ্ঠানের নাম প্রদান করা আবশ্যক।')}

            try:
                bird_count = int(payload.get('bird_count', 0) or 0)
            except (ValueError, TypeError):
                bird_count = 0

            if bird_count < 0:
                return {'status': 'error', 'message': _('পশু বা পাখির সংখ্যা ঋণাত্মক হতে পারে না।')}

            report = request.env['ffm.daily.report'].get_or_create_today_report()

            visit = request.env['ffm.farm.visit'].sudo().create({
                'report_id': report.id,
                'farm_name': farm_name,
                'address': (payload.get('address') or '').strip(),
                'broiler': (payload.get('broiler') or '').strip(),
                'layer': (payload.get('layer') or '').strip(),
                'sonali': (payload.get('sonali') or '').strip(),
                'cattle': (payload.get('cattle') or '').strip(),
                'aqua': (payload.get('aqua') or '').strip(),
                'bird_count': bird_count,
                'note': (payload.get('note') or '').strip(),
                'client_uuid': client_uuid or False,
            })

            # Journey leg if mode provided
            mode = (payload.get('mode') or '').strip()
            if mode:
                travel_log = report.travel_log_ids[:1]
                if not travel_log:
                    travel_log = request.env['ffm.travel.log'].sudo().create({
                        'daily_report_id': report.id,
                        'employee_id': report.employee_id.id,
                        'date': report.date,
                    })

                place_from_id = payload.get('place_from_id')
                place_to_id = payload.get('place_to_id')
                distance_km = float(payload.get('distance_km', 0) or 0.0)
                fare_tk = float(payload.get('fare_tk', 0) or 0.0)

                def_place = report.working_place_id or request.env['ffm.place'].sudo().search([], limit=1)
                p_from = int(place_from_id) if place_from_id else (def_place.id if def_place else False)
                p_to = int(place_to_id) if place_to_id else (def_place.id if def_place else False)

                if p_from and p_to:
                    request.env['ffm.travel.journey'].sudo().create({
                        'travel_log_id': travel_log.id,
                        'place_from_id': p_from,
                        'place_to_id': p_to,
                        'mode': mode,
                        'other_mode': (payload.get('other_mode') or '').strip(),
                        'distance_km': distance_km,
                        'fare_tk': fare_tk,
                        'farm_visit_id': visit.id,
                        'client_uuid': f"{client_uuid}_leg" if client_uuid else False,
                    })

            return {
                'status': 'success',
                'visit_id': visit.id,
                'message': _('খামার ভিজিট সফলভাবে সংরক্ষিত হয়েছে।'),
            }
        except Exception as exc:
            _logger.exception("Error submitting farm visit")
            return {'status': 'error', 'message': str(exc)}

    # ── 7. Daily Expense (Phase 4) ──────────────────────────────────────────
    @http.route('/ff/expense', type='http', auth='user')
    def ff_daily_expense_page(self, **kw):
        """Marketer Daily Expense form and today's submitted expenses."""
        ctx = self._get_app_context()
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
                        'message': _('দৈনিক খরচ ইতিমধ্যে সংরক্ষিত আছে।')
                    }

            user = request.env.user
            employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            if not employee:
                return {'status': 'error', 'message': _('বর্তমান ব্যবহারকারীর জন্য কোনো কর্মী রেকর্ড পাওয়া যায়নি।')}

            today_date, _now_time = self._get_dhaka_date_and_time()

            try:
                entertainment = float(payload.get('entertainment', 0) or 0.0)
                courier = float(payload.get('courier', 0) or 0.0)
                photocopy = float(payload.get('photocopy', 0) or 0.0)
                promotion = float(payload.get('promotion', 0) or 0.0)
                stationery = float(payload.get('stationery', 0) or 0.0)
                carrying = float(payload.get('carrying', 0) or 0.0)
                banking = float(payload.get('banking', 0) or 0.0)
                hotel_rent = float(payload.get('hotel_rent', 0) or 0.0)
                bike = float(payload.get('bike', 0) or 0.0)
            except (ValueError, TypeError):
                return {'status': 'error', 'message': _('খরচের টাকার পরিমাণ সঠিক সংখ্যায় হতে হবে।')}

            amounts = [entertainment, courier, photocopy, promotion, stationery, carrying, banking, hotel_rent, bike]
            if any(val < 0 for val in amounts):
                return {'status': 'error', 'message': _('খরচের পরিমাণ ঋণাত্মক হতে পারে না।')}

            if sum(amounts) <= 0:
                return {'status': 'error', 'message': _('অন্তত একটি খাতের খরচের পরিমাণ শূন্যের বেশি হতে হবে।')}

            # Clean and validate vouchers
            v_entertainment = _clean_base64_image(payload.get('voucher_entertainment'))
            v_courier = _clean_base64_image(payload.get('voucher_courier'))
            v_photocopy = _clean_base64_image(payload.get('voucher_photocopy'))
            v_hotel_rent = _clean_base64_image(payload.get('voucher_hotel_rent'))

            if entertainment > 0:
                if not v_entertainment:
                    return {'status': 'error', 'message': _('আপ্যায়ন (Entertainment) খরচের ভাউচার ছবি আবশ্যক।')}
                _check_and_validate_voucher(v_entertainment, _('আপ্যায়ন ভাউচার'))

            if courier > 0:
                if not v_courier:
                    return {'status': 'error', 'message': _('কুরিয়ার খরচের ভাউচার ছবি আবশ্যক।')}
                _check_and_validate_voucher(v_courier, _('কুরিয়ার ভাউচার'))

            if photocopy > 0:
                if not v_photocopy:
                    return {'status': 'error', 'message': _('ফটোকপি খরচের ভাউচার ছবি আবশ্যক।')}
                _check_and_validate_voucher(v_photocopy, _('ফটোকপি ভাউচার'))

            if hotel_rent > 0:
                if not v_hotel_rent:
                    return {'status': 'error', 'message': _('হোটেল ভাড়া খরচের ভাউচার ছবি আবশ্যক।')}
                _check_and_validate_voucher(v_hotel_rent, _('হোটেল ভাড়া ভাউচার'))

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
                'message': _('দৈনিক খরচ ও ভাউচার সফলভাবে সংরক্ষিত হয়েছে।'),
            }
        except ValidationError as ve:
            return {'status': 'error', 'message': ve.name or str(ve)}
        except Exception as exc:
            _logger.exception("Error submitting daily expense")
            return {'status': 'error', 'message': str(exc)}

    # ── 8. Today's Entries & Date/Month/Year Summary ────────────────────────
    @http.route('/ff/entries/today', type='http', auth='user')
    def ff_entries_today(self, **kw):
        """View today's submitted visit lines and summary metrics."""
        ctx = self._get_app_context()
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']

        selected_date_str = kw.get('date')
        if selected_date_str:
            try:
                query_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                query_date = today_date
        else:
            query_date = today_date

        report = False
        chemist_visits = []
        doctor_visits = []
        farm_visits = []
        journey_legs = []
        daily_expenses = []
        day_expense_total = 0.0

        if employee:
            report = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', query_date)
            ], limit=1)
            if report:
                chemist_visits = report.chemist_visit_ids
                doctor_visits = report.prescriber_visit_ids
                farm_visits = report.farm_visit_ids
                travel_log = report.travel_log_ids[:1]
                if travel_log:
                    journey_legs = travel_log.journey_ids

            daily_expenses = request.env['ffm.daily.expense'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', query_date)
            ], order='id desc')
            day_expense_total = sum(daily_expenses.mapped('total_amount'))

        # Breakdown doctor counts by grade
        grade_counts = {'a_plus': 0, 'a': 0, 'b': 0, 'c': 0}
        for d in doctor_visits:
            if d.grade in grade_counts:
                grade_counts[d.grade] += 1

        # Month totals (rolling current month)
        first_day_of_month = query_date.replace(day=1)
        reports_in_month = request.env['ffm.daily.report'].sudo().search([
            ('employee_id', '=', employee.id if employee else False),
            ('date', '>=', first_day_of_month),
            ('date', '<=', query_date),
        ])

        month_order = sum(reports_in_month.mapped('total_order_tk'))
        month_sale = sum(reports_in_month.mapped('total_sale_tk'))
        month_coll = sum(reports_in_month.mapped('total_coll_tk'))
        month_chemists = sum(reports_in_month.mapped('total_chemist_visited'))
        month_doctors = sum(reports_in_month.mapped('total_prescriber_visited'))

        ctx.update({
            'today_str': query_date.strftime('%d %B, %Y'),
            'query_date': str(query_date),
            'report': report,
            'chemist_visits': chemist_visits,
            'doctor_visits': doctor_visits,
            'farm_visits': farm_visits,
            'journey_legs': journey_legs,
            'daily_expenses': daily_expenses,
            'day_expense_total': day_expense_total,
            'grade_counts': grade_counts,
            'month_order': month_order,
            'month_sale': month_sale,
            'month_coll': month_coll,
            'month_chemists': month_chemists,
            'month_doctors': month_doctors,
        })
        return request.render('ffm_daily_report.ff_entries_today', ctx)

    # ── 8. Daily & Monthly Report Cards (Phase 5) ───────────────────────────
    @http.route('/ff/report/cards', type='http', auth='user')
    def ff_report_cards(self, **kw):
        """Daily & Monthly Report Cards with role scoping, team attendance, and pagination."""
        ctx = self._get_app_context()
        today_date, _now_time = self._get_dhaka_date_and_time()
        employee = ctx['employee']
        user = request.env.user

        mode = kw.get('mode') or 'daily'  # 'daily' or 'monthly'
        report_type = kw.get('report_type') or 'personal'  # 'personal', 'asm', 'attendance', 'individual', 'rsm'

        # Date calculations
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
            # Monthly
            period = kw.get('period') or 'current'  # 'current', 'last_30_days', 'prev'
            if period == 'last_30_days':
                date_start = today_date - timedelta(days=30)
                date_end = today_date
                period_label = f"গত ৩০ দিন ({date_start.strftime('%d %b')} - {date_end.strftime('%d %b, %Y')})"
            elif period == 'prev':
                first_this_month = today_date.replace(day=1)
                last_prev_month = first_this_month - timedelta(days=1)
                date_start = last_prev_month.replace(day=1)
                date_end = last_prev_month
                period_label = date_start.strftime('%B, %Y')
            else:
                # Current month
                date_start = today_date.replace(day=1)
                date_end = today_date
                period_label = date_start.strftime('%B, %Y')

        # Subordinates & Scoping (strict adherence to hierarchy)
        is_higher_role = (
            user.has_group('field_force_management.group_ffm_admin') or
            user.has_group('field_force_management.group_ffm_director') or
            user.has_group('field_force_management.group_ffm_nsm')
        )
        if is_higher_role:
            allowed_subordinates = request.env['hr.employee'].sudo().search([('active', '=', True)], order='name asc')
        elif employee:
            allowed_subordinates = request.env['hr.employee'].sudo().search([('id', 'child_of', employee.id), ('active', '=', True)], order='name asc')
        else:
            allowed_subordinates = request.env['hr.employee'].sudo().browse([])

        # Target employee for individual / personal report
        target_employee = employee
        if report_type == 'individual':
            target_emp_id = kw.get('employee_id')
            if target_emp_id:
                try:
                    found = allowed_subordinates.filtered(lambda e: e.id == int(target_emp_id))
                    if found:
                        target_employee = found[0]
                except (ValueError, TypeError):
                    pass

        # Pagination setup
        page = max(1, int(kw.get('page') or 1))
        limit = 10

        # Context output variables
        attendance_summary = {}
        target_reports = []
        chemist_visits = []
        doctor_visits = []
        farm_visits = []
        journey_legs = []
        daily_expenses = []
        team_members_data = []

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

        # ── Scenario A: Territory Attendance ──────────────────────────────
        if report_type == 'attendance':
            emp_ids = allowed_subordinates.ids
            attendances = request.env['ffm.attendance'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', '=', date_start)
            ])
            att_map = {att.employee_id.id: att for att in attendances}
            present_list = []
            absent_list = []
            for emp in allowed_subordinates:
                if emp.id in att_map:
                    present_list.append({
                        'employee': emp,
                        'attendance': att_map[emp.id],
                    })
                else:
                    absent_list.append({
                        'employee': emp,
                    })

            attendance_summary = {
                'total_strength': len(allowed_subordinates),
                'present_count': len(present_list),
                'absent_count': len(absent_list),
                'present_list': present_list,
                'absent_list': absent_list,
            }

        # ── Scenario B: ASM / RSM Team Reports ────────────────────────────
        elif report_type in ('asm', 'rsm'):
            emp_ids = allowed_subordinates.ids
            reports = request.env['ffm.daily.report'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', '>=', date_start),
                ('date', '<=', date_end),
            ], order='date desc')

            # Aggregate per employee
            emp_metrics = {}
            for emp in allowed_subordinates:
                emp_metrics[emp.id] = {
                    'employee': emp,
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
                }

            for rep in reports:
                eid = rep.employee_id.id
                if eid in emp_metrics:
                    m = emp_metrics[eid]
                    m['reports_count'] += 1
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

        # ── Scenario C: Personal / Individual Report ──────────────────────
        else:
            if target_employee:
                target_reports = request.env['ffm.daily.report'].sudo().search([
                    ('employee_id', '=', target_employee.id),
                    ('date', '>=', date_start),
                    ('date', '<=', date_end),
                ], order='date desc')

                for rep in target_reports:
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
                        journey_legs.extend(tl.journey_ids)

                    chemist_visits.extend(rep.chemist_visit_ids)
                    doctor_visits.extend(rep.prescriber_visit_ids)
                    farm_visits.extend(rep.farm_visit_ids)

                expenses = request.env['ffm.daily.expense'].sudo().search([
                    ('employee_id', '=', target_employee.id),
                    ('date', '>=', date_start),
                    ('date', '<=', date_end),
                ], order='date desc, id desc')
                daily_expenses = expenses

                # Paginate chemist visits if many
                total_items = len(chemist_visits)
                total_pages = max(1, math.ceil(total_items / limit))
                chemist_visits = chemist_visits[(page - 1) * limit : page * limit]

        # Doctor grades count
        grade_counts = {'a_plus': 0, 'a': 0, 'b': 0, 'c': 0}
        for d in doctor_visits:
            if d.grade in grade_counts:
                grade_counts[d.grade] += 1

        # Attendance record for single day view
        single_day_attendance = False
        if mode == 'daily' and target_employee:
            single_day_attendance = request.env['ffm.attendance'].sudo().search([
                ('employee_id', '=', target_employee.id),
                ('date', '=', date_start)
            ], limit=1)

        ctx.update({
            'mode': mode,
            'report_type': report_type,
            'query_date': str(date_start),
            'period_label': period_label,
            'allowed_subordinates': allowed_subordinates,
            'target_employee': target_employee,
            'attendance_summary': attendance_summary,
            'single_day_attendance': single_day_attendance,
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
        """Direct stream download of Daily Report PDF with Bengali font."""
        user = request.env.user
        employee = user.employee_id or request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        target_emp_id = kw.get('employee_id')
        if target_emp_id:
            target_emp = request.env['hr.employee'].sudo().browse(int(target_emp_id))
            allowed = request.env['hr.employee'].search([('id', 'child_of', employee.id)]).ids
            if (target_emp.id in allowed or
                user.has_group('field_force_management.group_ffm_nsm') or
                user.has_group('field_force_management.group_ffm_director') or
                user.has_group('field_force_management.group_ffm_admin')):
                employee = target_emp

        query_date_str = kw.get('date')
        if query_date_str:
            try:
                q_date = datetime.strptime(query_date_str, '%Y-%m-%d').date()
            except ValueError:
                q_date = date.today()
        else:
            q_date = date.today()

        report = request.env['ffm.daily.report'].sudo().search([
            ('employee_id', '=', employee.id),
            ('date', '=', q_date)
        ], limit=1)

        if not report:
            return request.not_found()

        pdf_content, _ = request.env.ref('ffm_daily_report.action_report_ffm_daily_report_pdf').sudo()._render_qweb_pdf(report.ids)
        pdf_filename = f"Daily_Report_{employee.name}_{q_date}.pdf"
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
        """View monthly expense statement for logged in marketer."""
        ctx = self._get_app_context()
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
        """Download Monthly Expense Statement PDF."""
        ctx = self._get_app_context()
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

        if not statement:
            return request.not_found()

        pdf_content, _ = request.env.ref('ffm_daily_report.action_report_ffm_expense_statement_pdf').sudo()._render_qweb_pdf(statement.ids)
        pdf_filename = f"Monthly_Statement_{employee.name}_{selected_year}_{selected_month}.pdf"
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
                return {'status': 'error', 'message': _('প্রারম্ভিক ও গন্তব্য স্থান নির্বাচন করুন।')}

            p_from = request.env['ffm.place'].sudo().browse(int(place_from_id))
            p_to = request.env['ffm.place'].sudo().browse(int(place_to_id))

            if not p_from.exists() or not p_to.exists():
                return {'status': 'error', 'message': _('স্থান পাওয়া যায়নি।')}

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
                'source': 'manual'
            }

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
