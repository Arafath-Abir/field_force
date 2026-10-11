# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ffm_app_name = fields.Char(
        string='Marketer App Name',
        default='Newtec FFM',
        config_parameter='ffm.app_name',
        help='Display name shown in the /ff mobile application and PWA header.'
    )
    ffm_app_logo = fields.Binary(
        string='Marketer App Logo',
        help='Custom logo image displayed on the /ff header.'
    )
    ffm_app_icon = fields.Binary(
        string='Marketer PWA Icon',
        help='App icon for mobile home-screen install.'
    )
    ffm_routing_key_status = fields.Char(
        string='Routing Provider Key Status',
        compute='_compute_routing_key_status',
        readonly=True,
        help='Indicates whether routing provider key is present without exposing secret value.'
    )

    def _compute_routing_key_status(self):
        key = self.env['ir.config_parameter'].sudo().get_param('field_force_management.geoapify_api_key', default='').strip()
        status_text = 'Configured (Key Present)' if key else 'Not Configured (Missing)'
        for rec in self:
            rec.ffm_routing_key_status = status_text

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        param = self.env['ir.config_parameter'].sudo()
        if self.ffm_app_logo:
            param.set_param('ffm.app_logo', self.ffm_app_logo.decode('utf-8') if isinstance(self.ffm_app_logo, bytes) else self.ffm_app_logo)
        if self.ffm_app_icon:
            param.set_param('ffm.app_icon', self.ffm_app_icon.decode('utf-8') if isinstance(self.ffm_app_icon, bytes) else self.ffm_app_icon)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        param = self.env['ir.config_parameter'].sudo()
        logo = param.get_param('ffm.app_logo', default=False)
        icon = param.get_param('ffm.app_icon', default=False)
        res.update(
            ffm_app_logo=logo.encode('utf-8') if isinstance(logo, str) else logo,
            ffm_app_icon=icon.encode('utf-8') if isinstance(icon, str) else icon,
        )
        return res
