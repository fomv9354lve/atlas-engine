# Atlas — resultados en hardware real (ibm_kingston, 2026-06-22)

> 4 jobs ejecutados en `ibm_kingston` (Heron r2, plan open). ~8 s de cómputo QPU total
> (de 10 min/mes). Reproducible: `benchmarks/qpu_validation.py` (validación) y
> `qpu_submit.py` (A/B). IDs en `benchmarks/qpu_jobs.json`. Token nunca impreso/commiteado.

## 1. Validación end-to-end: "no necesitas el QPU" (lo demostrable)

Circuitos que Atlas rutea **CPU** → se corren clásico-exacto (statevector) Y en el QPU real;
TVD bajo = el clásico reproduce al device dentro del error → **no se necesitaba el QPU**.

| Circuito | Atlas | TVD(ideal, QPU) | QPU usage |
|---|---|---|---|
| ghz4 (4q) | CPU | **0.059** | ~2 s |
| cliffordT5 (5q) | CPU | **0.055** | ~2 s |

→ TVD ~0.06 (dentro del error del dispositivo: 2Q ~2e-3, readout ~8e-3). El veredicto
"CPU/cheap" de Atlas, **validado en hardware real**, no solo contra el modelo de ruido local.

## 2. A/B de embedding: la dureza depende del LAYOUT (hallazgo #4, en hardware)

Mismo GHZ4 lógico, dos mapeos físicos (ideal = {0000:0.5, 1111:0.5}):

| Layout | qubits | TVD(ideal, QPU) | top outcomes |
|---|---|---|---|
| **GOOD** | `[0,1,2,3]` (zona norte limpia) | **0.064** | {0000:0.48, 1111:0.46} — GHZ limpio |
| **TLS** | `[120,121,122,123]` (edge roto 120_121 + Q121) | **0.465** | {0000:0.56, 1110:0.12, 0010:0.11, …} — basura |

**Contraste: 7.3× peor por embedding.** El MISMO circuito da resultado correcto en qubits
buenos y ruido casi uniforme a través del cluster TLS. Demuestra en hardware real que:
- la dureza/fidelidad de un circuito **depende del embedding físico**, no solo de su estructura;
- la guía `exclude_qubits` / la lente hardware-aware de Atlas (`atlas_hardware`) es **accionable**:
  elegir el layout que evita el cluster TLS cambia el resultado de inútil a correcto.

## 3. Para el pricing (número medido)
QPU usage ~2 s por circuito chico (1024 shots). Ancla el modelo de coste con un número
**medido**, no solo pricing publicado. (El wall-clock incluye cola: ghz4 ~4.3 h de espera.)

## Honestidad
- TVD~0.06 NO es cero: el device es ruidoso; el punto es que el clásico lo reproduce dentro
  de ese ruido → ruta clásica suficiente.
- El A/B usa un layout deliberadamente malo (Q121, T1=11µs, readout 23%) para mostrar el
  contraste; no es el peor caso adversarial, es el cluster TLS real documentado.
- Alcance: n≤5. No prueba nada sobre el régimen duro (sin ground-truth clásico ahí).

---

# Segunda tanda — high-limit stress + calibración PT propia (ibm_kingston, 2026-06-22)

> 17 jobs adicionales (8 stress + 9 PT), ~36 s de cómputo QPU. Recogidos con
> `qpu_collect.py` (stress → `results_scaled/qpu_stress_results.csv`) y `qpu_collect_pt.py`
> (PT → `results_scaled/qpu_pt_calib.json`). IDs en `qpu_jobs.json`.

## 4. Embedding A/B, replicado y MÁS FUERTE (ghz6, n=6)

| Layout | TVD(ideal, QPU) | TVD(QPU, uniforme) | lectura |
|---|---|---|---|
| **GOOD** | **0.081** | 0.888 (lejos de uniforme = estructurado) | GHZ correcto |
| **TLS**  | **0.782** | 0.736 (cerca de uniforme = colapsado) | basura |

**Contraste 9.7×** (vs 7.3× en ghz4). El hallazgo de embedding-dependencia es robusto y crece
con n. Confirma que la lente `recommend_embedding_offline` es accionable en metal real.

## 5. Discriminante n=20: el QPU FALLA donde Atlas dijo "CPU" (y tenía razón)

`disc_n20_d2` (20q, 40 T-gates) → Atlas ruta **CPU** (treewidth bajo, clásico-exacto).
QPU: TVD(ideal, QPU) = **0.999** (output totalmente corrupto). Atlas estaba en lo correcto:
el circuito es clásicamente trivial Y el QPU ni siquiera lo corre con fidelidad → **no gastes
el QPU**. La asimetría "no necesitas QPU" se sostiene incluso a n=20.

## 6. Rampa de ruido (n=12): NO hay colapso monótono — saturado desde d=2 (resultado nulo honesto)

