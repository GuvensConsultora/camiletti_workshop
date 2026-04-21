from odoo import fields, models


EQUIPO_TIPO = [
    ("elevador_2col", "Elevador 2 columnas"),
    ("elevador_4col", "Elevador 4 columnas"),
    ("alineadora", "Alineadora"),
    ("balanceadora", "Balanceadora"),
    ("desmontadora", "Desmontadora"),
    ("foso_inspeccion", "Foso de inspección"),
    ("torque_hidraulico", "Torque hidráulico"),
    ("otro", "Otro"),
]


class WorkshopEquipo(models.Model):
    _name = "workshop.equipo"
    _description = "Equipamiento de taller"
    _order = "tipo, name"

    name = fields.Char(required=True, translate=False)
    tipo = fields.Selection(EQUIPO_TIPO, required=True)
    active = fields.Boolean(default=True)
    description = fields.Text()
