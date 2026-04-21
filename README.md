# Camiletti Taller

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
empresa).

## 2. Funcionamiento usuario

### 2.1 Creación de una OT

La OT se crea desde dos puntos:

- **Desde la ficha del vehículo** (`Taller → Vehículos`), botón "Nueva OT".
- **Desde el kanban** (`Taller → Órdenes de Taller`), con "Crear".

Datos mínimos: cliente, vehículo (patente), km al ingreso. La OT arranca en
estado **Recibido**.

### 2.2 Las 6 etapas del taller

| Etapa | Qué pasa | Botón principal |
|---|---|---|
| Recibido | Auto ingresó, OT abierta | "Iniciar Diagnóstico" o "Pasar a Presupuesto" |
| Diagnóstico | Técnico revisa y arma la lista | "Pasar a Presupuesto" |
| Presupuestado | Cotización enviada al cliente | "Registrar Aprobación" |
| En reparación | Cliente aprobó, técnico trabajando | "Marcar Listo" |
| Listo | Trabajo terminado, esperando retiro | "Entregar y Facturar" |
| Entregado | Auto entregado y facturado | — |

Las etapas **no son secuenciales forzadas**. Un pedido telefónico arranca
directo en *Presupuestado*; un walk-in con decisión tomada se saltea
*Diagnóstico*. Cada transición está autorizada por rol y valida pre-condiciones.

### 2.3 Guards (puntos de control)

El módulo bloquea transiciones que no cumplan condiciones:

- `→ Presupuestado`: requiere líneas con precio y DOT cargado si hay neumáticos.
- `→ En reparación`: requiere aprobación del cliente registrada (con el modo).
- `→ Listo`: requiere que todos los items de línea estén marcados terminados.
- `→ Entregado`: requiere km al egreso cargado y mayor o igual al km de ingreso.

### 2.4 Kanban visual

El tablero principal agrupa las OT por estado con color semántico por columna.
El operador arrastra la tarjeta del auto de columna a columna. Cada tarjeta
muestra patente, cliente, técnico asignado, total, progreso y alerta visual si
está esperando aprobación.

### 2.5 Trazabilidad warranty Michelín

Cada línea de neumático exige DOT (semana+año de fabricación, formato WWYY)
antes de presupuestar. Con el DOT cargado, ante un reclamo Michelín se responde
con un filtro sobre `sale.order.line` por DOT o por cliente.

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
click.

## 4. Referencia técnica

### 4.1 Modelos

- **`workshop.vehicle`**: vehículo del cliente. Campos: `license_plate` (con
  validación AR), `partner_id`, `brand`, `model`, `year`, `color`,
  `vehicle_type`, `odometer`, `service_order_ids` (O2m a `sale.order`).
- **`sale.order` (extensión)**: `workshop_state` (Selection, 7 valores),
  `vehicle_id`, `km_in`, `km_out`, `technician_id`, `customer_approved`,
  `approval_note`, `diagnosis_notes`, `diagnosis_done`. Computados:
  `workshop_color`, `workshop_progress`, `workshop_next_action`,
  `workshop_helper`.
- **`sale.order.line` (extensión)**: `dot_code`, `installed_position`,
  `workshop_done`, `is_tire_line` (computed).

### 4.2 Métodos de transición

Cada transición es un método `action_workshop_*` que valida guards, hace la
transición y (si corresponde) dispara el método nativo del SO (`action_confirm`,
`action_quotation_sent`, creación de factura, etc.).

- `action_workshop_receive()`
- `action_workshop_start_diagnosis()`
- `action_workshop_to_quote()`
- `action_workshop_register_approval()`
- `action_workshop_start_repair()`
- `action_workshop_mark_ready()`
- `action_workshop_deliver()`
- `action_workshop_cancel()`
- `action_workshop_reopen()`

### 4.3 Diccionario de transiciones permitidas

Definido en `sale_order.py` como `ALLOWED_TRANSITIONS`. Modificable si cambia
el flujo operativo.

### 4.4 Vistas

- `view_sale_order_form_workshop`: hereda el form nativo con header de botones
  contextuales, banner de ayuda, statusbar del taller, pestaña "Taller".
- `view_sale_order_kanban_workshop`: kanban propio agrupado por
  `workshop_state`, no reemplaza el kanban nativo de ventas.
- `view_workshop_vehicle_form/list/kanban/search`: ficha y listados del
  vehículo.

### 4.5 Assets (UX)

`static/src/scss/workshop.scss` implementa la paleta semántica por etapa,
botones CTA destacados (Von Restorff), banner contextual, progress bar y
tarjetas kanban con borde izquierdo coloreado.

### 4.6 Dependencias

`sale_management`, `sale_stock`, `l10n_ar_edi`, `portal`, `contacts`.

**No** depende de `fleet` ni de `repair` ni de `industry_fsm`.

## 5. Roadmap

### Fase 2 (post-MVP)

- Matrix pricing de partes (markup por costo × categoría × tipo cliente).
- GBB (Good-Better-Best) con 3 opciones en la misma cotización.
- DVI (Digital Vehicle Inspection) con fotos adjuntas por punto de chequeo.
- Catálogo de operaciones de labor con tiempos estándar.
- Tire fitment database (medidas OEM por marca/modelo/año).

### Fase 3

- Integración WhatsApp Business (Odoo Enterprise nativo).
- Métricas de taller (conversion rate, ticket promedio, tiempo ciclo OT).
- Reporte sell-out Michelín (export del portal B2B).

---

**Autor:** Yagüven C.G.
