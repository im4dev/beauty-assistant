# Beauty Assistant - Plan de Desarrollo y Análisis

**Estado del proyecto:** MVP con dashboard funcional  
**Fecha:** Mayo 2026  
**Última actualización:** Hoy

---

## 1. Visión General

Sistema de asistente virtual por WhatsApp para gestionar citas en talleres de belleza. El asistente maneja agendamiento, reagendamiento, cancelaciones, y gestión de lista de espera.

**Stack actual:**
- Backend: Python + FastAPI
- DB: PostgreSQL (via Supabase)
- Frontend: HTML + Vanilla JS + SSE
- LLM: DeepSeek API
- Autenticación: Usuario/contraseña hardcodeados

---

## 2. Funcionalidades Implementadas

### ✅ Completadas

| Feature | Estado | Descripción |
|---------|--------|------------|
| Recepción de mensajes WhatsApp | ✅ | Webhook integrado con Meta Business API |
| Login dashboard | ✅ | Usuario/contraseña en .env |
| Selector de salones | ✅ | Carga desde Supabase |
| Tabla de citas del día | ✅ | Con SSE (tiempo real) |
| Estadísticas (7 días) | ✅ | Confirmadas, canceladas, completadas |
| Filtros por fecha y estado | ✅ | En el dashboard |
| Modelos de BD | ✅ | Salones, clientes, estilistas, servicios, citas, waitlist |
| Enum de estados | ✅ | SCHEDULED, CANCELLED, COMPLETED, RESCHEDULED |

### 🚧 Pendientes (Prioridad Alta)

| Feature | Estado | Prioridad | Descripción |
|---------|--------|-----------|------------|
| Orquestador de conversación | 🚧 | 🔴 CRÍTICA | Flujo principal del LLM |
| Detección de intención | 🚧 | 🔴 CRÍTICA | Agendar/cancelar/reagendar |
| Motor de disponibilidad | 🚧 | 🔴 CRÍTICA | Consultar horarios libres |
| Agendar cita | 🚧 | 🔴 CRÍTICA | Crear appointment en BD |
| Reagendar cita | 🚧 | 🔴 CRÍTICA | Modificar cita existente |
| Cancelar cita | 🚧 | 🔴 CRÍTICA | Cambiar status + gestionar list de espera |
| Gestión de lista de espera | 🚧 | 🔴 CRÍTICA | Cascada inversa (FLEXIBLE only) |
| Notificaciones por WhatsApp | 🚧 | 🔴 CRÍTICA | Enviar respuestas al cliente |
| Recordatorios automáticos | 🚧 | 🟡 ALTA | 24h y 1h antes de cita |
| Notificaciones al salón | 🚧 | 🟡 ALTA | Cancelaciones, nuevas citas |

---

## 3. Requisitos de Negocio (Confirmados)

### Punto 1: Solicitud de cita
```
Usuario: "Quiero una cita"
         ↓
¿Horario específico o automático?
├─ "Automático" → Sugerir más cercano
└─ "Específico" → Preguntar fecha/hora
     ↓
  Validar disponibilidad
  ├─ Disponible → Agendar
  └─ No disponible → Mostrar 3 opciones más cercanas
```

### Punto 2: Consulta de horarios
- Mostrar 3 opciones más cercanas si no hay disponibilidad exacta
- Considerar: fecha, hora, estilista (si especifica)

### Punto 3: Cancelación (REVISADO)
```
Usuario cancela cita
     ↓
Liberar horario
     ↓
Notificar al salón
     ↓
¿Hay lista de espera FLEXIBLE?
├─ Sí → Intentar agendar (cascada inversa)
└─ No → Marcar horario como disponible
```

#### Subcasos de Cancelación

**Caso F: Tiempo de preparación**
- ⚠️ Si se libera horario con <15 min hasta siguiente cita
- ⚠️ Validar que estilista puede hacerlo
- Solución: Agrupar con siguiente horario o descartar

