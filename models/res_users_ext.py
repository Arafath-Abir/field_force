from odoo import models, fields, api


class ResUsersFFM(models.Model):
    """Convenience computed fields so views can read logged-in user's
    employee record, territory, designation and branch in one shot."""
    _inherit = 'res.users'

    # These already exist in aam_branch_management; we just add employee link
    employee_id = fields.Many2one(
        'hr.employee',
        string='Related Employee',
        compute='_compute_employee_id',
        store=False,
    )

    def _compute_employee_id(self):
        for user in self:
            emp = self.env['hr.employee'].search(
                [('user_id', '=', user.id)], limit=1)
            user.employee_id = emp.id
