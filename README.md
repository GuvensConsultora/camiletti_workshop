# Camiletti Taller

Módulo Odoo 19 para gestión de taller de neumáticos, tren delantero y servicios
mecánicos, con flujo integrado desde lead CRM hasta factura.

## 1. Introducción

**Limitación en Odoo 19 nativo:** ni `repair.order` ni `fsm.order` encajan
conceptualmente con un taller de neumáticos y tren delantero/trasero. `repair`
exige un producto a reparar en el catálogo (pensado para service centers de
electrodomésticos). `fsm` está diseñado para servicio en domicilio del cliente,
con features de ruteo/GPS que en un taller fijo son peso muerto.

**Mejora:** los DMS líderes internacionales (Tekmetric, Shopmonkey, AutoFluent,
Shop-Ware, Mitchell 1, Protractor) modelan cotización → OT → factura como **el
mismo documento con estados**, no como entidades separadas. Este módulo adopta
ese patrón extendiendo `sale.order` con los campos de taller estrictamente
necesarios, sin duplicar modelos ni romper la integración nativa con stock,
facturación electrónica ARCA y contabilidad.

Los vehículos del cliente se modelan en un modelo propio `workshop.vehicle`
(**no** en `fleet.vehicle`, que está reservado para flota propia de la
empresa). El vehículo mantiene su propio historial de titulares, independiente
de quién trae el auto al taller o de quién termina facturando.

## 2. Funcionamiento usuario

### 2.1 Los 4 roles cliente-vehículo

Un vehículo puede pasar por situaciones donde el titular, el conductor que lo
trae y el que paga son personas distintas (flotas de empresa, autos de
familiares, clientes corporativos con aprobador dedicado). El módulo separa
estos roles en cada OT:

| Rol | Dónde vive | Editable por OT |
|---|---|---|
| **Titular** | `workshop.vehicle.partner_id` + historial | No — cambia solo al transferir el vehículo |
| **Conductor** | `sale.order.driver_id` | Sí — quien trae el auto ese día |
| **Facturación** | `sale.order.partner_id` (nativo) | Sí — puede ser empresa o persona |
| **Aprobador** | `sale.order.approver_id` | Sí — quien autoriza el presupuesto |

Al elegir el vehículo en la OT se sugieren los 3 otros campos desde el titular
actual, pero cualquiera es editable. Si el vehículo cambia de dueño, se cierra
el registro abierto del historial y se crea uno nuevo; las OTs viejas siguen
apuntando al titular que correspondía en su momento.

### 2.2 Creación de una OT

La OT se crea desde tres puntos:

- **Desde la ficha del vehículo** (`Taller → Vehículos`), botón "Nueva OT".
- **Desde el kanban de OT** (`Taller → Órdenes de Taller`), con "Crear".
- **Desde un lead de CRM** en etapa Diagnóstico: matching automático de bahía
  y técnico según el equipamiento requerido del servicio.

Datos mínimos: cliente, vehículo (patente), km al ingreso. La OT arranca en
estado **Recibido**.

### 2.3 Las 6 etapas del taller

| Etapa | Qué pasa | Botón principal |
|---|---|---|
| Recibido | Auto ingresó, OT abierta | "Iniciar Diagnóstico" o "Pasar a Presupuesto" |
| Diagnóstico | Técnico revisa con DVI, arma la lista | "Pasar a Presupuesto" |
| Presupuestado | Cotización enviada al cliente | "Registrar Aprobación" |
| En reparación | Cliente aprobó, técnico trabajando | "Marcar Listo" |
| Listo | Trabajo terminado, esperando retiro | "Entregar y Facturar" |
| Entregado | Auto entregado y facturado | — |

Las etapas **no son secuenciales forzadas**. Un pedido telefónico arranca
directo en *Presupuestado*; un walk-in con decisión tomada se saltea
*Diagnóstico*. Cada transición está autorizada por rol y valida pre-condiciones.

### 2.4 Guards (puntos de control)

El módulo bloquea transiciones que no cumplan condiciones:

- `→ Diagnóstico`: requiere técnico asignado; crea automáticamente la
  inspección DVI con los 44 puntos del template.
- `→ Presupuestado`: requiere líneas con precio y DOT cargado si hay neumáticos.
- `→ En reparación`: requiere aprobación del cliente registrada (con el modo:
  WhatsApp, firma, mail, etc.). Dispara el `action_confirm` nativo → reserva
  de stock.
- `→ Listo`: requiere que todos los items de línea estén marcados terminados.
- `→ Entregado`: requiere km al egreso cargado y mayor o igual al km de
  ingreso; actualiza el odómetro del vehículo automáticamente.

### 2.5 DVI — inspección vehicular digital

