from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class DailyReport(models.Model):
    _name = 'ffm.daily.report'
    _description = 'Daily Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    # ── Header ──────────────────────────────────────────────────────────────
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        default=lambda self: self._default_employee(),
        required=True, tracking=False,
    )
    name = fields.Char(
        string='Name', related='employee_id.name', store=True, readonly=True)
    designation = fields.Char(
        string='Designation', related='employee_id.job_title',
        store=True, readonly=True)
    territory_id = fields.Many2one(
        'territory.territory', string='Territory',
        compute='_compute_employee_info', store=True, readonly=False)
    working_place = fields.Char(string='Working Place')
    date = fields.Date(
        string='Date', required=True,
        default=fields.Date.today, tracking=False)
    branch_id = fields.Many2one(
        'aam.branch', string='Branch',
        related='employee_id.branch_id', store=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=False)

    display_name = fields.Char(
        string='Report', compute='_compute_display_name', store=True)

    # ── Chemist Visit Lines ──────────────────────────────────────────────────
    chemist_visit_ids = fields.One2many(
        'ffm.chemist.visit', 'report_id', string='Chemist Visits')

    # ── Prescriber / Doctor Visit Lines ─────────────────────────────────────
    prescriber_visit_ids = fields.One2many(
        'ffm.prescriber.visit', 'report_id', string='Prescriber Visits')

    # ── Summary (computed) ──────────────────────────────────────────────────
    total_order_tk = fields.Float(
        string='Total Order (Tk)', compute='_compute_chemist_totals', store=True)
    total_sale_tk = fields.Float(
        string='Total Sale (Tk)', compute='_compute_chemist_totals', store=True)
    total_coll_tk = fields.Float(
        string='Total Collection (Tk)', compute='_compute_chemist_totals', store=True)
    total_chemist_visited = fields.Integer(
        string='Chemists Visited', compute='_compute_chemist_totals', store=True)
    total_prescriber_visited = fields.Integer(
        string='Prescribers Visited', compute='_compute_prescriber_totals', store=True)

    # ── Notes ───────────────────────────────────────────────────────────────
    note = fields.Text(string='Remarks')

    # ── Defaults / Computes ─────────────────────────────────────────────────
    def _default_employee(self):
        return self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1)

    @api.depends('employee_id')
    def _compute_employee_info(self):
        for rec in self:
            if rec.employee_id:
                # 1. Try territory from res.users directly (set in aam_branch_management)
                user = rec.employee_id.user_id
                if user and user.territory_id:
                    rec.territory_id = user.territory_id.id
                else:
                    # 2. Try as field person
                    territory = self.env['territory.territory'].search(
                        [('field_person_id', '=', rec.employee_id.id)], limit=1)
                    if territory:
                        rec.territory_id = territory.id
                    else:
                        # 3. Try as ASM (manager_id)
                        territory = self.env['territory.territory'].search(
                            [('manager_id', '=', rec.employee_id.id)], limit=1)
                        rec.territory_id = territory.id if territory else False
            else:
                rec.territory_id = False

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Autofill working_place from branch when employee changes."""
        if self.employee_id and self.employee_id.branch_id:
            self.working_place = self.employee_id.branch_id.name

    @api.depends('employee_id', 'date')
    def _compute_display_name(self):
        for rec in self:
            emp = rec.employee_id.name or ''
            dt = str(rec.date) if rec.date else ''
            rec.display_name = f"{emp} / {dt}" if emp or dt else 'New Report'

    @api.depends('chemist_visit_ids.order_tk',
                 'chemist_visit_ids.sale_tk',
                 'chemist_visit_ids.coll_tk',
                 'chemist_visit_ids.chemist_id',
                 'chemist_visit_ids.chemist_name_manual')
    def _compute_chemist_totals(self):
        for rec in self:
            lines = rec.chemist_visit_ids
            rec.total_order_tk = sum(lines.mapped('order_tk'))
            rec.total_sale_tk = sum(lines.mapped('sale_tk'))
            rec.total_coll_tk = sum(lines.mapped('coll_tk'))
            rec.total_chemist_visited = len(
                lines.filtered(lambda l: l.chemist_id or l.chemist_name_manual))

    @api.depends('prescriber_visit_ids.prescriber_id',
                 'prescriber_visit_ids.prescriber_name_manual')
    def _compute_prescriber_totals(self):
        for rec in self:
            rec.total_prescriber_visited = len(
                rec.prescriber_visit_ids.filtered(lambda l: l.prescriber_id or l.prescriber_name_manual))

    # ── Constraints ─────────────────────────────────────────────────────────
    _sql_constraints = [
        ('unique_employee_date',
         'UNIQUE(employee_id, date)',
         'A daily report already exists for this employee on this date.'),
    ]

    # ── Actions ─────────────────────────────────────────────────────────────
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft reports can be submitted.'))
            rec.state = 'submitted'

    def _can_approve_or_reject(self):
        self.ensure_one()
        user = self.env.user
        higher_groups = [
            'field_force_management.group_ffm_rsm',
            'field_force_management.group_ffm_dsm',
            'field_force_management.group_ffm_nsm',
            'field_force_management.group_ffm_director',
            'field_force_management.group_ffm_admin',
            'base.group_system',
        ]
        for grp in higher_groups:
            try:
                if user.has_group(grp):
                    return True
            except Exception:
                pass
        manager_user = self.employee_id.parent_id.user_id
        if manager_user and manager_user == user:
            return True
        return False

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted reports can be approved.'))
            if not rec._can_approve_or_reject():
                raise UserError(_('Only the direct manager or a higher authority (RSM, DSM, NSM, Director, Admin) can approve this daily report.'))
            rec.state = 'approved'

    def action_reject(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted reports can be rejected.'))
            if not rec._can_approve_or_reject():
                raise UserError(_('Only the direct manager or a higher authority (RSM, DSM, NSM, Director, Admin) can reject this daily report.'))
            rec.state = 'rejected'

    def action_reset_draft(self):
        for rec in self:
            if not rec._can_approve_or_reject() and rec.employee_id.user_id != self.env.user:
                raise UserError(_('You do not have permission to reset this report to draft.'))
            rec.state = 'draft'


class ChemistVisit(models.Model):
    _name = 'ffm.chemist.visit'
    _description = 'Chemist / Pharmacy Visit Line'
    _order = 'sequence, id'

    report_id = fields.Many2one(
        'ffm.daily.report', string='Daily Report',
        required=True, ondelete='cascade')
    sequence = fields.Integer(string='#', default=10)

    chemist_id = fields.Many2one(
        'customer.information', string='Chemist Name',
    )
    chemist_name_manual = fields.Char(string='Manual Chemist Name')
    address = fields.Text(
        string='Address', related='chemist_id.address',
        readonly=True, store=False)

    order_tk = fields.Float(string='Order (Tk)', digits=(16, 2))
    sale_tk = fields.Float(string='Sale (Tk)', digits=(16, 2))
    coll_tk = fields.Float(string='Collection (Tk)', digits=(16, 2))

    note = fields.Char(string='Note')

    @api.constrains('chemist_id', 'chemist_name_manual')
    def _check_chemist_presence(self):
        for rec in self:
            if not rec.chemist_id and not (rec.chemist_name_manual and rec.chemist_name_manual.strip()):
                raise ValidationError(_('Either select a Chemist or provide a Manual Chemist Name.'))

    @api.constrains('order_tk', 'sale_tk', 'coll_tk')
    def _check_amounts(self):
        for rec in self:
            for val, label in [(rec.order_tk, _('Order')), (rec.sale_tk, _('Sale')), (rec.coll_tk, _('Collection'))]:
                if val < 0:
                    raise ValidationError(_('%s Tk cannot be negative.') % label)
                if not float(val).is_integer():
                    raise ValidationError(_('%s Tk must be a whole number.') % label)


class PrescriberVisit(models.Model):
    _name = 'ffm.prescriber.visit'
    _description = 'Prescriber / Doctor Visit Line'
    _order = 'sequence, id'

    report_id = fields.Many2one(
        'ffm.daily.report', string='Daily Report',
        required=True, ondelete='cascade')
    sequence = fields.Integer(string='#', default=10)

    prescriber_id = fields.Many2one(
        'customer.information', string="Prescriber's Name",
    )
    prescriber_name_manual = fields.Char(string='Manual Doctor / Prescriber Name')
    mailing_address = fields.Text(
        string='Mailing Address', related='prescriber_id.address',
        readonly=True, store=False)

    product_discussion = fields.Char(string='Product Discussion')
    sample = fields.Char(string='Sample / Gift')

    grade = fields.Selection([
        ('a_plus', 'A+'),
        ('a', 'A'),
        ('b', 'B'),
        ('c', 'C'),
    ], string='Grade')

    @api.constrains('prescriber_id', 'prescriber_name_manual')
    def _check_prescriber_presence(self):
        for rec in self:
            if not rec.prescriber_id and not (rec.prescriber_name_manual and rec.prescriber_name_manual.strip()):
                raise ValidationError(_('Either select a Doctor or provide a Manual Doctor Name.'))


# Injected by travel_log upgrade: back-relation to travel logs for this report
# (travel_log already has daily_report_id M2O → this gives O2M on daily report)
# We patch DailyReport here to avoid circular imports.
from odoo import models, fields as _fields

class DailyReportTravelLogExt(models.Model):
    _inherit = 'ffm.daily.report'

    travel_log_ids = _fields.One2many(
        'ffm.travel.log', 'daily_report_id', string='Travel Logs')

    travel_log_count = _fields.Integer(
        string='Travel Logs', compute='_compute_travel_log_count')

    def _compute_travel_log_count(self):
        for rec in self:
            rec.travel_log_count = len(rec.travel_log_ids)

    def action_open_travel_log(self):
        """Open/create travel log for today's report."""
        self.ensure_one()
        existing = self.travel_log_ids[:1]
        if existing:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'ffm.travel.log',
                'view_mode': 'form',
                'res_id': existing.id,
            }
        # Auto-create travel log pre-linked to this report
        log = self.env['ffm.travel.log'].create({
            'daily_report_id': self.id,
            'employee_id': self.employee_id.id,
            'date': self.date,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ffm.travel.log',
            'view_mode': 'form',
            'res_id': log.id,
        }
