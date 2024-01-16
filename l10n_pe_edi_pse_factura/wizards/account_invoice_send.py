# -*- coding: utf-8 -*-
import base64

import requests

from odoo import api, models
import logging
log = logging.getLogger(__name__)

class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"
    
    def _print_document(self):
        """ to override for each type of models that will use this composer."""        
        """self.ensure_one()
        action = self.invoice_ids.action_invoice_print()
        action.update({'close_on_report_download': True})
        return action"""
        return {'type': 'ir.actions.act_window_close'}

    @api.onchange("template_id")
    def onchange_template_id(self):
        conf = self.env['ir.config_parameter']
        res = super(AccountInvoiceSend, self).onchange_template_id()
        for wizard in self:
            Attachment = self.env["ir.attachment"]
            if wizard.template_id and wizard.composition_mode != "mass_mail":
                invoice_id = self.env[wizard.composer_id.model].browse(
                    wizard.composer_id.res_id
                )
                einvoice_attachments = []
                pdf_format_pse = conf.sudo().get_param('account.l10n_pe_edi_pdf_use_pse_%s' % invoice_id.company_id.id,"False")
                if pdf_format_pse.lower() == "true":
                    pdf_format_pse = True
                else:
                    pdf_format_pse = False
                if invoice_id.l10n_pe_edi_pdf_file and pdf_format_pse:
                    r = requests.get(invoice_id.l10n_pe_edi_pdf_file.url)
                    data_content = r.content
                    invoice_id.l10n_pe_edi_pdf_file.write({
                        "datas": base64.encodebytes(data_content),
                        "type": "binary",
                    })
                    einvoice_attachments.append(invoice_id.l10n_pe_edi_pdf_file.id)
                else:
                    einvoice_attachments = wizard.composer_id.attachment_ids.ids
                if invoice_id.l10n_pe_edi_cdr_file:
                    r = requests.get(invoice_id.l10n_pe_edi_pdf_file.url)
                    data_content = r.content
                    invoice_id.l10n_pe_edi_cdr_file.write({
                        "datas": base64.encodebytes(data_content),
                        "type": "binary",
                    })
                    einvoice_attachments.append(invoice_id.l10n_pe_edi_cdr_file.id)
                if invoice_id.l10n_pe_edi_xml_file:
                    r = requests.get(invoice_id.l10n_pe_edi_xml_file.url)
                    data_content = r.content
                    invoice_id.l10n_pe_edi_xml_file.write({
                        "datas": base64.encodebytes(data_content),
                        "type": "binary",
                    })
                    einvoice_attachments.append(invoice_id.l10n_pe_edi_xml_file.id)
                if einvoice_attachments:
                    wizard.write(
                        {
                            "attachment_ids": [
                                (
                                    6,
                                    0,
                                    einvoice_attachments,
                                )
                            ]
                        }
                    )
        return res
