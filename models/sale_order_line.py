import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# DOT: WWYY (semana 01-53 + año 2 dígitos), con margen por códigos viejos.
_DOT_RE = re.compile(r"^(?:[0-4]\d|5[0-3])\d{2}$")


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    dot_code = fields.Char(
        string="DOT",
        help="Fecha de fabricación del neumático (semana+año, ej: 3524 = "
             "semana 35 de 2024). Requerido por garantía Michelín.")
    installed_position = fields.Selection([
        ("fl", "Delantera izquierda"),
        ("fr", "Delantera derecha"),
        ("rl", "Trasera izquierda"),
        ("rr", "Trasera derecha"),
        ("rl_int", "Trasera izq. interior"),
        ("rr_int", "Trasera der. interior"),
        ("spare", "Auxilio"),
        ("other", "Otra"),
    ], string="Posición instalada")
    workshop_done = fields.Boolean(
        string="Terminado", copy=False, tracking=True,
        help="Técnico marca cuando completa este item.")

    is_tire_line = fields.Boolean(
        compute="_compute_is_tire_line", store=True, string="Es neumático")

    @api.depends("product_id", "product_id.categ_id")
    def _compute_is_tire_line(self):
        for l in self:
            l.is_tire_line = l._is_tire()

    def _is_tire(self):
        """Detecta si la línea corresponde a un neumático por categoría."""
        self.ensure_one()
        if not self.product_id:
            return False
        cat = self.product_id.categ_id
        # Match laxo por nombre de categoría, ajustable desde configuración.
        names = []
        while cat:
            names.append((cat.name or "").lower())
            cat = cat.parent_id
        composite = " / ".join(names)
        return "neumátic" in composite or "neumatic" in composite

    @api.constrains("dot_code")
    def _check_dot_format(self):
        for l in self.filtered("dot_code"):
            code = (l.dot_code or "").strip()
            if code and not _DOT_RE.match(code):
                raise ValidationError(_(
                    "DOT '%s' inválido. Formato esperado: WWYY "
                    "(semana 01-53 + año 2 dígitos, ej: 3524).", code))

    def action_toggle_done(self):
        for l in self:
            l.workshop_done = not l.workshop_done
