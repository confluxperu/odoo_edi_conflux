# -*- coding: utf-8 -*-
from odoo import api, fields, models
import logging
log = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_pe_edi_pse_uid = fields.Char(string='PSE Unique identifier', copy=False)
    l10n_pe_edi_pse_cancel_uid = fields.Char(string='PSE Identifier for Cancellation', copy=False)
    l10n_pe_edi_pse_attachment_ids = fields.Many2many('ir.attachment', string='EDI Attachments')
    l10n_pe_edi_pse_status = fields.Selection([
        ('ask_for_status', 'Ask For Status'),
        ('accepted', 'Accepted'),
        ('objected', 'Accepted With Objections'),
        ('rejected', 'Rejected'),
    ], string='SUNAT DTE status', copy=False, tracking=True, help="""Status of sending the DTE to the SUNAT:
    - Ask For Status: The DTE is asking for its status to the SUNAT.
    - Accepted: The DTE has been accepted by SUNAT.
    - Accepted With Objections: The DTE has been accepted with objections by SUNAT.
    - Rejected: The DTE has been rejected by SUNAT.""")
    l10n_pe_edi_pse_void_status = fields.Selection([
        ('ask_for_status', 'Ask For Status'),
        ('accepted', 'Accepted'),
        ('objected', 'Accepted With Objections'),
        ('rejected', 'Rejected'),
    ], string='SUNAT DTE Void status', copy=False, tracking=True, help="""Status of sending the DTE to the SUNAT:
    - Ask For Status: The DTE is asking for its status to the SUNAT.
    - Accepted: The DTE has been accepted by SUNAT.
    - Accepted With Objections: The DTE has been accepted with objections by SUNAT.
    - Rejected: The DTE has been rejected by SUNAT.""")
    l10n_pe_edi_accepted_by_sunat = fields.Boolean(string='EDI Accepted by Sunat', copy=False)
    l10n_pe_edi_void_accepted_by_sunat = fields.Boolean(string='Void EDI Accepted by Sunat', copy=False)
    l10n_pe_edi_rectification_ref_type = fields.Many2one('l10n_latam.document.type', string='Rectification - Invoice Type')
    l10n_pe_edi_rectification_ref_number = fields.Char('Rectification - Invoice number')
    l10n_pe_edi_rectification_ref_date = fields.Char('Rectification - Invoice Date')
    l10n_pe_edi_payment_fee_ids = fields.One2many('account.move.l10n_pe_payment_fee','move_id', string='Credit Payment Fees')
    l10n_pe_edi_transportref_ids = fields.One2many(
        'account.move.l10n_pe_transportref', 'move_id', string='Attached Despatchs', copy=True)
    
    l10n_pe_edi_hash = fields.Char(string='DTE Hash', copy=False)
    l10n_pe_edi_xml_file = fields.Many2one('ir.attachment', string='DTE file', copy=False)
    l10n_pe_edi_xml_file_link = fields.Char(string='DTE file', compute='_compute_l10n_pe_edi_links')
    l10n_pe_edi_pdf_file = fields.Many2one('ir.attachment', string='DTE PDF file', copy=False)
    l10n_pe_edi_pdf_file_link = fields.Char(string='DTE PDF file', compute='_compute_l10n_pe_edi_links')
    l10n_pe_edi_cdr_file = fields.Many2one('ir.attachment', string='CDR file', copy=False)
    l10n_pe_edi_cdr_file_link = fields.Char(string='CDR file', compute='_compute_l10n_pe_edi_links')
    l10n_pe_edi_cdr_void_file = fields.Many2one('ir.attachment', string='CDR Void file', copy=False)
    l10n_pe_edi_cdr_void_file_link = fields.Char(string='CDR Void file', compute='_compute_l10n_pe_edi_links')

    def _compute_l10n_pe_edi_links(self):
        for move in self:
            move.l10n_pe_edi_xml_file_link = move.l10n_pe_edi_xml_file.url if move.l10n_pe_edi_xml_file else None
            move.l10n_pe_edi_pdf_file_link = move.l10n_pe_edi_pdf_file.url if move.l10n_pe_edi_pdf_file else None
            move.l10n_pe_edi_cdr_file_link = move.l10n_pe_edi_cdr_file.url if move.l10n_pe_edi_cdr_file else None
            move.l10n_pe_edi_cdr_void_file_link = move.l10n_pe_edi_cdr_void_file.url if move.l10n_pe_edi_cdr_void_file else None

    def _post(self, soft=True):
        res = super(AccountMove, self)._post(soft=soft)
        pe_edi_format = self.env.ref('l10n_pe_edi_pse_factura.edi_pe_pse')
        for move in self.filtered(lambda m: pe_edi_format._is_required_for_invoice(m) and m.is_sale_document()):
            move.l10n_pe_edi_compute_fees()
        return res
    
    def _get_starting_sequence(self):
        # OVERRIDE
        if self.l10n_pe_edi_is_required and self.l10n_latam_document_type_id:
            doc_mapping = {'01': 'FFI', '03': 'BOL', '07': 'CNE', '08': 'NDI'}
            middle_code = doc_mapping.get(self.l10n_latam_document_type_id.code, self.journal_id.code)
            # TODO: maybe there is a better method for finding decent 2nd journal default invoice names
            if self.journal_id.code != 'INV':
                middle_code = self.journal_id.code[:3]
            return "%s %s-00000000" % (self.l10n_latam_document_type_id.doc_code_prefix, middle_code)

        return super()._get_starting_sequence()

    def _get_last_sequence_domain(self, relaxed=False):
        where_string, param = super()._get_last_sequence_domain(relaxed=relaxed)
        log.info('where_string: %s', where_string)
        log.info('param: %s', param)
        if self.l10n_pe_edi_is_required:
            where_string += " AND l10n_latam_document_type_id = %(l10n_latam_document_type_id)s"
            param['l10n_latam_document_type_id'] = self.l10n_latam_document_type_id.id or 0
            if not relaxed:
                param['anti_regex'] = 'NULL'''
        return where_string, param

    def l10n_pe_edi_retention_amount(self):
        if self.partner_id.l10n_pe_edi_retention_type:
            return self.amount_total*(0.03 if self.partner_id.l10n_pe_edi_retention_type=='01' else 0.06)
        return 0

    def l10n_pe_edi_credit_amount_deduction(self):
        spot = self._l10n_pe_edi_get_spot()
        amount = 0
        if spot:
            amount+=spot['spot_amount']
        if self.partner_id.l10n_pe_edi_retention_type:
            amount+=self.l10n_pe_edi_retention_amount()
        return amount

    def l10n_pe_edi_compute_fees(self):
        self.l10n_pe_edi_payment_fee_ids.unlink()
        if self.invoice_date_due and self.invoice_date_due>self.invoice_date:
            invoice_date_due_vals_list = []
            first_time = True
            amount_deduction = self.l10n_pe_edi_credit_amount_deduction()
            for rec_line in self.line_ids.filtered(lambda l: l.account_internal_type=='receivable'):
                amount = rec_line.amount_currency
                if rec_line.date_maturity<=self.invoice_date:
                    continue
                if amount_deduction and first_time:
                    amount -= amount_deduction
                invoice_date_due_vals_list.append([0, 0,{'amount_total': rec_line.move_id.currency_id.round(amount),
                                                'currency_id': rec_line.move_id.currency_id.id,
                                                'date_due': rec_line.date_maturity}])

            self.write({
                'l10n_pe_edi_payment_fee_ids': invoice_date_due_vals_list
            })

    def _retry_edi_documents_error_hook(self):
        for move in self.filtered(lambda m: m.l10n_pe_edi_pse_uid and (m.l10n_pe_edi_pse_status=='ask_for_status')):
            move.edi_document_ids.filtered(lambda d: d.state in ('sent')).write({'state': 'to_send'})
        for move in self.filtered(lambda m: m.l10n_pe_edi_pse_cancel_uid and (m.l10n_pe_edi_pse_void_status=='ask_for_status')):
            move.edi_document_ids.filtered(lambda d: d.state in ('cancelled')).write({'state': 'to_cancel'})

    def _l10n_pe_edi_get_extra_report_values(self):
        self.ensure_one()

        # Parse the edi document.
        edi_attachment_zipped = self._get_edi_attachment(self.env.ref('l10n_pe_edi_pse_factura.edi_pe_pse'))
        if not edi_attachment_zipped:
            res = super()._l10n_pe_edi_get_extra_report_values()
            return res

        serie_folio = self._l10n_pe_edi_get_serie_folio()
        qr_code_values = [
            self.company_id.vat,
            self.company_id.partner_id.l10n_latam_identification_type_id.l10n_pe_vat_code,
            serie_folio['serie'],
            serie_folio['folio'],
            str(self.amount_tax),
            str(self.amount_total),
            fields.Date.to_string(self.date),
            self.partner_id.l10n_latam_identification_type_id.l10n_pe_vat_code,
            self.commercial_partner_id.vat or '00000000',
            ''
        ]

        return {
            'qr_str': '|'.join(qr_code_values) + '|\r\n',
            'amount_to_text': self._l10n_pe_edi_amount_to_text(),
        }

    def button_cancel(self):
        pe_edi_format = self.env.ref('l10n_pe_edi_pse_factura.edi_pe_pse')
        if pe_edi_format._is_required_for_invoice(self) and self.is_sale_document() and self.l10n_pe_edi_pse_uid and not self.l10n_pe_edi_pse_cancel_uid:
            cancel_reason = self.l10n_pe_edi_cancel_reason or 'Anulacion'
            self.write({'l10n_pe_edi_cancel_reason':cancel_reason})
            self.edi_document_ids.filtered(lambda doc: doc.state == 'to_send').write({'state': 'sent', 'error': False, 'blocking_level': False})
        res = super().button_cancel()
        return res

    def button_cancel_posted_moves(self):
        # OVERRIDE
        pe_edi_format = self.env.ref('l10n_pe_edi_pse_factura.edi_pe_pse')
        pe_invoices = self.filtered(pe_edi_format._is_required_for_invoice)
        if pe_invoices:
            cancel_reason_needed = pe_invoices.filtered(lambda move: not move.l10n_pe_edi_cancel_reason)
            if cancel_reason_needed:
                return self.env.ref('l10n_pe_edi.action_l10n_pe_edi_cancel').sudo().read()[0]
        return super().button_cancel_posted_moves()

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_pe_edi_downpayment_line = fields.Boolean('Is Downpayment?', store=True, default=False)
    l10n_pe_edi_downpayment_invoice_id = fields.Many2one('account.move', string='Downpayment Invoice', store=True, readonly=True, help='Invoices related to the advance regualization')
    l10n_pe_edi_downpayment_ref_type = fields.Selection([('02','Factura'),('03','Boleta de venta')], string='Downpayment Ref. Type')
    l10n_pe_edi_downpayment_ref_number = fields.Char('Downpayment Ref. Number')
    l10n_pe_edi_downpayment_date = fields.Date('Downpayment date')

    def _prepare_edi_vals_to_export(self):
        res = super()._prepare_edi_vals_to_export()
        res.update({
            'price_subtotal_unit': self.price_subtotal / self.quantity if self.quantity else 0.0,
            'price_total_unit': self.price_total / self.quantity if self.quantity else 0.0,
        })
        return res