from odoo import models, fields

class CustomerInformation(models.Model):
    _name = 'customer.information'
    _description = 'Customer Information'

    name = fields.Char(string='Name', required=True)
    type = fields.Selection([
        ('chemist', 'Chemist'),
        ('doctor', 'Doctor / Prescriber'),
        ('institution', 'Institution'),
        ('other', 'Other'),
    ], string='Type', default='chemist')
    mobile = fields.Char(string='Mobile')
    address = fields.Text(string='Address')
    field_person_id = fields.Many2one('hr.employee', string='Field Person')
    territory = fields.Char(string='Territory')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string='State', default='draft')
    active = fields.Boolean(default=True)

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS customer_info_type_idx ON customer_information (type);
            CREATE INDEX IF NOT EXISTS customer_info_field_person_idx ON customer_information (field_person_id);
            CREATE INDEX IF NOT EXISTS customer_info_state_idx ON customer_information (state);
            CREATE INDEX IF NOT EXISTS customer_info_active_idx ON customer_information (active);
        """)

