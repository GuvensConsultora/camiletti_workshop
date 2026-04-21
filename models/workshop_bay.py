from odoo import api, fields, models


BAY_STATES = [
    ("available", "Disponible"),
    ("busy", "Ocupada"),
    ("maintenance", "En mantenimiento"),
    ("closed", "Fuera de servicio"),
]

ACTIVE_ORDER_STATES = ("received", "diagnosis", "quoted", "in_repair", "ready")


class WorkshopBay(models.Model):
    _name = "workshop.bay"
    _description = "Bahía de taller"
    _inherits = {"appointment.resource": "resource_id"}
    _order = "sequence, id"

    resource_id = fields.Many2one(
        "appointment.resource", string="Recurso de agendamiento",
        required=True, ondelete="cascade", auto_join=True,
        help="Registro en appointment.resource que se usa para el motor nativo "
             "de slots y disponibilidad.")

    code = fields.Char(required=True, copy=False, help="Código corto, ej. EL1, AL, BAL.")
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    note = fields.Text(string="Observaciones")
    notas_internas = fields.Text(string="Notas internas")

    accepts_auto = fields.Boolean(string="Acepta auto", default=True)
    accepts_camioneta = fields.Boolean(string="Acepta camioneta / SUV", default=True)
    accepts_camion = fields.Boolean(string="Acepta camión", default=False)

    equipamiento_ids = fields.Many2many(
        "workshop.equipo", "workshop_bay_equipo_rel", "bay_id", "equipo_id",
        string="Equipamiento instalado")
    tecnico_por_defecto_id = fields.Many2one(
        "res.users", string="Técnico por defecto",
        domain="[('share','=',False)]",
        help="Técnico preferido para asignar cuando esté disponible.")
    tecnico_ids = fields.Many2many(
        "res.users", "workshop_bay_tecnico_rel", "bay_id", "user_id",
        string="Técnicos habilitados",
        domain="[('share','=',False)]")

    state = fields.Selection(
        BAY_STATES, default="available", required=True, tracking=True,
        help="Estado operativo manual.")

    current_order_ids = fields.One2many(
        "sale.order", "bay_id", string="OTs asignadas",
        domain=[("workshop_state", "in", ACTIVE_ORDER_STATES)])
    active_order_count = fields.Integer(
        compute="_compute_occupation", string="OTs activas")
    is_occupied = fields.Boolean(
        compute="_compute_occupation", string="Ocupada")

    _sql_constraints = [
        ("code_unique", "unique(code)", "El código de bahía ya existe."),
    ]

    @api.depends("current_order_ids")
    def _compute_occupation(self):
        for b in self:
            count = len(b.current_order_ids)
            b.active_order_count = count
            b.is_occupied = bool(count)

    def _tipos_vehiculo_admitidos(self):
        """Lista de valores de workshop.vehicle.vehicle_type que esta bahía acepta."""
        self.ensure_one()
        out = []
        if self.accepts_auto:
            out += ["auto", "utilitario", "moto", "otro"]
        if self.accepts_camioneta:
            out += ["camioneta"]
        if self.accepts_camion:
            out += ["camion", "maquina"]
        return out

    def name_get(self):
        return [(b.id, f"{b.code} — {b.name}" if b.code else (b.name or "")) for b in self]