Al entrar en **Diagnóstico** se genera automáticamente una `workshop.inspection`
con 44 puntos agrupados en 9 categorías (frenos, suspensión, dirección,
neumáticos, motor, transmisión, eléctrico, refrigeración, seguridad). Cada punto
se marca como OK / atención / urgente, con fotos adjuntas opcionales. Desde los
puntos en "urgente" se puede generar sugerencias de línea para la cotización.

### 2.6 Kanban visual

El tablero principal agrupa las OT por estado con color semántico por columna.
El operador arrastra la tarjeta del auto de columna a columna. Cada tarjeta
muestra patente, cliente, técnico asignado, total, progreso y alerta visual si
está esperando aprobación.

### 2.7 Trazabilidad warranty Michelín

Cada línea de neumático exige DOT (semana+año de fabricación, formato WWYY)
antes de presupuestar. Con el DOT cargado, ante un reclamo Michelín se responde
con un filtro sobre `sale.order.line` por DOT o por cliente.

### 2.8 Bahías y matching de recursos

El taller se modela como un conjunto de bahías (`workshop.bay`) con:
- Tipo de vehículo admitido (auto, camioneta, camión).
- Equipamiento instalado (elevador, alineadora, balanceadora).
- Técnico por defecto.

Cada `appointment.type` declara el equipamiento requerido. Al pasar un lead a
Diagnóstico o al crear una OT desde turno, el sistema matchea automáticamente
la bahía con el equipo correcto y sugiere el técnico por default.

### 2.9 No-show y walk-in

- **No-show**: un cron diario identifica turnos sin OT creada 1 hora después
  de la hora prevista y suma 1 al contador `res.partner.no_show_count`. Clientes
  con más de N no-shows quedan marcados para requerir seña previa.
- **Walk-in**: desde el botón "Walk-in" en el kanban de turnos se arma una OT
  al vuelo sin necesidad de lead previo.

## 3. Parametrización

### 3.1 Grupos de seguridad

| Grupo | Permisos |
|---|---|
| Taller / Recepción | Crea OT, toma datos vehículo, emite presupuestos, registra aprobación, entrega |
| Taller / Técnico | Lee vehículos, ejecuta diagnóstico y reparación, marca items terminados |
| Taller / Gerente | Todos los permisos + puede anular guards con justificación en chatter |

### 3.2 Categoría "Neumáticos"

El módulo crea la categoría `product.category` **Neumáticos** bajo *Goods*. Los
productos con esa categoría (o subcategorías) se consideran neumáticos y
disparan la validación de DOT. Si el plan de cuentas ya tiene otra categoría
equivalente, reasignar los productos o ajustar el método `_is_tire()` en
`sale_order_line.py`.

### 3.3 Técnicos

Los técnicos son usuarios internos (no portal). Asignación en el campo
`technician_id` de la OT. Filtro "Asignadas a mí" disponible.

### 3.4 Canned jobs / plantillas

Usar **`sale.order.template`** nativo de Odoo. Crear una plantilla por servicio
frecuente (ej: "Montaje 4 neumáticos + balanceo + rotación") con las líneas
prearmadas. Al crear la OT, elegir la plantilla y las líneas se cargan con un
click. El módulo incluye plantillas base en `data/sale_order_template_data.xml`.

### 3.5 Bahías y equipamiento

Cargar bahías reales del taller en `Taller → Configuración → Bahías`. Cada una
apunta a los `workshop.equipo` instalados. El matching automático usa estos
datos para asignar turno.

## 4. Referencia técnica

### 4.1 Modelos propios

- **`workshop.vehicle`**: vehículo del cliente. Campos: `license_plate` (con
  validación AR), `partner_id` (titular actual), `owner_history_ids`,
  `previous_owner_ids`, `brand`, `vehicle_model`, `year`, `color`,
  `vehicle_type`, `fuel_type`, `odometer`, `service_order_ids` (O2m a
  `sale.order`). Override de `create`/`write` mantiene el historial sincronizado
  con cambios de `partner_id`.
- **`workshop.vehicle.owner.history`**: una fila por período de titularidad.
  Campos: `vehicle_id`, `partner_id`, `date_from`, `date_to`, `is_current`
  (computed), `notes`. Constraint gist garantiza un único registro abierto
  (`date_to=False`) por vehículo.
- **`workshop.inspection`**, **`workshop.inspection.template`**,
  **`workshop.inspection.line`**: DVI con 44 puntos templates vs relevamiento.
- **`workshop.bay`**: delegación de `appointment.resource` con tipo de vehículo
  admitido, equipamiento, técnico default.
- **`workshop.equipo`**: catálogo de equipamiento.

### 4.2 Extensiones sobre nativo

- **`sale.order`**: `workshop_state` (Selection, 7 valores), `vehicle_id`,
  `license_plate` (related), `km_in`, `km_out`, `technician_id`, `bay_id`,
  `driver_id`, `approver_id`, `inspection_id`, `customer_approved`,
  `approval_note`, `diagnosis_notes`, `diagnosis_done`. Computed:
  `workshop_color`, `workshop_progress`, `workshop_next_action`,
  `workshop_helper`.
