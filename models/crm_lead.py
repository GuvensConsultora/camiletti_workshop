from datetime import datetime, timedelta
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


MEDIDA_ORIGEN = [
    ("declarada", "Declarada por cliente"),
    ("derivada", "Derivada del modelo"),
    ("verificada", "Verificada al llegar"),
]


class CrmLead(models.Model):
    _inherit = "crm.lead"

    vehicle_id = fields.Many2one(
        "workshop.vehicle", string="Vehículo", tracking=True, index=True,
        domain="[('partner_id','=?', partner_id)]")
    license_plate = fields.Char(
        related="vehicle_id.license_plate", string="Patente",
        store=True, readonly=True)
    medida = fields.Char(
        string="Medida de neumático",
        help="Medida relevada (ej. 185/65 R15 91H).")
    medida_origen = fields.Selection(
        MEDIDA_ORIGEN, default="declarada", string="Origen de la medida")

    dvi_id = fields.Many2one(
        "workshop.inspection", string="Inspección DVI",
        copy=False, ondelete="set null", tracking=True)
    dvi_event_id = fields.Many2one(
        "calendar.event", string="Turno de diagnóstico",
        copy=False, ondelete="set null", tracking=True)

    walk_in_directo = fields.Boolean(
        string="Cliente sabe qué busca",
        help="Walk-in directo: saltea diagnóstico, va a presupuesto.")

    es_flota = fields.Boolean(
        string="Cliente flota", compute="_compute_es_flota", store=True,
        help="Marcado cuando el cliente es una empresa (is_company=True).")

    quote_id = fields.Many2one(
        "sale.order", string="Cotización armada",
        copy=False, ondelete="set null")

    @api.depends("partner_id", "partner_id.is_company", "partner_id.parent_id")
    def _compute_es_flota(self):
        for l in self:
            p = l.partner_id
            l.es_flota = bool(
                p and (p.is_company or (p.parent_id and p.parent_id.is_company)))

    def write(self, vals):
        res = super().write(vals)
        if "stage_id" in vals:
            for lead in self:
                lead._workshop_on_stage_change()
        return res

    def _workshop_on_stage_change(self):
        """Si entra a la etapa de diagnóstico, dispara matching + DVI."""
        self.ensure_one()
        stage_xmlid = self._get_stage_xmlid()
        if stage_xmlid != "camiletti_workshop.crm_stage_diagnostico":
            return
        if self.walk_in_directo:
            return
        if self.dvi_event_id and not self.dvi_event_id.workshop_no_show:
            return  # ya tiene turno activo
        if not self.vehicle_id:
            self.message_post(body=_(
                "⚠️ No se puede agendar diagnóstico: el lead no tiene vehículo."))
            return
        appointment_type = self.env["appointment.type"].search(
            [("workshop_is_diagnostic", "=", True)], limit=1)
        if not appointment_type:
            self.message_post(body=_(
                "⚠️ No hay ningún appointment.type marcado como diagnóstico DVI. "
                "Configure uno en Taller → Configuración → Tipos de turno."))
            return
        event = self._workshop_schedule_event(appointment_type)
        inspection = self._workshop_ensure_dvi()
        if event and inspection:
            event.workshop_inspection_id = inspection.id
            self.write({
                "dvi_event_id": event.id,
                "dvi_id": inspection.id,
            })
            self.message_post(body=_(
                "🔧 Turno de diagnóstico agendado: %s en bahía %s%s",
                fields.Datetime.to_string(event.start),
                event.workshop_bay_id.name or "(sin asignar)",
                f" con {event.user_id.name}" if event.user_id else "",
            ))

    def _get_stage_xmlid(self):
        self.ensure_one()
        data = self.env["ir.model.data"].sudo().search([
            ("model", "=", "crm.stage"),
            ("res_id", "=", self.stage_id.id),
        ], limit=1)
        return f"{data.module}.{data.name}" if data else ""

    def _workshop_find_matching_bay(self, appointment_type):
        """Devuelve bahías que aceptan el tipo de vehículo y tienen el equipamiento
        requerido del appointment_type."""
        self.ensure_one()
        domain = [("state", "=", "available")]
        if self.vehicle_id:
            vt = self.vehicle_id.vehicle_type
            if vt in ("auto", "utilitario", "moto", "otro"):
                domain.append(("accepts_auto", "=", True))
            elif vt == "camioneta":
                domain.append(("accepts_camioneta", "=", True))
            elif vt in ("camion", "maquina"):
                domain.append(("accepts_camion", "=", True))
        bahias = self.env["workshop.bay"].search(domain)
        required = appointment_type.equipamiento_requerido_ids
        if required:
            bahias = bahias.filtered(
                lambda b: all(e in b.equipamiento_ids for e in required))
        # Priorizar bahías cuyo técnico por defecto esté en el staff del appointment
        if appointment_type.staff_user_ids:
            bahias = bahias.sorted(
                key=lambda b: (
                    0 if b.tecnico_por_defecto_id
                    and b.tecnico_por_defecto_id in appointment_type.staff_user_ids
                    else 1,
                    b.sequence))
        return bahias

    def _workshop_schedule_event(self, appointment_type):
        """Crea un calendar.event en el primer slot libre (simple greedy).
        Usa appointment.resource del motor nativo."""
        self.ensure_one()
        bahias = self._workshop_find_matching_bay(appointment_type)
        if not bahias:
            self.message_post(body=_(
                "⚠️ No hay bahías compatibles con el vehículo y el equipamiento "
                "requerido por %s.", appointment_type.name))
            return self.env["calendar.event"]
        duration_h = appointment_type.appointment_duration or 0.5
        start = self._workshop_next_business_slot(duration_h)
        stop = start + timedelta(hours=duration_h)

        user = bahias[0].tecnico_por_defecto_id
        if not user and appointment_type.staff_user_ids:
            user = appointment_type.staff_user_ids[0]

        event = self.env["calendar.event"].create({
            "name": _("Diagnóstico DVI — %s", self.name or self.partner_id.name or ""),
            "start": fields.Datetime.to_string(start),
            "stop": fields.Datetime.to_string(stop),
            "user_id": user.id if user else self.env.user.id,
            "partner_ids": [(4, self.partner_id.id)] if self.partner_id else [],
            "appointment_type_id": appointment_type.id,
            "appointment_resource_ids": [(4, bahias[0].resource_id.id)],
            "workshop_lead_id": self.id,
            "workshop_bay_id": bahias[0].id,
        })
        return event

    def _workshop_next_business_slot(self, duration_h):
        """Greedy sencillo: primera hora hábil libre (lun-vie 8–17hs) desde ahora
        en la TZ de la compañía."""
        tz = self.env.user.tz or "America/Argentina/Buenos_Aires"
        now = fields.Datetime.context_timestamp(
            self.with_context(tz=tz), fields.Datetime.now())
        # Próxima franja válida
        cursor = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        for _ in range(14 * 24):  # 2 semanas de margen
            if cursor.weekday() < 5 and 8 <= cursor.hour < 17:
                break
            cursor += timedelta(hours=1)
        # A UTC
        return cursor.astimezone().replace(tzinfo=None)

    def _workshop_ensure_dvi(self):
        """Crea workshop.inspection en borrador si todavía no existe."""
        self.ensure_one()
        if self.dvi_id:
            return self.dvi_id
        vals = {"technician_id": self.user_id.id or self.env.user.id}
        inspection = self.env["workshop.inspection"].create(vals)
        return inspection

    def action_workshop_build_quote(self):
        """Arma la sale.order combinando cubiertas del lead, servicios de plantilla
        y sugerencias de la DVI."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("El lead no tiene cliente asignado."))
        template = self.env.ref(
            "camiletti_workshop.sale_order_template_compra_colocacion",
            raise_if_not_found=False)
        vals = {
            "partner_id": self.partner_id.id,
            "opportunity_id": self.id,
        }
        if template:
            vals["sale_order_template_id"] = template.id
        if self.vehicle_id:
            vals["vehicle_id"] = self.vehicle_id.id
        order = self.env["sale.order"].create(vals)
        if template:
            order._onchange_sale_order_template_id() \
                if hasattr(order, "_onchange_sale_order_template_id") else None
        if self.dvi_id and hasattr(self.dvi_id, "action_add_suggestions_to_quote"):
            self.dvi_id.sale_order_id = order.id
            self.dvi_id.action_add_suggestions_to_quote()
        self.quote_id = order.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Cotización"),
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
        }

    def action_view_quote(self):
        self.ensure_one()
        if not self.quote_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("Cotización"),
            "res_model": "sale.order",
            "res_id": self.quote_id.id,
            "view_mode": "form",
        }

    def action_workshop_reschedule(self):
        """Libera el turno actual y vuelve a disparar matching."""
        self.ensure_one()
        if self.dvi_event_id:
            self.dvi_event_id.unlink()
            self.dvi_event_id = False
        self._workshop_on_stage_change()
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _cron_mark_no_shows(self):
        """Cron: marca como no-show los eventos vencidos hace más de 15 min
        que no pasaron a ejecución."""
        threshold = fields.Datetime.now() - timedelta(minutes=15)
        events = self.env["calendar.event"].sudo().search([
            ("stop", "<", threshold),
            ("workshop_lead_id", "!=", False),
            ("workshop_no_show", "=", False),
        ])
        for ev in events:
            ev.write({"workshop_no_show": True})
            if ev.workshop_lead_id:
                ev.workshop_lead_id.message_post(body=_(
                    "🚫 Turno marcado automáticamente como 'No se presentó' "
                    "(vencido sin ejecución)."))
        return True
