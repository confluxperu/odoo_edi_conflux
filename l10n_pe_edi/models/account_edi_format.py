# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import zipfile
import io
from requests.exceptions import ConnectionError as ReqConnectionError, HTTPError, InvalidSchema, InvalidURL, ReadTimeout
from zeep.wsse.username import UsernameToken
from zeep import Client, Settings
from zeep.transports import Transport
from lxml import etree
from lxml import objectify
from copy import deepcopy

from odoo import models, api, _, _lt
from odoo.addons.iap.tools.iap_tools import iap_jsonrpc
from odoo.exceptions import AccessError
from odoo.tools import float_round, html_escape

import logging
log = logging.getLogger(__name__)

class AccountEdiFormat(models.Model):
    _inherit = 'account.edi.format'

    # -------------------------------------------------------------------------
    # EDI: HELPERS
    # -------------------------------------------------------------------------

    @api.model
    def _l10n_pe_edi_zip_edi_document(self, documents):
        buffer = io.BytesIO()
        zipfile_obj = zipfile.ZipFile(buffer, 'w')
        for filename, content in documents:
            zipfile_obj.writestr(filename, content, compress_type=zipfile.ZIP_DEFLATED)
        zipfile_obj.close()
        content = buffer.getvalue()
        buffer.close()
        return content

    @api.model
    def _l10n_pe_edi_unzip_edi_document(self, zip_str):
        """Unzip the first XML file of a zip file,
        or, if the zip file does not contain an XML file, unzip the first file.
        :param zip_str: zipfile in base64 bytes
        :returns: the contents of the first xml file (or first file)
        """
        buffer = io.BytesIO(zip_str)
        zipfile_obj = zipfile.ZipFile(buffer)
        # We need to select the first xml file of the zip file because SUNAT sometimes sends a CDR zip file
        # which has an empty folder named 'dummy' as the first file in the zip file.
        filenames = zipfile_obj.namelist()
        xml_filenames = [x for x in filenames if x.endswith(('.xml', '.XML'))]
        filename_to_decode = xml_filenames[0] if xml_filenames else filenames[0]
        content = zipfile_obj.read(filename_to_decode)
        buffer.close()
        return content

    @api.model
    def _l10n_pe_edi_unzip_all_edi_documents(self, zip_bytes):
        """Unzips all the files of a base64 zip_bytes and if contains a CDR XML, it will unzip
        that one first
        :param zip_bytes: Zipfile in base64 that contains the response and signed XML
        :returns: xml files in base64
        """
        with io.BytesIO(base64.b64decode(zip_bytes)) as buffer:
            zip_bytes = zipfile.ZipFile(buffer)
            result = []
            for content_name in zip_bytes.namelist():
                xml_bytes = zip_bytes.read(content_name)
                application_response = etree.fromstring(xml_bytes).xpath('//applicationResponse')
                # If application response is in the xml file, we are actually interested in the contents of it
                # (which is a zip in base64, which contains the file we are interested in)
                if not application_response:
                    result.append([content_name, base64.b64encode(xml_bytes)])
                else:
                    unzipped_cdr = self._l10n_pe_edi_unzip_edi_document(base64.b64decode(application_response[0].text))
                    result.append([content_name[2:], base64.b64encode(unzipped_cdr)])
        return result

    @api.model
    def _l10n_pe_edi_get_general_error_messages(self):
        return {
            'L10NPE08': _lt("There was an error in the connection or the response from the OSE server. Please try again later."),
            'L10NPE17': _lt("There are problems with the connection to the IAP server. "
                            "Please try again in a few minutes."),
            'L10NPE18': _lt("The URL provided for the IAP server is wrong, please go to  Settings --> System "
                            "Parameters and add the right URL to parameter l10n_pe_edi.endpoint."),
        }

    @api.model
    def _l10n_pe_edi_get_cdr_error_messages(self):
        """The codes from the response of the CDR  and the service we are consulting must be processed to find if the
        message is common, if it is, we will set a friendly message giving instructions on how to fix the
        error/warning."""
        return {
            '2800': _lt("The type of identity document used for the client is not valid. Review the type of document "
                        "used in the client and change it according to the case of the document to be created. For "
                        "invoices it's only valid to use RUC as identity document."),
            '2801': _lt("The VAT you use for the customer is a DNI type, to be a valid DNI it must be the exact length "
                        "of 8 digits."),
            '2315': _lt("The cancellation reason field should not be empty when canceling the invoice, you must return "
                        "this invoice to Draft, edit the document and enter a cancellation reason."),
            '3105': _lt("One or more lines of this document do not have taxes assigned, to solve this you must return "
                        "the document to the Draft state and place taxes on the lines that do not have them."),
            '4332': _lt("One or more products do not have the UNSPSC code configured, to avoid this warning you must "
                        "configure a code for this product. This warning does not invalidate the document."),
            '2017': _lt("For invoices, the customer's identity document must be RUC. Check that the client has a valid "
                        "RUC and the type of document is RUC."),
            '3206': _lt("The type of operation is not valid for the type of document you are trying to create. The "
                        "document must return to Draft state and change the type of operation."),
            '2022': _lt("The name of the Partner must contain at least 2 characters and must not contain special characters."),
            '151': _lt("The name of the file depends on the sequence in the journal, please go to the journal and "
                       "configure the shortcode as LLL- (three (3) letters plus a dash and the 3 letters must be UPPERCASE.)"),
            '156': _lt("The zip file is corrupted, check again if the file trying to access is not damaged."),
            '2119': _lt("The invoice related to this Credit Note has not been reported, go to the invoice related and "
                        "sign it in order to generate this Credit Note."),
            '2120': _lt("The invoice related to this Credit Note has been canceled, set this document to draft and "
                        "cancel it."),
            '2209': _lt("The invoice related to this Debit Note has not been reported, go to the invoice related and "
                        "sign it in order to generate this Debit Note"),
            '2207': _lt("The invoice related to this Debit Note has been canceled, set this document to draft and "
                        "cancel it."),
            '001': _lt("This invoice has been validated by the OSE and we can not allow set it to draft, please try "
                       "to revert it with a credit not or cancel it and create a new one instead."),
            '1033': _lt("This document already exists on the OSE side.  Check if you gave a proper unique name to your "
                        "document. "),
            '1034': _lt("Check that the VAT set in the company is correct, this error generally happen when you did "
                        "not set a proper VAT in the company, go to company form and set it properly.."),
            '2371': _lt("Check your tax configuration, go to Configuration -> Taxes and set the field "
                        "'Affectation reason' to set it by default or set the proper value in the field Affect. Reason "
                        "in the line"),
            '2204': _lt("The document type of the invoice related is not the same of this document. Check the "
                        "document type of the invoice related and set this document with that document type. In case of "
                        "this document being posted and having a number already, reset to draft and cancel it, this "
                        "document will be cancelled locally and not reported."),
            '2116': _lt("The document type of the invoice related is not the same of this document. Check the "
                        "document type of the invoice related and set this document with that document type. In case of "
                        "this document being posted and having a number already, reset to draft and cancel it, this "
                        "document will be cancelled locally and not reported."),
            '3034': _lt("You need to configure the account for 'Banco de la Nación'. go to the Other Info setting"
                        " on this invoice and select the Recipient Bank field, If you want to set it by default go to "
                        "the partner related to your company and set the bank account related to the Banco de la "
                        "Nación"),
            '3128': _lt("As you have a document that must be detracted (withheld) which mean a document over 700 "
                        "Soles With services you must select on the 'Operation Type field the correct code 1001 "
                        "for example"),
            '98': _lt("The cancellation request has not yet finished processing by SUNAT. Please retry in a few minutes.")
        }

    def _l10n_pe_edi_extract_cdr_status(self, cdr):
        """
        Parse a CDR in XML format.

        Returns a dict that contains the following fields:
        'code': the ResponseCode of the CDR. 0 = success. Any other value = error.
        'description': a description of the CDR's response in HTML format, combining the
                       'Description' tag and the 'Note' tags.
        """
        cdr_tree = etree.fromstring(cdr)
        code = cdr_tree.find('.//{*}ResponseCode').text
        description = html_escape(cdr_tree.find('.//{*}Description').text)
        notes = cdr_tree.findall('.//{*}Note')
        for note in notes:
            description += '<br/>' + html_escape(note.text)

        if code != '0':
            error_messages_map = self._l10n_pe_edi_get_cdr_error_messages()
            description = '%s<br/><br/><b>%s</b><br/>%s|%s' % (
                error_messages_map.get(code, _("We got an error response from the OSE. ")),
                _('Original message:'),
                html_escape(code),
                html_escape(description),
            )

        return {'code': code, 'description': description}

    # -------------------------------------------------------------------------
    # EDI: IAP service
    # -------------------------------------------------------------------------

    def _l10n_pe_edi_get_iap_buy_credits_message(self, company):
        url = self.env['iap.account'].get_credits_url(service_name="l10n_pe_edi")
        return '''<p><b>%s</b></p><p>%s</p>''' % (
            _('You have insufficient credits to sign or verify this document!'),
            _('Please proceed to buy more credits <a href="%s">here.</a>', html_escape(url)),
        )

    # -------------------------------------------------------------------------
    # EDI: SUNAT / DIGIFLOW services
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # EDI OVERRIDDEN METHODS
    # -------------------------------------------------------------------------
    
    def _get_move_applicability(self, move):
        # EXTENDS account_edi
        self.ensure_one()
        if self.code != 'pe_ubl_2_1':
            return super()._get_move_applicability(move)

        if move.l10n_pe_edi_is_required:
            return {
                'post': self._l10n_pe_edi_sign_invoice,
                'cancel': self._l10n_pe_edi_cancel_invoices,
                'cancel_batching': lambda invoice: (invoice.l10n_pe_edi_cancel_cdr_number,),
                'edi_content': self._l10n_pe_edi_xml_invoice_content,
            }
        
    def _needs_web_services(self):
        # OVERRIDE
        return self.code == 'pe_ubl_2_1' or super()._needs_web_services()
    
    def _check_move_configuration(self, move):
        # OVERRIDE
        res = super()._check_move_configuration(move)
        if self.code != 'pe_ubl_2_1':
            return res

        if not move.company_id.vat:
            res.append(_("VAT number is missing on company %s", move.company_id.display_name))
        if not move.commercial_partner_id.vat:
            res.append(_("VAT number is missing on partner %s", move.commercial_partner_id.display_name))
        lines = move.invoice_line_ids.filtered(lambda line: line.display_type not in ('line_note', 'line_section'))
        for line in lines:
            taxes = line.tax_ids
            if len(taxes) > 1 and len(taxes.filtered(lambda t: t.tax_group_id.l10n_pe_edi_code == 'IGV')) > 1:
                res.append(_("You can't have more than one IGV tax per line to generate a legal invoice in Peru"))
        if any(not line.tax_ids for line in move.invoice_line_ids if line.display_type not in ('line_note', 'line_section')):
            res.append(_("Taxes need to be assigned on all invoice lines"))

        # When this condition is met in `_l10n_pe_edi_get_spot` we will need this bank account.
        # As the mentioned method is meant to be run by a CRON, the user won't be able to see the error hence we raise it here.
        max_percent = max(move.invoice_line_ids.mapped('product_id.l10n_pe_withhold_percentage'), default=0)
        need_national_bank_account = not (not max_percent or not move.l10n_pe_edi_operation_type in ['1001', '1002', '1003', '1004'] or move.move_type == 'out_refund')
        if need_national_bank_account:
            national_bank = self.env.ref('l10n_pe.peruvian_national_bank')
            national_bank_account = move.company_id.bank_ids.filtered(lambda b: b.bank_id == national_bank)
            if not national_bank_account:
                res.append(_("To generate the electronic document with this invoice, the bank account at the national bank will be needed.\n"
                             "Please configure it.\n"))

        return res
    
    def _is_compatible_with_journal(self, journal):
        # OVERRIDE
        if self.code != 'pe_ubl_2_1':
            return super()._is_compatible_with_journal(journal)
        return journal.type == 'sale' and journal.country_code == 'PE' and journal.l10n_latam_use_documents

    def _l10n_pe_edi_xml_invoice_content(self, invoice):
        return self._generate_edi_invoice_bstr(invoice)

    def _generate_edi_invoice_bstr(self, invoice):
        latam_invoice_type = self._get_latam_invoice_type(invoice.l10n_latam_document_type_id.code)
        if not latam_invoice_type:
            return _("Missing LATAM document code.").encode()

        builder = self.env['account.edi.xml.ubl_pe']
        xml_content, errors = builder._export_invoice(invoice)

        if errors:
            return "".join([
                _("Errors occured while creating the EDI document (format: %s):", builder._description),
                "\n",
                "\n".join(errors)
            ]).encode()

        # Since the default UBL construction removes empty nodes, we need to recreate them here.
        edi_tree = objectify.fromstring(xml_content)
        namespaces = {'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'}
        ubl_version_id_element = edi_tree.xpath('.//cbc:UBLVersionID', namespaces=namespaces)[0]
        ubl_extensions_str = self.env['ir.qweb']._render('l10n_pe_edi.ubl_pe_21_ubl_extensions_empty_signature')
        ubl_version_id_element.addprevious(objectify.fromstring(ubl_extensions_str))

        return etree.tostring(edi_tree)

    def _get_latam_invoice_type(self, code):
        template_by_latam_type_mapping = {
            '07': 'credit_note',
            '08': 'debit_note',
            '01': 'invoice',
            '03': 'invoice',
        }
        return template_by_latam_type_mapping.get(code, False)

    def _get_sunat_wsdl(self):
        """This method will handle the SUNAT WSDL, in production we have an error while using zeep because of one
        definition that has no binding, so, we just store the XML of the service and remove the unvalid data.
        Reported https://github.com/mvantellingen/python-zeep/issues/924
        """
        return io.BytesIO(b'''
            <wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:soap11="http://schemas.xmlsoap.org/wsdl/soap/" xmlns:soap12="http://schemas.xmlsoap.org/wsdl/soap12/" xmlns:http="http://schemas.xmlsoap.org/wsdl/http/" xmlns:mime="http://schemas.xmlsoap.org/wsdl/mime/" xmlns:wsp="http://www.w3.org/ns/ws-policy" xmlns:wsp200409="http://schemas.xmlsoap.org/ws/2004/09/policy" xmlns:wsp200607="http://www.w3.org/2006/07/ws-policy" xmlns:ns0="http://service.gem.factura.comppago.registro.servicio.sunat.gob.pe/" xmlns:ns1="http://service.sunat.gob.pe" xmlns:ns2="http://www.datapower.com/extensions/http://schemas.xmlsoap.org/wsdl/soap12/" targetNamespace="http://service.gem.factura.comppago.registro.servicio.sunat.gob.pe/">
            <wsdl:import location="https://e-factura.sunat.gob.pe/ol-ti-itcpfegem/billService?ns1.wsdl" namespace="http://service.sunat.gob.pe"/>
            <wsdl:binding name="BillServicePortBinding" type="ns1:billService">
                <soap11:binding transport="http://schemas.xmlsoap.org/soap/http" style="document"/>
                <wsdl:operation name="getStatus">
                <soap11:operation soapAction="urn:getStatus" style="document"/>
                <wsdl:input name="getStatusRequest">
                    <soap11:body use="literal"/>
                </wsdl:input>
                <wsdl:output name="getStatusResponse">
                    <soap11:body use="literal"/>
                </wsdl:output>
                </wsdl:operation>
                <wsdl:operation name="sendBill">
                <soap11:operation soapAction="urn:sendBill" style="document"/>
                <wsdl:input name="sendBillRequest">
                    <soap11:body use="literal"/>
                </wsdl:input>
                <wsdl:output name="sendBillResponse">
                    <soap11:body use="literal"/>
                </wsdl:output>
                </wsdl:operation>
                <wsdl:operation name="sendPack">
                <soap11:operation soapAction="urn:sendPack" style="document"/>
                <wsdl:input name="sendPackRequest">
                    <soap11:body use="literal"/>
                </wsdl:input>
                <wsdl:output name="sendPackResponse">
                    <soap11:body use="literal"/>
                </wsdl:output>
                </wsdl:operation>
                <wsdl:operation name="sendSummary">
                <soap11:operation soapAction="urn:sendSummary" style="document"/>
                <wsdl:input name="sendSummaryRequest">
                    <soap11:body use="literal"/>
                </wsdl:input>
                <wsdl:output name="sendSummaryResponse">
                    <soap11:body use="literal"/>
                </wsdl:output>
                </wsdl:operation>
            </wsdl:binding>
            <wsdl:service name="billService">
                <wsdl:port name="BillServicePort" binding="ns0:BillServicePortBinding">
                <soap11:address location="https://e-factura.sunat.gob.pe:443/ol-ti-itcpfegem/billService"/>
                </wsdl:port>
                <wsdl:port name="BillServicePort.0" binding="ns2:BillServicePortBinding">
                <soap12:address location="https://e-factura.sunat.gob.pe:443/ol-ti-itcpfegem/billService"/>
                </wsdl:port>
                <wsdl:port name="BillServicePort.3" binding="ns0:BillServicePortBinding">
                <soap11:address location="https://e-factura.sunat.gob.pe:443/ol-ti-itcpfegem/billService"/>
                </wsdl:port>
            </wsdl:service>
            </wsdl:definitions>''')
