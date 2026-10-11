from odoo import models, fields, api, _
from odoo.exceptions import UserError

TRANSPORT_MODES = [
    ('bus', 'Bus'),
    ('rickshaw', 'Rickshaw'),
    ('auto_cng', 'Auto / CNG'),
    ('motorcycle', 'Motorcycle'),
    ('uber_pathao', 'Uber / Pathao'),
    ('on_foot', 'On Foot'),
    ('train', 'Train'),
    ('launch', 'Launch / Ferry'),
    ('others', 'Others'),
]


class TravelLog(models.Model):
    _name = 'ffm.travel.log'
    _description = 'Travel Log'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    daily_report_id = fields.Many2one(
        'ffm.daily.report', string='Daily Report', ondelete='cascade')
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        default=lambda self: self._default_employee(), required=True)
    date = fields.Date(
        string='Date', required=True, default=fields.Date.today)
    territory_id = fields.Many2one(
        'territory.territory', string='Territory',
        related='daily_report_id.territory_id', store=True, readonly=True)
    journey_ids = fields.One2many(
        'ffm.travel.journey', 'travel_log_id', string='Journey Legs')
    total_distance_km = fields.Float(
        string='Total Distance (km)',
        compute='_compute_totals', store=True, digits=(16, 2))
    total_fare_tk = fields.Float(
        string='Total Fare (Tk)',
        compute='_compute_totals', store=True, digits=(16, 2))
    visited_places = fields.Char(
        string='Visited Places',
        compute='_compute_totals', store=True)

    # ── Workflow ──────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string='Status', default='draft', tracking=False)

    # ── Vendor Bill link ──────────────────────────────────────────────────
    vendor_bill_id = fields.Many2one(
        'account.move', string='Vendor Bill', readonly=True, copy=False)
    vendor_bill_state = fields.Char(
        string='Bill Status',
        compute='_compute_bill_state')

    def _default_employee(self):
        return self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1)

    @api.depends('journey_ids.distance_km', 'journey_ids.fare_tk',
                 'journey_ids.place_to_id')
    def _compute_totals(self):
        for rec in self:
            legs = rec.journey_ids
            rec.total_distance_km = sum(legs.mapped('distance_km'))
            rec.total_fare_tk = sum(legs.mapped('fare_tk'))
            places = [j.place_to_id.name for j in legs if j.place_to_id]
            rec.visited_places = ', '.join(places) if places else ''

    @api.depends('vendor_bill_id', 'vendor_bill_id.state')
    def _compute_bill_state(self):
        for rec in self:
            if rec.vendor_bill_id:
                rec.vendor_bill_state = dict(
                    rec.vendor_bill_id._fields['state'].selection
                ).get(rec.vendor_bill_id.state, rec.vendor_bill_id.state)
            else:
                rec.vendor_bill_state = False

    # ── Confirm & create vendor bill ──────────────────────────────────────


    def action_confirm(self):
        auto_bill_param = self.env['ir.config_parameter'].sudo().get_param(
            'field_force_management.travel_auto_bill', False
        )
        auto_bill = auto_bill_param in (True, 'True', 'true', '1', 1)
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft travel logs can be confirmed.'))
            if not rec.journey_ids:
                raise UserError(_('Add at least one journey leg before confirming.'))

            vals = {'state': 'confirmed'}
            if auto_bill:
                bill = rec._create_vendor_bill()
                vals['vendor_bill_id'] = bill.id
            rec.write(vals)

    def action_reset_draft(self):
        for rec in self:
            if rec.vendor_bill_id and rec.vendor_bill_id.state != 'cancel':
                raise UserError(_(
                    'Cancel the linked vendor bill first before resetting to draft.'))
            rec.state = 'draft'

    def action_open_vendor_bill(self):
        self.ensure_one()
        if not self.vendor_bill_id:
            raise UserError(_('No vendor bill linked yet.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.vendor_bill_id.id,
        }

    def _create_vendor_bill(self):
        self.ensure_one()
        # ── Get travel product from system param or IrConfig ──────────────
        travel_product = self._get_travel_product()

        # ── Partner: sudo to bypass hr.employee field restrictions ─────────
        employee_sudo = self.employee_id.sudo()
        partner = (employee_sudo.address_home_id
                   or employee_sudo.user_id.partner_id
                   or self.env.company.partner_id)

        # ── Build invoice lines ────────────────────────────────────────────
        lines = []

        if travel_product and self.total_fare_tk:
            lines.append((0, 0, {
                'product_id': travel_product.id,
                'name': _('Travel Allowance — %s (%s)') % (
                    self.date, self.visited_places or ''),
                'quantity': 1.0,
                'price_unit': self.total_fare_tk,
                'account_id': (
                    travel_product.property_account_expense_id.id
                    or travel_product.categ_id.property_account_expense_categ_id.id
                    or self._get_default_expense_account()),
            }))
        elif not travel_product:
            # No product configured — use generic line with expense account
            lines.append((0, 0, {
                'name': _('Travel Fare — %s (%s)') % (
                    self.date, self.visited_places or ''),
                'quantity': 1.0,
                'price_unit': self.total_fare_tk,
                'account_id': self._get_default_expense_account(),
            }))

        if not lines:
            raise UserError(_('Total fare is zero. Add journey legs with fare before confirming.'))

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'invoice_date': self.date,
            'ref': _('Travel Log — %s — %s') % (
                self.employee_id.name or '', self.date),
            'invoice_line_ids': lines,
            'narration': _('Auto-created from FFM Travel Log for %s on %s') % (
                self.employee_id.name or '', self.date),
        }
        return self.env['account.move'].sudo().create(bill_vals)

    def _get_travel_product(self):
        """Return configured travel service product, or False."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            'ffm.travel_product_id')
        if param:
            product = self.env['product.product'].browse(int(param))
            if product.exists():
                return product
        return False

    def _get_default_expense_account(self):
        """Fallback: first expense account in chart."""
        account = self.env['account.account'].sudo().search([
            ('user_type_id.type', '=', 'other'),
            ('user_type_id.name', 'ilike', 'expense'),
        ], limit=1)
        if not account:
            account = self.env['account.account'].sudo().search([
                ('user_type_id.internal_group', '=', 'expense'),
            ], limit=1)
        return account.id if account else False


class TravelJourney(models.Model):
    _name = 'ffm.travel.journey'
    _description = 'Journey Leg'
    _order = 'sequence, id'

    travel_log_id = fields.Many2one(
        'ffm.travel.log', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)

    place_from_id = fields.Many2one('ffm.place', string='From', required=True)
    place_to_id = fields.Many2one('ffm.place', string='To', required=True)

    mode = fields.Selection(TRANSPORT_MODES, string='Mode of Journey', required=True)
    distance_km = fields.Float(string='Distance (km)', digits=(16, 2), readonly=True)
    duration_minutes = fields.Float(
        string='Duration (min)', digits=(16, 2), readonly=True)
    fare_tk = fields.Float(string='Fare (Tk)', digits=(16, 2), readonly=True)
    route_info = fields.Char(string='Route Info', readonly=True)

    def _recalc(self):
        FareConfig = self.env['ffm.fare.config']
        for record in self:
            if record.place_from_id and record.place_to_id:
                if record.place_from_id == record.place_to_id:
                    record.distance_km = 0.0
                    record.duration_minutes = 0.0
                    record.fare_tk = 0.0
                    record.route_info = _('From and To locations must be different.')
                    continue

                route = record.place_from_id.compute_route_to(
                    record.place_to_id, mode=record.mode
                )
                distance = route.get('distance_km', 0.0)
                duration = route.get('duration_minutes', 0.0)
                fare = (
                    FareConfig.get_fare(record.mode, distance)
                    if record.mode and distance
                    else 0.0
                )
                record.distance_km = distance
                record.duration_minutes = duration
                record.fare_tk = fare

                source_label = (
                    _('Road route')
                    if route.get('source') == 'geoapify'
                    else _('Fallback distance')
                )
                record.route_info = (
                    '%s → %s · %.2f km · %.0f min · ৳%.0f · %s' % (
                        record.place_from_id.name,
                        record.place_to_id.name,
                        distance,
                        duration,
                        fare,
                        source_label,
                    )
                )
            else:
                record.distance_km = 0.0
                record.duration_minutes = 0.0
                record.fare_tk = 0.0
                record.route_info = False

    @api.onchange('place_from_id', 'place_to_id', 'mode')
    def _onchange_recalculate_route(self):
        """Show distance and fare immediately in the editable journey line."""
        self._recalc()

    def write(self, vals):
        res = super().write(vals)
        if {'place_from_id', 'place_to_id', 'mode'} & set(vals.keys()):
            self._recalc()
        return res

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._recalc()
        return rec
