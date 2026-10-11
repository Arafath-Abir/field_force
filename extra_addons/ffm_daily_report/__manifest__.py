# -*- coding: utf-8 -*-
{
    'name': 'FFM Daily Report & Monthly Expense',
    'version': '14.0.1.0.0',
    'category': 'Sales/Field Force',
    'summary': 'Newtec Field Force Daily Reporting, Attendance, Visits and Monthly Expense',
    'author': 'Newtec Solutions / Senior Odoo Engineer',
    'website': 'https://www.newtecpharma.com',
    'depends': [
        'base',
        'hr',
        'mail',
        'account',
        'field_force_management',
        'aam_branch_management',
        'customer_management',
    ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
