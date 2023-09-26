# -*- encoding: utf-8 -*-
from odoo import fields, api, models, _
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
import requests
import json
import datetime

import logging
log = logging.getLogger(__name__)


class Vehicle(models.Model):
    _inherit = 'fleet.vehicle'

    l10n_pe_edi_vehicle_tuc = fields.Char(string='TUC')