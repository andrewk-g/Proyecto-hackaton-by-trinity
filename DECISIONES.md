# Decisiones acordadas

Contrato del equipo. **Nadie programa algo que no esté aquí.** Si algo cambia, se cambia primero en este documento y luego en el código.

Estado: ✅ cerrado · 🟡 pendiente de discutir

---

## 0. Principios

| # | Principio |
|---|---|
| P1 | **Una sola fuente de verdad.** Todos los parámetros viven en un archivo de configuración (YAML). Backend, interfaz (`/api/config`), prompt de la IA y validador de la IA leen de ahí. Nadie copia valores a mano. |
| P2 | **La configuración se valida al arrancar y al recargar.** Si es incoherente, se muestra el error exacto y se conserva la última configuración válida. |
| P3 | **La IA clasifica lo ambiguo; las reglas deciden las consecuencias.** Área responsable, impacto e inhabilitación los decide una regla determinista, nunca la IA. |
| P4 | **Nunca se simula la IA.** Si falla, el sistema lo dice y pasa a clasificación manual. |
| P5 | **Los datos originales son inmutables.** Las operaciones se guardan aparte, con auditoría. |
| P6 | **Mandan los datos oficiales (D4).** Sus catálogos se adoptan tal cual y se mapean a *significados* en la configuración. Las reglas trabajan sobre significados, nunca sobre texto literal. |

## 1. Convenciones globales ✅

| Convención | Valor |
|---|---|
| Zona horaria | `America/Bogota` |
| Fechas | ISO 8601 |
| Duraciones | Siempre en **minutos** |
| Intervalos | Semiabiertos `[inicio, fin)` (8:00–10:00 y 10:00–12:00 no chocan) |
| Identidad | Selector "Actuando como" con las personas del dataset, sin login |
| Datos personales | Solo los del dataset oficial; en pruebas, nombres ficticios |

## 2. Catálogos y datos (D4) ✅

- Los valores del dataset (estados, tipos, roles) se usan tal cual en BD e interfaz.
- La configuración mapea cada valor a un significado. Ejemplo:
  ```yaml
  estados_recurso:
    "Operativo":         disponible
    "En uso":            prestado
    "Fuera de servicio": inhabilitado
  ```
- Valor del dataset sin mapeo → **cuarentena** con motivo.

### Importación
| Situación | Resultado |
|---|---|
| Espacios sobrantes, mayúsculas, formatos de fecha | Corrección automática (registrada) |
| ID duplicado | Gana el primero; el resto a cuarentena |
| Referencia rota (recurso → espacio inexistente) | Cuarentena |
| Fechas inconsistentes (devolución antes del préstamo, "devuelto" sin fecha) | Cuarentena |
| Tipo de recurso sin pool | Cuarentena |
| Sin columna de tipo de recurso | Todo al pool `General` (portátil) con aviso |
| Aforo vacío, 0 o negativo | Cuarentena |
| Aforo distinto al de referencia | Manda el dataset; aviso visible |
| Reserva histórica que excede el aforo | Se importa tal cual, marcada como inconsistente |
| Reserva sin número de asistentes | Se importa con asistentes = desconocido |

- La cuarentena **nunca se borra** y se puede **reprocesar** tras ajustar la configuración.
- Botón **"Recargar configuración"** y **"Reprocesar cuarentena"** (Administrativo y TI).

## 3. Roles y permisos ✅

Los roles se mapean desde el dataset. Trainer y Teacher tienen los mismos permisos.

| Acción | Trainer | Teacher | Administrativo | TI |
|---|---|---|---|---|
| Reservar espacios | ✅ | ✅ | ✅ (para cualquiera) | — |
| Pedir préstamos | ✅ | ✅ | ✅ | — |
| Reportar incidencias | ✅ | ✅ | ✅ | ✅ |
| Verificar incidencias | — | — | ✅ infraestructura | ✅ equipos |
| Rehabilitar (D3) | — | — | — | ✅ |
| Gestionar conflictos (D2) | — | — | ✅ | — |
| Recargar configuración / cuarentena | — | — | ✅ | ✅ |

