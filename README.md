# Sistema Central de Gestión Operativa · Equipo Trinity

MVP para la Hackatón Campuslands **"El campus bajo presión"**. Unifica espacios, recursos tecnológicos e incidencias en un solo flujo operativo asistido por IA.

> Las decisiones de diseño están en [DECISIONES.md](DECISIONES.md). Es el contrato del equipo: lo que no está ahí, no se programa.

## Integrantes
- _(completar)_

## Problema
Campuslands crece rápido y gestiona aulas, préstamo de equipos e incidencias con registros dispersos y revisiones manuales. Eso genera demoras, errores y asignaciones de espacios o equipos que no están en condiciones de usarse.

## La solución en un flujo
```
1. Una persona reporta en texto libre: "No hay internet en Sputnik"
2. La IA clasifica          → categoría, prioridad, confianza
3. El sistema valida        → ¿existe el elemento? ¿coincide con lo seleccionado?
4. Regla de impacto         → internet en Sputnik: INVALIDA
5. R7 decide                → ¿crítica + confianza + vínculo en ventana? → automático; si no → humano
6. Reservas afectadas       → quedan en conflicto
7. Recomendación            → espacio libre con aforo más ajustado; la IA explica
8. Administrativo confirma  → reasignación registrada en auditoría
```

**Principio:** la IA clasifica lo ambiguo; las reglas deciden las consecuencias.

## Módulos
| Módulo | Qué hace |
|---|---|
| Espacios | Reservas sin solapamientos, control de aforo y ocupación mínima en salas grandes |
| Recursos | Préstamos de equipos portátiles agrupados en pools, con límites globales o por pool |
| Incidencias | Triaje con IA, impacto por elemento, inhabilitación automática controlada y verificación humana |

## Rol de la IA
1. **Triaje de incidencias:** categoría, prioridad, confianza y objeto afectado, en JSON validado contra la configuración.
2. **Recomendación de alternativas:** explica y desempata entre opciones que las reglas ya filtraron.

**Controles:**
- Salida estructurada y validada; categorías u objetos inexistentes se rechazan.
- Confianza por debajo del umbral, objeto que no coincide o falta de vínculo → verificación humana.
- Temperatura 0 para respuestas reproducibles.
- Si la IA no responde, el sistema lo indica y pasa a clasificación manual. **Nunca se simula una respuesta.**
- Se registran el prompt, la respuesta cruda y la decisión final.

## Reglas de negocio
| Código | Regla |
|---|---|
| R1 | Sin solapamiento de reservas en un espacio |
| R2 | Asistentes entre 1 y el aforo |
| R3 | No se asigna nada inhabilitado; con incidencia crítica en revisión, solo con advertencia |
| R4 | Límites de préstamo por persona (global o por pool); préstamo vencido bloquea |
| R5 | Transiciones de estado válidas de los recursos |
| R6 | Impacto de la incidencia según el elemento (invalida, degrada, no afecta, umbral de PCs) |
| R7 | Inhabilitación automática solo con prioridad crítica, confianza alta y vínculo dentro de la ventana |
| R8 | Ocupación mínima en salas grandes (advertencia) |
| R9 | Los elementos instalados en un espacio no se prestan |

Detalle completo en [DECISIONES.md](DECISIONES.md).

## Configuración
Todos los parámetros (horarios, límites, umbrales, catálogos, pools, elementos e impacto) viven en un único archivo de configuración. Se valida al arrancar y al recargar; si es incoherente, se muestra el error y se conserva la última configuración válida.

## Datos
- Se usan los datos oficiales entregados al inicio del evento; sus catálogos se adoptan tal cual y se mapean en la configuración.
- Los registros inconsistentes van a **cuarentena** con su motivo, nunca se borran y se pueden reprocesar.
- Los datos originales son inmutables; las operaciones se guardan aparte con auditoría.
- En pruebas solo se usan datos ficticios.

## Stack
_(por definir)_

## Instalación y ejecución
_(por definir con el stack)_

Las credenciales van en `.env` (nunca en el repositorio). Ver `.env.example`.
