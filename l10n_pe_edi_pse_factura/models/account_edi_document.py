# -*- coding: utf-8 -*-

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

class AccountEdiDocument(models.Model):
    _inherit = 'account.edi.document'

    @api.model
    def _cron_process_documents_web_services(self, job_count=None):
        super()._cron_process_documents_web_services(job_count=job_count)
        edi_documents = self.search([('state', 'in', ('to_cancel')), ('move_id.state', '=', 'cancel')])
        edi_documents._process_documents_web_services(job_count=job_count)