Fuera del MVP: campers como usuarios.

## 4. Espacios ✅

Sin pools ni sectores. Aforo oficial de referencia:

| Espacio | Aforo | Sala grande | Mínimo (R8) | PCs |
|---|---|---|---|---|
| Auditorio | 100 | ✅ | 30 | — |
| Sputnik | 38 | ✅ | 12 | ✅ |
| Apolo | 34 | ✅ | 11 | — |
| Artemis | 32 | ✅ | 10 | ✅ |
| Cosmos | 25 | ✅ | 8 | — |
| Skilab | 20 | ✅ | 6 | ✅ |
| Blanca | 12 | — | — | — |
| Azul | 10 | — | — | — |
| Amarillas | 6 | — | — | — |
| Verdes | 6 | — | — | — |

### Elementos de los espacios e impacto

Elementos comunes a todos los espacios:

| Elemento | Impacto | Área |
|---|---|---|
| Internet | ⛔ Invalida (excepto Auditorio: ⚠️ degrada) | TI |
| Televisor | ⚠️ Degrada | TI |
| A.C. | ⚠️ Degrada | Administrativo |
| Lector de pines | ⚠️ Degrada | TI |
| Tableros | ➖ No afecta | Administrativo |
| Sillas | ➖ No afecta | Administrativo |
| **PC** (Sputnik, Artemis, Skilab) | ⚠️ Degrada; ⛔ invalida si dañados ≥ ⌊aforo / 2⌋ + 1 | TI |

- **Invalida:** el espacio se inhabilita y sus reservas pasan a D2.
- **Degrada:** el espacio sigue disponible; sus reservas reciben un aviso.
- **No afecta:** solo se abre la incidencia.
- **PCs:** cada uno tiene ID. Umbrales: Sputnik 20, Artemis 17, Skilab 11. El tipo de impacto "umbral" es genérico (aplicable a cualquier elemento por configuración).
- Los elementos **no se prestan**.

```yaml
elementos_base:
  internet:      { impacto: invalida }
  televisor:     { impacto: degrada }
  aire_acond:    { impacto: degrada }
  lector_pines:  { impacto: degrada }
  tableros:      { impacto: no_afecta }
  sillas:        { impacto: no_afecta }
  pc:            { impacto: degrada, invalida_si_danados_mayor_a_pct: 50 }   # base: aforo

espacios:
  Auditorio: { aforo: 100, excepciones: { internet: degrada } }
  Sputnik:   { aforo: 38, elementos_extra: [pc] }
  Artemis:   { aforo: 32, elementos_extra: [pc] }
  Skilab:    { aforo: 20, elementos_extra: [pc] }
  # ...
```

### Tipos de inhabilitación
| Tipo | Causa | Rehabilitación |
|---|---|---|
| Directa | Falla de un elemento que invalida (ej. internet) | **Manual** por TI (D3) |
| Derivada | Se calcula (ej. PCs dañados ≥ umbral) | **Automática** al bajar del umbral |

Al rehabilitarse un espacio: las reservas en conflicto **no reasignadas** vuelven a la normalidad con la nota *"conflicto resuelto: espacio rehabilitado"*; las **ya reasignadas** se quedan donde están.

### Asistentes
- La reserva pide solo **el número** de asistentes (sin nombres). Incluye a quien reserva.
- El número se guarda: D2 lo necesita para buscar alternativas.

## 5. Recursos portátiles (pools) ✅

Los pools agrupan **solo recursos portátiles** (se prestan). Manuales y editables en la configuración.

```yaml
limites:
  por_pool: false            # ← INTERRUPTOR
  global:
    prestamos_activos_max_persona: 2
    prestamo_duracion_max_min: 480

pools:
  computo_portatil:
    nombre: "Cómputo portátil"
    area_responsable: "TI"
    tipos_dataset: ["Laptop", "Portatil", "Portátil", "Tablet"]
    limites:                 # Solo si por_pool: true
      prestamos_activos_max_persona: 1
      prestamo_duracion_max_min: 240
```

