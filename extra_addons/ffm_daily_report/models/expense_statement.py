# -*- coding: utf-8 -*-
import calendar
from datetime import date, datetime
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class FFMExpenseStatement(models.Model):
    _name = 'ffm.expense.statement'
    _description = 'Monthly Expense Statement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, employee_id asc'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        required=True, index=True, tracking=True,
        default=lambda self: self._default_employee())
    user_id = fields.Many2one(
        'res.users', string='Related User',
        related='employee_id.user_id', store=True, index=True)
    job_id = fields.Many2one(
        'hr.job', string='Designation',
        related='employee_id.job_id', store=True)
    branch_id = fields.Many2one(
        'aam.branch', string='Branch / HQ',
        related='employee_id.branch_id', store=True)
    territory_id = fields.Many2one(
        'territory.territory', string='Territory',
        compute='_compute_territory', store=True)

    month = fields.Selection([
        ('01', 'January (জানুয়ারি)'),
        ('02', 'February (ফেব্রুয়ারি)'),
        ('03', 'March (মার্চ)'),
        ('04', 'April (এপ্রিল)'),
        ('05', 'May (মে)'),
        ('06', 'June (জুন)'),
        ('07', 'July (জুলাই)'),
        ('08', 'August (আগস্ট)'),
        ('09', 'September (সেপ্টেম্বর)'),
        ('10', 'October (অক্টোবর)'),
        ('11', 'November (নভেম্বর)'),
        ('12', 'December (ডিসেম্বর)'),
    ], string='Month', required=True, default=lambda self: self._default_month(), tracking=True)

    year = fields.Integer(
        string='Year', required=True,
        default=lambda self: date.today().year, tracking=True)

    name = fields.Char(string='Statement Reference', compute='_compute_name', store=True)
    date_from = fields.Date(string='Period From', compute='_compute_dates', store=True)
    date_to = fields.Date(string='Period To', compute='_compute_dates', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('checked', 'Checked'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)

    # ── Daily Breakdown Lines ───────────────────────────────────────────────
    line_ids = fields.One2many(
        'ffm.expense.statement.line', 'statement_id',
        string='Daily Allowance & Travel Lines')

    total_daily_ta = fields.Float(
        string='Total T.A. (Tk)', compute='_compute_totals', store=True, digits=(16, 2))
    total_daily_da = fields.Float(
        string='Total D.A. (Tk)', compute='_compute_totals', store=True, digits=(16, 2))
    total_daily_table = fields.Float(
        string='Daily Table Total (Tk)', compute='_compute_totals', store=True, digits=(16, 2))

    # ── Other Expenses (Vouchers 1 to 9) ────────────────────────────────────
    other_entertainment = fields.Float(string='1. Entertainment (Tk)', default=0.0, digits=(16, 2))
    other_courier = fields.Float(string='2. Postage / Courier (Tk)', default=0.0, digits=(16, 2))
    other_photocopy = fields.Float(string='3. Photocopy (Tk)', default=0.0, digits=(16, 2))
    other_promotion = fields.Float(string='4. Promotion (Tk)', default=0.0, digits=(16, 2))
    other_stationery = fields.Float(string='5. Stationery (Tk)', default=0.0, digits=(16, 2))
    other_carrying = fields.Float(string='6. Carrying Charge (Tk)', default=0.0, digits=(16, 2))
    other_banking = fields.Float(string='7. Banking Charge (Tk)', default=0.0, digits=(16, 2))
    other_hotel_rent = fields.Float(string='8. Hotel Rent (Tk)', default=0.0, digits=(16, 2))
    motorcycle_maintenance = fields.Float(string='9. Motorcycle Maintenance (Tk)', default=0.0, digits=(16, 2))

    total_other_expenses = fields.Float(
        string='Total Other Expenses (Tk)', compute='_compute_totals', store=True, digits=(16, 2))
    grand_total = fields.Float(
        string='Grand Total Expenses (Tk)', compute='_compute_totals', store=True, digits=(16, 2))

    remarks = fields.Text(string='Employee Remarks / Comments')
    rejection_reason = fields.Text(string='Rejection Reason', readonly=True)

    # ── Audit Signatures ────────────────────────────────────────────────────
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True)
    submitted_date = fields.Datetime(string='Submission Time', readonly=True)

    checked_by = fields.Many2one('res.users', string='Checked By', readonly=True)
    checked_date = fields.Datetime(string='Check Time', readonly=True)

    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Datetime(string='Approval Time', readonly=True)

    paid_by = fields.Many2one('res.users', string='Paid By', readonly=True)
    paid_date = fields.Datetime(string='Payment Time', readonly=True)

    _sql_constraints = [
        ('unique_employee_month_year',
         'unique(employee_id, month, year)',
         'A monthly expense statement already exists for this employee for the selected month and year!'),
    ]

    def _default_employee(self):
        user = self.env.user
        return user.employee_id or self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)

    @api.model
    def _default_month(self):
        return f"{date.today().month:02d}"

    @api.depends('employee_id')
    def _compute_territory(self):
        for rec in self:
            if rec.employee_id:
                t = self.env['territory.territory'].search([
                    '|', ('field_person_id', '=', rec.employee_id.id),
                    ('manager_id', '=', rec.employee_id.id)
                ], limit=1)
                rec.territory_id = t.id if t else False
            else:
                rec.territory_id = False

    @api.depends('employee_id', 'month', 'year')
    def _compute_name(self):
        for rec in self:
            emp_name = rec.employee_id.name or 'Employee'
            m = rec.month or 'MM'
            y = rec.year or 2026
            rec.name = f"MES/{emp_name}/{y}-{m}"

    @api.depends('month', 'year')
    def _compute_dates(self):
        for rec in self:
            if rec.month and rec.year:
                m_int = int(rec.month)
                _, last_day = calendar.monthrange(rec.year, m_int)
                rec.date_from = date(rec.year, m_int, 1)
                rec.date_to = date(rec.year, m_int, last_day)
            else:
                rec.date_from = False
                rec.date_to = False

    @api.depends('line_ids.ta_amount', 'line_ids.da_amount', 'line_ids.day_total',
                 'other_entertainment', 'other_courier', 'other_photocopy',
                 'other_promotion', 'other_stationery', 'other_carrying',
                 'other_banking', 'other_hotel_rent', 'motorcycle_maintenance')
    def _compute_totals(self):
        for rec in self:
            rec.total_daily_ta = sum(rec.line_ids.mapped('ta_amount'))
            rec.total_daily_da = sum(rec.line_ids.mapped('da_amount'))
            rec.total_daily_table = sum(rec.line_ids.mapped('day_total'))

            rec.total_other_expenses = (
                (rec.other_entertainment or 0.0)
                + (rec.other_courier or 0.0)
                + (rec.other_photocopy or 0.0)
                + (rec.other_promotion or 0.0)
                + (rec.other_stationery or 0.0)
                + (rec.other_carrying or 0.0)
                + (rec.other_banking or 0.0)
                + (rec.other_hotel_rent or 0.0)
                + (rec.motorcycle_maintenance or 0.0)
            )
            rec.grand_total = rec.total_daily_table + rec.total_other_expenses

    # ── Workflow Actions ────────────────────────────────────────────────────
    def action_generate_or_refresh(self):
        """Populate or refresh the statement from daily reports, travel logs, allowance rate, and daily expenses."""
        for rec in self:
            if rec.state not in ('draft', 'rejected'):
                raise UserError(_("You can only generate or refresh statements in Draft or Rejected state."))

            # 1. Fetch allowance rate by designation
            rate = False
            if rec.employee_id.job_id:
                rate = self.env['ffm.allowance.rate'].sudo().search([
                    ('job_id', '=', rec.employee_id.job_id.id),
                    ('active', '=', True)
                ], limit=1)

            da_rate = rate.da_per_day if rate else 0.0
            motorcycle_maint = rate.motorcycle_maintenance_per_month if rate else 0.0

            # 2. Daily reports for this employee within the month
            reports = self.env['ffm.daily.report'].sudo().search([
                ('employee_id', '=', rec.employee_id.id),
                ('date', '>=', rec.date_from),
                ('date', '<=', rec.date_to),
            ], order='date asc')

            # Clear old lines
            rec.line_ids.unlink()

            lines_vals = []
            for rep in reports:
                # Travel fares
                t_fares = 0.0
                destinations = []
                for tl in rep.travel_log_ids:
                    t_fares += sum(tl.journey_ids.mapped('fare_tk'))
                    for j in tl.journey_ids:
                        if j.place_to_id and j.place_to_id.name not in destinations:
                            destinations.append(j.place_to_id.name)

                visited = []
                if rep.working_place_id:
                    visited.append(rep.working_place_id.name)
                visited.extend([d for d in destinations if d not in visited])
                visited_str = ", ".join(visited) if visited else "Regular Area"

                day_da = da_rate
                lines_vals.append((0, 0, {
                    'statement_id': rec.id,
                    'date': rep.date,
                    'daily_report_id': rep.id,
                    'visited_places': visited_str,
                    'ta_amount': t_fares,
                    'da_amount': day_da,
                    'day_total': t_fares + day_da,
                }))

            if lines_vals:
                rec.write({'line_ids': lines_vals})

            # 3. Sum other expenses from ffm.daily.expense
            expenses = self.env['ffm.daily.expense'].sudo().search([
                ('employee_id', '=', rec.employee_id.id),
                ('date', '>=', rec.date_from),
                ('date', '<=', rec.date_to),
            ])

            rec.write({
                'other_entertainment': sum(expenses.mapped('entertainment')),
                'other_courier': sum(expenses.mapped('courier')),
                'other_photocopy': sum(expenses.mapped('photocopy')),
                'other_promotion': sum(expenses.mapped('promotion')),
                'other_stationery': sum(expenses.mapped('stationery')),
                'other_carrying': sum(expenses.mapped('carrying')),
                'other_banking': sum(expenses.mapped('banking')),
                'other_hotel_rent': sum(expenses.mapped('hotel_rent')),
                'motorcycle_maintenance': motorcycle_maint,
            })

            self.env['ffm.audit.log'].log_action(
                model_name='ffm.expense.statement',
                res_id=rec.id,
                action='write',
                new_values={'refreshed_lines_count': len(lines_vals)},
                res_name=rec.name
            )

    def action_submit(self):
        """Submit the statement for superior checking."""
        for rec in self:
            if rec.state not in ('draft', 'rejected'):
                raise UserError(_("Only Draft or Rejected statements can be submitted."))
            if not rec.line_ids and rec.total_other_expenses <= 0:
                raise UserError(_("Cannot submit an empty statement. Please click 'Generate / Refresh' first."))

            rec.write({
                'state': 'submitted',
                'submitted_by': self.env.user.id,
                'submitted_date': fields.Datetime.now(),
                'rejection_reason': False,
            })
            self.env['ffm.audit.log'].log_action(
                model_name='ffm.expense.statement',
                res_id=rec.id,
                action='submit',
                res_name=rec.name
            )

    def action_check(self):
        """Direct superior (ASM, RSM, DSM, NSM) checks the statement."""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Only Submitted statements can be checked."))

            # Superior check
            user = self.env.user
            emp = rec.employee_id
            is_manager = False
            if emp.parent_id and emp.parent_id.user_id == user:
                is_manager = True
            elif (user.has_group('field_force_management.group_ffm_nsm') or
                  user.has_group('field_force_management.group_ffm_director') or
                  user.has_group('field_force_management.group_ffm_admin')):
                is_manager = True
            elif emp.parent_id and user.id in self.env['res.users'].search([('employee_id', 'child_of', user.employee_id.id)]).ids:
                is_manager = True

            if not is_manager and not emp.parent_id:
                # If employee has no superior, check can proceed or NSM
                is_manager = True

            if not is_manager:
                raise UserError(_("Only the direct supervisor or higher management can check this statement."))

            rec.write({
                'state': 'checked',
                'checked_by': self.env.user.id,
                'checked_date': fields.Datetime.now(),
            })
            self.env['ffm.audit.log'].log_action(
                model_name='ffm.expense.statement',
                res_id=rec.id,
                action='check',
                new_values={'step': 'checked'},
                res_name=rec.name
            )

    def action_approve(self):
        """NSM, MM, Director or Super Admin approves the statement."""
        for rec in self:
            if rec.state != 'checked':
                raise UserError(_("Only Checked statements can be approved."))

            user = self.env.user
            if not (user.has_group('field_force_management.group_ffm_nsm') or
                    user.has_group('field_force_management.group_ffm_director') or
                    user.has_group('field_force_management.group_ffm_admin')):
                raise UserError(_("Only NSM, Marketing Manager, Director or Super Admin can approve statements."))

            rec.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            self.env['ffm.audit.log'].log_action(
                model_name='ffm.expense.statement',
                res_id=rec.id,
                action='approve',
                new_values={'step': 'approved'},
                res_name=rec.name
            )

    def action_pay(self):
        """Accounts marks the statement as paid."""
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_("Only Approved statements can be marked as paid."))

            user = self.env.user
            if not (user.has_group('field_force_management.group_ffm_accounts') or
                    user.has_group('account.group_account_user') or
                    user.has_group('field_force_management.group_ffm_admin')):
                raise UserError(_("Only Accounts personnel can mark statements as paid."))

            rec.write({
                'state': 'paid',
                'paid_by': self.env.user.id,
                'paid_date': fields.Datetime.now(),
            })
            self.env['ffm.audit.log'].log_action(
                model_name='ffm.expense.statement',
                res_id=rec.id,
                action='pay',
                res_name=rec.name
            )

    def action_open_reject_wizard(self):
        """Open the reject wizard with mandatory reason."""
        self.ensure_one()
        return {
            'name': _('Reject Monthly Expense Statement'),
            'type': 'ir.actions.act_window',
            'res_model': 'ffm.expense.statement.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_statement_id': self.id,
            }
        }

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ffm_expense_statement_emp_period_idx ON ffm_expense_statement (employee_id, year, month);
            CREATE INDEX IF NOT EXISTS ffm_expense_statement_period_idx ON ffm_expense_statement (year, month);
            CREATE INDEX IF NOT EXISTS ffm_expense_statement_state_idx ON ffm_expense_statement (state);
            CREATE INDEX IF NOT EXISTS ffm_expense_statement_line_stmt_idx ON ffm_expense_statement_line (statement_id);
            CREATE INDEX IF NOT EXISTS ffm_expense_statement_line_date_idx ON ffm_expense_statement_line (date);
        """)


class FFMExpenseStatementLine(models.Model):
    _name = 'ffm.expense.statement.line'
    _description = 'Monthly Expense Statement Daily Line'
    _order = 'date asc, id asc'

    statement_id = fields.Many2one(
        'ffm.expense.statement', string='Statement',
        required=True, ondelete='cascade', index=True)
    date = fields.Date(string='Date', required=True, index=True)
    daily_report_id = fields.Many2one(
        'ffm.daily.report', string='Daily Report',
        ondelete='set null')
    visited_places = fields.Char(string='Visited Places', default='')
    ta_amount = fields.Float(string='T.A. (Tk)', default=0.0, digits=(16, 2))
    da_amount = fields.Float(string='D.A. (Tk)', default=0.0, digits=(16, 2))
    day_total = fields.Float(string='Day Total (Tk)', default=0.0, digits=(16, 2))
