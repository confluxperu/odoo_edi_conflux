import requests
import base64
from odoo import models


class MailTemplate(models.Model):
    _inherit = "mail.template"

    def _get_edi_attachments(self, document):
        if not document.attachment_id or document.edi_format_id.code != 'pe_pse':
            return super()._get_edi_attachments(document)
        einvoice_attachments = []
        if document.move_id.l10n_pe_edi_pse_uid and document.move_id.company_id.l10n_pe_edi_provider=='conflux':
            invoice = document.move_id
            conf = self.env['ir.config_parameter']
            pdf_format_pse = bool(conf.sudo().get_param('account.l10n_pe_edi_pdf_use_pse_%s' % invoice.company_id.id,False))
            if invoice.l10n_pe_edi_pdf_file and pdf_format_pse:
                if invoice.l10n_pe_edi_pdf_file.type=="url":
                    r = requests.get(invoice.l10n_pe_edi_pdf_file.url)
                    data_content = r.content
                    einvoice_attachments.append((invoice.l10n_pe_edi_pdf_file.name, base64.encodebytes(data_content)))
            if invoice.l10n_pe_edi_cdr_file:
                if invoice.l10n_pe_edi_cdr_file.type=="url":
                    r = requests.get(invoice.l10n_pe_edi_cdr_file.url)
                    data_content = r.content
                    einvoice_attachments.append((invoice.l10n_pe_edi_cdr_file.name, base64.encodebytes(data_content)))
            if invoice.l10n_pe_edi_xml_file:
                if invoice.l10n_pe_edi_xml_file.type=="url":
                    r = requests.get(invoice.l10n_pe_edi_xml_file.url)
                    data_content = r.content
                    einvoice_attachments.append((invoice.l10n_pe_edi_xml_file.name, base64.encodebytes(data_content)))
        return einvoice_attachments