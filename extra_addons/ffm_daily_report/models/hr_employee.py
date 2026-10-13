# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    hq = fields.Char(string='Headquarter / Base Station', help='Headquarter location, e.g. Dhaka, Bogura, Rajshahi')
    ffm_phone = fields.Char(string='Field Force Phone', help='Primary contact mobile for field activities')

    def _get_target_ffm_group_xmlid(self):
        self.ensure_one()
        job_name = (self.job_id.name or '').upper()
        if 'DIRECTOR' in job_name:
            return 'field_force_management.group_ffm_director'
        if 'NSM' in job_name or 'NATIONAL' in job_name or 'MARKETING MANAGER' in job_name:
            return 'field_force_management.group_ffm_nsm'
        if 'DSM' in job_name or 'DIVISION' in job_name:
            return 'field_force_management.group_ffm_dsm'
        if 'RSM' in job_name or 'REGION' in job_name:
            return 'field_force_management.group_ffm_rsm'
        if 'ASM' in job_name or 'AREA' in job_name:
            return 'field_force_management.group_ffm_asm'
        return 'field_force_management.group_ffm_field_person'

    def action_create_or_link_user(self):
        """Helper action to create or properly link an FFM user account with the correct security role."""
        self.ensure_one()
        if not self.env.user.has_group('field_force_management.group_ffm_admin'):
            raise AccessError(_("Only System Administrators can manage FFM user accounts."))
        group_xmlid = self._get_target_ffm_group_xmlid()
        target_group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not target_group:
            raise UserError(_("Security group %s not found in system.") % group_xmlid)

        user = self.user_id
        if not user:
            # Generate clean login name
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '', (self.name or 'user').lower().replace(' ', '_'))
            login = self.work_email or f"{clean_name}_{self.id}@ffm.local"
            
            # Check if login already exists
            existing_user = self.env['res.users'].sudo().search([('login', '=', login)], limit=1)
            if existing_user:
                user = existing_user
                self.sudo().write({'user_id': user.id})
            else:
                user_vals = {
                    'name': self.name,
                    'login': login,
                    'email': self.work_email or login,
                    'groups_id': [(6, 0, [
                        self.env.ref('base.group_user').id,
                        target_group.id,
                    ])],
                }
                if hasattr(self, 'branch_id') and self.branch_id:
                    user_vals['branch_id'] = self.branch_id.id
                user = self.env['res.users'].sudo().create(user_vals)
                self.sudo().write({'user_id': user.id})

        # Ensure user has target group
        if target_group.id not in user.groups_id.ids:
            user.sudo().write({'groups_id': [(4, target_group.id)]})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("User Account Synchronized"),
                'message': _("Employee %s is now linked to user '%s' with role '%s'.") % (
                    self.name, user.login, target_group.name
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_open_change_password_wizard(self):
        self.ensure_one()
        if not self.env.user.has_group('field_force_management.group_ffm_admin'):
            raise AccessError(_("Only System Administrators can set or reset passwords."))
        if not self.user_id:
            self.action_create_or_link_user()
        return {
            'name': _('Set / Reset User Password'),
            'type': 'ir.actions.act_window',
            'res_model': 'ffm.change.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_id': self.id,
                'default_user_id': self.user_id.id if self.user_id else False,
            }
        }


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    branch_id = fields.Many2one('aam.branch', string='Branch')
    hq = fields.Char(string='Headquarter / Base Station')
    ffm_phone = fields.Char(string='Field Force Phone')