| `por_pool` | Comportamiento |
|---|---|
| `false` | Solo el límite global; los de pool se ignoran |
| `true` | Límite del pool; si no lo define, hereda el global. El global es **techo total** por persona |

- Los mensajes de error **dicen qué límite aplicó** ("del pool X" o "global").
- Un tipo del dataset no puede estar en dos pools. El límite de un pool no puede superar el techo global.
- Recomendación de alternativa: otro recurso **del mismo pool**, disponible y sin incidencia crítica en revisión.
- Estados: `disponible → prestado → disponible | dañado`, `dañado → mantenimiento → disponible`. Sin estado `perdido`.

## 6. Reglas de negocio ✅

| Código | Regla |
|---|---|
| **R1** | Sin solapamiento de reservas en un espacio (`a.inicio < b.fin + margen && b.inicio < a.fin + margen`) |
| **R2** | `1 ≤ asistentes ≤ aforo × FACTOR_AFORO` |
| **R3** | No se asigna un espacio o recurso inhabilitado. Con incidencia crítica **en revisión**: reserva manual permitida con advertencia; las recomendaciones lo excluyen (D1.6) |
| **R4** | Límites de préstamo (global o por pool). Préstamo vencido bloquea nuevos préstamos |
| **R5** | Transiciones de estado inválidas se rechazan |
| **R6** | La incidencia aplica el impacto del elemento (invalida / degrada / no afecta / umbral) |
| **R7** | Inhabilitación automática solo con crítica + confianza + vínculo en ventana (ver §7) |
| **R8** | Ocupación mínima en salas grandes: **advertencia** (no bloquea) |
| **R9** | Los elementos de un espacio no se prestan |

## 7. Incidencias y R7 ✅

### R7: inhabilitación automática
Se aplica sin intervención humana **solo si** se cumplen las tres condiciones:
1. La IA la clasifica como `crítica` con confianza ≥ `IA_UMBRAL_CONFIANZA`.
2. Quien reporta tiene **vínculo** con el espacio o recurso.
3. El reporte ocurre **durante** la reserva o préstamo, o hasta `VENTANA_REPORTE_POST_MIN` (60) después. **Sin ventana previa.**

Si falla cualquiera → **verificación humana**.

### Vínculo por reserva
| Significado | ¿Da vínculo? |
|---|---|
| `confirmada` | ✅ |
| `finalizada` | ✅ dentro de la ventana POST |
| `pendiente`, `cancelada`, `rechazada`, `no-show` | ❌ |

Quien reservó un espacio tiene vínculo con sus **elementos** (incluidos los PCs).

### Vínculo por préstamo
El "fin" es la **devolución real**.

| Caso | Resultado |
|---|---|
| A. Prestado, en plazo | ✅ Vínculo |
| B. Prestado, vencido | ✅ Vínculo, con nota en auditoría |
| C. Devuelto sin observaciones, reporta dentro de la ventana | ⚠️ Verificación humana |
| D. Ya lo tiene otra persona; reporta quien lo tenía antes | ⚠️ Verificación humana |
| E. Devuelto y registrado como dañado | Pasa a `dañado` por la máquina de estados |

Un portátil solo lo puede reportar con vínculo quien lo tiene prestado (no quien reservó el aula donde está).

**Recurso prestado que se inhabilita:** pasa a `dañado`; el préstamo sigue abierto y cuenta para R4; al devolverse queda `dañado` → mantenimiento manual; lo futuro pasa a D2.

### Control de la respuesta de la IA
- El formulario **sugiere** el espacio o recurso según la reserva o préstamo activo de quien reporta. Para PCs se **seleccionan los IDs** afectados.
- La IA extrae el objeto del texto. Si **no coincide** con el seleccionado o **no existe** → verificación humana.

