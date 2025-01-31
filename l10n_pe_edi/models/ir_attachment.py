# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, models
from odoo.tools import xml_utils
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model
    def _l10n_pe_edi_load_xsd_files(self, force_reload=False):
        url = 'http://cpe.sunat.gob.pe/sites/default/files/inline-files/XSD%202.1.zip'
        def modify_xsd_content(content):
            return content.replace(b'schemaLocation="../common/', b'schemaLocation="')
        xml_utils.load_xsd_files_from_url(self.env, url, modify_xsd_content=modify_xsd_content, xsd_name_prefix='l10n_pe_edi')

    @api.model
    def action_download_xsd_files(self):
        # EXTENDS account/models/ir_attachment.py
        self._l10n_pe_edi_load_xsd_files()
        super().action_download_xsd_files()
