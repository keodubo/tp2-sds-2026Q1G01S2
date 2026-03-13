# Auditoría de Fases 0 y 1 — tp2-sds-2026Q1G01S2

**Fecha:** 2026-03-13
**Rol:** Arquitecto de Software / Revisor de Código (solo lectura)
**Alcance:** Fases 0 (base del proyecto) y 1 (motor Vicsek estándar + líderes + exportador + análisis)

---

## 1. Análisis de Requisitos (fuentes: enunciado, teóricas, guías de formato)

### 1.1 Modelo físico (Vicsek estándar — Escenario A)

- Partículas autopropulsadas en caja cuadrada L×L con contorno periódico.
- Parámetros por defecto: L=10, ρ=4, N=400, r=1, v=0.03, dt=1.
- Regla de actualización simultánea:
  - θ_i(t+1) = ⟨θ_j(t)⟩_{|r_i−r_j|<r} + η·ξ, con ξ ~ U(−1/2, 1/2).
  - **x_i(t+1) = x_i(t) + v·(cos θ_i(t+1), sin θ_i(t+1))·Δt** — la posición se actualiza con el ángulo NUEVO.
- Promedio angular circular: atan2(Σ sin θ_j, Σ cos θ_j), incluyendo la propia partícula.
- Parámetro de orden: va(t) = |Σ v_i(t)| / (N·v), en [0, 1].

### 1.2 Escenarios con líder (B y C)

- **B**: una partícula (la 0) se convierte en líder de dirección fija θ₀ aleatoria. El líder influye en sus vecinos pero no se ve influido por ellos. N sigue siendo 400.
- **C**: el líder sigue una circunferencia de radio R=5, centro (5,5), ω=v/R=0.006 rad/paso. Mismas reglas de influencia unidireccional.

### 1.3 Entregables obligatorios por escenario

- 2 demos OVITO representativas (bajo/alto ruido o configuraciones clave).
- Curvas va(t) justificando la detección de régimen estacionario.
- Curva η vs ⟨va⟩ ± error (desvío estándar entre seeds).
- Figura comparativa única A vs B vs C.

### 1.4 Formato de entrega

- Presentación: máx. 15 min, guía de formato ITBA.
- Informe: PDF, guía de informes ITBA.

---

## 2. Revisión del Plan (`Plan_Implementacion_TP2_OVITO.md`)

### 2.1 Cobertura

| Requisito del enunciado | Fase del plan | Estado |
|---|---|---|
| Motor Vicsek estándar (A) | Fase 1 | ✅ Cubierto |
| Vecinos all-pairs / cell-list | Fase 1.1 | ✅ All-pairs implementado, cell-list como mejora opcional |
| Líderes B y C | Fase 2 | ✅ Cubierto |
| Exportador extended XYZ | Fase 3 + 3.1–3.3 | ✅ Cubierto con detalle de schema |
| Helper OVITO | Fase 4 | ⬜ Pendiente (no bloqueante) |
| Observable va y análisis estacionario | Fase 5 | ⚠️ Parcialmente implementado (ver §3) |
| Barrido de η y comparativas | Fase 5.1 | ⬜ Pendiente |
| Demos y resultados obligatorios | Fase 6 | ⬜ Pendiente |
| Opcionales (ρ=2, ρ=8) | Fase 7 | ⬜ Pendiente |
| Entregables (presentación, informe) | Fase 8 | ⬜ Pendiente |

### 2.2 Consistencia plan ↔ requisitos

El plan es consistente con el enunciado en lo estructural. Los parámetros por defecto coinciden (L=10, ρ=4, N=400, r=1, v=0.03, dt=1). La elección de omega=0.006 para C es correcta (v/R = 0.03/5).

**Observaciones menores sobre el plan:**

- El plan dice "producir resumenes por corrida y luego mean ± std entre seeds" pero no especifica el algoritmo de detección de régimen estacionario. Esto se delega a "corridas piloto" sin criterio concreto.
- El plan no menciona explícitamente que la posición se actualiza con el ángulo NUEVO (θ(t+1)), lo cual es la formulación canónica de Vicsek.

---

## 3. Auditoría de Código — Hallazgos

### 3.1 🔴 CRÍTICO — Actualización de posiciones usa velocidad ANTERIOR

**Archivo:** `simulation.py`, líneas 53 y 85–92
**Problema:** La posición se actualiza con `velocities_xy` calculadas a partir de `angles` (el ángulo del paso actual), en lugar de usar `next_angles` (el ángulo recién calculado).

```
# Línea 53: velocidades del paso actual
velocities_xy = angles_to_velocities(angles, config.v)
...
# Línea 92: posición actualizada con velocidad del paso actual
next_positions = (next_positions + velocities_xy * config.dt) % config.L
```

**Formulación correcta de Vicsek (1995):**

```
x_i(t+1) = x_i(t) + v · (cos θ_i(t+1), sin θ_i(t+1)) · Δt
```

