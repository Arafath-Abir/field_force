# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FFMAllowanceRate(models.Model):
    _name = 'ffm.allowance.rate'
    _description = 'FFM Allowance Rate by Designation'
    _order = 'job_id asc'

    job_id = fields.Many2one('hr.job', string='Designation', required=True, ondelete='restrict', index=True)
    da_per_day = fields.Float(string='Daily Allowance / Day (BDT)', required=True, default=0.0)
    motorcycle_maintenance_per_month = fields.Float(string='Motorcycle Maintenance / Month (BDT)', default=0.0)
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('unique_job_id', 'unique(job_id)', 'An allowance rate configuration already exists for this designation!'),
    ]

    @api.constrains('da_per_day', 'motorcycle_maintenance_per_month')
    def _check_rates_positive(self):
        for rec in self:
            if rec.da_per_day < 0.0:
                raise ValidationError(_("Daily Allowance per day cannot be negative."))
            if rec.motorcycle_maintenance_per_month < 0.0:
                raise ValidationError(_("Motorcycle maintenance allowance cannot be negative."))

    @api.model
    def create(self, vals):
        rec = super(FFMAllowanceRate, self).create(vals)
        audit_vals = {
            'job_id': rec.job_id.name,
            'da_per_day': rec.da_per_day,
            'motorcycle_maintenance_per_month': rec.motorcycle_maintenance_per_month,
            'active': rec.active,
        }
        self.env['ffm.audit.log'].log_action(
            model_name='ffm.allowance.rate',
            res_id=rec.id,
            action='create',
            new_values=audit_vals,
            res_name=rec.job_id.name
        )
        return rec

    def write(self, vals):
        old_values = {
            rec.id: {
                'job_id': rec.job_id.name,
                'da_per_day': rec.da_per_day,
                'motorcycle_maintenance_per_month': rec.motorcycle_maintenance_per_month,
                'active': rec.active,
            }
            for rec in self
        }
        res = super(FFMAllowanceRate, self).write(vals)
        for rec in self:
            self.env['ffm.audit.log'].log_action(
                model_name='ffm.allowance.rate',
                res_id=rec.id,
                action='write',
                old_values=old_values.get(rec.id),
                new_values=vals,
                res_name=rec.job_id.name
            )
        return res

    def unlink(self):
        for rec in self:
            self.env['ffm.audit.log'].log_action(
                model_name='ffm.allowance.rate',
                res_id=rec.id,
                action='unlink',
                old_values={'job_id': rec.job_id.name, 'da_per_day': rec.da_per_day},
                res_name=rec.job_id.name
            )
        return super(FFMAllowanceRate, self).unlink()
