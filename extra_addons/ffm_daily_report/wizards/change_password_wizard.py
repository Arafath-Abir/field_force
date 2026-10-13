# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, AccessError

class FFMChangePasswordWizard(models.TransientModel):
    _name = 'ffm.change.password.wizard'
    _description = 'FFM Change & Reset Password Wizard'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    user_id = fields.Many2one('res.users', string='User Account', required=True)
    login = fields.Char(related='user_id.login', string='Login Username', readonly=True)
    user_name = fields.Char(related='user_id.name', string='Full Name', readonly=True)
    new_password = fields.Char(string='New Password', required=True)
    confirm_password = fields.Char(string='Confirm Password', required=True)
    send_email = fields.Boolean(
        string='Send Password Reset Email',
        default=False,
        help='If checked, will also trigger standard Odoo password reset email to user email address.')

    @api.model
    def default_get(self, fields_list):
        if not self.env.user.has_group('field_force_management.group_ffm_admin'):
            raise AccessError(_("Only System Administrators can set or reset passwords."))
        res = super(FFMChangePasswordWizard, self).default_get(fields_list)
        active_model = self._context.get('active_model')
        active_id = self._context.get('active_id')

        if active_model == 'hr.employee' and active_id:
            emp = self.env['hr.employee'].browse(active_id)
            if emp.exists():
                res['employee_id'] = emp.id
                if not emp.user_id:
                    emp.action_create_or_link_user()
                res['user_id'] = emp.user_id.id
        elif active_model == 'res.users' and active_id:
            user = self.env['res.users'].browse(active_id)
            if user.exists():
                res['user_id'] = user.id
                emp = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
                if emp:
                    res['employee_id'] = emp.id
        return res

    def action_apply_password(self):
        self.ensure_one()
        if not self.env.user.has_group('field_force_management.group_ffm_admin'):
            raise AccessError(_("Only System Administrators can set or reset passwords."))
        if not self.new_password:
            raise UserError(_("Please provide a new password."))
        if self.new_password != self.confirm_password:
            raise ValidationError(_("New password and confirm password do not match!"))
        if len(self.new_password) < 6:
            raise ValidationError(_("Password must be at least 6 characters long."))

        # Update password directly on res.users
        self.user_id.sudo().write({'password': self.new_password})

        # Audit Log
        if 'ffm.audit.log' in self.env:
            self.env['ffm.audit.log'].sudo().log_action(
                model_name='res.users',
                res_id=self.user_id.id,
                action='write',
                new_values={'login': self.user_id.login, 'reset_by': self.env.user.name, 'note': 'Password updated by admin'},
                res_name=self.user_id.name
            )

        # Send email if requested
        if self.send_email and self.user_id.email:
            try:
                self.user_id.sudo().action_reset_password()
            except Exception:
                pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Password Updated Successfully"),
                'message': _("Password for user '%s' (%s) has been updated successfully.") % (
                    self.user_id.name, self.user_id.login
                ),
                'type': 'success',
                'sticky': False,
            }
        }
