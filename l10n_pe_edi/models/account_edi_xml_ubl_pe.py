from odoo import models

class AccountEdiXmlUBLPE(models.AbstractModel):
    _inherit = 'account.edi.xml.ubl_21'
    _name = 'account.edi.xml.ubl_pe'
    _description = 'PE UBL 2.1'

    # -------------------------------------------------------------------------
    # EXPORT
    # -------------------------------------------------------------------------

    def _get_invoice_line_vals(self, line, taxes_vals, idx=None):
        # EXTENDS account.edi.xml.ubl_21
        vals = super()._get_invoice_line_vals(line, taxes_vals, idx)
        line_vals = line._prepare_edi_vals_to_export()
        vals['line_quantity_attrs']['unitCode'] = line.product_uom_id.l10n_pe_edi_measure_unit_code
        vals['pricing_reference_vals'] = {
            'alternative_condition_price_vals': [{
                'currency': line.currency_id,
                'price_amount': line_vals['price_total_unit'],
                'price_amount_dp': self.env['decimal.precision'].precision_get('Product Price'),
                'price_type_code': '02' if line.currency_id.is_zero(line_vals['price_unit_after_discount']) else '01',
            }]
        }
        return vals

    def _export_invoice_vals(self, invoice):
        # EXTENDS account.edi.xml.ubl_21
        vals = super()._export_invoice_vals(invoice)

        supplier = invoice.company_id.partner_id.commercial_partner_id
        customer = invoice.commercial_partner_id

        vals['vals'].update({
            'customization_id': '2.0',
            'id': invoice.name.replace(' ', ''),
            'signature_vals': [{
                'id': 'IDSignKG',
                'signatory_party_vals': {
                    'party_id': invoice.company_id.vat,
                    'party_name': invoice.company_id.name.upper(),
                },
                'digital_signature_attachment_vals': {
                    'external_reference_uri': '#SignVX',
                },
            }],
        })

        vals['vals']['accounting_supplier_party_vals'].update({
            'customer_assigned_account_id': supplier.vat,
        })
        vals['vals']['accounting_supplier_party_vals']['party_vals']['party_legal_entity_vals'][0]['registration_address_vals'].update({
            'address_type_code': invoice.company_id.l10n_pe_edi_address_type_code,
        })

        vals['vals']['accounting_customer_party_vals'].update({
            'additional_account_id': (
                customer.l10n_latam_identification_type_id
                and customer.l10n_latam_identification_type_id.l10n_pe_vat_code
            ),
        })

        if vals['vals']['order_reference']:
            vals['vals']['order_reference'] = vals['vals']['order_reference'][:20]

        # Invoice specific changes
        if vals['document_type'] == 'invoice':
            vals['vals'].update({
                'document_type_code': invoice.l10n_latam_document_type_id.code,
                'document_type_code_attrs': {
                    'listID': invoice.l10n_pe_edi_operation_type,
                    'listAgencyName': 'PE:SUNAT',
                    'listName': 'Tipo de Documento',
                    'listURI': 'urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01',
                },
            })
            if invoice.l10n_pe_edi_legend_value:
                vals['vals']['note_vals'].append({
                    'note': invoice.l10n_pe_edi_legend_value,
                    'note_attrs': {'languageLocaleID': invoice.l10n_pe_edi_legend},
                })
            vals['vals']['note_vals'].append({
                'note': invoice._l10n_pe_edi_amount_to_text(),
                'note_attrs': {'languageLocaleID': '1000'},
            })
            if invoice.l10n_pe_edi_operation_type == '1001':
                vals['vals']['note_vals'].append({
                    'note': 'Leyenda: Operacion sujeta a detraccion',
                    'note_attrs': {'languageLocaleID': '2006'},
                })

        # Credit Note specific changes
        if vals['document_type'] == 'credit_note':
            if invoice.l10n_latam_document_type_id.code == '07':
                vals['vals'].update({
                    'discrepancy_response_vals': [{
                        'response_code': invoice.l10n_pe_edi_refund_reason,
                        'description': invoice.ref
                    }]
                })
            if invoice.reversed_entry_id:
                vals['vals'].update({
                    'billing_reference_vals': {
                        'id': invoice.reversed_entry_id.name.replace(' ', ''),
                        'document_type_code': invoice.reversed_entry_id.l10n_latam_document_type_id.code,
                    },
                })

        # Debit Note specific changes
        if vals['document_type'] == 'debit_note':
            if invoice.l10n_latam_document_type_id.code == '08':
                vals['vals'].update({
                    'discrepancy_response_vals': [{
                        'response_code': invoice.l10n_pe_edi_charge_reason,
                        'description': invoice.ref
                    }]
                })
            if invoice.debit_origin_id:
                vals['vals'].update({
                    'billing_reference_vals': {
                        'id': invoice.debit_origin_id.name.replace(' ', ''),
                        'document_type_code': invoice.debit_origin_id.l10n_latam_document_type_id.code,
                    },
                })

        return vals