Es decir, primero se computa θ(t+1), luego se usa θ(t+1) para la velocidad que desplaza la partícula. El código actual usa θ(t) para el desplazamiento.

**Impacto:** Altera la dinámica del sistema. El comportamiento cualitativo (transición orden/desorden) se mantiene, pero las curvas va(η) diferirán cuantitativamente de la referencia canónica. Puede afectar la calificación si el docente compara contra resultados de referencia.

**Corrección sugerida:** Después de computar `next_angles`, generar `next_velocities = angles_to_velocities(next_angles, config.v)` y usarlas para el desplazamiento.

---

### 3.2 🔴 CRÍTICO — Sin detección de régimen estacionario

**Archivo:** `analysis.py`, líneas 19–25
**Problema:** `analyze_run()` usa `t_start=0` y promedia va sobre TODOS los frames, incluyendo el transitorio inicial.

```python
summary = RunSummary(
    scenario=config.scenario,
    eta=config.eta,
    seed=config.seed,
    t_start=0,
    t_end=len(va_series) - 1,
    va_mean_stationary=float(np.mean([value for _, value in va_series])),
)
```

**Requisito:** El enunciado pide "detectar régimen estacionario" y el plan (Fase 5) lo especifica como tarea pendiente. Promediar incluyendo el transitorio sesga ⟨va⟩ hacia valores más bajos a bajo ruido (donde el sistema arranca desordenado y luego se ordena).

**Impacto:** Las curvas η vs ⟨va⟩ serán incorrectas, especialmente a bajo η donde el transitorio es más marcado.

**Corrección sugerida:** Implementar al menos un criterio simple (ej. descarte de primer 20-30% de frames, o detección por pendiente de media móvil) y registrar `t_start` real en el summary.

---

### 3.3 🟡 MEDIO — Líder circular no aplica contorno periódico

**Archivo:** `simulation.py`, líneas 172–176
**Problema:** `_circular_position()` retorna `center + offset` sin aplicar `% config.L`. Con los parámetros por defecto (center=(5,5), radius=5), la posición del líder alcanza exactamente 10.0 en los extremos de la órbita. El valor 10.0 está fuera del rango semiabierto [0, L=10).

```python
def _circular_position(config, phase0, step):
    phase = phase0 + float(config.leader_spec.omega) * step
    center = np.array([float(config.leader_spec.center_x), float(config.leader_spec.center_y)])
    offset = float(config.leader_spec.radius) * np.array([np.cos(phase), np.sin(phase)])
    return center + offset  # ← sin % config.L
```

**Impacto:** La posición 10.0 es equivalente a 0.0 bajo PBC, así que el cálculo de vecinos (que usa minimum image) funciona correctamente. Pero si se verifica el invariante de caja (`assert positions < L`), falla. OVITO puede interpretar la posición fuera de celda correctamente (con PBC), pero es una inconsistencia.

**Corrección sugerida:** Aplicar `% config.L` al resultado de `_circular_position`.

---

### 3.4 🟡 MEDIO — `va_std` usa ddof=0

**Archivo:** `analysis.py`, línea 107
**Problema:** `values.std(ddof=0)` calcula el desvío estándar poblacional. Con pocas seeds (típicamente 3-5), el desvío muestral (`ddof=1`) es más apropiado para barras de error.

**Impacto:** Las barras de error subestiman la incertidumbre real. Con 5 seeds, la diferencia es un factor √(5/4) ≈ 12%.

**Corrección sugerida:** Usar `ddof=1` o, mejor, documentar explícitamente la convención elegida.

---

### 3.5 🟢 BAJO — `_velocity_colors()` usa loop de Python

**Archivo:** `simulation.py`, líneas 193–199
**Problema:** `colorsys.hsv_to_rgb` se llama en un loop por partícula. Con N=400 y cientos de steps, no es un cuello de botella real, pero rompe la convención vectorizada del resto del módulo.

**Corrección sugerida:** Vectorizar la conversión HSV→RGB con numpy (H=angle/(2π), S=1, V=1 tiene fórmula cerrada vectorizable).

---

### 3.6 🟢 BAJO — Redundancia en manejo de líder escenario B

**Archivo:** `simulation.py`, líneas 41–48, 45–48, 54–55
**Problema:** El ángulo del líder B se setea antes del loop (línea 42) y redundantemente en cada iteración (línea 46). La posición se wrappea con `% config.L` (línea 48), lo cual es correcto, pero está en un bloque `if` separado e idéntico al anterior.

**Impacto:** Solo claridad de código; no afecta resultados.

---

### 3.7 ℹ️ NOTA — Frames se graban ANTES de actualizar

El loop graba el estado actual como frame y luego actualiza. Esto significa que el frame 0 es el estado inicial aleatorio. Es una convención válida y consistente con "el frame N-1 es el último estado antes de la actualización N-1". No es un bug, pero hay que tenerlo en cuenta al interpretar `t_start` para el estacionario.

