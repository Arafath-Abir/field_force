# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class FFMAuditLog(models.Model):
    _name = 'ffm.audit.log'
    _description = 'FFM Audit Log'
    _order = 'timestamp desc, id desc'

    user_id = fields.Many2one('res.users', string='User', required=True, index=True, readonly=True)
    model_name = fields.Char(string='Model', required=True, index=True, readonly=True)
    res_id = fields.Integer(string='Record ID', required=True, index=True, readonly=True)
    res_name = fields.Char(string='Record Name', readonly=True)
    action = fields.Selection([
        ('create', 'Create'),
        ('write', 'Update'),
        ('unlink', 'Delete'),
        ('submit', 'Submit'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('pay', 'Pay'),
        ('export', 'Export'),
    ], string='Action', required=True, index=True, readonly=True)
    old_values = fields.Text(string='Old Values', readonly=True)
    new_values = fields.Text(string='New Values', readonly=True)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now, required=True, index=True, readonly=True)
    ip_address = fields.Char(string='IP Address', readonly=True)

    @api.model
    def log_action(self, model_name, res_id, action, old_values=None, new_values=None, res_name=None, user_id=None, ip_address=None):
        """Helper method to record audit events safely without interrupting business flow."""
        try:
            uid = user_id or self.env.uid
            vals = {
                'user_id': uid,
                'model_name': model_name,
                'res_id': int(res_id) if res_id else 0,
                'action': action,
                'res_name': str(res_name or ''),
                'old_values': str(old_values) if old_values is not None else '',
                'new_values': str(new_values) if new_values is not None else '',
                'timestamp': fields.Datetime.now(),
                'ip_address': ip_address or '',
            }
            return self.sudo().create(vals)
        except Exception:
            _logger.exception("Failed to create FFM audit log for %s (%s)", model_name, res_id)
            return False
