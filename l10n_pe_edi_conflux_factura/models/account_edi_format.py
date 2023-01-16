# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import zipfile
import io
import requests
import json
from requests.exceptions import ConnectionError, HTTPError, InvalidSchema, InvalidURL, ReadTimeout
from lxml import etree
from lxml.objectify import fromstring
from copy import deepcopy

from odoo import models, fields, api, _, _lt
from odoo.addons.iap.tools.iap_tools import iap_jsonrpc
from odoo.exceptions import AccessError
from odoo.tools import float_round, html_escape

import logging
log = logging.getLogger(__name__)

DEFAULT_CONFLUX_FACTURA_ENDPOINT = 'https://einvoice.conflux.pe/api/v/1/account_einvoice/invoice/'
DEFAULT_CONFLUX_BAJA_ENDPOINT = 'https://einvoice.conflux.pe/api/v/1/account_einvoice/void/'

def request_json(token="", method="post", url=None, data_dict=None):
    s = requests.Session()
    if not url:
        raise InvalidURL(_("Url not provided"))
    try:
        if method=='post':
            r = s.post(
                url,
                headers={'Authorization': 'Token '+token},
                json=data_dict)
        else:
            r = s.get(
                url,
                headers={'Authorization': 'Token '+token},
                json=data_dict)
    except requests.exceptions.RequestException as e:
        return {"message":_("Exception: %s" % e)}
    if r.status_code in (200,400):
        try:
            response = json.loads(r.content.decode())
            log.info(response)
        except ValueError as e:
            return {"message":_("Exception decoding JSON response: %s" % e)}

        return response
    else:
        log.info(url)
        log.info(token)
        log.info(data_dict)
        log.info(r.status_code)
        log.info(r.content)
        return {"message":_("There's problems to connecte with Conflux Server")}


