{
    "name": "Camiletti Taller",
    "version": "19.0.1.6.0",
    "summary": "Gestión de taller de neumáticos, tren delantero y flujo de venta CRM",
    "description": """
Taller para NEUMATICOS CAMILETTI SRL.
Cubre todo el flujo de venta de gomería: lead CRM → DVI → cotización → taller.

Extiende:
- sale.order como única entidad de cotización / OT / factura (DOT por neumático).
- crm.lead con vehículo, DVI, walk-in directo y matching automático de bahía/técnico
  al entrar en etapa 'Diagnóstico'.
- res.partner con flags de autorización y contador de no-shows.
- appointment.type con equipamiento requerido para matching de bahía.
- workshop.inspection.line con tipo de sugerencia (fijo/dinámico).

Aporta modelos nuevos:
- workshop.bay (delegación a appointment.resource): tipo de vehículo admitido,
  equipamiento instalado, técnico por defecto.
- workshop.equipo: catálogo de equipamiento (elevador, alineadora, balanceadora).

Incluye 6 estados de taller (Recibido → Diagnóstico → Presupuestado → En reparación →
Listo → Entregado), kanban visual, recepción telefónica, walk-in y cron de no-show.
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
        "crm",
        "calendar",
        "appointment",
    ],
    "data": [
        "security/workshop_security.xml",
        "security/ir.model.access.csv",
        "data/workshop_categ_data.xml",
        "data/workshop_inspection_template_data.xml",
        "data/workshop_equipo_data.xml",
        "data/workshop_bay_data.xml",
        "data/crm_stage_data.xml",
        "data/product_data.xml",
        "data/appointment_type_data.xml",
        "data/sale_order_template_data.xml",
        "data/ir_cron_data.xml",
        "views/workshop_equipo_views.xml",
        "views/workshop_bay_views.xml",
        "views/workshop_vehicle_views.xml",
        "views/workshop_inspection_views.xml",
        "views/appointment_type_views.xml",
        "views/crm_lead_views.xml",
        "views/res_partner_views.xml",
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
