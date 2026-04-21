from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    autoriza_ordenes = fields.Boolean(
        string="Autoriza órdenes",
        help="Contacto habilitado para aprobar cotizaciones de vehículos de flota.")
    es_conductor = fields.Boolean(
        string="Es conductor",
        help="Contacto que conduce vehículos del cliente flota pero no autoriza gastos.")
    umbral_no_shows = fields.Integer(
        string="Umbral de no-shows",
        default=3,
        help="Cantidad de no-shows a partir de la cual mostrar warning al reservar stock.")
    cantidad_no_shows = fields.Integer(
        string="No-shows", compute="_compute_cantidad_no_shows",
        help="Cantidad de turnos en los que el cliente no se presentó.")

    def _compute_cantidad_no_shows(self):
        Event = self.env["calendar.event"].sudo()
        for p in self:
            if not p.id:
                p.cantidad_no_shows = 0
                continue
            p.cantidad_no_shows = Event.search_count([
                ("workshop_no_show", "=", True),
                ("workshop_lead_id.partner_id", "=", p.id),
            ])