---

### 3.8 ℹ️ NOTA — Velocidad del frame registrado vs. velocidad de desplazamiento

Dado el bug §3.1, la velocidad registrada en cada frame (la que se escribe en el extxyz y la que usa OVITO para las flechas) es la velocidad del paso actual θ(t), NO la velocidad que efectivamente desplazó la partícula. Si se corrige §3.1, hay que decidir si el frame registra v(θ(t)) o v(θ(t+1)). Lo más coherente es registrar v(θ(t+1)) ya que es la velocidad que produjo el desplazamiento.

---

## 4. Resumen de hallazgos

| # | Severidad | Componente | Hallazgo |
|---|---|---|---|
| 3.1 | 🔴 CRÍTICO | `simulation.py` | Posición actualizada con v(θ(t)) en vez de v(θ(t+1)) |
| 3.2 | 🔴 CRÍTICO | `analysis.py` | Sin detección de régimen estacionario; promedia todo el transitorio |
| 3.3 | 🟡 MEDIO | `simulation.py` | Líder circular sin `% L`, posición puede ser = L |
| 3.4 | 🟡 MEDIO | `analysis.py` | `std(ddof=0)` subestima barras de error con pocas seeds |
| 3.5 | 🟢 BAJO | `simulation.py` | `_velocity_colors` no vectorizado |
| 3.6 | 🟢 BAJO | `simulation.py` | Bloques `if scenario=="B"` redundantes |

---

## 5. Propuesta de mejora — Plan de correcciones prioritarias

No se requiere reescribir el plan completo. El `Plan_Implementacion_TP2_OVITO.md` es sólido y está bien alineado con los requisitos. Las correcciones se aplican sobre la implementación existente:

### Prioridad 1 — Corregir regla de actualización (§3.1)

1. En `simulate_trajectory()`, después de `compute_next_angles()`, computar `next_velocities = angles_to_velocities(next_angles, config.v)`.
2. Usar `next_velocities` (no `velocities_xy`) para el desplazamiento de posiciones.
3. Para escenarios B y C, overridear `next_velocities[0]` con la velocidad del líder derivada de su ángulo fijo/circular en t+1 (que ya se computa correctamente en `next_angles[0]`).
4. Decidir qué velocidad registrar en el frame: recomiendo registrar la velocidad que produjo el desplazamiento hacia ese estado (es decir, la velocidad del paso anterior), o alternativamente registrar la velocidad instantánea del estado actual. Documentar la convención elegida.
5. Actualizar el test `test_simulate_trajectory_preserves_speed_and_box_invariants_for_standard_case` para verificar que la speed invariant siga valiendo con la nueva lógica.

### Prioridad 2 — Implementar detección de estacionario (§3.2)

1. Implementar al menos un criterio simple: descarte de los primeros K frames (K configurable, default ~30% de steps) o detección automática por estabilización de media móvil.
2. `analyze_run()` debe escribir `t_start` y `t_end` reales en el summary.
3. Agregar test que verifique que `t_start > 0` para corridas con transitorio visible.
4. Producir curvas `va(t)` como entregable intermedio para justificar el corte visualmente.

### Prioridad 3 — Correcciones menores

1. Aplicar `% config.L` en `_circular_position()` (§3.3).
2. Cambiar `ddof=0` a `ddof=1` en `write_aggregate_csv()` o documentar la convención (§3.4).
3. Vectorizar `_velocity_colors()` (§3.5) — opcional, no bloqueante.
4. Consolidar bloques redundantes de escenario B (§3.6) — opcional, no bloqueante.

### Tests a agregar/actualizar

- Test de box invariant para escenario C (actualmente solo se testea A).
- Test que verifique que la posición se desplaza con v(θ(t+1)), no v(θ(t)). Por ejemplo: con η=0 y todos los vecinos visibles, después de 1 paso la velocidad de desplazamiento debe ser la media angular, no la individual original.
- Test de que `t_start` en el summary es > 0 para corridas largas con transitorio.

---

## 6. Aspectos positivos

- Estructura de paquete limpia con `pyproject.toml`, src layout, CLI bien organizado.
- `TrajectoryFrame` con validación de shapes en `__post_init__` — robusto.
- Serialización roundtrip completa para config, LeaderSpec y extxyz — bien testeada.
- `SimulationConfig` frozen y con validación de consistencia N/ρ — sólido.
- Separación clara simulación / IO / análisis / CLI.
- Extended XYZ con schema OVITO-ready funcional y verificado.
- Tests cubren los escenarios principales y verifican invariantes físicos clave.
- Seed determinista para reproducibilidad, incluyendo el leader_spec de B (seed+10001).

---

**Siguiente acción:** Corregir §3.1 (regla de actualización) y §3.2 (estacionario) antes de avanzar a las fases de barrido y resultados. Sin estas correcciones, los resultados cuantitativos no serán confiables.