| depth | 2 | 8 | 16 | 24 | 32 |
|---|---|---|---|---|---|
| TVD(ideal, QPU) | 0.777 | 0.779 | 0.782 | 0.780 | 0.779 |

Esperábamos una rampa de colapso con la profundidad. **No ocurre**: a n=12 el device ya está
saturado (~0.78 de error) desde d=2; más profundidad no lo empeora porque ya está cerca del
piso. Resultado nulo para la hipótesis de "colapso gradual"; sí confirma que n=12 ya está
**pasado el límite de fidelidad** del device. Nota: el QPU NO colapsa a uniforme (TVD(QPU,unif)
≈0.78 también) → ruido sesgado/coherente, no despolarizante puro.

## 7. Calibración conformal PROPIA → AUTO-CORRECCIÓN #10 (reversión de signo de κ̂)

9 circuitos 2D-random Porter-Thomas (n=12, 2048 shots), XEB lineal normalizada por colisión real
vs fidelidad inferida de 1er orden (medianas medidas). **7 puntos PT-válidos** (colisión≈2, d≥6;
d=2,4 anti-concentrados → excluidos).

| depth | colisión | F_inferida | F_medida | κ (por capa) |
|---|---|---|---|---|
| 6  | 1.37 | 0.836 | 0.780 | 1.38 |
| 8  | 1.77 | 0.813 | 0.575 | 2.61 |
| 10 | 2.31 | 0.796 | 0.610 | 2.14 |
| 12 | 3.41 | 0.774 | 0.397 | 3.51 |
| 14 | 2.28 | 0.760 | 0.316 | 4.06 |
| 16 | 2.04 | 0.728 | 0.316 | 3.54 |
| 18 | 2.42 | 0.716 | 0.422 | 2.54 |

**κ̂ = 2.62** (mediana PT-válida). MAE held-out (LOO conformal) 29% → 12%, banda 80% ±0.21.

### El hallazgo (y la corrección)
La sesión anterior, con un Aer "device-faithful", midió κ̂≈0.40 (**<1**): "el hardware se degrada
más LENTO que lo inferido → extiende el techo de profundidad ~14%". **Eso era un artefacto del
simulador.** Aer subestima el ruido CORRELACIONADO/no-Markoviano (crosstalk, TLS, leakage) que el
metal real sí tiene. En `ibm_kingston` real, la fidelidad cae ~2.6× MÁS RÁPIDO que lo inferido
(κ̂>1) → la inferencia de 1er orden **SOBREESTIMA** la profundidad alcanzable.

**Impacto en Atlas (corregido en este commit):**
- `atlas_conformal_hardware`: `CALIB` ← datos propios PT; κ̂=2.62; dirección "aprieta el techo".
- `atlas_hardware.qualify_offline`: techo REALISTA = techo_1er_orden / κ̂ ≈ **11 capas** (vs el
  rango de 1er orden optimista 29–49). La zona gris ahora dice "POCO probable que corra", no
  "probablemente corra". La corrección APRIETA (seguridad), no extiende.
- La dirección de la corrección es ahora del lado **conservador correcto**: no prometemos
  profundidad que el metal real no entrega.

### Honestidad
- 7 puntos PT-válidos (no 9): d=2,4 no son Porter-Thomas (colisión 36, 6) → la XEB no es métrica
  honesta ahí. 90% de cobertura conformal necesita ≥9 PT-válidos; tenemos 7 → ~87% máx con banda
  finita; reportamos 80%.
- Familia 2D-random **worst-case**: κ̂ alto aplica a candidatos ESCALATE (alta magia/entrelazado),
  que es exactamente la familia relevante; un circuito estructurado podría tener techo mayor.
- Cada uno de los 9 circuitos tuvo su propio layout físico (transpile) → varianza de embedding
  incluida en la banda (parte del ruido no-monótono d=8 vs d=10, d=16 vs d=18).

---

# Depth-resolved 3-regime validation (ibm_kingston, 2026-06-24)

> Cierra el hueco del peer-review ("solo n=2 circuitos fáciles"). **19 puntos (n,depth)** con
> TVD(statevector ideal, conteos QPU) + **mirror-RB con barras de error (K=6 repeticiones)**.
> 1024 shots (TVD) / 500 shots (RB). **0 nuevo tiempo QPU** — recuperado de jobs ya completados.
> Fuentes: `qpu_regime_results.json`, `qpu_mirror_results.json`, `qpu_jobs.json`. Todos los
> números trazables a esos JSON por `job_id`.

## 8. Tabla de 3 regímenes — profundidad → ruta Atlas → TVD(ideal,QPU) → fidelidad mirror-RB

Eje físico: **TVD(ideal, QPU) SUBE con la profundidad** porque el *dispositivo* se decohera
(ruido de hardware crece con depth), **no** porque Atlas se equivoque: a estos n (≤12) la
distribución ideal es clásicamente tratable por statevector exacto, así que el "ideal" es la
verdad de tierra. La fidelidad mirror-RB (independiente, readout-corregida) confirma la causa:
cae monótonamente con depth con barras de error.

