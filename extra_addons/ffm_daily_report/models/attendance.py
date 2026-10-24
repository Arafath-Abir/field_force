# -*- coding: utf-8 -*-
from datetime import datetime
import pytz
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import psycopg2

_logger = logging.getLogger(__name__)

class FFMAttendance(models.Model):
    _name = 'ffm.attendance'
    _description = 'FFM Daily Marketer Attendance'
    _order = 'date desc, reporting_time desc, id desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, index=True, readonly=True)
    date = fields.Date(string='Date', required=True, index=True, readonly=True)
    reporting_time = fields.Datetime(string='Reporting Time (Server)', required=True, readonly=True)
    reporting_time_bd = fields.Char(string='Reporting Time (BD)', compute='_compute_reporting_time_bd', store=True)
    name = fields.Char(string='Employee Name', readonly=True)
    designation = fields.Char(string='Designation', readonly=True)
    territory_id = fields.Many2one('territory.territory', string='Territory', index=True, readonly=True)
    latitude = fields.Float(string='Latitude', digits=(12, 7), required=True, readonly=True)
    longitude = fields.Float(string='Longitude', digits=(12, 7), required=True, readonly=True)
    accuracy = fields.Float(string='Accuracy (Meters)', required=True, readonly=True)
    mode_of_journey = fields.Char(string='Mode of Journey', readonly=True)
    client_uuid = fields.Char(string='Client UUID', index=True, readonly=True)
    state = fields.Selection([
        ('submitted', 'Submitted')
    ], string='Status', default='submitted', readonly=True, required=True)
    map_url = fields.Char(string='Map Location', compute='_compute_map_url')
    place_name = fields.Char(string='Location / Place', compute='_compute_place_name')

    _sql_constraints = [
        ('unique_employee_date', 'unique(employee_id, date)', 'Only one attendance record is allowed per employee per day!'),
        ('unique_client_uuid', 'unique(client_uuid)', 'Attendance submission with this UUID already exists!'),
    ]

    def _compute_map_url(self):
        for rec in self:
            if rec.latitude and rec.longitude:
                rec.map_url = f"https://www.google.com/maps?q={rec.latitude},{rec.longitude}"
            else:
                rec.map_url = False

    def _compute_place_name(self):
        for rec in self:
            rec.place_name = rec.territory_id.name or rec.employee_id.hq or 'Bangladesh'

    @api.depends('reporting_time')
    def _compute_reporting_time_bd(self):
        dhaka_tz = pytz.timezone('Asia/Dhaka')
        for rec in self:
            if rec.reporting_time:
                utc_dt = pytz.utc.localize(rec.reporting_time)
                rec.reporting_time_bd = utc_dt.astimezone(dhaka_tz).strftime('%I:%M %p')
            else:
                rec.reporting_time_bd = ''

    def get_reporting_time_bd(self, fmt='%I:%M %p'):
        self.ensure_one()
        if not self.reporting_time:
            return ''
        dhaka_tz = pytz.timezone('Asia/Dhaka')
        utc_dt = pytz.utc.localize(self.reporting_time)
        return utc_dt.astimezone(dhaka_tz).strftime(fmt)

    @api.constrains('latitude', 'longitude', 'accuracy')
    def _check_coordinates(self):
        for rec in self:
            if rec.latitude is not None and not (-90.0 <= rec.latitude <= 90.0):
                raise ValidationError(_("Latitude must be between -90 and 90 degrees."))
            if rec.longitude is not None and not (-180.0 <= rec.longitude <= 180.0):
                raise ValidationError(_("Longitude must be between -180 and 180 degrees."))
            if rec.accuracy is not None and rec.accuracy <= 0.0:
                raise ValidationError(_("GPS accuracy must be a positive number of meters."))

    @classmethod
    def get_dhaka_today(cls):
        tz = pytz.timezone('Asia/Dhaka')
        return datetime.now(tz).date()

    @api.model
    def submit_attendance(self, vals):
        """Submit daily attendance with strict server-side validation and idempotency handling.
        
        Ignores browser-supplied employee_id and date to prevent spoofing.
        Derives employee from current session user and date in Asia/Dhaka timezone.
        """
        user = self.env.user
        employee = user.employee_id or self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            raise UserError(_("No employee profile is linked to your user account (%s).") % user.name)

        server_today = self.get_dhaka_today()
        client_uuid = (vals.get('client_uuid') or '').strip()

        # Idempotency check 1: Search by client_uuid if provided
        if client_uuid:
            existing = self.sudo().search([('client_uuid', '=', client_uuid)], limit=1)
            if existing:
                _logger.info("Idempotent hit: Attendance already recorded with client_uuid %s", client_uuid)
                return existing

        # Enforce exactly one attendance per calendar date
        existing_today = self.sudo().search([
            ('employee_id', '=', employee.id),
            ('date', '=', server_today)
        ], limit=1)
        if existing_today:
            if client_uuid and existing_today.client_uuid == client_uuid:
                return existing_today
            raise UserError(_("Attendance has already been recorded for today (%s). You can only submit attendance once per calendar date.") % server_today)

        # Coordinate extraction & validation
        try:
            lat = float(vals.get('latitude'))
            lon = float(vals.get('longitude'))
            acc = float(vals.get('accuracy', 10.0))
        except (TypeError, ValueError):
            raise ValidationError(_("Valid GPS coordinates (latitude, longitude, accuracy) are required."))

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            raise ValidationError(_("Invalid GPS coordinates out of allowable range."))
        if acc <= 0.0:
            raise ValidationError(_("Accuracy must be a positive value in meters."))

        # Snapshots
        emp_name = employee.name
        job_title = employee.job_id.name if employee.job_id else ''
        territory_id = employee.user_id.territory_id.id if hasattr(employee.user_id, 'territory_id') and employee.user_id.territory_id else False

        attendance_vals = {
            'employee_id': employee.id,
            'date': server_today,
            'reporting_time': fields.Datetime.now(),
            'name': emp_name,
            'designation': job_title,
            'territory_id': territory_id,
            'latitude': lat,
            'longitude': lon,
            'accuracy': acc,
            'mode_of_journey': (vals.get('mode_of_journey') or '').strip(),
            'client_uuid': client_uuid or False,
            'state': 'submitted',
        }

        # Concurrency safe insertion handling PostgreSQL IntegrityError
        try:
            with self.env.cr.savepoint():
                attendance = self.sudo().create(attendance_vals)
                self.env['ffm.audit.log'].log_action(
                    model_name='ffm.attendance',
                    res_id=attendance.id,
                    action='create',
                    new_values={
                        'employee': emp_name,
                        'date': str(server_today),
                        'lat': lat,
                        'lon': lon,
                        'accuracy': acc,
                    },
                    res_name=f"{emp_name} - {server_today}"
                )
                return attendance
        except (psycopg2.IntegrityError, Exception) as exc:
            _logger.warning("Concurrency conflict or constraint caught during attendance submit: %s", exc)
            # Re-fetch already created record to guarantee idempotency
            existing = self.sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', server_today)
            ], limit=1)
            if existing:
                return existing
            raise

    def write(self, vals):
        if not self.env.is_admin() and not self.env.user.has_group('field_force_management.group_ffm_admin'):
            raise UserError(_("Attendance records are permanently locked after submission and cannot be edited."))
        return super(FFMAttendance, self).write(vals)

    def unlink(self):
        if not self.env.is_admin() and not self.env.user.has_group('field_force_management.group_ffm_admin'):
            raise UserError(_("Attendance records cannot be deleted."))
        return super(FFMAttendance, self).unlink()

    def init(self):
        cr = self.env.cr
        cr.execute("""
            CREATE INDEX IF NOT EXISTS ffm_attendance_emp_date_idx ON ffm_attendance (employee_id, date);
            CREATE INDEX IF NOT EXISTS ffm_attendance_date_idx ON ffm_attendance (date);
            CREATE INDEX IF NOT EXISTS ffm_attendance_territory_idx ON ffm_attendance (territory_id);
            CREATE INDEX IF NOT EXISTS ffm_attendance_client_uuid_idx ON ffm_attendance (client_uuid);
        """)
