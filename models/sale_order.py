from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


WORKSHOP_STATES = [
    ("received", "Recibido"),
    ("diagnosis", "Diagnóstico"),
    ("quoted", "Presupuestado"),
    ("in_repair", "En reparación"),
    ("ready", "Listo"),
    ("delivered", "Entregado"),
    ("cancelled", "Cancelado"),
]

# Mapa de transiciones permitidas (estado_actual -> set(estados_destino))
ALLOWED_TRANSITIONS = {
    False: {"received", "quoted"},
    "received": {"diagnosis", "quoted", "cancelled"},
    "diagnosis": {"quoted", "cancelled"},
    "quoted": {"in_repair", "cancelled"},
    "in_repair": {"ready", "cancelled"},
    "ready": {"delivered"},
    "delivered": set(),
    "cancelled": {"received"},
}

# Color por estado para kanban (Von Restorff + color semántico)
WORKSHOP_COLORS = {
    "received": 0,       # gris
    "diagnosis": 4,      # celeste
    "quoted": 3,         # amarillo
    "in_repair": 2,      # naranja
    "ready": 10,         # verde
    "delivered": 5,      # teal
    "cancelled": 1,      # rojo
}


class SaleOrder(models.Model):
    _inherit = "sale.order"

    workshop_state = fields.Selection(
        WORKSHOP_STATES, string="Estado de Taller", default="received",
        tracking=True, copy=False, index=True, group_expand="_group_expand_states")

    # ────── Vehículo y datos de servicio ──────
    vehicle_id = fields.Many2one(
        "workshop.vehicle", string="Vehículo", tracking=True, index=True,
        domain="[('partner_id','=',partner_id)]",
        help="Vehículo del cliente sobre el que se realiza el trabajo.")
    license_plate = fields.Char(
        related="vehicle_id.license_plate", string="Patente",
        store=True, readonly=True)
    km_in = fields.Integer(
        string="Km al ingreso", tracking=True,
        help="Lectura del odómetro al recibir el vehículo.")
    km_out = fields.Integer(
        string="Km al egreso", tracking=True,
        help="Lectura del odómetro al entregar el vehículo.")

    technician_id = fields.Many2one(
        "res.users", string="Técnico asignado",
        domain="[('share','=',False)]", tracking=True)

    inspection_id = fields.Many2one(
        "workshop.inspection", string="Inspección DVI",
        copy=False, ondelete="set null", tracking=True,
        help="Inspección vehicular digital asociada a esta OT. "
             "Se crea automáticamente al pasar la OT a Diagnóstico.")

    # ────── Flags de control (guards) ──────
    customer_approved = fields.Boolean(
        string="Aprobación cliente registrada", copy=False, tracking=True,
        help="Marca que el cliente aceptó el presupuesto (firma, WhatsApp, mail).")
    approval_note = fields.Char(
        string="Modo de aprobación",
        help="Ej: 'OK por WhatsApp 20/04', 'Firma en OT impresa', 'Mail del 21/04'.")
    diagnosis_notes = fields.Html(string="Diagnóstico")
    diagnosis_done = fields.Boolean(
        string="Diagnóstico finalizado", copy=False, tracking=True)

    # ────── Progreso visual ──────
    workshop_color = fields.Integer(
        compute="_compute_workshop_color", string="Color")
    workshop_progress = fields.Integer(
        compute="_compute_workshop_progress", string="Progreso %")
    workshop_next_action = fields.Char(
        compute="_compute_workshop_next_action",
        string="¿Qué hacer ahora?")

    # ────── Helpers contextuales (ayudas neurociencia) ──────
    workshop_helper = fields.Html(
        compute="_compute_workshop_helper", string="Guía de etapa",
        help="Mensaje contextual que orienta al operador sobre la acción actual.")

    @api.model
    def _group_expand_states(self, states, domain):
        return [s for s, _ in WORKSHOP_STATES if s != "cancelled"]

    @api.depends("workshop_state")
    def _compute_workshop_color(self):
        for o in self:
            o.workshop_color = WORKSHOP_COLORS.get(o.workshop_state, 0)

    @api.depends("workshop_state")
    def _compute_workshop_progress(self):
        # Recibido 10 · Diagnóstico 25 · Presupuestado 45 · En reparación 70 · Listo 90 · Entregado 100
        m = {"received": 10, "diagnosis": 25, "quoted": 45,
             "in_repair": 70, "ready": 90, "delivered": 100, "cancelled": 0}
        for o in self:
            o.workshop_progress = m.get(o.workshop_state, 0)

    @api.depends("workshop_state")
    def _compute_workshop_next_action(self):
        m = {
            "received": _("Iniciar diagnóstico o armar presupuesto directo"),
            "diagnosis": _("Completar diagnóstico y pasar a presupuesto"),
            "quoted": _("Enviar cotización y registrar aprobación del cliente"),
            "in_repair": _("Ejecutar trabajo y marcar listo cuando termine"),
            "ready": _("Avisar al cliente que puede retirar"),
            "delivered": _("OT cerrada"),
            "cancelled": _("OT cancelada"),
        }
        for o in self:
            o.workshop_next_action = m.get(o.workshop_state, "")

    @api.depends("workshop_state", "customer_approved", "km_in", "km_out")
    def _compute_workshop_helper(self):
        """
        Mensajes guía por etapa, inspirados en UX basado en carga cognitiva:
        - Una acción principal por pantalla
        - Lenguaje corto, directo
        - Foco en el siguiente paso
        """
        msgs = {
            "received": _(
                "🚗 <b>Auto recibido.</b> Confirmá cliente, patente y km. "
                "Elegí el camino: iniciar diagnóstico (si hay síntomas) o "
                "saltar directo a presupuesto (si el cliente ya sabe qué quiere)."),
            "diagnosis": _(
                "🔍 <b>Diagnóstico.</b> Cargá lo que encontraste en el bloque "
                "<i>Diagnóstico</i>, y agregá las líneas de partes y servicios "
                "necesarios. Cuando termines, tocá <b>Pasar a Presupuesto</b>."),
            "quoted": _(
                "💬 <b>Esperando aprobación.</b> Enviá la cotización al cliente "
                "(mail / WhatsApp / impresa). Cuando confirme, marcá "
                "<b>Registrar aprobación</b> con el modo (WhatsApp, firma, etc.)."),
            "in_repair": _(
                "🔧 <b>En reparación.</b> El técnico está trabajando. "
                "Stock reservado. Cuando terminen todos los items, "
                "tocá <b>Marcar listo</b>."),
            "ready": _(
                "✅ <b>Trabajo terminado.</b> Avisá al cliente que puede retirar. "
                "Al entregar, cargá km de egreso y tocá <b>Entregar + Facturar</b>."),
            "delivered": _(
                "🏁 <b>OT entregada.</b> El trabajo cerró. Si hubo warranty "
                "Michelín, verificá que los DOTs estén cargados por si hay reclamo."),
            "cancelled": _(
                "⛔ <b>OT cancelada.</b> El trabajo no se realizó. "
                "Si cambia el criterio, podés reabrir a Recibido."),
        }
        for o in self:
            o.workshop_helper = msgs.get(o.workshop_state, "")

    # ───────────────────────────── Transiciones ─────────────────────────────

    def _check_transition(self, new_state):
        """Valida que la transición desde el estado actual sea permitida."""
        for o in self:
            allowed = ALLOWED_TRANSITIONS.get(o.workshop_state, set())
            if new_state not in allowed:
                raise UserError(_(
                    "No se puede pasar de '%(from)s' a '%(to)s'. "
                    "Transiciones permitidas desde acá: %(allowed)s.",
                    **{
                        "from": dict(WORKSHOP_STATES).get(o.workshop_state, "—"),
                        "to": dict(WORKSHOP_STATES).get(new_state, new_state),
                        "allowed": ", ".join(
                            dict(WORKSHOP_STATES).get(s, s) for s in allowed
                        ) or "ninguna",
                    }))

    def _guard_required_fields(self, fields_list, error_msg):
        for o in self:
            for f in fields_list:
                if not o[f]:
                    raise UserError(error_msg)

    # ─── Recibido ───
    def action_workshop_receive(self):
        self._check_transition("received")
        self._guard_required_fields(
            ["partner_id", "vehicle_id"],
            _("Para recibir el auto, cargá cliente y vehículo."))
        self.write({"workshop_state": "received"})
        return self._notify_stage_change(_("Auto recibido en taller"))

    # ─── Diagnóstico ───
    def action_workshop_start_diagnosis(self):
        self._check_transition("diagnosis")
        self._guard_required_fields(
            ["technician_id"],
            _("Asigná un técnico antes de empezar el diagnóstico."))
        # Crear la inspección DVI con los 44 puntos del template si no existe
        for o in self:
            if not o.inspection_id:
                insp = self.env["workshop.inspection"].create({
                    "sale_order_id": o.id,
                    "technician_id": o.technician_id.id,
                })
                o.inspection_id = insp.id
        self.write({"workshop_state": "diagnosis"})
        return self._notify_stage_change(_("Diagnóstico iniciado"))

    def action_view_inspection(self):
        self.ensure_one()
        if not self.inspection_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "workshop.inspection",
            "res_id": self.inspection_id.id,
            "view_mode": "form",
        }

    # ─── Presupuestado ───
    def action_workshop_to_quote(self):
        self._check_transition("quoted")
        self._guard_lines_ready_for_quote()
        self.write({"workshop_state": "quoted"})
        # Mueve el state comercial a 'sent' al emitir la cotización
        if self.state == "draft":
            self.action_quotation_sent()
        return self._notify_stage_change(_("Pasado a Presupuestado"))

    def _guard_lines_ready_for_quote(self):
        for o in self:
            if not o.order_line:
                raise UserError(_(
                    "No se puede presupuestar sin líneas. "
                    "Agregá al menos una parte o servicio."))
            for l in o.order_line.filtered(lambda x: not x.display_type):
                if l.price_unit <= 0:
                    raise UserError(_(
                        "La línea '%s' no tiene precio cargado.", l.name))
                # DOT obligatorio si es neumático
                if l._is_tire() and not l.dot_code:
                    raise UserError(_(
                        "El neumático '%s' necesita el DOT cargado antes "
                        "de presupuestar (requerido por garantía Michelín).",
                        l.product_id.display_name))

    # ─── Aprobación + En reparación ───
    def action_workshop_register_approval(self):
        for o in self:
            if o.workshop_state != "quoted":
                raise UserError(_(
                    "La aprobación solo se registra en estado Presupuestado."))
            if not o.approval_note:
                raise UserError(_(
                    "Ingresá el modo de aprobación (ej: 'OK por WhatsApp 20/04')."))
        self.write({"customer_approved": True})
        for o in self:
            o.message_post(body=_(
                "Aprobación cliente registrada: %s", o.approval_note))

    def action_workshop_start_repair(self):
        self._check_transition("in_repair")
        for o in self:
            if not o.customer_approved:
                raise UserError(_(
                    "No se puede iniciar la reparación sin aprobación del cliente. "
                    "Registrá primero la aprobación."))
        # Confirma el SO nativo → reserva stock
        for o in self:
            if o.state == "draft" or o.state == "sent":
                o.action_confirm()
        self.write({"workshop_state": "in_repair"})
        return self._notify_stage_change(_("Reparación iniciada"))

    # ─── Listo ───
    def action_workshop_mark_ready(self):
        self._check_transition("ready")
        for o in self:
            pending = o.order_line.filtered(
                lambda l: not l.display_type and not l.workshop_done)
            if pending:
                raise UserError(_(
                    "Hay items sin marcar terminados: %s",
                    ", ".join(pending.mapped("name")[:5])))
        self.write({"workshop_state": "ready"})
        return self._notify_stage_change(_("Trabajo terminado. Listo para retirar"))

    # ─── Entregado ───
    def action_workshop_deliver(self):
        self._check_transition("delivered")
        for o in self:
            if not o.km_out:
                raise UserError(_(
                    "Cargá los km al egreso antes de entregar."))
            if o.km_in and o.km_out < o.km_in:
                raise ValidationError(_(
                    "Km egreso (%(out)s) no puede ser menor que km ingreso (%(in)s).",
                    out=o.km_out, **{"in": o.km_in}))
        self.write({"workshop_state": "delivered"})
        # Actualiza odómetro del vehículo
        for o in self.filtered(lambda r: r.vehicle_id and r.km_out):
            if o.km_out > (o.vehicle_id.odometer or 0):
                o.vehicle_id.odometer = o.km_out
        return self._notify_stage_change(_("Auto entregado"))

    # ─── Cancelar / Reabrir ───
    def action_workshop_cancel(self):
        self._check_transition("cancelled")
        self.write({"workshop_state": "cancelled"})
        for o in self:
            if o.state not in ("cancel", "done"):
                o._action_cancel()
        return self._notify_stage_change(_("OT cancelada"))

    def action_workshop_reopen(self):
        for o in self:
            if o.workshop_state != "cancelled":
                raise UserError(_("Solo OTs canceladas pueden reabrirse."))
        self.write({"workshop_state": "received"})

    # ────── Helpers ──────
    def _notify_stage_change(self, message):
        for o in self:
            o.message_post(
                body=_("<b>%s</b><br/>Próxima acción: %s",
                       message, o.workshop_next_action or "—"))
        return True

    @api.onchange("partner_id")
    def _onchange_partner_clear_vehicle(self):
        for o in self:
            if o.vehicle_id and o.vehicle_id.partner_id != o.partner_id:
                o.vehicle_id = False

    @api.onchange("vehicle_id")
    def _onchange_vehicle_suggest_km(self):
        for o in self:
            if o.vehicle_id and not o.km_in:
                o.km_in = o.vehicle_id.odometer or 0
