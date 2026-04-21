from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WorkshopVehicleOwnerHistory(models.Model):
    _name = "workshop.vehicle.owner.history"
    _description = "Historial de titulares del vehículo"
    _order = "date_from desc, id desc"
    _rec_name = "partner_id"

    vehicle_id = fields.Many2one(
        "workshop.vehicle", string="Vehículo", required=True,
        ondelete="cascade", index=True)
    partner_id = fields.Many2one(
        "res.partner", string="Titular", required=True,
        ondelete="restrict", index=True)
    date_from = fields.Date(
        string="Desde", required=True, default=fields.Date.context_today)
    date_to = fields.Date(
        string="Hasta",
        help="Vacío = titular actual.")
    notes = fields.Char(string="Nota",
        help="Ej.: compra, herencia, venta, transferencia vía VIN.")
    is_current = fields.Boolean(
        string="Titular actual", compute="_compute_is_current", store=True)
    company_id = fields.Many2one(
        related="vehicle_id.company_id", store=True, index=True)

    @api.depends("date_to")
    def _compute_is_current(self):
        for r in self:
            r.is_current = not r.date_to

    _sql_constraints = [
        ("one_current_per_vehicle",
         "exclude using gist (vehicle_id with =) where (date_to IS NULL)",
         "Solo puede haber un titular actual por vehículo."),
    ]

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for r in self:
            if r.date_to and r.date_to < r.date_from:
                raise ValidationError(_(
                    "La fecha 'Hasta' no puede ser anterior a 'Desde'."))
