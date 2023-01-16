# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_pe_edi_conflux_client_id = fields.Char(
        string="Conflux-ClientID",
        related="company_id.l10n_pe_edi_conflux_client_id",
        readonly=False)
    l10n_pe_edi_conflux_token = fields.Char(
        string="Conflux-Token",
        related="company_id.l10n_pe_edi_conflux_token",
        readonly=False)