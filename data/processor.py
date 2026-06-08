import math
from typing import Optional
from config import DEFAULT_FTP, DEFAULT_HR_THRESHOLD


# Power zones (% of FTP): z1-z7
POWER_ZONES = [
    ("Z1 Recuperación", 0, 0.55),
    ("Z2 Resistencia",  0.55, 0.75),
    ("Z3 Tempo",        0.75, 0.90),
    ("Z4 Umbral",       0.90, 1.05),
    ("Z5 VO2max",       1.05, 1.20),
    ("Z6 Anaeróbico",   1.20, 1.50),
    ("Z7 Neuromuscular",1.50, 99.0),
]

# HR zones (% of threshold HR)
HR_ZONES = [
    ("Z1 Recuperación", 0,    0.68),
    ("Z2 Resistencia",  0.68, 0.83),
    ("Z3 Tempo",        0.83, 0.94),
    ("Z4 Umbral",       0.94, 1.05),
    ("Z5 VO2max",       1.05, 99.0),
]


def format_duration(seconds: Optional[int]) -> str:
    """
    Consistent human-readable duration formatting used across all pages
    (e.g. Overview, Activity Detail, Routes): "45 min" or "1h 23min".
    """
    if not seconds:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h > 0:
        return f"{h}h {m:02d}min"
    return f"{m} min"


def normalized_power(watts_stream: list[float]) -> Optional[float]:
    if not watts_stream or len(watts_stream) < 30:
        return None
    window = 30
    rolling = [
        sum(watts_stream[i:i+window]) / window
        for i in range(len(watts_stream) - window + 1)
    ]
    np = (sum(x**4 for x in rolling) / len(rolling)) ** 0.25
    return round(np, 1)


def intensity_factor(np: float, ftp: float) -> float:
    return round(np / ftp, 3)


def tss(duration_s: int, np: float, if_val: float, ftp: float) -> float:
    return round((duration_s * np * if_val) / (ftp * 3600) * 100, 1)


def estimate_ftp(watts_stream: list[float], duration_s: int) -> Optional[float]:
    """Estimate FTP as 95% of best 20-minute average power."""
    if not watts_stream or duration_s < 1200:
        return None
    window = min(1200, len(watts_stream))
    best = max(
        sum(watts_stream[i:i+window]) / window
        for i in range(len(watts_stream) - window + 1)
    )
    return round(best * 0.95, 1)


def power_zones(watts_stream: list[float], ftp: float) -> dict:
    """Returns seconds spent in each power zone."""
    zones = {z[0]: 0 for z in POWER_ZONES}
    for w in watts_stream:
        pct = w / ftp
        for name, lo, hi in POWER_ZONES:
            if lo <= pct < hi:
                zones[name] += 1
                break
    return zones


def hr_zones(hr_stream: list[float], threshold_hr: float) -> dict:
    """Returns seconds spent in each HR zone."""
    zones = {z[0]: 0 for z in HR_ZONES}
    for hr in hr_stream:
        pct = hr / threshold_hr
        for name, lo, hi in HR_ZONES:
            if lo <= pct < hi:
                zones[name] += 1
                break
    return zones


def compute_activity_metrics(
    watts_stream: Optional[list],
    moving_time_s: int,
    ftp: float = DEFAULT_FTP,
) -> dict:
    result = {"np_watts": None, "tss": None, "if_value": None, "ftp_estimate": None}
    if not watts_stream:
        return result

    np = normalized_power(watts_stream)
    if np is None:
        return result

    if_val = intensity_factor(np, ftp)
    tss_val = tss(moving_time_s, np, if_val, ftp)
    ftp_est = estimate_ftp(watts_stream, moving_time_s)

    result.update({
        "np_watts": np,
        "tss": tss_val,
        "if_value": if_val,
        "ftp_estimate": ftp_est,
    })
    return result


def ctl_atl(tss_by_date: dict) -> tuple[list, list, list]:
    """
    Compute CTL (42-day) and ATL (7-day) from a dict {date_str: tss_value}.
    Returns (dates, ctl_values, atl_values).
    """
    import pandas as pd
    if not tss_by_date:
        return [], [], []

    s = pd.Series(tss_by_date)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    full = s.resample("D").sum().fillna(0)

    ctl = full.ewm(span=42, adjust=False).mean()
    atl = full.ewm(span=7, adjust=False).mean()

    return (
        [d.strftime("%Y-%m-%d") for d in full.index],
        [round(v, 1) for v in ctl.values],
        [round(v, 1) for v in atl.values],
    )