class AccountEdiFormat(models.Model):
    _inherit = 'account.edi.format'

    def _l10n_pe_edi_get_edi_values_conflux(self, invoice):
        base_dte = self._l10n_pe_edi_get_edi_values(invoice)

        record = base_dte.get('record')

        invoice_sequence = record.name.replace(' ','').split('-')
        
        dte_serial = ''
        dte_number = ''
        if len(invoice_sequence)==2:
            dte_serial = invoice_sequence[0]
            dte_number = invoice_sequence[1]

        conflux_dte = {
            "enviar":True,
            "nombre_de_archivo": "%s-%s-%s-%s" % (record.company_id.vat, record.l10n_latam_document_type_id.code, dte_serial, dte_number),
            "cliente_tipo_de_documento":record.partner_id.l10n_latam_identification_type_id.l10n_pe_vat_code,
            "cliente_numero_de_documento":record.partner_id.vat,
            "cliente_denominacion": record.partner_id.name,
            "cliente_direccion": (record.partner_id.street or '') \
                                + (record.partner_id.l10n_pe_district and ', ' + record.partner_id.l10n_pe_district.name or '') \
                                + (record.partner_id.city_id and ', ' + record.partner_id.city_id.name or '') \
                                + (record.partner_id.state_id and ', ' + record.partner_id.state_id.name or '') \
                                + (record.partner_id.country_id and ', ' + record.partner_id.country_id.name or ''),
            "fecha_de_emision": base_dte.get('certificate_date').strftime('%Y-%m-%d'),
            "tipo_de_operacion": record.l10n_pe_edi_operation_type,
            "tipo_de_comprobante": record.l10n_latam_document_type_id.code,
            "serie": dte_serial,
            "numero": dte_number,
            "forma_de_pago_credito":False if base_dte.get('PaymentMeansID') == 'Contado' else True,
            "credito_cuotas":[],
            "moneda": record.currency_id.name,
            #"tipo_de_cambio": round(base_dte.get('currency_rate',1),3),
            "total_gravada": 0,
            "total_exonerada": 0,
            "total_inafecta": 0,
            "total_gratuita": 0,
            "total_exportacion": 0,
            "total_prepagado": 0,
            "total_igv": 0,
            "total_isc": 0,
            "total_icbper": 0,
            #"total_otros": 0,
            "total": 0,
            "descuento_base": 0,
            "descuento_importe": 0,
            "total_otros_cargos": 0,
            "items": []
        }

        for tax_subtotal in base_dte['tax_details']['grouped_taxes']:
            if tax_subtotal['l10n_pe_edi_group_code']=='IGV':
                conflux_dte['total_gravada']+=tax_subtotal['base']
                conflux_dte['total_igv']+=tax_subtotal['amount']
            if tax_subtotal['l10n_pe_edi_group_code']=='EXO':
                conflux_dte['total_exonerada']+=tax_subtotal['base']
            if tax_subtotal['l10n_pe_edi_group_code']=='INA':
                conflux_dte['total_inafecta']+=tax_subtotal['base']
            if tax_subtotal['l10n_pe_edi_group_code']=='GRA':
                conflux_dte['total_gratuita']+=tax_subtotal['base']
            if tax_subtotal['l10n_pe_edi_group_code']=='EXP':
                conflux_dte['total_exportacion']+=tax_subtotal['base']
            if tax_subtotal['l10n_pe_edi_group_code']=='ISC':
                conflux_dte['total_isc']+=tax_subtotal['amount']
            if tax_subtotal['l10n_pe_edi_group_code']=='ICBPER':
                conflux_dte['total_icbper']+=tax_subtotal['amount']
            if tax_subtotal['l10n_pe_edi_group_code']=='OTROS':
                conflux_dte['total_otros_cargos']+=tax_subtotal['amount']
        
        conflux_dte['total'] = conflux_dte['total_gravada']+conflux_dte['total_igv']+conflux_dte['total_exonerada']+conflux_dte['total_inafecta']+conflux_dte['total_exportacion']+conflux_dte['total_isc']

        descuento_importe_02 = 0
        descuento_importe_03 = 0
        descuento_base = 0

        if base_dte.get('invoice_lines_vals'):
            for invoice_line in base_dte.get('invoice_lines_vals', []):
                log.info(invoice_line)
                line = invoice_line.get('line')
                if line.price_subtotal<0 and line.l10n_pe_edi_allowance_charge_reason_code=='02':
                    descuento_importe_02+=abs(line.price_subtotal)
                    continue
                if line.price_subtotal<0 and line.l10n_pe_edi_allowance_charge_reason_code=='03':
                    descuento_importe_03+=abs(line.price_subtotal)
                    continue
                else:
                    descuento_base+=abs(line.price_subtotal)
                    default_uom = 'NIU'
                    if line.product_id.type=='service':
                        default_uom = 'ZZ'

                    igv_type = '10'
                    isc_type = ''
                    is_free = False

                    if line.discount >= 100.0:  
                        # Discount >= 100% means the product is free and the IGV type should be 'No onerosa' and 'taxed'
                        igv_type = self.tax_ids.filtered(lambda r: r.l10n_pe_edi_tax_code == '9996')[0].l10n_pe_edi_igv_type
                    elif any(tax['l10n_pe_edi_tax_code'] in ['1000'] for tax in invoice_line['tax_details']['taxes']):
                        # Tax with code '1000' is IGV
                        igv_type = '10'
                    elif all(tax['l10n_pe_edi_tax_code'] in ['9997'] for tax in invoice_line['tax_details']['taxes']):
                        # Tax with code '9997' is Exonerated
                        igv_type = '20'
                    elif all(tax['l10n_pe_edi_tax_code'] in ['9998'] for tax in invoice_line['tax_details']['taxes']):
                        # Tax with code '9998' is Unaffected
                        igv_type = '30'
                    elif all(tax['l10n_pe_edi_tax_code'] in ['9995'] for tax in invoice_line['tax_details']['taxes']):
                        # Tax with code '9995' is for Exportation
                        igv_type = '40'
                    elif any(tax['l10n_pe_edi_tax_code'] in ['9996'] for tax in invoice_line['tax_details']['taxes']):
                        # Tax with code '9996' is for Free operations
                        is_free = True
                        for tax in invoice_line['tax_details']['taxes']:
                            if tax['l10n_pe_edi_tax_code'] == '9996':
                                tax_browse = self.env['account.tax'].browse(tax['id'])
                                igv_type = tax_browse.l10n_pe_edi_affectation_reason
                                break

                    if any(tax['l10n_pe_edi_tax_code'] in ['2000'] for tax in invoice_line['tax_details']['taxes']):
                        isc_type = self.tax_ids.filtered(lambda r: r.l10n_pe_edi_tax_code == '2000')[0].l10n_pe_edi_isc_type

                    igv_amount = 0
                    isc_amount = 0
                    icbper_amount = 0

                    for tax in invoice_line['tax_details']['taxes']:
                        if tax['l10n_pe_edi_group_code'] == 'IGV':
                            igv_amount+=tax['amount']
                        if tax['l10n_pe_edi_group_code'] == 'ISC':
                            isc_amount+=tax['amount']
                        if tax['l10n_pe_edi_group_code'] == 'ICBPER':
                            icbper_amount+=tax['amount']

                        
                    _item = {
                        "codigo":line.product_id.default_code if line.product_id.default_code else '',
                        "codigo_producto_sunat":line.product_id.unspsc_code_id.code if line.product_id.unspsc_code_id else '',
                        "descripcion":line.name.replace('[%s] ' % line.product_id.default_code,'') if line.product_id else line.name,
                        "cantidad":abs(line.quantity),
                        "unidad_de_medida":line.product_uom_id.l10n_pe_edi_measure_unit_code if line.product_uom_id.l10n_pe_edi_measure_unit_code else default_uom,
                        "valor_unitario": invoice_line['tax_details']['unit_total_excluded'],
                        "precio_unitario": invoice_line['tax_details']['unit_total_included'],
                        "subtotal":invoice_line['tax_details']['total_excluded'] if not is_free else 0,
                        "total":invoice_line['tax_details']['total_included'] if not is_free else 0,
                        "tipo_de_igv": igv_type,
                        "igv":igv_amount,
                        "isc":isc_amount,
                        "icbper":icbper_amount,
                        "gratuito":is_free,
                    }

                    if line.discount>0 and line.discount<100:
                        _item['descuento_tipo']=line.l10n_pe_edi_allowance_charge_reason_code if line.l10n_pe_edi_allowance_charge_reason_code else '00'
                        _item['descuento_factor']=(line.discount or 0.0) / 100.0
                        _item['descuento_base']=line.price_subtotal/(1.0 - line['discount_factor'])
                        _item['descuento_importe']=_item['discount_base'] * _item['discount_factor']

                    if isc_amount>0:
                        _item['tipo_de_calculo_isc'] = isc_type

                    '''if item.get('advance_line',False):
                        _item['anticipo_regularizacion'] = item.get('advance_line',False)
                        _item['anticipo_numero_de_documento'] = '%s-%s' % (item.get('advance_serial'), item.get('advance_number'))
                        _item['anticipo_tipo_de_documento'] = item.get('advance_type', '01')'''
                    conflux_dte['items'].append(_item)


        if record.ref and record.l10n_latam_document_type_id.internal_type == 'invoice':
            conflux_dte['orden_compra_servicio'] = record.ref[:20]
        if record.partner_id.email:
            conflux_dte['cliente_email'] = record.partner_id.email
        if record.narration and record.narration!='':
            conflux_dte['observaciones'] = record.narration
        if record.company_id.l10n_pe_edi_address_type_code and record.company_id.l10n_pe_edi_address_type_code!='0000':
            conflux_dte['establecimiento_anexo'] = record.company_id.l10n_pe_edi_address_type_code

        if descuento_importe_02>0:
            conflux_dte["descuento_tipo"]="02"
            conflux_dte["descuento_base"]=descuento_base
            conflux_dte["descuento_importe"]=descuento_importe_02/conflux_dte["descuento_base"]
        
        if descuento_importe_03>0:
            conflux_dte["descuento_tipo"]="03"
            conflux_dte["descuento_base"]=descuento_base
            conflux_dte["descuento_importe"]=descuento_importe_03/conflux_dte["descuento_base"]


        if record.l10n_latam_document_type_id.code=='07':
            conflux_dte['tipo_de_nota_de_credito'] = record.l10n_pe_edi_refund_reason
            conflux_dte['documento_que_se_modifica_tipo'] = record.l10n_pe_edi_rectification_ref_type
            conflux_dte['documento_que_se_modifica_numero'] = record.l10n_pe_edi_rectification_ref_number
        
        if record.l10n_latam_document_type_id.code=='08':
            conflux_dte['tipo_de_nota_de_debito'] = record.l10n_pe_edi_charge_reason
            conflux_dte['documento_que_se_modifica_tipo'] = record.l10n_pe_edi_rectification_ref_type
            conflux_dte['documento_que_se_modifica_numero'] = record.l10n_pe_edi_rectification_ref_number

        if record.l10n_latam_document_type_id.code=='01' and record.invoice_date_due:
            conflux_dte['fecha_de_vencimiento'] = record.invoice_date_due.strftime('%Y-%m-%d')

        payment_fee_id = 0
        for payment_fee in record.l10n_pe_edi_payment_fee_ids:
            payment_fee_id+=1
            conflux_dte['credito_cuotas'].append({
                'codigo':"Cuota" + str(payment_fee_id).zfill(3),
                'fecha_de_vencimiento':payment_fee.date_due.strftime('%Y-%m-%d'),
                'importe_a_pagar':payment_fee.amount_total,
            })

        spot = record._l10n_pe_edi_get_spot()

        if spot:
            conflux_dte["detraccion"]=True
            conflux_dte["total_detraccion"]=spot['Amount']
            conflux_dte["porcentaje_detraccion"]=spot['PaymentPercent']
            conflux_dte["codigo_detraccion"]=spot['PaymentMeansID']
            conflux_dte['medio_de_pago_detraccion']=spot['PaymentMeansCode']
        
        if record.l10n_pe_edi_retention_type:
            conflux_dte["retencion_tipo"]=record.l10n_pe_edi_retention_type
            conflux_dte["retencion_base_imponible"]=record.amount_total
            retention_percentage = 0
            if record.l10n_pe_dte_retention_type=='01':
                retention_percentage = 0.03
            elif record.l10n_pe_dte_retention_type=='02':
                retention_percentage = 0.06
            conflux_dte["total_retencion"]=retention_percentage*conflux_dte["retencion_base_imponible"]

        if record.l10n_pe_edi_transportref_ids:
            conflux_dte['guias'] = []
            for despatch in record.l10n_pe_edi_transportref_ids:
                conflux_dte['guias'].append({
                    'guia_tipo': despatch.ref_type,
                    'guia_serie_numero': despatch.ref_number
                })

        return conflux_dte

    def _l10n_pe_edi_sign_invoices_conflux(self, invoice, edi_filename, edi_str):

        edi_conflux_values = self._l10n_pe_edi_get_edi_values_conflux(invoice)
        log.info(edi_conflux_values)

        service_iap = self._l10n_pe_edi_sign_service_conflux(
            invoice.company_id, edi_conflux_values, invoice.l10n_latam_document_type_id.code,
            invoice._l10n_pe_edi_get_serie_folio())
        if service_iap.get('extra_msg'):
            invoice.message_post(body=service_iap['extra_msg'])
        return service_iap

    def _l10n_pe_edi_sign_service_conflux(self, company, data_dict, latam_document_type, serie_folio):
        try:
            result = request_json(url=DEFAULT_CONFLUX_FACTURA_ENDPOINT, method='post', token=company.l10n_pe_edi_conflux_token, data_dict=data_dict)
        except InvalidSchema:
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE16'], 'blocking_level': 'error'}
        except AccessError:
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE17'], 'blocking_level': 'warning'}
        except InvalidURL:
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE18'], 'blocking_level': 'error'}

        if result.get('message') and result.get('status')=='error':
            if result['message'] == 'no-credit':
                error_message = self._l10n_pe_edi_get_iap_buy_credits_message(company)
            else:
                error_message = result['message']
            return {'error': error_message, 'blocking_level': 'error'}

        if result.get('status')=='success':
            xml_document = None
            cdr = None
            pdf_url = None
            if result['success']['data'].get('enlace_del_pdf', False):
                pdf_url = result['success']['data']['enlace_del_pdf']
            if result['success']['data'].get('enlace_del_xml', False):
                r_xml = requests.get(result['success']['data']['enlace_del_xml'])
                xml_document = r_xml.content
            if result['success']['data'].get('enlace_del_cdr', False):
                r_cdr = requests.get(result['success']['data']['enlace_del_cdr'])
                cdr = r_cdr.content
            
            return {
                'xml_document':xml_document,
                'cdr':cdr
            }

        soap_response = result.get('cdr') and base64.b64decode(result['cdr'])
        soap_response_decoded = self._l10n_pe_edi_decode_soap_response(soap_response) if soap_response else {}

        cdr = None
        extra_msg = ''
        if soap_response_decoded.get('error'):
            # Error code 1033 means that the invoice was already registered with the OSE.
            if soap_response_decoded.get('code') == '1033':
                status_cdr_response = self._l10n_pe_edi_get_status_cdr_iap_service(company, serie_folio, latam_document_type)
                if status_cdr_response.get('error'):
                    error_msg = '%s<br/>%s<br/>%s' % (soap_response_decoded['error'], _('Error requesting CDR status:'),
                                                      status_cdr_response['error'])
                    return {'error': error_msg, 'blocking_level': 'error'}
                # Status code 0004 means the CDR already exists.
                elif status_cdr_response.get('code') == '0004':
                    extra_msg = _('The invoice already exists on SUNAT. CDR successfully retrieved.')
                    cdr = status_cdr_response['cdr']
                else:
                    error_msg = '%s<br/>%s<br/>%s' % (soap_response_decoded['error'], _('CDR status:'), status_cdr_response['status'])
                    return {'error': error_msg, 'blocking_level': 'error'}
            else:
                return {'error': soap_response_decoded['error'], 'blocking_level': 'error'}

        if not cdr:  # The 'cdr' variable might be set if we retrieved the cdr after getting error code 1033 - see above
            cdr = soap_response_decoded['cdr']

        cdr_status = self._l10n_pe_edi_extract_cdr_status(cdr)

        if cdr_status['code'] != '0':
            error_message = '%s<br/><br/><b>%s</b>' % (
                cdr_status['description'],
                _('This invoice number is now registered by SUNAT as invalid. Duplicate this invoice or create a new invoice to retry.')
            )
            return {'error': error_message, 'blocking_level': 'error'}

        xml_document = result.get('signed') and self._l10n_pe_edi_unzip_edi_document(base64.b64decode(result['signed']))
        return {'xml_document': xml_document, 'cdr': cdr, 'extra_msg': extra_msg}

    '''def _post_invoice_edi(self, invoices, test_mode=False):
        res = super(AccountEdiFormat, self)._post_invoice_edi(invoices, test_mode=test_mode)
        log.info('_post_invoice_edi*****************')
        log.info(res)
        invoice = invoices # Batching is disabled for this EDI.
        provider = invoice.company_id.l10n_pe_edi_provider
        if provider == 'conflux':
            if res[invoice].get('error'):
                return res
            #res = {}
            edi_filename = '%s-%s-%s' % (
                invoice.company_id.vat,
                invoice.l10n_latam_document_type_id.code,
                invoice.name.replace(' ', ''),
            )
            latam_invoice_type = self._get_latam_invoice_type(invoice.l10n_latam_document_type_id.code)
            if res[invoice].get('xml_document_url'):
                res['attachment'] = self.env['ir.attachment'].create({
                    "name":"%s.xml" % edi_filename,
                    'res_model': invoice._name,
                    'res_id': invoice.id,
                    "type":'url',
                    "url":res[invoice]['xml_document_url']
                })

                message = _("The EDI document was successfully created and signed by the government.")
                invoice.with_context(no_new_invoice=True).message_post(
                    body=message,
                    attachment_ids=res['attachment'].ids,
                )
                return {invoice: res}
        return res'''