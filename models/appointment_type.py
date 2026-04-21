from odoo import fields, models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    equipamiento_requerido_ids = fields.Many2many(
        "workshop.equipo",
        "appointment_type_equipo_rel", "appointment_type_id", "equipo_id",
        string="Equipamiento requerido",
        help="Equipamiento mínimo que debe tener una bahía para realizar este tipo "
             "de servicio. Usado para filtrar bahías compatibles al agendar.")
    workshop_is_diagnostic = fields.Boolean(
        string="Es diagnóstico DVI",
        help="Marca el tipo que dispara creación automática de workshop.inspection "
             "cuando un crm.lead entra en etapa de diagnóstico.")