# Standard durations (seconds) for power-curve analysis
POWER_CURVE_DURATIONS = [5, 15, 60, 300, 600, 1200, 3600]
POWER_CURVE_LABELS = {5: "5s", 15: "15s", 60: "1min", 300: "5min",
                      600: "10min", 1200: "20min", 3600: "1h"}


def best_power_for_duration(watts_stream: list[float], duration_s: int) -> Optional[float]:
    """Best (max) rolling average power sustained for `duration_s` seconds."""
    n = len(watts_stream)
    if n < duration_s:
        return None
    window_sum = sum(watts_stream[:duration_s])
    best = window_sum
    for i in range(duration_s, n):
        window_sum += watts_stream[i] - watts_stream[i - duration_s]
        if window_sum > best:
            best = window_sum
    return round(best / duration_s, 1)


def power_curve(streams_by_activity: dict[str, list[float]],
                durations: list[int] = None) -> dict[int, float]:
    """
    Aggregate power curve across many activities.
    `streams_by_activity`: {activity_id: watts_stream}
    Returns {duration_s: best_power_ever_seen}.
    """
    durations = durations or POWER_CURVE_DURATIONS
    best = {d: None for d in durations}
    for watts in streams_by_activity.values():
        if not watts:
            continue
        for d in durations:
            p = best_power_for_duration(watts, d)
            if p is not None and (best[d] is None or p > best[d]):
                best[d] = p
    return best


def decoupling(watts_stream: list[float], hr_stream: list[float]) -> Optional[float]:
    """
    Pw:HR decoupling (%) — compares the power-to-heart-rate ratio between the
    first and second half of an activity. Positive values indicate drift
    (cardiac fatigue): your HR rises relative to power as the effort continues.
    Formula: ((ratio_first_half - ratio_second_half) / ratio_first_half) * 100
    """
    n = min(len(watts_stream), len(hr_stream))
    if n < 600:  # need at least ~10 minutes of overlapping data
        return None

    half = n // 2
    w1, h1 = watts_stream[:half], hr_stream[:half]
    w2, h2 = watts_stream[half:n], hr_stream[half:n]

    avg_w1 = sum(w1) / len(w1)
    avg_h1 = sum(h1) / len(h1)
    avg_w2 = sum(w2) / len(w2)
    avg_h2 = sum(h2) / len(h2)

    if avg_h1 == 0 or avg_h2 == 0 or avg_w2 == 0:
        return None

    ratio1 = avg_w1 / avg_h1
    ratio2 = avg_w2 / avg_h2
    if ratio1 == 0:
        return None

    return round((ratio1 - ratio2) / ratio1 * 100, 1)


def detect_intervals(watts_stream: list[float], ftp: float,
                      threshold_pct: float = 0.88, min_duration_s: int = 90) -> list[dict]:
    """
    Detect sustained high-effort intervals within a ride.
    An interval is a contiguous stretch where power stays above
    `threshold_pct` * FTP for at least `min_duration_s` seconds.
    Returns a list of {start_s, end_s, duration_s, avg_watts}.
    """
    if not watts_stream or not ftp:
        return []

    threshold = threshold_pct * ftp
    intervals = []
    start = None

    for i, w in enumerate(watts_stream):
        above = w >= threshold
        if above and start is None:
            start = i
        elif not above and start is not None:
            duration = i - start
            if duration >= min_duration_s:
                seg = watts_stream[start:i]
                intervals.append({
                    "start_s": start, "end_s": i, "duration_s": duration,
                    "avg_watts": round(sum(seg) / len(seg), 1),
                })
            start = None

    if start is not None:
        duration = len(watts_stream) - start
        if duration >= min_duration_s:
            seg = watts_stream[start:]
            intervals.append({
                "start_s": start, "end_s": len(watts_stream), "duration_s": duration,
                "avg_watts": round(sum(seg) / len(seg), 1),
            })

    return intervals


# ---------------------------------------------------------------------------
# Fase 6 — "panel de decisiones": traducir métricas derivadas a algo accionable
# ---------------------------------------------------------------------------

HEURISTIC_DISCLAIMER = (
    "⚠️ Esto es una heurística orientativa basada en TSS/CTL/ATL/TSB — no "
    "sustituye el criterio de un entrenador ni considera factores externos "
    "como sueño, nutrición, estrés o enfermedad. Úsalo como una sugerencia "
    "de partida, no como una prescripción."
)


