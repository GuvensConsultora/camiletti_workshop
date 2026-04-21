{
    "name": "Camiletti Taller",
    "version": "19.0.1.2.1",
    "summary": "Gestión de taller de neumáticos y tren delantero/trasero",
    "description": """
Taller para NEUMATICOS CAMILETTI SRL.
Extiende sale.order como única entidad de cotización / OT / factura.
Incluye ficha de vehículo del cliente, DOT por neumático, 6 estados de taller
con máquina de estados guardada por rol, kanban visual y flujo optimizado para
recepción telefónica, walk-in directo y walk-in con diagnóstico.
    """,
    "author": "Yagüven C.G.",
    "website": "https://yaguvencg.com.ar",
    "license": "LGPL-3",
    "category": "Services/Workshop",
    "depends": [
        "sale_management",
        "sale_stock",
        "l10n_ar_edi",
        "portal",
        "contacts",
    ],
    "data": [
        "security/workshop_security.xml",
        "security/ir.model.access.csv",
        "data/workshop_categ_data.xml",
        "data/workshop_inspection_template_data.xml",
        "data/workshop_bay_data.xml",
        "views/workshop_bay_views.xml",
        "views/workshop_vehicle_views.xml",
        "views/workshop_inspection_views.xml",
        "views/sale_order_views.xml",
        "views/workshop_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "camiletti_workshop/static/src/scss/workshop.scss",
        ],
    },
    "installable": True,
    "application": True,
}