- **`sale.order.line`**: `dot_code`, `installed_position`, `workshop_done`,
  `is_tire_line` (computed).
- **`res.partner`**: flags de autorización y contador de no-shows.
- **`appointment.type`**: equipamiento requerido para matching de bahía.
- **`crm.lead`**: vehículo, DVI, walk-in directo.
- **`calendar.event`**: integración con turnos de appointment.

### 4.3 Métodos de transición

Cada transición es un método `action_workshop_*` que valida guards, hace la
transición y (si corresponde) dispara el método nativo del SO (`action_confirm`,
`action_quotation_sent`, creación de factura, etc.). Definidos en
`sale_order.py`:

- `action_workshop_receive()`
- `action_workshop_start_diagnosis()` → crea DVI
- `action_workshop_to_quote()`
- `action_workshop_register_approval()`
- `action_workshop_start_repair()` → dispara action_confirm
- `action_workshop_mark_ready()`
- `action_workshop_deliver()` → actualiza odómetro
- `action_workshop_cancel()`
- `action_workshop_reopen()`

El diccionario `ALLOWED_TRANSITIONS` en el mismo archivo define las
transiciones permitidas desde cada estado.

### 4.4 Vistas

- `view_sale_order_form_workshop`: hereda el form nativo con header de botones
  contextuales, banner de ayuda, statusbar del taller, pestaña "Taller".
- `view_sale_order_kanban_workshop`: kanban propio agrupado por
  `workshop_state`, no reemplaza el kanban nativo de ventas.
- `view_workshop_vehicle_form/list/kanban/search`: ficha y listados del
  vehículo; el form incluye pestaña "Titulares" con editable list del historial.
- `view_workshop_inspection_form`: DVI interactivo con grupos por categoría.

### 4.5 Assets (UX)

`static/src/scss/workshop.scss` implementa la paleta semántica por etapa,
botones CTA destacados (Von Restorff), banner contextual, progress bar y
tarjetas kanban con borde izquierdo coloreado.

### 4.6 Dependencias

`sale_management`, `sale_stock`, `l10n_ar_edi`, `portal`, `contacts`, `crm`,
`calendar`, `appointment`.

**No** depende de `fleet` ni de `repair` ni de `industry_fsm`.

## 5. Instalación

Como submódulo git del proyecto principal de la instancia:

```bash
git submodule add -b 19.0 \
  https://github.com/GuvensConsultora/camiletti_workshop.git \
  camiletti_workshop
git commit -m "chore: add camiletti_workshop submodule"
git push
```

En odoo.sh el rebuild detecta el addon automáticamente. Para instalar en la
base: `Apps → Update Apps List → buscar "Camiletti Taller" → Install`.

Para upgrade tras nuevos commits:

```bash
git submodule update --remote camiletti_workshop
git commit -am "chore: bump camiletti_workshop"
git push
```

Tras el rebuild, `Apps → camiletti_workshop → Upgrade` aplica las migraciones.

## 6. Roadmap

### Próximo (Fase 3)

- Matrix pricing de partes (markup por costo × categoría × tipo cliente).
- GBB (Good-Better-Best) con 3 opciones en la misma cotización.
- Catálogo de operaciones de labor con tiempos estándar.
- Tire fitment database (medidas OEM por marca/modelo/año).

### Posterior

- Integración WhatsApp Business (Odoo Enterprise nativo).
- Métricas de taller (conversion rate, ticket promedio, tiempo ciclo OT).
- Reporte sell-out Michelín (export del portal B2B).

## 7. Changelog

- **19.0.1.4.0** — 4 roles cliente-vehículo (titular / conductor / facturación /
  aprobador). Nuevo `workshop.vehicle.owner.history` con constraint gist para
  un titular actual por vehículo. Sacado el domain restrictivo que exigía
  `sale.order.partner_id == vehicle.partner_id`.
- **19.0.1.3.1** — Fix visibilidad vehículo/medida en form CRM cuando el lead
  está en modo opportunity.
- **19.0.1.3.0** — Fix `ir.cron` para Odoo 19 (remoción de `numbercall`/`doall`).
- **19.0.1.2.x** — Flujo CRM → DVI → cotización con matching automático de
  bahía y técnico al entrar en etapa Diagnóstico.
- **19.0.1.1.x** — DVI (Digital Vehicle Inspection) con 44 puntos en 9
  categorías.
- **19.0.1.0.x** — Modelo `workshop.bay` con bahías estándar y equipamiento.
- **19.0.1.0.0** — MVP: 6 estados de taller, `workshop.vehicle`, extensión
  `sale.order`, validación DOT Michelín, kanban visual.

---

**Autor:** Yagüven C.G. · **Licencia:** LGPL-3 · **Versión Odoo:** 19.0+e
