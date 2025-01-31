# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_pe_edi_provider = fields.Selection(
        string="Signature Provider",
        readonly=False,
        related="company_id.l10n_pe_edi_provider")
    l10n_pe_edi_test_env = fields.Boolean(
        string="Testing Environment",
        related='company_id.l10n_pe_edi_test_env',
        readonly=False)
    l10n_pe_edi_provider_username = fields.Char(
        string="SOL User",
        related="company_id.l10n_pe_edi_provider_username",
        readonly=False,
        help="SUNAT Operaciones en Línea")
    l10n_pe_edi_provider_password = fields.Char(
        string="SOL Password",
        related="company_id.l10n_pe_edi_provider_password",
        readonly=False,
        help="SUNAT Operaciones en Línea")
