# -*- coding: utf-8 -*-
import base64
from datetime import datetime
import pytz

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _validate_image_bytes(binary_data, field_label):
    """Validate that binary data is a valid image (JPEG, PNG, WebP) within size limit."""
    if not binary_data:
        return
    try:
        raw_bytes = base64.b64decode(binary_data)
    except Exception:
        raise ValidationError(_('%s: Invalid binary encoding.') % field_label)

    if len(raw_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            _('%s: File size (%0.2f MB) exceeds the maximum allowed limit of 5 MB.')
            % (field_label, len(raw_bytes) / (1024 * 1024))
        )

    # Magic byte verification
    is_jpeg = raw_bytes.startswith(b'\xff\xd8\xff')
    is_png = raw_bytes.startswith(b'\x89PNG\r\n\x1a\n')
    is_webp = raw_bytes[:4] == b'RIFF' and len(raw_bytes) > 12 and raw_bytes[8:12] == b'WEBP'

    if not (is_jpeg or is_png or is_webp):
        raise ValidationError(
            _('%s: Only valid image files (JPEG, PNG, WebP) are allowed as voucher attachments.')
            % field_label
        )


class FFMDailyExpense(models.Model):
    _name = 'ffm.daily.expense'
    _inherit = ['ffm.live.location.mixin']
    _description = 'Daily Field Expense'
    _order = 'date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        required=True, index=True,
        default=lambda self: self._default_employee())
    date = fields.Date(
        string='Date', required=True,
        index=True, default=lambda self: self._default_date())
    daily_report_id = fields.Many2one(
        'ffm.daily.report', string='Daily Report',
        index=True, ondelete='set null')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)

    # ── Expense Categories (Tk) ──────────────────────────────────────────────
    entertainment = fields.Float(string='Entertainment (Tk)', default=0.0, digits=(16, 2))
    courier = fields.Float(string='Courier (Tk)', default=0.0, digits=(16, 2))
    photocopy = fields.Float(string='Photocopy (Tk)', default=0.0, digits=(16, 2))
    promotion = fields.Float(string='Promotion (Tk)', default=0.0, digits=(16, 2))
    stationery = fields.Float(string='Stationery (Tk)', default=0.0, digits=(16, 2))
    carrying = fields.Float(string='Carrying (Tk)', default=0.0, digits=(16, 2))
    banking = fields.Float(string='Banking (Tk)', default=0.0, digits=(16, 2))
    hotel_rent = fields.Float(string='Hotel Rent (Tk)', default=0.0, digits=(16, 2))
    bike = fields.Float(string='Bike Maintenance (Tk)', default=0.0, digits=(16, 2))

    total_amount = fields.Float(
        string='Total Expense (Tk)',
        compute='_compute_total_amount', store=True, digits=(16, 2))

    note = fields.Text(string='Note / Remarks')
    client_uuid = fields.Char(string='Client UUID', index=True)

    # ── Voucher Attachments (Stored in ir.attachment via attachment=True) ──
    voucher_entertainment = fields.Binary(string='Entertainment Voucher', attachment=True)
    voucher_entertainment_filename = fields.Char(string='Entertainment Voucher Filename')

    voucher_courier = fields.Binary(string='Courier Voucher', attachment=True)
    voucher_courier_filename = fields.Char(string='Courier Voucher Filename')

    voucher_photocopy = fields.Binary(string='Photocopy Voucher', attachment=True)
    voucher_photocopy_filename = fields.Char(string='Photocopy Voucher Filename')

    voucher_hotel_rent = fields.Binary(string='Hotel Rent Voucher', attachment=True)
    voucher_hotel_rent_filename = fields.Char(string='Hotel Rent Voucher Filename')

    _sql_constraints = [
        ('unique_client_uuid', 'unique(client_uuid)', 'An expense with this UUID has already been submitted!'),
    ]

    def _default_employee(self):
        user = self.env.user
        return user.employee_id or self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)

    @api.model
    def _default_date(self):
        tz = pytz.timezone('Asia/Dhaka')
        return datetime.now(tz).date()

    @api.depends('entertainment', 'courier', 'photocopy', 'promotion',
                 'stationery', 'carrying', 'banking', 'hotel_rent', 'bike')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = (
                (rec.entertainment or 0.0)
                + (rec.courier or 0.0)
                + (rec.photocopy or 0.0)
                + (rec.promotion or 0.0)
                + (rec.stationery or 0.0)
                + (rec.carrying or 0.0)
                + (rec.banking or 0.0)
                + (rec.hotel_rent or 0.0)
                + (rec.bike or 0.0)
            )

    @api.constrains('entertainment', 'courier', 'photocopy', 'promotion',
                    'stationery', 'carrying', 'banking', 'hotel_rent', 'bike')
    def _check_expense_amounts(self):
        for rec in self:
            amounts = [
                rec.entertainment, rec.courier, rec.photocopy, rec.promotion,
                rec.stationery, rec.carrying, rec.banking, rec.hotel_rent, rec.bike
            ]
            if any(val < 0 for val in amounts):
                raise ValidationError(_('Expense amounts cannot be negative.'))
            if sum(amounts) <= 0:
                raise ValidationError(_('At least one expense amount greater than zero is required.'))

    @api.constrains('entertainment', 'courier', 'photocopy', 'hotel_rent',
                    'voucher_entertainment', 'voucher_courier',
                    'voucher_photocopy', 'voucher_hotel_rent')
    def _check_voucher_requirements(self):
        for rec in self:
            if rec.voucher_entertainment:
                _validate_image_bytes(rec.voucher_entertainment, _('Entertainment Voucher'))

            if rec.voucher_courier:
                _validate_image_bytes(rec.voucher_courier, _('Courier Voucher'))

            if rec.voucher_photocopy:
                _validate_image_bytes(rec.voucher_photocopy, _('Photocopy Voucher'))

            if rec.voucher_hotel_rent:
                _validate_image_bytes(rec.voucher_hotel_rent, _('Hotel Rent Voucher'))

    @api.model
    def create(self, vals):
        # Auto-link today's daily report if available and not set
        if not vals.get('daily_report_id') and vals.get('employee_id'):
            date_val = vals.get('date') or self._default_date()
            report = self.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', vals['employee_id']),
                ('date', '=', date_val)
            ], limit=1)
            if report:
                vals['daily_report_id'] = report.id
        return super().create(vals)

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ffm_daily_expense_emp_date_idx ON ffm_daily_expense (employee_id, date);
            CREATE INDEX IF NOT EXISTS ffm_daily_expense_date_idx ON ffm_daily_expense (date);
            CREATE INDEX IF NOT EXISTS ffm_daily_expense_client_uuid_idx ON ffm_daily_expense (client_uuid);
            CREATE INDEX IF NOT EXISTS ffm_daily_expense_report_id_idx ON ffm_daily_expense (daily_report_id);
        """)
