# -*- coding: utf-8 -*-
from datetime import datetime, date
import json
import pytz
import logging

from odoo import http, fields, _
from odoo.http import request, Response
from odoo.addons.web.controllers.main import Home
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

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

    # ── 1. Dashboard ────────────────────────────────────────────────────────
    @http.route('/ff', type='http', auth='user')
    def ff_dashboard(self, **kw):
        """Marketer mobile start page with the 8 tiles."""
        ctx = self._get_app_context()
        today_date, _ = self._get_dhaka_date_and_time()
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
        today_date, _ = self._get_dhaka_date_and_time()
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
            today_date, _ = self._get_dhaka_date_and_time()
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
        today_date, _ = self._get_dhaka_date_and_time()
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
        today_date, _ = self._get_dhaka_date_and_time()
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
        today_date, _ = self._get_dhaka_date_and_time()
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

    # ── 7. Today's Entries & Date/Month/Year Summary ────────────────────────
    @http.route('/ff/entries/today', type='http', auth='user')
    def ff_entries_today(self, **kw):
        """View today's submitted visit lines and summary metrics."""
        ctx = self._get_app_context()
        today_date, _ = self._get_dhaka_date_and_time()
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
            'grade_counts': grade_counts,
            'month_order': month_order,
            'month_sale': month_sale,
            'month_coll': month_coll,
            'month_chemists': month_chemists,
            'month_doctors': month_doctors,
        })
        return request.render('ffm_daily_report.ff_entries_today', ctx)

    # ── 8. Rapid Local Places & Customers API ───────────────────────────────
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
