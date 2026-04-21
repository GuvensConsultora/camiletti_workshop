from odoo import api, fields, models
from odoo.exceptions import ValidationError


BAY_TYPES = [
    ("elevator", "Elevador"),
    ("alignment", "Alineación"),
    ("balancer", "Balanceo"),
    ("pit", "Foso"),
    ("outdoor", "Playa externa"),
]

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
    _order = "sequence, code, id"

    name = fields.Char(required=True, translate=False)
    code = fields.Char(required=True, copy=False, help="Código corto, ej. EL1, AL, BAL.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(help="Color en kanban.")
    note = fields.Text(string="Observaciones")

    bay_type = fields.Selection(BAY_TYPES, required=True, default="elevator")
    capacity = fields.Integer(
        default=1, required=True,
        help="Cantidad de vehículos que la bahía puede atender en simultáneo.")
    max_vehicle_weight = fields.Float(
        string="Peso máx. vehículo (kg)",
        help="Límite del elevador o del piso. 0 = sin restricción declarada.")
    equipment_description = fields.Text(
        string="Equipamiento",
        help="Marca/modelo de elevador, alineadora, balanceadora, torque, etc.")

    technician_ids = fields.Many2many(
        "res.users", "workshop_bay_technician_rel", "bay_id", "user_id",
        string="Técnicos habilitados",
        domain="[('share','=',False)]")
    default_technician_id = fields.Many2one(
        "res.users", string="Técnico por defecto",
        domain="[('share','=',False)]")

    state = fields.Selection(
        BAY_STATES, default="available", required=True, tracking=True,
        help="Estado operativo manual. 'Ocupada' también se infiere automáticamente "
             "si hay una OT activa asignada.")

    current_order_ids = fields.One2many(
        "sale.order", "bay_id", string="OTs asignadas",
        domain=[("workshop_state", "in", ACTIVE_ORDER_STATES)])
    active_order_count = fields.Integer(
        compute="_compute_occupation", string="OTs activas")
    is_occupied = fields.Boolean(
        compute="_compute_occupation", string="Ocupada")

    _sql_constraints = [
        ("code_unique", "unique(code)", "El código de bahía ya existe."),
        ("capacity_positive", "CHECK(capacity > 0)", "La capacidad debe ser mayor a cero."),
    ]

    @api.depends("current_order_ids", "capacity")
    def _compute_occupation(self):
        for b in self:
            count = len(b.current_order_ids)
            b.active_order_count = count
            b.is_occupied = count >= b.capacity

    @api.constrains("default_technician_id", "technician_ids")
    def _check_default_technician_in_list(self):
        for b in self:
            if b.default_technician_id and b.technician_ids and \
               b.default_technician_id not in b.technician_ids:
                raise ValidationError(
                    "El técnico por defecto debe estar en la lista de técnicos "
                    "habilitados de la bahía.")