**Caso G: Cascada inversa (SOLO FLEXIBLE)**
```
1. Cliente cancela cita 2pm-2:30pm con María
   → Se libera ese horario
   
2. Buscar lista de espera FLEXIBLE (último → primero)
   → Descartar SPECIFIC (no tocarlos)
   
3. Ofrecerle al último flexible:
   "¿Disponible para Corte a las 2pm con María?"
   
4. Esperar 5 min (timeout)
   ├─ Acepta → Agendar, FIN
   ├─ Rechaza → Siguiente cliente
   └─ No responde → Recordatorio 3 min más
                   ├─ Acepta → Agendar, FIN
                   └─ No → Siguiente
                   
5. Si nadie acepta → Marcar horario disponible
```

**Caso G-2: Múltiples responden "sí"**
- Usar LOCK: Solo el primero que aceptó se agenda
- Otros quedan en lista (no se pierden)
- No revertir a anterior

---

## 4. Arquitectura Actual

```
Cliente WhatsApp
     ↓
Meta Webhook (POST /webhook)
     ↓
webhooks/whatsapp.py (valida firma, extrae mensaje)
     ↓
tenants/resolver.py (identifica salón por número)
     ↓
core/orchestrator.py (STUB - para implementar)
     ↓
     ├─ core/session.py (mantener contexto)
     ├─ core/intent.py (detectar intención)
     ├─ core/llm.py (llamar DeepSeek)
     ↓
appointments/ (lógica de negocio)
├─ create.py
├─ reschedule.py
├─ cancel.py
├─ availability.py
└─ waitlist.py
     ↓
db/models.py (Salons, Clients, Stylists, Appointments, Waitlist, SessionStates)
     ↓
api/routes.py (endpoints para dashboard)
     ↓
notifications/sender.py (enviar por WhatsApp)
```

---

## 5. Estructuras de Datos Actualizadas

### Tabla: waitlist (REVISADA)

```sql
CREATE TABLE waitlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  salon_id UUID NOT NULL REFERENCES salons(id),
  client_id UUID NOT NULL REFERENCES clients(id),
  
  -- Tipo de solicitud
  request_type ENUM('flexible', 'specific'),
  
  -- Para FLEXIBLE: sin preferencias específicas
  -- Para SPECIFIC: preferencias exactas
  preferred_date TIMESTAMP,
  preferred_time TIME,
  preferred_stylist_id UUID REFERENCES stylists(id),
  preferred_service_id UUID REFERENCES services(id),
  
  -- Timestamps
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  
  -- Estado
  is_notified BOOLEAN DEFAULT false,
  rejection_count INT DEFAULT 0,  -- Cuántas veces rechazó
  status ENUM('waiting', 'offered', 'rejected', 'no_response') DEFAULT 'waiting'
);
```

### SessionState (para mantener contexto)

```sql
CREATE TABLE session_states (
  wa_id VARCHAR PRIMARY KEY,
  salon_id UUID NOT NULL REFERENCES salons(id),
  
  -- Estado actual del flujo
  current_step VARCHAR,  -- 'greeting', 'ask_service', 'ask_date', etc.
  
  -- Contexto de la conversación (JSON)
  context_data TEXT,  -- {"service_id": "...", "preferred_date": "...", etc.}
  
  updated_at TIMESTAMP DEFAULT now()
);
```

---

## 6. Flujos Principales a Implementar

### Flujo 1: Agendar Cita (Nuevo cliente)

```
U: "Quiero una cita"
A: "¡Claro! ¿Para cuál servicio?"
U: "Corte de cabello"
A: "¿Prefieres un horario específico o te agendo el más cercano?"
U: "El más cercano"
A: "Tengo disponible hoy a las 3pm con María. ¿Te va?"
U: "Sí"
A: ✓ Cita confirmada. Te recordamos mañana 1 hora antes.
  [Notificar al salón: Nueva cita hoy 3pm - Corte, María, Juan]
```

### Flujo 2: Agendar Cita (Horario específico)

```
U: "Quiero cita el martes a las 2pm"
A: "¿Con cuál estilista prefieres?"
U: "Con María"
A: "Lamentablemente martes 2pm está ocupado. Tengo:
    1️⃣ Martes 2:30pm con María
    2️⃣ Martes 1:30pm con Carlos
    3️⃣ Miércoles 2pm con María"
U: "La 1"
A: ✓ Cita confirmada para martes 2:30pm con María.
```

### Flujo 3: Cancelar Cita

