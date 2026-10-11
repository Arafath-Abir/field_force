# -*- coding: utf-8 -*-
from odoo import models, fields

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    branch_id = fields.Many2one('aam.branch', string='Branch')