def fitness_fatigue_form_labels(ctl: float, atl: float, tsb: float) -> dict:
    """
    Traduce CTL/ATL/TSB (cifras abstractas) a etiquetas simples en lenguaje
    natural — "Fitness", "Fatiga" y "Forma" — para que el usuario no tenga
    que interpretar números derivados por sí mismo.
    """
    # Fitness: nivel de CTL (umbral orientativo para ciclistas recreativo-amateur)
    if ctl >= 70:
        fitness = "Alta"
    elif ctl >= 40:
        fitness = "Media"
    else:
        fitness = "Base / en construcción"

    # Fatiga: relación ATL vs CTL — ATL muy por encima de CTL = carga aguda alta
    if atl > ctl * 1.3:
        fatigue = "Alta"
    elif atl > ctl * 1.05:
        fatigue = "Moderada"
    else:
        fatigue = "Baja"

    # Forma: TSB (= CTL - ATL)
    if tsb < -20:
        form = "Comprometida (mucha fatiga acumulada)"
    elif tsb < -10:
        form = "Cargada (entrenando duro)"
    elif tsb <= 5:
        form = "Equilibrada"
    else:
        form = "Fresca"

    return {"fitness": fitness, "fatigue": fatigue, "form": form,
            "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(tsb, 1)}


def recommend_next_session(ctl: float, atl: float, tsb: float,
                            recent_hours: float = None,
                            recent_tss: float = None) -> dict:
    """
    Heurística simple de reglas que traduce el estado de forma actual en una
    sugerencia accionable para la próxima sesión. No es una prescripción
    médica/deportiva — ver HEURISTIC_DISCLAIMER.

    Devuelve {label, detail, color} listo para renderizar como tarjeta.
    """
    # Reglas ordenadas de "más cauteloso" a "más agresivo"
    if tsb < -20 or (recent_hours is not None and recent_hours > 12 and tsb < -10):
        return {
            "label": "Descanso o Z2 muy suave",
            "detail": ("Tu fatiga acumulada (TSB muy negativo) sugiere que tu cuerpo "
                       "necesita recuperarse. Lo ideal: día libre o, como mucho, "
                       "60-90 min en Z1-Z2 sin intensidad."),
            "color": "#F44336",
        }
    if tsb < -10:
        return {
            "label": "Z2 moderado, sin intensidad",
            "detail": ("Estás en una fase de carga — tu forma está algo comprometida. "
                       "Prioriza resistencia aeróbica (Z2) y evita series de alta "
                       "intensidad hoy; dale a tu cuerpo un día para asimilar."),
            "color": "#FF9800",
        }
    if tsb <= 5:
        return {
            "label": "Buen momento para series de calidad",
            "detail": ("Tu forma está equilibrada — fitness y fatiga en balance. "
                       "Es un buen día para meter intervalos de calidad (umbral, "
                       "VO2max) si tu plan lo contempla."),
            "color": "#4CAF50",
        }
    # tsb > 5 — fresco
    if recent_hours is not None and recent_hours < 5:
        return {
            "label": "Estás fresco — aprovecha para sumar volumen o calidad",
            "detail": ("Tu carga reciente ha sido baja y tu forma está fresca. "
                       "Es un buen momento para una salida larga de base o para "
                       "un entrenamiento de alta intensidad — según lo que tu "
                       "plan necesite más ahora mismo."),
            "color": "#2196F3",
        }
    return {
        "label": "Estás fresco — buen momento para un entreno de calidad",
        "detail": ("Tu forma está en positivo (TSB alto). Aprovecha para un "
                   "entrenamiento exigente: series, umbral o un objetivo "
                   "específico de tu calendario."),
        "color": "#2196F3",
    }


def aerobic_efficiency(watts_stream: list[float], hr_stream: list[float]) -> Optional[float]:
    """
    Eficiencia aeróbica: ratio potencia/FC promedio de una actividad
    (Watts por pulsación). Subir en el tiempo = misma FC produce más potencia,
    es decir, mejora de la base aeróbica. Es la contraparte "positiva" del
    decoupling: una sola cifra por actividad, comparable en una serie temporal.
    """
    n = min(len(watts_stream), len(hr_stream))
    if n < 300:  # al menos ~5 minutos de datos simultáneos
        return None

    avg_w = sum(watts_stream[:n]) / n
    avg_h = sum(hr_stream[:n]) / n
    if avg_h == 0:
        return None

    return round(avg_w / avg_h, 2)


def detect_milestones(activities: list[dict], computed_by_id: dict,
                       power_curve_history: dict = None,
                       lookback_days: int = 30) -> list[dict]:
    """
    Compara el periodo reciente (últimos `lookback_days` días) contra el
    histórico para detectar hitos dignos de destacar. No requiere ML — son
    comparaciones directas de máximos/promedios.

    `activities`: lista de actividades (con start_date, moving_time_s, etc.)
    `computed_by_id`: {activity_id: {ftp_estimate, np_watts, tss, ...}}
    `power_curve_history`: opcional, {duration_s: best_watts} ya calculado

    Devuelve una lista de {title, detail, icon} para mostrar como tarjetas/badges.
    """
    import datetime as _dt

    if not activities:
        return []

    milestones = []

    try:
        now = _dt.datetime.now()
        cutoff = now - _dt.timedelta(days=lookback_days)

        def _parse_date(a):
            try:
                return _dt.datetime.strptime((a.get("start_date") or "")[:10], "%Y-%m-%d")
            except Exception:
                return None

        recent = [a for a in activities if (d := _parse_date(a)) and d >= cutoff]
        older = [a for a in activities if (d := _parse_date(a)) and d < cutoff]

        # 1. FTP estimado: ¿el mejor reciente supera al mejor histórico previo?
        recent_ftp = max((computed_by_id.get(a["id"], {}).get("ftp_estimate") or 0 for a in recent), default=0)
        older_ftp = max((computed_by_id.get(a["id"], {}).get("ftp_estimate") or 0 for a in older), default=0)
        if recent_ftp and older_ftp and recent_ftp > older_ftp:
            pct = (recent_ftp - older_ftp) / older_ftp * 100
            if pct >= 1.5:
                milestones.append({
                    "title": f"Nuevo mejor FTP estimado: {recent_ftp:.0f} W",
                    "detail": f"+{pct:.0f}% respecto a tu mejor estimación anterior ({older_ftp:.0f} W).",
                    "icon": "⚡",
                })
        elif recent_ftp and not older_ftp:
            milestones.append({
                "title": f"FTP estimado: {recent_ftp:.0f} W",
                "detail": "Primera estimación de FTP registrada en tu histórico reciente.",
                "icon": "⚡",
            })

        # 2. Mejor potencia normalizada (NP) reciente vs histórica
        recent_np = max((computed_by_id.get(a["id"], {}).get("np_watts") or 0 for a in recent), default=0)
        older_np = max((computed_by_id.get(a["id"], {}).get("np_watts") or 0 for a in older), default=0)
        if recent_np and older_np and recent_np > older_np:
            milestones.append({
                "title": f"Mejor potencia normalizada: {recent_np:.0f} W",
                "detail": f"Superaste tu anterior mejor NP de {older_np:.0f} W en los últimos {lookback_days} días.",
                "icon": "🔥",
            })

        # 3. Récord de volumen semanal (horas) reciente
        def _week_key(a):
            d = _parse_date(a)
            return d.isocalendar()[:2] if d else None

        weekly_hours: dict = {}
        for a in activities:
            wk = _week_key(a)
            if wk:
                weekly_hours[wk] = weekly_hours.get(wk, 0) + (a.get("moving_time_s") or 0) / 3600

        if weekly_hours:
            sorted_weeks = sorted(weekly_hours.items())
            best_week, best_hours = max(sorted_weeks, key=lambda x: x[1])
            # ¿el récord cae dentro del periodo reciente?
            recent_weeks = {wk for a in recent if (wk := _week_key(a))}
            if best_week in recent_weeks and len(sorted_weeks) > 1:
                second_best = max((h for wk, h in sorted_weeks if wk != best_week), default=0)
                if best_hours > second_best:
                    milestones.append({
                        "title": f"Récord de volumen semanal: {best_hours:.1f} h",
                        "detail": f"Tu semana más larga hasta ahora — superando las {second_best:.1f} h previas.",
                        "icon": "📈",
                    })

        # 4. Curva de potencia: ¿algún PR reciente en duraciones clave?
        if power_curve_history:
            for dur in (300, 1200, 3600):  # 5min, 20min, 1h
                best = power_curve_history.get(dur)
                if not best:
                    continue
                # ¿el PR proviene de una actividad reciente?
                for a in recent:
                    w = computed_by_id.get(a["id"], {})
                    # Heurística simple: si el NP de la actividad reciente es muy
                    # cercano al mejor histórico de esa duración, lo consideramos candidato
                    if w.get("np_watts") and abs(w["np_watts"] - best) / best < 0.03:
                        milestones.append({
                            "title": f"Posible nuevo mejor esfuerzo de {POWER_CURVE_LABELS.get(dur, f'{dur}s')}: {best:.0f} W",
                            "detail": f"Detectado en una actividad de los últimos {lookback_days} días.",
                            "icon": "🏆",
                        })
                        break
    except Exception:
        # Detección de hitos es "nice to have" — nunca debe romper la página
        return milestones

    return milestones
