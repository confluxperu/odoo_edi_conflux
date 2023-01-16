# -*- coding: utf-8 -*-
{
    'name': 'EDI for Peru with Conflux PSE',
    'version': '1.0',
    'summary': 'Electronic Invoicing for Peru using direct connection with Conflux PSE',
    'category': 'Accounting/Localizations/EDI',
    'author': 'Obox',
    'license': 'OPL-1',
'description': """
Extends EDI Peru Localization
=============================
    """,
    'depends': [
        'l10n_pe_edi',
    ],
    "data": [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
}