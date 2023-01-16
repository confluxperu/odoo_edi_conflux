# -*- coding: utf-8 -*-
from odoo import api, fields, models

class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_pe_edi_conflux_uid = fields.Char(string='DTE Conflux UID', copy=False)
    l10n_pe_edi_rectification_ref_type = fields.Many2one('l10n_latam.document.type', string='Rectification - Invoice Type')
    l10n_pe_edi_rectification_ref_number = fields.Char('Rectification - Invoice number')
    l10n_pe_edi_rectification_ref_date = fields.Char('Rectification - Invoice Date')
    l10n_pe_edi_retention_type = fields.Selection([
        ('01', 'Tasa 3%'),
        ('02', 'Tasa 6%'),
    ], string='IGV Retention Type', copy=True, readonly=True,
        states={'draft': [('readonly', False)]},)
    l10n_pe_edi_payment_fee_ids = fields.One2many('account.move.l10n_pe_payment_fee','move_id', string='Credit Payment Fees')
    l10n_pe_edi_transportref_ids = fields.One2many(
        'account.move.l10n_pe_transportref', 'move_id', string='Attached Despatchs', copy=True)

    def _post(self, soft=True):
        res = super(AccountMove, self)._post(soft=soft)
        pe_edi_format = self.env.ref('l10n_pe_edi.edi_pe_ubl_2_1')
        for move in self.filtered(lambda m: pe_edi_format._is_required_for_invoice(m) and m.is_sale_document()):
            move.l10n_pe_edi_compute_fees()
        return res

    def l10n_pe_edi_credit_amount_deduction(self):
        spot = self._l10n_pe_edi_get_spot()
        amount = 0
        if spot:
            amount+=spot['Amount']
        if self.l10n_pe_edi_retention_type:
            amount+=self.amount_total*(0.03 if self.l10n_pe_dte_retention_type=='01' else 0.06)
        return amount

    def l10n_pe_edi_compute_fees(self):
        if self.invoice_date_due and self.invoice_date_due>self.invoice_date:
            invoice_date_due_vals_list = []
            first_time = True
            amount_deduction = self.l10n_pe_edi_credit_amount_deduction()
            for rec_line in self.line_ids.filtered(lambda l: l.account_internal_type=='receivable'):
                amount = rec_line.amount_currency
                if amount_deduction and first_time:
                    amount -= amount_deduction
                invoice_date_due_vals_list.append([0, 0,{'amount': rec_line.move_id.currency_id.round(amount),
                                                'currency_id': rec_line.move_id.currency_id.id,
                                                'date_maturity': rec_line.date_maturity}])

            self.write({
                'l10n_pe_edi_payment_fee_ids': invoice_date_due_vals_list
            })