# CampusPulse: Hackatón Campuslands "El campus bajo presión"

MVP del **Sistema Central de Gestión Operativa del Campus**. Unifica espacios, recursos tecnológicos e incidencias en un único flujo asistido por IA.

## Integrantes
- (completar nombres del equipo)

## Problema
Campuslands crece rápido y gestiona aulas, equipos e incidencias con registros dispersos. CampusPulse centraliza los tres procesos y evita asignar espacios o recursos inhabilitados o en conflicto.

## Stack
Python 3.10+ (solo librería estándar), persistencia en JSON, interfaz de consola, `unittest`. La IA se conecta por HTTP a un endpoint tipo chat-completions (API autorizada o modelo local).

## Arquitectura
```
cli.py  ->  service.py  ->  rules.py        (reglas de negocio)
                        ->  ai/triage.py    (IA + validación de salida)
                        ->  data/*.json     (datos oficiales + estado)
```
- `models.py`: entidades. `rules.py`: reglas R0 a R5. `service.py`: orquestación y cascada. `ai/triage.py`: cliente de IA y validación.

## Rol de la IA
1. **Triaje de incidencias:** categoría, prioridad, área y justificación en JSON.
2. **Recomendación de reasignación:** elige entre alternativas que el motor de reglas ya validó.

Controles: la salida se valida contra listas cerradas, hay un reintento, y si falla se usa un **respaldo marcado como `respaldo`** (nunca se simula la IA). La IA no puede saltarse las reglas: toda reasignación se vuelve a validar y la aplica una persona.

## Reglas de negocio
| Código | Regla |
|---|---|
| R0 | Intervalo coherente y con duración permitida |
| R1 | Sin solapamiento de reservas en un espacio |
| R2 | Asistentes no superan el aforo |
| R3 | No se asigna un espacio inhabilitado o con incidencia crítica abierta |
| R4 | Solo se presta o asigna un recurso operativo, no prestado y sin otra reserva solapada |
| R5 | Una incidencia no se cierra sin resolución |

## Flujo vertical principal
Incidencia, triaje con IA, bloqueo del recurso o espacio, reservas afectadas, alternativas validadas, recomendación de la IA, reasignación y cierre.

## Datos
`data/seed_ejemplo.json` es ficticio e incluye casos borde (ids duplicados, aforo inválido, estados desconocidos, referencias inexistentes, fechas invertidas). Los registros inconsistentes se omiten y se reportan como anomalías. Para el evento, apunta `CAMPUS_SEED` al archivo oficial.

## Instalación y ejecución
```bash
cp .env.example .env     # completar AI_API_URL, AI_MODEL (y AI_API_KEY si aplica)
python -m campuspulse.cli
python -m unittest discover -s tests -v
```
Nunca subas `.env` (está en `.gitignore`).

