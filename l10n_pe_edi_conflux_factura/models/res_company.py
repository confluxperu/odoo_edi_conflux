# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_pe_edi_provider = fields.Selection(selection_add=[('conflux', 'Conflux')])
    l10n_pe_edi_conflux_client_id = fields.Char(string='Conflux-ClientID')
    l10n_pe_edi_conflux_token = fields.Char(string='Conflux-Token')