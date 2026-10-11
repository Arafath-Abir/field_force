# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FFMFarmVisit(models.Model):
    _name = 'ffm.farm.visit'
    _description = 'Farm & Others Visit Line'
    _order = 'sequence, id'

    report_id = fields.Many2one(
        'ffm.daily.report', string='Daily Report',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='#', default=10)

    farm_name = fields.Char(string='Farm / Others Name', required=True)
    address = fields.Text(string='Address')
    
    # Livestock / Poultry details
    broiler = fields.Char(string='Broiler')
    layer = fields.Char(string='Layer')
    sonali = fields.Char(string='Sonali')
    cattle = fields.Char(string='Cattle')
    aqua = fields.Char(string='Aqua')
    bird_count = fields.Integer(string='No. of Birds / Cattle', default=0)

    note = fields.Text(string='Note / Discussion')
    client_uuid = fields.Char(string='Client UUID', index=True)

    _sql_constraints = [
        ('unique_client_uuid', 'unique(client_uuid)', 'A farm visit with this UUID has already been submitted!'),
    ]

    @api.constrains('bird_count')
    def _check_bird_count(self):
        for rec in self:
            if rec.bird_count < 0:
                raise ValidationError(_('Bird / cattle count cannot be negative.'))

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ffm_farm_visit_report_id_idx ON ffm_farm_visit (report_id);
            CREATE INDEX IF NOT EXISTS ffm_farm_visit_client_uuid_idx ON ffm_farm_visit (client_uuid);
        """)
