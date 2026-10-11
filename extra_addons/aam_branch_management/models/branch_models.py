from odoo import models, fields

class AamBranch(models.Model):
    _name = 'aam.branch'
    _description = 'Branch'

    name = fields.Char(string='Branch Name', required=True)
    code = fields.Char(string='Branch Code')

class TerritoryTerritory(models.Model):
    _name = 'territory.territory'
    _description = 'Territory'

    name = fields.Char(string='Territory Name', required=True)
    field_person_id = fields.Many2one('hr.employee', string='Field Person')
    manager_id = fields.Many2one('hr.employee', string='Manager / ASM')
    branch_id = fields.Many2one('aam.branch', string='Branch')

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    branch_id = fields.Many2one('aam.branch', string='Branch')

class ResUsers(models.Model):
    _inherit = 'res.users'

    branch_id = fields.Many2one('aam.branch', string='Branch')
    territory_id = fields.Many2one('territory.territory', string='Territory')
