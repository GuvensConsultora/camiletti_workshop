from odoo import fields, models


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    workshop_lead_id = fields.Many2one(
        "crm.lead", string="Lead gomería", index=True, ondelete="set null",
        help="Lead de CRM que originó este turno.")
    workshop_inspection_id = fields.Many2one(
        "workshop.inspection", string="Inspección DVI",
        index=True, ondelete="set null")
    workshop_bay_id = fields.Many2one(
        "workshop.bay", string="Bahía", index=True, ondelete="set null",
        help="Bahía asignada al turno.")
    workshop_no_show = fields.Boolean(
        string="No se presentó", default=False, tracking=True,
        help="Marcado cuando el cron detecta que el evento venció sin ejecución.")
    workshop_cancel_reason = fields.Selection([
        ("cliente", "Cliente"),
        ("operativa", "Operativa del taller"),
        ("clima", "Clima"),
        ("otro", "Otro"),
    ], string="Motivo de cancelación")
