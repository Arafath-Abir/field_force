{
    'name': 'Field Force Management',
    'version': '14.0.1.6.0',
    'summary': 'Daily Report, Travel Log, Expense Claim & Approval for Pharma Field Force',
    'author': 'Md Mohiuddin, NewTec Solutions',
    'website': 'https://www.mohiuddindev.com',
    'category': 'Sales/Field Force',
    
    'depends': ['base', 'hr', 'mail', 'account', 'customer_management', 'aam_branch_management'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/assets.xml',
        'views/fare_config_views.xml',
        'views/daily_report_views.xml',
        'views/travel_log_views.xml',
        'views/location_settings_views.xml',
        'views/menu_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
