# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FFMLiveLocationMixin(models.AbstractModel):
    """Live GPS position captured on the device at the moment a field form is submitted."""
    _name = 'ffm.live.location.mixin'
    _description = 'FFM Live Location Mixin'

    latitude = fields.Float(string='Latitude', digits=(12, 7), readonly=True)
    longitude = fields.Float(string='Longitude', digits=(12, 7), readonly=True)
    gps_accuracy = fields.Float(string='GPS Accuracy (m)', readonly=True)
    map_url = fields.Char(string='Map Link', compute='_compute_map_url')

    @api.depends('latitude', 'longitude')
    def _compute_map_url(self):
        for rec in self:
            if rec.latitude or rec.longitude:
                rec.map_url = f"https://www.google.com/maps?q={rec.latitude},{rec.longitude}"
            else:
                rec.map_url = False
