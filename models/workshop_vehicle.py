import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_PLATE_OLD = re.compile(r"^[A-Z]{3}\d{3}$")
_PLATE_NEW = re.compile(r"^[A-Z]{2}\d{3}[A-Z]{2}$")


class WorkshopVehicle(models.Model):
    _name = "workshop.vehicle"
    _description = "Vehículo del Cliente"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "display_name"
    _order = "license_plate"

    active = fields.Boolean(default=True)
    display_name = fields.Char(compute="_compute_display_name", store=True, index=True)

    license_plate = fields.Char(
        string="Patente", required=True, tracking=True, index=True,
        help="Patente argentina. Formato viejo AAA123 o nuevo AA123AA.")
    vin_sn = fields.Char(
        string="VIN / Número de chasis", tracking=True,
        help="17 caracteres alfanuméricos (ISO 3779). Opcional pero recomendado.")
    partner_id = fields.Many2one(
        "res.partner", string="Titular actual", required=True, tracking=True,
        index=True, ondelete="restrict",
        help="Titular vigente del vehículo. Se sincroniza con el registro "
             "abierto en el historial de titulares.")

    owner_history_ids = fields.One2many(
        "workshop.vehicle.owner.history", "vehicle_id",
        string="Historial de titulares")
    previous_owner_ids = fields.Many2many(
        "res.partner", string="Titulares anteriores",
        compute="_compute_previous_owners")

    @api.depends("owner_history_ids.partner_id", "owner_history_ids.date_to", "partner_id")
    def _compute_previous_owners(self):
        for v in self:
            v.previous_owner_ids = v.owner_history_ids.filtered(
                "date_to").mapped("partner_id") - v.partner_id

    brand = fields.Char(string="Marca", tracking=True)
    vehicle_model = fields.Char(string="Modelo", tracking=True)
    year = fields.Integer(string="Año", tracking=True)
    color = fields.Char(string="Color")
    vehicle_type = fields.Selection([
        ("auto", "Auto"),
        ("camioneta", "Camioneta / SUV"),
        ("camion", "Camión"),
        ("utilitario", "Utilitario"),
        ("moto", "Moto"),
        ("maquina", "Máquina / Agrícola"),
        ("otro", "Otro"),
    ], string="Tipo", default="auto", required=True, tracking=True)
    fuel_type = fields.Selection([
        ("nafta", "Nafta"),
        ("gasoil", "Gasoil"),
        ("gnc", "GNC"),
        ("hibrido", "Híbrido"),
        ("electrico", "Eléctrico"),
    ], string="Combustible")

    odometer = fields.Integer(
        string="Km actual", tracking=True,
        help="Kilometraje al último servicio registrado.")
    notes = fields.Html(string="Observaciones")

    service_order_ids = fields.One2many(
        "sale.order", "vehicle_id", string="Órdenes de servicio")
    service_order_count = fields.Integer(
        compute="_compute_service_order_count", string="OTs")
    last_service_date = fields.Date(
        compute="_compute_last_service", string="Último servicio")

    _sql_constraints = [
        ("license_plate_uniq", "unique(license_plate, company_id)",
         "Ya existe un vehículo con esa patente."),
    ]

    company_id = fields.Many2one(
        "res.company", default=lambda s: s.env.company, index=True)

    @api.depends("license_plate", "brand", "vehicle_model")
    def _compute_display_name(self):
        for v in self:
            parts = [v.license_plate or "?"]
            if v.brand or v.vehicle_model:
                parts.append(" ".join(filter(None, [v.brand, v.vehicle_model])))
            v.display_name = " · ".join(parts)

    def _compute_service_order_count(self):
        data = dict(self.env["sale.order"]._read_group(
            [("vehicle_id", "in", self.ids)],
            ["vehicle_id"], ["__count"]))
        for v in self:
            v.service_order_count = data.get(v, 0)

    def _compute_last_service(self):
        for v in self:
            so = self.env["sale.order"].search(
                [("vehicle_id", "=", v.id), ("state", "in", ["sale", "done"])],
                order="date_order desc", limit=1)
            v.last_service_date = so.date_order.date() if so and so.date_order else False

    @api.constrains("license_plate")
    def _check_license_plate_ar(self):
        for v in self.filtered("license_plate"):
            plate = self._normalize_plate(v.license_plate)
            if not (_PLATE_OLD.match(plate) or _PLATE_NEW.match(plate)):
                raise ValidationError(_(
                    "La patente '%s' no respeta el formato argentino "
                    "(AAA123 o AA123AA).", v.license_plate))

    @api.constrains("vin_sn")
    def _check_vin(self):
        for v in self.filtered("vin_sn"):
            if len(v.vin_sn.strip()) not in (0, 17):
                raise ValidationError(_(
                    "El VIN debe tener 17 caracteres (ISO 3779). Recibido: %s",
                    len(v.vin_sn.strip())))

    @api.constrains("year")
    def _check_year(self):
        for v in self.filtered("year"):
            if v.year < 1900 or v.year > fields.Date.today().year + 1:
                raise ValidationError(_("Año de vehículo inválido: %s", v.year))

    @staticmethod
    def _normalize_plate(plate):
        return (plate or "").upper().replace(" ", "").replace("-", "")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("license_plate"):
                vals["license_plate"] = self._normalize_plate(vals["license_plate"])
        vehicles = super().create(vals_list)
        today = fields.Date.context_today(self)
        self.env["workshop.vehicle.owner.history"].create([
            {"vehicle_id": v.id,
             "partner_id": v.partner_id.id,
             "date_from": today,
             "notes": _("Alta del vehículo")}
            for v in vehicles if v.partner_id
        ])
        return vehicles

    def write(self, vals):
        if vals.get("license_plate"):
            vals["license_plate"] = self._normalize_plate(vals["license_plate"])
        new_partner = vals.get("partner_id")
        transitions = []
        if new_partner:
            for v in self:
                if v.partner_id.id != new_partner:
                    transitions.append(v)
        res = super().write(vals)
        if transitions:
            today = fields.Date.context_today(self)
            History = self.env["workshop.vehicle.owner.history"]
            for v in transitions:
                open_rec = History.search(
                    [("vehicle_id", "=", v.id), ("date_to", "=", False)], limit=1)
                if open_rec:
                    open_rec.date_to = today
                History.create({
                    "vehicle_id": v.id,
                    "partner_id": new_partner,
                    "date_from": today,
                    "notes": _("Cambio de titular"),
                })
        return res

    def action_view_service_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("OTs — %s", self.license_plate),
            "res_model": "sale.order",
            "view_mode": "list,kanban,form",
            "domain": [("vehicle_id", "=", self.id)],
            "context": {
                "default_vehicle_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }

    def action_new_service_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Nueva OT"),
            "res_model": "sale.order",
            "view_mode": "form",
            "context": {
                "default_vehicle_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_workshop_state": "received",
            },
        }
