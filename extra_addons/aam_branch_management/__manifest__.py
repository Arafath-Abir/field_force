{
    'name': 'Branch & Territory Management',
    'version': '14.0.1.0.0',
    'summary': 'Branch and Territory Management Base Module',
    'category': 'Human Resources',
    'depends': ['base', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/branch_views.xml',
    ],
    'installable': True,
    'application': True,
}