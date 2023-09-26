# -*- encoding: utf-8 -*-
from odoo import fields, api, models, _
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning

import logging
log = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    despatch_id = fields.Many2one('logistic.despatch', string='Despatch')

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_generate_despatch(self):
        for rec in self:
            for line in rec.order_line.filtered(lambda x: not x.despatch_id):
                #if 'TRANSPORTES' in line.analytic_line_ids.mapped('name'):
                if 'TRANSPORTE TERRESTRE' in line.name:
                    despatch = {
                        'company_id':rec.company_id.id,
                        'partner_id':rec.partner_id.id,
                        'origin_address_id':rec.partner_id.id,
                        'delivery_address_id':rec.partner_id.id,
                        'line_ids':[],
                        'l10n_pe_edi_type': '31',
                        'l10n_pe_edi_receiver_id': rec.partner_id.id,
                        'l10n_pe_edi_despatch_description': line.name
                    }
                    self.env['logistic.despatch'].create(despatch)

