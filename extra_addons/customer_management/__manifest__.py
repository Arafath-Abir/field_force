{
    'name': 'Customer Information Management',
    'version': '14.0.1.0.0',
    'summary': 'Customer & Chemist Information Base Module',
    'category': 'Sales',
    'depends': ['base', 'hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/customer_views.xml',
    ],
    'installable': True,
    'application': True,
}