| Régimen | Circuito | n | depth | t_count | Ruta Atlas | TVD(ideal,QPU) | mirror-RB F (±SEM) | job_id (prefijo) |
|---|---|---|---|---|---|---|---|---|
| **Fácil** (low-depth / Clifford) | ghz6 GOOD | 6 | Clifford | 0 | CPU | **0.081** | — | `d8sliestq…` |
| **Fácil** | pt_n12_d2 | 12 | 2 | — | CPU | **0.135** | 0.947 ± 0.021 | `d8sm88tpo…` |
| **Frontera** (MPS↔treewidth divergen) | pt_n12_d4 | 12 | 4 | — | CPU | 0.358 | 0.781 ± 0.041 | `d8sm895bh…` |
| **Frontera** | pt_n12_d6 | 12 | 6 | — | CPU | 0.533 | 0.678 ± 0.044 | `d8sm89dpo…` |
| **Frontera** | pt_n12_d8 | 12 | 8 | — | CPU | 0.551 | 0.451 ± 0.055 | `d8sm89sbp…` |
| **Frontera** | pt_n12_d10 | 12 | 10 | — | CPU | 0.532 | — | `d8sm8a4tq…` |
| **Difícil/profundo** (high depth) | pt_n12_d12 | 12 | 12 | — | CPU | 0.583 | — | `d8sm8actq…` |
| **Difícil/profundo** | pt_n12_d16 | 12 | 16 | — | CPU | 0.602 | — | `d8sm8b4bp…` |
| **Difícil/profundo** | pt_n12_d18 | 12 | 18 | — | CPU | 0.570 | — | `d8sm8bcbp…` |
| **Difícil/profundo** | ramp_n12_d32 | 12 | 32 | 384 | CPU | 0.779 | — | `d8slielpo…` |
| **Difícil/profundo** | ghz6 TLS (mal layout) | 6 | Clifford | 0 | CPU | **0.782** | — | `d8slif4bp…` |
| **Más allá del oráculo** (n>24, sin GT clásico) | disc_n20_d2 | 20 | 2 | 40 | CPU | 0.999 | — | `d8slictpo…` |

(mirror-RB usa la *familia* mirror equivalente al depth, no el mismo job que TVD; n=8 también
medido: d8/16/32 → F = 0.655±0.010 / 0.415±0.039 / 0.126±0.031. Ajustes exponenciales:
r_per_layer = **6.7%** a n=8 (R²=0.996), **11.2%** a n=12 (R²=0.944).)

### Lectura honesta (lo que valida y lo que NO)
La señal central: **TVD sube de ~0.08 (somero) a ~0.55–0.78 (profundo), y la fidelidad mirror-RB
cae en espejo (0.95→0.13)**. Esto es el dispositivo decoherándose — ruido real de hardware que
crece con la profundidad — **no** Atlas equivocándose: a n≤12 la distribución ideal es
clásicamente tratable (statevector exacto) y ES la verdad de tierra, por lo que el TVD mide la
desviación del *device* respecto al ideal. Lo que esto **valida**: a baja profundidad el motor
clásico de Atlas reproduce el device dentro del error (régimen fácil, TVD~0.08–0.14, F~0.95); a
alta profundidad el device es simplemente ruidoso mientras el ideal sigue siendo tratable —
consistente con Shao et al. (arXiv:2606.00474): el ruido hace los circuitos MÁS simulables
clásicamente, pero la salida ruidosa del device diverge del ideal. Lo que esto **NO** afirma:
que clásico == device-ruidoso en todas partes; el TVD alto a profundidad es la huella del ruido
del device, no una métrica de fidelidad de Atlas. Las barras de error mirror-RB (K=6) son la
pieza de evidencia estadística de que la caída de fidelidad es real, no varianza de shots.

### Honestidad / alcance
- Todo este barrido es n≤20, con n≤12 como zona de oráculo exacto (statevector). El régimen
  **cuánticamente duro (n>24, sin oráculo clásico) sigue siendo inmedible**: no hay verdad de
  tierra ahí por construcción (false-security inmedible, no cero).
- `disc_n20_d2` (TVD 0.999) muestra el device totalmente corrupto donde Atlas dijo "CPU" y tenía
  razón (trivial clásicamente) — pero n=20 ya no es zona de oráculo barato; se incluye como
  frontera del device, no como validación de igualdad clásico=device.
- `ghz6 TLS` (0.782) es un layout deliberadamente malo (cluster TLS real), no peor-caso
  adversarial — explica por qué un Clifford somero puede dar TVD alto por *embedding*, no por
  profundidad. Por eso la columna régimen lo marca como contraste, no como punto de profundidad.
- mirror-RB no está medido en cada depth de TVD; los huecos "—" son honestos (no interpolados).