```
U: "Cancelo mi cita del martes"
A: "Entendido. ¿Hay algún motivo?"
U: "No puedo asistir"
A: ✓ Cita cancelada. Esperamos verte pronto.
  
[Backend]
├─ Marcar cita como CANCELLED
├─ Liberar horario martes 2:30pm con María
├─ Buscar lista de espera FLEXIBLE (ordenada inversamente)
├─ Ofrecerle a último flexible: "¿Disponible martes 2:30pm con María?"
├─ Si ACEPTA → Agendar automáticamente
├─ Si RECHAZA/TIMEOUT → Siguiente
└─ Si nadie → Notificar al salón: "Horario libre martes 2:30pm"
```

### Flujo 4: Reagendar Cita

```
U: "Necesito cambiar mi cita"
A: "¿Para cuándo la quieres cambiar?"
U: "Para el jueves a las 4pm"
A: ✓ Cita movida de martes 2:30pm a jueves 4pm.
  
[Backend]
├─ Si nuevo horario está libre → directo
├─ Si está ocupado → mostrar 3 alternativas
└─ Liberar horario anterior (martes 2:30pm)
    └─ Cascada de lista de espera
```

### Flujo 5: Gestión de Lista de Espera (NUEVO)

```
PARTE A: Cliente se pone en lista

U: "No hay horario para mañana?"
A: "Mañana está lleno. ¿Te agrego a lista de espera?"
U: "Sí"
A: ✓ Te notificaremos cuando haya disponibilidad.
   [Tipo: FLEXIBLE - se agenda automáticamente]

---

PARTE B: Se libera horario

[Alguien cancela cita mañana 3pm]
A (al último en lista de espera): "¡Se liberó un horario! 
   ¿Estás disponible mañana 3pm para Corte con María?"
(timeout 5 min)
├─ "Sí" → ✓ Agendado automáticamente
├─ "No" → Pasar al siguiente
└─ Sin respuesta → Recordatorio (3 min más)
                 ├─ "Sí" → Agendado
                 └─ No → Siguiente

[Si nadie flexible acepta]
→ Notificar al salón: "Horario disponible: mañana 3pm"
```

---

## 7. Plan de Desarrollo (Próximos pasos)

### FASE 1: Core del asistente (Semana 1-2)

**Sprint 1.1: Orquestador + Session**
- [ ] Implementar `core/session.py` (guardar contexto en Redis o DB)
- [ ] Implementar `core/orchestrator.py` (flujo principal)
- [ ] Implementar `core/intent.py` (detectar intención con DeepSeek)
- [ ] Implementar `core/llm.py` (wrapper de DeepSeek)

**Sprint 1.2: Lógica de citas**
- [ ] `appointments/availability.py` - Consultar horarios libres
- [ ] `appointments/create.py` - Crear nueva cita
- [ ] Validar conflictos de horarios

### FASE 2: Cancelación y lista de espera (Semana 2-3)

**Sprint 2.1: Cancelación básica**
- [ ] `appointments/cancel.py` - Marcar como cancelada
- [ ] Liberar horario
- [ ] Notificar al salón

**Sprint 2.2: Cascada inversa de lista de espera**
- [ ] `appointments/waitlist.py` - Lógica de cascada
- [ ] Diferenciar FLEXIBLE vs SPECIFIC
- [ ] Timeout de 5 min + recordatorio 3 min
- [ ] Lock para evitar doble-aceptación

**Sprint 2.3: Notificaciones**
- [ ] `notifications/sender.py` - Enviar respuestas por WhatsApp
- [ ] Notificar al salón de cambios
- [ ] Notificar a cliente de lista de espera

### FASE 3: Refinamientos (Semana 3-4)

**Sprint 3.1: Reagendamiento**
- [ ] `appointments/reschedule.py`
- [ ] Liberar anterior + cascada

**Sprint 3.2: Casos edge**
- [ ] Tiempo de preparación (Caso F)
- [ ] Validación de múltiples respuestas (Caso G-2)
- [ ] No-shows y cancelaciones de último momento

**Sprint 3.3: Recordatorios automáticos**
- [ ] `notifications/scheduler.py` (cron jobs)
- [ ] 24 horas antes
- [ ] 1 hora antes

### FASE 4: Validación y polish (Semana 4)

