# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FFMExpenseStatementRejectWizard(models.TransientModel):
    _name = 'ffm.expense.statement.reject.wizard'
    _description = 'Reject Monthly Expense Statement Wizard'

    statement_id = fields.Many2one(
        'ffm.expense.statement', string='Expense Statement',
        required=True, readonly=True)
    reason = fields.Text(string='Rejection Reason', required=True)

    def action_reject(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(_("Please provide a mandatory rejection reason."))

        statement = self.statement_id
        if statement.state not in ('submitted', 'checked'):
            raise UserError(_("Only submitted or checked statements can be rejected."))

        statement.write({
            'state': 'rejected',
            'rejection_reason': self.reason.strip(),
        })

        self.env['ffm.audit.log'].log_action(
            model_name='ffm.expense.statement',
            res_id=statement.id,
            action='reject',
            new_values={'reason': self.reason.strip()},
            res_name=statement.name
        )

        try:
            statement.with_context(mail_activity_quick_update=True).activity_feedback(['mail.mail_activity_data_todo'])
        except Exception:
            pass

        if statement.employee_id.user_id:
            statement.with_context(mail_activity_quick_update=True).activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=statement.employee_id.user_id.id,
                summary=_('Correct & Resubmit Statement: %s') % statement.name,
                note=_('Statement was rejected. Reason: %s') % self.reason.strip()
            )

        return {'type': 'ir.actions.act_window_close'}
