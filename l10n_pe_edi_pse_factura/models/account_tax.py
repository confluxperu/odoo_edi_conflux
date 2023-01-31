# -*- coding: utf-8 -*-

from odoo import fields, api, models

class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_pe_edi_isc_type = fields.Selection([
        ('01', 'System to value'),
        ('02', 'Application of the Fixed Amount'),
        ('03', 'Retail Price System'),
    ], 'ISC Type',
        help='Used in Selective Consumption Tax to indicate the type of calculation for the ISC.')

class AccountTaxTemplate(models.Model):
    _inherit = "account.tax.template"

    l10n_pe_edi_isc_type = fields.Selection([
        ('01', 'System to value'),
        ('02', 'Application of the Fixed Amount'),
        ('03', 'Retail Price System'),
    ], 'ISC Type',
        help='Used in Selective Consumption Tax to indicate the type of calculation for the ISC.')

    def _get_tax_vals(self, company, tax_template_to_tax):
        val = super()._get_tax_vals(company, tax_template_to_tax)
        val.update({
            'l10n_pe_edi_isc_type': self.l10n_pe_edi_isc_type,
        })
        return val