- [ ] Pruebas con cliente real (2 semanas gratis)
- [ ] Ajustes según feedback
- [ ] Documentación de deployment

---

## 8. Cambios en BD Necesarios

```sql
-- Actualizar tabla waitlist
ALTER TABLE waitlist ADD COLUMN request_type ENUM('flexible', 'specific');
ALTER TABLE waitlist ADD COLUMN preferred_time TIME;
ALTER TABLE waitlist ADD COLUMN preferred_stylist_id UUID REFERENCES stylists(id);
ALTER TABLE waitlist ADD COLUMN preferred_service_id UUID REFERENCES services(id);
ALTER TABLE waitlist ADD COLUMN rejection_count INT DEFAULT 0;
ALTER TABLE waitlist ADD COLUMN status ENUM('waiting', 'offered', 'rejected', 'no_response');
ALTER TABLE waitlist ADD COLUMN updated_at TIMESTAMP DEFAULT now();

-- Crear tabla session_states si no existe
CREATE TABLE IF NOT EXISTS session_states (
  wa_id VARCHAR PRIMARY KEY,
  salon_id UUID NOT NULL REFERENCES salons(id),
  current_step VARCHAR,
  context_data TEXT,
  updated_at TIMESTAMP DEFAULT now()
);
```

---

## 9. Decisiones de Diseño Importantes

### 🔴 Decisión 1: Cascada INVERSA para lista de espera
- **Por qué:** Minimizar notificaciones (solo 1 oferta por hueco)
- **Alternativa rechazada:** Cascada normal (uno tras otro)
- **Impacto:** Los últimos en lista tienen mayor chance

### 🔴 Decisión 2: NO tocar SPECIFIC en cascada
- **Por qué:** Respetan sus preferencias exactas
- **Alternativa rechazada:** Ofrecerles alternativas
- **Impacto:** Clientes specific esperan más, pero no se molestan

### 🔴 Decisión 3: Lock optimista (pending_response)
- **Por qué:** Evitar vender mismo horario a dos personas
- **Alternativa rechazada:** Transacciones DB
- **Impacto:** Más simple, menos overhead

### 🔴 Decisión 4: Timeout 5+3 min (no respuesta)
- **Por qué:** Balance entre oportunidad y tiempo
- **Alternativa:** 2+2, 10+5, etc.
- **Impacto:** A validar con cliente real

---

## 10. Métricas de Éxito

| Métrica | Meta | Método |
|---------|------|--------|
| Tiempo promedio de agendamiento | <2 min | Logs del LLM |
| Tasa de aceptación en cascada | >60% | Dashboard analytics |
| No-shows reducidos | -30% vs manual | Estadísticas |
| Satisfacción cliente | >4/5 | Encuesta post-2 semanas |
| Disponibilidad (uptime) | >99% | Monitoring |

---

## 11. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|--------|-----------|
| DeepSeek API caída | Media | Alto | Fallback a respuestas predefinidas |
| Timeout en cascada muy corto | Media | Medio | A/B test con 5 clientes |
| Cliente específico se enoja por cambio | Baja | Alto | Documentar bien el sistema |
| Doble-aceptación no detectada | Baja | Muy Alto | Tests unitarios, logs |
| DB se llena de session_states | Baja | Medio | Cleanup de sessions >24h |

---

## 12. Preguntas Abiertas

1. ¿Qué pasa si un cliente en lista de espera pide ver disponibilidad? ¿Se le muestra?
2. ¿Notificar a SPECIFIC cuando se libera su horario exacto? (Actualmente NO)
3. ¿Máximo de reintentos con no-respuesta antes de sacarlo de lista?
4. ¿Los horarios liberados se ofrecen con cualquier estilista o preferir el mismo?
5. ¿Penalidad si cliente FLEXIBLE rechaza más de X veces?

---

## 13. Roadmap Futuro (Post-MVP)

- [ ] Integración con Google Calendar
- [ ] Pagos integrados (Stripe)
- [ ] Reportes avanzados
- [ ] Descuentos automáticos por loyalty
- [ ] Reseñas y ratings en WhatsApp
- [ ] Integración con Instagram DM
- [ ] App móvil nativa

---

**Próximo paso:** ¿Empezamos con Sprint 1.1 (Orquestador)? ¿O hay cambios a este plan?