### D1.6: incidencia crítica en revisión
Reserva manual permitida con advertencia; recomendaciones la excluyen. Si se confirma → las reservas hechas mientras tanto pasan a D2. Si se descarta → se quita la advertencia.

### D2: reservas afectadas
Quedan **en conflicto**; el sistema recomienda una alternativa y Administrativo confirma.

Recomendación de espacio:
1. Filtra: libre en el horario, aforo ≥ asistentes, sin incidencia crítica en revisión.
2. Ordena por aforo más ajustado (*best-fit*).
3. La IA explica y desempata; solo elige entre lo ya filtrado.

### D3: rehabilitación
Manual, por TI, respetando la máquina de estados. Excepción: inhabilitación **derivada** (ver §4).

### Verificación humana
| Punto | Decisión |
|---|---|
| Acciones | Confirmar, reclasificar o descartar |
| Quién | Área responsable: TI (equipos), Administrativo (infraestructura) |
| Reversión | El área responsable puede revertir una inhabilitación automática |
| Auditoría | Quién, cuándo, qué propuso la IA (prompt y respuesta cruda), qué se decidió y por qué |

## 8. Parámetros (valores iniciales)

| Parámetro | Valor | Estado |
|---|---|---|
| `HORA_APERTURA` / `HORA_CIERRE` | 06:00 / 22:00 | 🟡 confirmar con Campuslands |
| `DIAS_HABILES` | Lunes a sábado | 🟡 |
| `GRANULARIDAD_MIN` | 30 | ✅ |
| `RESERVA_DURACION_MIN` / `MAX` | 30 / 240 | ✅ |
| `MARGEN_ENTRE_RESERVAS_MIN` | 0 | ✅ |
| `ANTICIPACION_MAX_DIAS` | 14 | ✅ |
| `FACTOR_AFORO` | 1.0 | ✅ |
| `RESERVAS_ACTIVAS_MAX_PERSONA` | 3 | ✅ |
| `SALA_GRANDE_DESDE_AFORO` | 20 | ✅ |
| `OCUPACION_MIN_PCT` | 30 | ✅ |
| `PRESTAMOS_ACTIVOS_MAX_PERSONA` (global) | 2 | ✅ |
| `PRESTAMO_DURACION_MAX_MIN` (global) | 480 | ✅ |
| `PRIORIDADES` | baja, media, alta, crítica | ✅ |
| `SLA_HORAS` | 72 / 24 / 8 / 2 | ✅ |
| `PRIORIDAD_QUE_INHABILITA` | crítica | ✅ |
| `VENTANA_REPORTE_POST_MIN` | 60 | ✅ |
| `IA_UMBRAL_CONFIANZA` | 0.70 | ✅ |
| `IA_TEMPERATURA` | 0 | ✅ |
| `IA_TIMEOUT_SEG` / `REINTENTOS` | 15 / 1 | ✅ |

### Validaciones de coherencia de la configuración
- Duraciones múltiplos de `GRANULARIDAD_MIN` y dentro del horario.
- `PRIORIDAD_QUE_INHABILITA` ∈ `PRIORIDADES`; un SLA por prioridad, decreciente.
- Todo pool y elemento tiene área responsable.
- Un tipo del dataset en un solo pool; límite de pool ≤ techo global.
- `OCUPACION_MIN_PCT` entre 0 y 100; `SALA_GRANDE_DESDE_AFORO` > 0.
- El préstamo no termina después de `HORA_CIERRE`.

## 9. Fuera del MVP (mejoras para el pitch)

- Incidencia creada automáticamente al devolver un recurso dañado.
- Reserva que declara equipo requerido ("necesito televisor").
- Degradación de aforo por sillas dañadas.
- Campers como usuarios.
- Login institucional (la lógica de permisos ya está separada).

## 10. Pendientes 🟡

- Horario y días hábiles reales.
- IA: proveedor autorizado, prompt y esquema de salida.
- Stack tecnológico.
- Plan de trabajo por persona.
