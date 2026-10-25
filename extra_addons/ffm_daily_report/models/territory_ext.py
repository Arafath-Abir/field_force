# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TerritoryTerritory(models.Model):
    """A territory holds any number of RSMs, ASMs and Field Persons, and a person
    can belong to several territories (shared relation with hr.employee)."""
    _inherit = 'territory.territory'

    member_ids = fields.Many2many(
        'hr.employee', 'ffm_territory_member_rel', 'territory_id', 'employee_id',
        string='Assigned Personnel')
    rsm_ids = fields.Many2many('hr.employee', string='RSMs', compute='_compute_role_members')
    asm_ids = fields.Many2many('hr.employee', string='ASMs', compute='_compute_role_members')
    fp_ids = fields.Many2many('hr.employee', string='Field Persons', compute='_compute_role_members')

    @api.depends('member_ids', 'member_ids.ffm_role')
    def _compute_role_members(self):
        for rec in self:
            active = rec.member_ids.filtered('active')
            rec.rsm_ids = active.filtered(lambda e: e.ffm_role == 'rsm')
            rec.asm_ids = active.filtered(lambda e: e.ffm_role == 'asm')
            rec.fp_ids = active.filtered(lambda e: e.ffm_role == 'fp')

    def _sync_legacy_links(self):
        """Keep the single-value legacy fields (used by reports and statements) pointing
        at the first ASM/RSM and first Field Person of the member list."""
        for rec in self:
            manager = rec.asm_ids[:1] or rec.rsm_ids[:1]
            rec.sudo().write({
                'manager_id': manager.id or False,
                'field_person_id': rec.fp_ids[:1].id or False,
            })

    @api.model
    def _ffm_migrate_legacy_members(self):
        """Idempotent: refresh field force roles, then copy legacy manager / field person /
        user territory links into member_ids."""
        Emp = self.env['hr.employee'].sudo().with_context(active_test=False)
        self.env.add_to_compute(Emp._fields['ffm_role'], Emp.search([]))
        Emp.recompute()
        for rec in self.sudo().search([]):
            legacy = rec.manager_id | rec.field_person_id
            missing = legacy - rec.member_ids
            if missing:
                rec.write({'member_ids': [(4, emp.id) for emp in missing]})
        users = self.env['res.users'].sudo().with_context(active_test=False).search([('territory_id', '!=', False)])
        for user in users:
            emp = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            if emp and user.territory_id not in emp.ffm_territory_ids:
                emp.write({'ffm_territory_ids': [(4, user.territory_id.id)]})
        return True
