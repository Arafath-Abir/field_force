# -*- coding: utf-8 -*-
from datetime import datetime
import pytz

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class DailyReport(models.Model):
    _inherit = 'ffm.daily.report'

    working_place_id = fields.Many2one(
        'ffm.place', string='Working Place (Thana/Area)', index=True)
    farm_visit_ids = fields.One2many(
        'ffm.farm.visit', 'report_id', string='Farm Visits')
    total_farm_visited = fields.Integer(
        string='Farms Visited', compute='_compute_farm_totals', store=True)
    expense_ids = fields.One2many(
        'ffm.daily.expense', 'daily_report_id', string='Daily Expenses')
    total_expense_tk = fields.Float(
        string='Total Daily Expense (Tk)', compute='_compute_expense_totals', store=True)

    @api.depends('farm_visit_ids.farm_name')
    def _compute_farm_totals(self):
        for rec in self:
            rec.total_farm_visited = len(rec.farm_visit_ids.filtered(lambda f: bool(f.farm_name)))

    @api.depends('expense_ids.total_amount')
    def _compute_expense_totals(self):
        for rec in self:
            rec.total_expense_tk = sum(rec.expense_ids.mapped('total_amount'))

    attendance_record = fields.Many2one(
        'ffm.attendance', string='Day Attendance', compute='_compute_attendance_record')

    def _compute_attendance_record(self):
        for rec in self:
            rec.attendance_record = self.env['ffm.attendance'].sudo().search([
                ('employee_id', '=', rec.employee_id.id),
                ('date', '=', rec.date)
            ], limit=1)

    def get_live_chemist_totals(self):
        self.ensure_one()
        lines = self.chemist_visit_ids
        sum_order = sum(lines.mapped('order_tk'))
        sum_sale = sum(lines.mapped('sale_tk'))
        sum_coll = sum(lines.mapped('coll_tk'))
        return {
            'order': sum_order if sum_order > 0 else self.total_order_tk,
            'sale': sum_sale if sum_sale > 0 else self.total_sale_tk,
            'coll': sum_coll if sum_coll > 0 else self.total_coll_tk,
            'count': len(lines),
        }

    def get_live_journey_totals(self):
        self.ensure_one()
        legs = self.travel_log_ids.mapped('journey_ids')
        sum_dist = sum(legs.mapped('distance_km'))
        sum_fare = sum(legs.mapped('fare_tk'))
        log_fare = sum(self.travel_log_ids.mapped('total_fare_tk'))
        log_dist = sum(self.travel_log_ids.mapped('total_distance_km'))
        return {
            'distance': sum_dist if sum_dist > 0 else log_dist,
            'fare': sum_fare if sum_fare > 0 else log_fare,
            'legs_count': len(legs),
        }

    def get_live_expense_total(self):
        self.ensure_one()
        sum_exp = sum(self.expense_ids.mapped('total_amount'))
        return sum_exp if sum_exp > 0 else self.total_expense_tk

    @classmethod
    def get_dhaka_today(cls):
        tz = pytz.timezone('Asia/Dhaka')
        return datetime.now(tz).date()

    @api.model
    def get_or_create_today_report(self, employee_id=None, working_place_id=None):
        """Get or create today's daily report in Asia/Dhaka timezone.
        Ensures a linked ffm.travel.log is also ready.
        """
        user = self.env.user
        employee = False
        if employee_id:
            employee = self.env['hr.employee'].sudo().browse(employee_id)
        if not employee:
            employee = user.employee_id or self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)

        if not employee:
            raise UserError(_("No employee record found for current user."))

        today = self.get_dhaka_today()

        # Search existing report
        report = self.sudo().search([
            ('employee_id', '=', employee.id),
            ('date', '=', today)
        ], limit=1)

        if not report:
            vals = {
                'employee_id': employee.id,
                'date': today,
                'state': 'draft',
            }
            if working_place_id:
                vals['working_place_id'] = working_place_id
                # Also fill legacy working_place char
                place = self.env['ffm.place'].sudo().browse(working_place_id)
                if place:
                    vals['working_place'] = place.name
            report = self.sudo().create(vals)
        elif working_place_id and not report.working_place_id:
            place = self.env['ffm.place'].sudo().browse(working_place_id)
            report.sudo().write({
                'working_place_id': working_place_id,
                'working_place': place.name if place else report.working_place,
            })

        # Ensure travel log exists
        if not report.travel_log_ids:
            self.env['ffm.travel.log'].sudo().create({
                'daily_report_id': report.id,
                'employee_id': employee.id,
                'date': today,
            })

        return report


class ChemistVisit(models.Model):
    _name = 'ffm.chemist.visit'
    _inherit = ['ffm.chemist.visit', 'ffm.live.location.mixin']

    client_uuid = fields.Char(string='Client UUID', index=True)

    _sql_constraints = [
        ('unique_client_uuid', 'unique(client_uuid)', 'Chemist visit with this UUID has already been submitted!'),
    ]

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ffm_chemist_visit_client_uuid_idx ON ffm_chemist_visit (client_uuid);
        """)


class PrescriberVisit(models.Model):
    _name = 'ffm.prescriber.visit'
    _inherit = ['ffm.prescriber.visit', 'ffm.live.location.mixin']

    client_uuid = fields.Char(string='Client UUID', index=True)
    mobile = fields.Char(string='Mail / Mobile')

    _sql_constraints = [
        ('unique_client_uuid', 'unique(client_uuid)', 'Doctor visit with this UUID has already been submitted!'),
    ]

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ffm_prescriber_visit_client_uuid_idx ON ffm_prescriber_visit (client_uuid);
        """)


class TravelJourney(models.Model):
    _inherit = 'ffm.travel.journey'

    chemist_visit_id = fields.Many2one(
        'ffm.chemist.visit', string='Chemist Visit', index=True, ondelete='set null')
    prescriber_visit_id = fields.Many2one(
        'ffm.prescriber.visit', string='Doctor Visit', index=True, ondelete='set null')
    farm_visit_id = fields.Many2one(
        'ffm.farm.visit', string='Farm Visit', index=True, ondelete='set null')
    client_uuid = fields.Char(string='Client UUID', index=True)
    other_mode = fields.Char(string='Other Transport Mode')

    _sql_constraints = [
        ('unique_client_uuid', 'unique(client_uuid)', 'Journey leg with this UUID has already been submitted!'),
    ]

    def _recalc(self, force=False):
        # Field forms no longer collect From/To places or distance: the T.A. bill
        # entered by the user is final, so skip the route and fare lookup.
        if self.env.context.get('ffm_manual_fare'):
            return
        return super()._recalc(force=force)

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ffm_travel_journey_chemist_visit_idx ON ffm_travel_journey (chemist_visit_id);
            CREATE INDEX IF NOT EXISTS ffm_travel_journey_prescriber_visit_idx ON ffm_travel_journey (prescriber_visit_id);
            CREATE INDEX IF NOT EXISTS ffm_travel_journey_farm_visit_idx ON ffm_travel_journey (farm_visit_id);
            CREATE INDEX IF NOT EXISTS ffm_travel_journey_client_uuid_idx ON ffm_travel_journey (client_uuid);
        """)
