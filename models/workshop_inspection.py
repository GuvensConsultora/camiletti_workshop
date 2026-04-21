from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


CATEGORY_SELECTION = [
    ("tires", "Neumáticos"),
    ("wheels", "Llantas"),
    ("brakes_front", "Frenos delanteros"),
    ("brakes_rear", "Frenos traseros"),
    ("suspension_front", "Tren delantero"),
    ("suspension_rear", "Tren trasero"),
    ("steering", "Dirección"),
    ("oil_fluids", "Aceite y lubricantes"),
    ("other", "Otros"),
]

STATUS_SELECTION = [
    ("na", "No aplica"),
    ("ok", "OK"),
    ("warning", "Atención"),
    ("critical", "Crítico"),
    ("replaced", "Ya reemplazado"),
]


class WorkshopInspection(models.Model):
    _name = "workshop.inspection"
    _description = "Inspección Vehicular (DVI)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    sale_order_id = fields.Many2one(
        "sale.order", string="OT", ondelete="cascade", index=True, tracking=True)
    vehicle_id = fields.Many2one(
        related="sale_order_id.vehicle_id", store=True, readonly=True)
    partner_id = fields.Many2one(
        related="sale_order_id.partner_id", store=True, readonly=True)
    technician_id = fields.Many2one(
        "res.users", string="Técnico", tracking=True,
        domain="[('share','=',False)]")
    date = fields.Datetime(default=fields.Datetime.now, tracking=True)
    state = fields.Selection([
        ("in_progress", "En curso"),
        ("done", "Completada"),
    ], default="in_progress", tracking=True, copy=False)

    line_ids = fields.One2many(
        "workshop.inspection.line", "inspection_id",
        string="Puntos de revisión", copy=True)

    count_ok = fields.Integer(compute="_compute_counts")
    count_warning = fields.Integer(compute="_compute_counts")
    count_critical = fields.Integer(compute="_compute_counts")
    count_na = fields.Integer(compute="_compute_counts")
    count_total = fields.Integer(compute="_compute_counts")

    overall_notes = fields.Html(string="Conclusiones del técnico")

    @api.depends("sale_order_id.name", "date")
    def _compute_name(self):
        for r in self:
            so_name = r.sale_order_id.name if r.sale_order_id else _("Sin OT")
            date_str = fields.Datetime.to_string(r.date)[:10] if r.date else ""
            r.name = f"DVI {so_name} · {date_str}"

    @api.depends("line_ids.status")
    def _compute_counts(self):
        for r in self:
            r.count_ok = len(r.line_ids.filtered(lambda l: l.status == "ok"))
            r.count_warning = len(r.line_ids.filtered(lambda l: l.status == "warning"))
            r.count_critical = len(r.line_ids.filtered(lambda l: l.status == "critical"))
            r.count_na = len(r.line_ids.filtered(lambda l: l.status == "na"))
            r.count_total = len(r.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            if not rec.line_ids:
                rec._load_default_template()
        return recs

    def _load_default_template(self):
        tmpl = self.env["workshop.inspection.template"].search(
            [("active", "=", True)], order="category, sequence, id")
        Line = self.env["workshop.inspection.line"]
        for t in tmpl:
            Line.create({
                "inspection_id": self.id,
                "name": t.name,
                "category": t.category,
                "sequence": t.sequence,
                "value_unit": t.value_unit or "",
                "is_measurable": t.is_measurable,
            })

    def action_add_suggestions_to_quote(self):
        """Agrega sale.order.line a partir de sugerencias en líneas warning/critical."""
        Line = self.env["sale.order.line"]
        total_added = 0
        for r in self:
            if not r.sale_order_id:
                continue
            to_add = r.line_ids.filtered(
                lambda l: l.status in ("warning", "critical") and l.suggested_service_id)
            for il in to_add:
                Line.create({
                    "order_id": r.sale_order_id.id,
                    "product_id": il.suggested_service_id.id,
                    "product_uom_qty": il.suggested_qty or 1,
                    "name": f"[{il.name}] {il.suggested_service_id.name}",
                })
                total_added += 1
            r.message_post(body=_(
                "%s sugerencias agregadas al presupuesto.", len(to_add)))
        if total_added:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "success",
                    "message": _("Se agregaron %s items al presupuesto.", total_added),
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }

    def action_mark_done(self):
        for r in self:
            critical_no_photo = r.line_ids.filtered(
                lambda l: l.status == "critical" and not l.photo)
            if critical_no_photo:
                raise ValidationError(_(
                    "No se puede cerrar la inspección: los siguientes puntos "
                    "críticos no tienen foto: %s",
                    ", ".join(critical_no_photo.mapped("name"))))
        self.write({"state": "done"})


class WorkshopInspectionLine(models.Model):
    _name = "workshop.inspection.line"
    _description = "Punto de Inspección"
    _order = "category, sequence, id"

    inspection_id = fields.Many2one(
        "workshop.inspection", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Punto", required=True)
    category = fields.Selection(
        CATEGORY_SELECTION, required=True, default="other")
    status = fields.Selection(
        STATUS_SELECTION, default="na", required=True, tracking=True)
    status_color = fields.Integer(compute="_compute_status_color")

    value = fields.Char(
        string="Valor medido",
        help="Ej: 5.2 (mm profundidad), 95 (PSI), 3524 (DOT).")
    value_unit = fields.Char(string="Unidad")
    is_measurable = fields.Boolean(
        default=False, string="Requiere valor",
        help="Si el punto requiere una medición numérica concreta.")

    notes = fields.Text(string="Observaciones")
    photo = fields.Image(max_width=1200, max_height=1200)
    photo_filename = fields.Char()

    suggested_service_id = fields.Many2one(
        "product.product", string="Servicio/parte sugerido",
        domain="[('sale_ok','=',True)]",
        help="Si se carga, aparecerá en el botón 'Agregar sugerencias al presupuesto'.")
    suggested_qty = fields.Float(string="Cantidad sugerida", default=1.0)
    tipo_sugerencia = fields.Selection([
        ("fijo", "Fijo"),
        ("dinamico", "Dinámico (resuelve por atributos del vehículo)"),
    ], default="fijo", string="Tipo de sugerencia",
        help="Fijo: usa suggested_service_id tal cual. "
             "Dinámico: resuelve producto en runtime cruzando medida del vehículo "
             "contra el catálogo de cubiertas.")

    @api.depends("status")
    def _compute_status_color(self):
        m = {"ok": 10, "warning": 3, "critical": 1, "replaced": 5, "na": 0}
        for r in self:
            r.status_color = m.get(r.status, 0)

    @api.constrains("status", "photo")
    def _check_photo_required_if_critical(self):
        for r in self:
            if r.status == "critical" and not r.photo:
                raise ValidationError(_(
                    "El punto '%s' está marcado como crítico y requiere una "
                    "foto obligatoria antes de guardar.",
                    r.name))


class WorkshopInspectionTemplate(models.Model):
    _name = "workshop.inspection.template"
    _description = "Punto de Inspección (Plantilla)"
    _order = "category, sequence, id"

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    category = fields.Selection(CATEGORY_SELECTION, required=True)
    value_unit = fields.Char(string="Unidad")
    is_measurable = fields.Boolean(
        default=False, string="Requiere valor")
