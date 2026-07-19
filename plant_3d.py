# -*- coding: utf-8 -*-
"""
Vue 3D de la chaine JFC5 - version dynamique complete avec traitement d'air et bacs.

Corrections v2 :
  - build_equipment_status enrichi : air_filter, drying_tower, turbo_blower
    utilisent les vraies valeurs des dicts fr/dr/turbo transmis.
  - payload enrichi : air_filter.Q_Nm3h, drying_tower.w_gNm3, turbo_blower.N_rpm
  - unitMetrics enrichi : toutes les grandeurs réelles affichées pour chaque
    équipement du traitement d'air.
  - fillTankPanel : affiche niveau / T / masse / alarme avec code couleur.
  - Panel latéral "Traitement d'air" ajouté avec valeurs en temps réel.
  - Score global recalculé en incluant le traitement d'air (filtre + séchage).
"""

from __future__ import annotations

import json
import streamlit as st
import streamlit.components.v1 as components


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


# ══════════════════════════════════════════════════════════════════════
# build_equipment_status — version corrigée
# ══════════════════════════════════════════════════════════════════════

def build_equipment_status(resultats: dict,
                            fr: dict | None = None,
                            dr: dict | None = None,
                            turbo: dict | None = None) -> dict:
    status = {k: ("off", "Arrêt") for k in
              ["air_filter", "drying_tower", "turbo_blower",
               "furnace", "boiler", "converter",
               "absorption_jd02", "absorption_jd03"]}

    # ── Filtre d'air ─────────────────────────────────────────────
    if fr and fr.get("delta_P_mmWC") is not None:
        dp = _safe_float(fr.get("delta_P_mmWC", 0.0))
        T_out = _safe_float(fr.get("T_out", 0.0))
        if dp > 120.0:
            status["air_filter"] = ("err",  f"ΔP {dp:.0f} mmCE")
        elif dp > 90.0:
            status["air_filter"] = ("warn", f"ΔP {dp:.0f} mmCE")
        elif T_out > 0:
            status["air_filter"] = ("running", f"ΔP {dp:.1f} mmCE / {T_out:.1f} °C")
        else:
            status["air_filter"] = ("warn", "Données partielles")

    # ── Tour de séchage ───────────────────────────────────────────
    if dr and dr.get("eff") is not None:
        eff = _safe_float(dr.get("eff", 0.0))
        w   = _safe_float(dr.get("w_gNm3", 0.0))
        if eff <= 0.0:
            status["drying_tower"] = ("off",  "Arrêt")
        elif eff < 90.0:
            status["drying_tower"] = ("warn", f"Eff. {eff:.1f} % — H₂O {w:.4f} g/Nm³")
        else:
            status["drying_tower"] = ("running", f"Eff. {eff:.1f} % — H₂O {w:.4f} g/Nm³")

    # ── Turbosoufflante ───────────────────────────────────────────
    if turbo and turbo.get("surge_margin_pct") is not None:
        surge = _safe_float(turbo.get("surge_margin_pct", 100.0))
        N_rpm = _safe_float(turbo.get("N_rpm", 0.0))
        W_kW  = _safe_float(turbo.get("W_shaft_kW", 0.0))
        if surge < 10.0:
            status["turbo_blower"] = ("err",  f"Pompage! marge {surge:.0f} %")
        elif surge < 20.0:
            status["turbo_blower"] = ("warn", f"Marge {surge:.0f} % — {N_rpm:.0f} rpm")
        elif N_rpm > 0:
            status["turbo_blower"] = ("running", f"{N_rpm:.0f} rpm — {W_kW:.0f} kW")
        else:
            status["turbo_blower"] = ("warn", "Données partielles")

    if not resultats:
        return status

    four  = resultats.get("four",        {}) or {}
    chaud = resultats.get("chaudiere",   {}) or {}
    conv  = resultats.get("convertisseur", {}) or {}
    jd02  = resultats.get("jd02",        {}) or {}
    jd03  = resultats.get("jd03",        {}) or {}

    # ── Four ─────────────────────────────────────────────────────
    t_flamme = _safe_float(four.get("T_flamme", 0.0))
    T_out_f  = _safe_float(four.get("T_out", 0.0))
    if t_flamme > 1250.0:
        status["furnace"] = ("err",     f"T flamme {t_flamme:.0f} °C")
    elif t_flamme > 1150.0:
        status["furnace"] = ("warn",    f"T flamme {t_flamme:.0f} °C — T sortie {T_out_f:.0f} °C")
    elif t_flamme > 0:
        status["furnace"] = ("running", f"T flamme {t_flamme:.0f} °C — T sortie {T_out_f:.0f} °C")

    # ── Chaudière ─────────────────────────────────────────────────
    t_out_chaud = _safe_float(chaud.get("T_out", 420.0))
    steam       = _safe_float(chaud.get("steam_flow", 0.0))
    if abs(t_out_chaud - 420.0) > 25.0:
        status["boiler"] = ("warn",    f"T sortie {t_out_chaud:.0f} °C — {steam:.1f} t/h")
    elif steam > 0:
        status["boiler"] = ("running", f"T sortie {t_out_chaud:.0f} °C — {steam:.1f} t/h")

    # ── Convertisseur ────────────────────────────────────────────
    tau_final = _safe_float(conv.get("tau_final_pct", 0.0))
    if tau_final < 95.0 and tau_final > 0:
        status["converter"] = ("warn",    f"Conv. {tau_final:.1f} %")
    elif tau_final > 0:
        status["converter"] = ("running", f"Conv. {tau_final:.2f} %")

    # ── Tours d'absorption ────────────────────────────────────────
    for key, eq_key in [("jd02", "absorption_jd02"), ("jd03", "absorption_jd03")]:
        eq = resultats.get(key, {}) or {}
        eff_abs  = _safe_float(eq.get("eff_abs", 0.0))
        ppm_out  = _safe_float(eq.get("ppm_SO3_out", 0.0))
        if eff_abs <= 0:
            pass  # reste "off"
        elif eff_abs < 98.0:
            status[eq_key] = ("warn",    f"Eff. {eff_abs:.1f} % — SO₃ {ppm_out:.1f} ppm")
        else:
            status[eq_key] = ("running", f"Eff. {eff_abs:.2f} % — SO₃ {ppm_out:.2f} ppm")

    return status


# ══════════════════════════════════════════════════════════════════════
# _tank_payload
# ══════════════════════════════════════════════════════════════════════

def _tank_payload(tank) -> dict:
    if tank is None:
        return {"level_pct": 0.0, "T_C": 0.0, "mass_t": 0.0, "name": "N/A", "alarm": False}
    state = getattr(tank, "state", {}) or {}
    alarm = bool(state.get("solidification_risk") or
                 state.get("overheat_risk") or
                 state.get("dilution_risk"))
    mass_kg = _safe_float(state.get("mass_kg",
                          getattr(tank, "mass_kg", 0.0)))
    return {
        "level_pct": _safe_float(state.get("level_pct",
                                 getattr(tank, "level_pct", 0.0))),
        "T_C":       _safe_float(state.get("T_C",
                                 getattr(tank, "T", 0.0))),
        "mass_t":    mass_kg / 1000.0,
        "name":      getattr(tank, "name", "Bac"),
        "alarm":     alarm,
    }


# ══════════════════════════════════════════════════════════════════════
# render_plant_3d — point d'entrée principal
# ══════════════════════════════════════════════════════════════════════

def render_plant_3d(resultats: dict,
                    fr:   dict | None = None,
                    dr:   dict | None = None,
                    turbo: dict | None = None,
                    tank_system=None,
                    mount_id: int = 0):

    instance_id = f"plant3d-{int(mount_id)}"

    if not resultats:
        st.warning("Aucun résultat de simulation disponible pour la vue 3D.")
        return

    four  = resultats.get("four",          {}) or {}
    chaud = resultats.get("chaudiere",     {}) or {}
    conv  = resultats.get("convertisseur", {}) or {}
    jd02  = resultats.get("jd02",          {}) or {}
    jd03  = resultats.get("jd03",          {}) or {}
    fr    = fr    or {}
    dr    = dr    or {}
    turbo = turbo or {}

    status = build_equipment_status(resultats, fr, dr, turbo)

    tank1 = getattr(tank_system, "sulfur_tank_1", None) if tank_system else None
    tank2 = getattr(tank_system, "sulfur_tank_2", None) if tank_system else None
    tanka = getattr(tank_system, "acid_tank",     None) if tank_system else None

    # ── Score global ─────────────────────────────────────────────
    tau      = _safe_float(conv.get("tau_final_pct",  0.0))
    eff_jd03 = _safe_float(jd03.get("eff_abs",        0.0))
    steam    = _safe_float(chaud.get("steam_flow",     0.0))
    eff_dry  = _safe_float(dr.get("eff",               0.0))
    score = ((tau / 100) * 35
             + (eff_jd03 / 100) * 25
             + (steam / 200) * 25
             + (min(eff_dry, 100) / 100) * 15)
    score = min(100, max(0, score))

    payload = {
        "status": {k: {"code": v[0], "label": v[1]} for k, v in status.items()},

        # ── Traitement d'air ──────────────────────────────────────
        "air_filter": {
            "T_out":         _safe_float(fr.get("T_out",         30.0)),
            "delta_P_mmWC":  _safe_float(fr.get("delta_P_mmWC",  0.0)),
            "Q_Nm3h":        _safe_float(fr.get("Q_Nm3h",
                                         four.get("Air_flow", 363934.0))),
        },
        "drying_tower": {
            "T_gas_out":  _safe_float(dr.get("TG_out",       30.0)),
            "T_acid_out": _safe_float(dr.get("TL_out",       50.0)),
            "eff":        _safe_float(dr.get("eff",           0.0)),
            "w_gNm3":     _safe_float(dr.get("w_gNm3",        0.0)),
            "w_H2SO4":    _safe_float(dr.get("w_H2SO4_in",   98.5)),
        },
        "turbo_blower": {
            "T_out":            _safe_float(turbo.get("T_out_C",          0.0)),
            "P_out_kPa":        _safe_float(turbo.get("P_out_kPa",        0.0)),
            "W_shaft_kW":       _safe_float(turbo.get("W_shaft_kW",       0.0)),
            "N_rpm":            _safe_float(turbo.get("N_rpm",            0.0)),
            "delta_P_mmCE":     _safe_float(turbo.get("delta_P_mmCE",     0.0)),
            "surge_margin_pct": _safe_float(turbo.get("surge_margin_pct", 100.0)),
        },

        # ── Procédé ───────────────────────────────────────────────
        "four": {
            "T_out":          _safe_float(four.get("T_out")),
            "T_flamme":       _safe_float(four.get("T_flamme")),
            "S_flow":         _safe_float(four.get("S_flow")),
            "Air_flow":       _safe_float(four.get("Air_flow")),
            "SO2_pct":        _safe_float(four.get("SO2_pct")),
            "O2_pct":         _safe_float(four.get("O2_pct")),
            "eta_combustion": _safe_float(four.get("eta_combustion")),
        },
        "boiler": {
            "T_in":        _safe_float(chaud.get("T_in")),
            "T_out":       _safe_float(chaud.get("T_out")),
            "steam_flow":  _safe_float(chaud.get("steam_flow")),
            "power_mw":    _safe_float(chaud.get("power_mw")),
            "bypass_pct":  _safe_float(chaud.get("bypass_pct")),
        },
        "converter": {
            "T_in_lits":    [_safe_float(t) for t in conv.get("T_in_lits",  [0,0,0,0])],
            "T_out_lits":   [_safe_float(t) for t in conv.get("T_out_lits", [0,0,0,0])],
            "tau_lits":     [_safe_float(t) for t in conv.get("tau_lits",   [0,0,0,0])],
            "dp_lits":      [_safe_float(t) for t in conv.get("dp_lits",    [0,0,0,0])],
            "tau_final_pct": _safe_float(conv.get("tau_final_pct")),
        },
        "jd02": {
            "T_gas_in":    _safe_float(jd02.get("T_gas_in")),
            "T_gas_out":   _safe_float(jd02.get("T_gas_out")),
            "T_acid_in":   _safe_float(jd02.get("T_acid_in")),
            "T_acid_out":  _safe_float(jd02.get("T_acid_out")),
            "eff_abs":     _safe_float(jd02.get("eff_abs")),
            "ppm_SO3_out": _safe_float(jd02.get("ppm_SO3_out")),
            "w_H2SO4_out": _safe_float(jd02.get("w_H2SO4_out")),
        },
        "jd03": {
            "T_gas_in":    _safe_float(jd03.get("T_gas_in")),
            "T_gas_out":   _safe_float(jd03.get("T_gas_out")),
            "T_acid_in":   _safe_float(jd03.get("T_acid_in")),
            "T_acid_out":  _safe_float(jd03.get("T_acid_out")),
            "eff_abs":     _safe_float(jd03.get("eff_abs")),
            "ppm_SO3_out": _safe_float(jd03.get("ppm_SO3_out")),
            "w_H2SO4_out": _safe_float(jd03.get("w_H2SO4_out")),
        },

        # ── Bacs ─────────────────────────────────────────────────
        "tanks": {
            "sulfur_1": _tank_payload(tank1),
            "sulfur_2": _tank_payload(tank2),
            "acid":     _tank_payload(tanka),
        },
        "global_score": round(score, 1),
    }

    payload_json = json.dumps(payload, ensure_ascii=True)
    html = _HTML_TEMPLATE.replace("__PAYLOAD_JSON__", payload_json)
    html = html.replace("__INSTANCE_ID__", instance_id)

    components.html(html, height=860, scrolling=False)
    st.caption(
        "Vue 3D dynamique : Filtre air → Tour séchage → Turbosoufflante → "
        "Four → Chaudière → Convertisseur → Absorption. "
        "Couleurs, vitesses et niveaux s'adaptent aux données process.")


# ══════════════════════════════════════════════════════════════════════
# _HTML_TEMPLATE
# ══════════════════════════════════════════════════════════════════════

_HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8" />
<style>
  html, body { margin:0; padding:0; width:100%; height:100%; background:#171717;
    font-family: Inter, Segoe UI, Arial, sans-serif; overflow:hidden; }
  .plant3d { height:100%; display:flex; flex-direction:column; background:#f3f4f6;
    border:1px solid #b7bcc5; border-radius:8px; }
  .topbar { height:42px; background:#202124; color:#f9fafb; display:flex;
    align-items:center; justify-content:space-between; padding:0 14px;
    border-bottom:3px solid #f5c542; font-size:13px; font-weight:800; }
  .body { flex:1; display:grid; grid-template-columns: minmax(0,1fr) 340px; min-height:0; }
  .canvasHost { position:relative; min-height:0; background:#d7d9de; }
  .panel { background:#f8fafc; border-left:1px solid #c7cbd1; overflow-y:auto; padding:10px; }
  .section { font-size:11px; font-weight:900; color:#111827; text-transform:uppercase;
    margin:8px 0 6px; border-bottom:2px solid #f5c542; padding-bottom:3px; }
  .card { border:1px solid #d1d5db; border-radius:6px; background:#fff; padding:8px;
    margin-bottom:8px; }
  .kv { display:flex; justify-content:space-between; gap:8px; font-size:12px;
    padding:3px 0; border-bottom:1px solid #edf0f3; }
  .kv:last-child { border-bottom:none; }
  .kv .lbl { color:#4b5563; }
  .value { font-family:Consolas,monospace; font-weight:900; color:#0f766e; white-space:nowrap; }
  .value.warn { color:#d97706; }
  .value.err  { color:#dc2626; }
  .unitStatus { display:grid; grid-template-columns:1fr auto; gap:6px; font-size:11px;
    padding:4px 0; border-bottom:1px solid #edf0f3; align-items:center; }
  .unitStatus:last-child { border-bottom:none; }
  .statusPill { border-radius:6px; padding:2px 7px; font-weight:800;
    border:1px solid #cbd5e1; font-size:10px; text-align:center; white-space:nowrap; }
  .statusPill.running { background:#dcfce7; border-color:#86efac; color:#166534; }
  .statusPill.warn    { background:#fef3c7; border-color:#f59e0b; color:#92400e; }
  .statusPill.err     { background:#fee2e2; border-color:#ef4444; color:#991b1b; }
  .statusPill.off     { background:#f3f4f6; border-color:#d1d5db; color:#6b7280; }
  .viewControls { position:absolute; left:10px; top:10px; z-index:6;
    display:flex; flex-wrap:wrap; gap:5px; max-width:85%; }
  .viewBtn { border:1px solid #9ca3af; background:rgba(255,255,255,.9); color:#111827;
    border-radius:5px; padding:5px 8px; font-size:10px; font-weight:800; cursor:pointer;
    transition:background .15s; }
  .viewBtn:hover { background:rgba(245,197,66,.8); }
  .viewBtn.is-active { border-color:#f59e0b; background:#fde68a; }
  .tooltip3d { position:absolute; display:none; z-index:8; max-width:230px;
    border:1px solid #111827; border-radius:6px; background:rgba(17,24,39,.94);
    color:#f9fafb; padding:8px 9px; font-size:12px; pointer-events:none;
    line-height:1.55; }
  .tooltip3d strong { display:block; color:#f5c542; margin-bottom:4px; font-size:13px; }
  .score-bar { flex:1; height:8px; background:#e5e7eb; border-radius:4px; overflow:hidden; }
  .score-fill { height:100%; background:linear-gradient(90deg,#22c55e,#f5c542);
    border-radius:4px; transition:width .3s; }
  .tank-level-bar { height:6px; background:#e5e7eb; border-radius:3px; overflow:hidden; margin-top:3px; }
  .tank-level-fill { height:100%; border-radius:3px; transition:width .3s; }
  .sub-lbl { font-size:10px; color:#9ca3af; margin:4px 0 2px; font-weight:700;
    text-transform:uppercase; letter-spacing:.3px; }
</style>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
<div class="plant3d" data-instance="__INSTANCE_ID__">
  <div class="topbar">
    <div>Vue 3D dynamique — JFC5 — Ligne sulfurique</div>
    <div id="clockDisplay" style="font-size:11px;font-weight:400;color:#9ca3af;"></div>
  </div>
  <div class="body">
    <div class="canvasHost" id="canvasHost">
      <div class="viewControls">
        <button class="viewBtn is-active" data-view="global">Vue globale</button>
        <button class="viewBtn" data-view="air_filter">Filtre air</button>
        <button class="viewBtn" data-view="drying_tower">Tour séchage</button>
        <button class="viewBtn" data-view="turbo_blower">Turbo</button>
        <button class="viewBtn" data-view="furnace">Four</button>
        <button class="viewBtn" data-view="boiler">Chaudière</button>
        <button class="viewBtn" data-view="converter">Convertisseur</button>
        <button class="viewBtn" data-view="absorption">Absorption</button>
        <button class="viewBtn" data-view="tanks">Bacs</button>
      </div>
      <div class="tooltip3d" id="tooltip3d"></div>
    </div>

    <!-- PANNEAU LATÉRAL -->
    <aside class="panel">

      <!-- Score global -->
      <div class="section">Performance globale</div>
      <div class="card">
        <div class="kv">
          <span class="lbl">Score process</span>
          <span class="value" id="globalScore">--</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;margin-top:4px;">
          <span style="font-size:10px;color:#9ca3af;">0</span>
          <div class="score-bar">
            <div class="score-fill" id="scoreFill" style="width:0%;"></div>
          </div>
          <span style="font-size:10px;color:#9ca3af;">100</span>
        </div>
      </div>

      <!-- État des équipements -->
      <div class="section">État des équipements</div>
      <div class="card" id="statusCard"></div>

      <!-- Traitement d'air (NOUVEAU) -->
      <div class="section">Traitement d'air</div>
      <div class="card" id="airTreatCard"></div>

      <!-- Bacs de stockage -->
      <div class="section">Bacs de stockage</div>
      <div class="card" id="tankCard"></div>

      <!-- Équipement sélectionné -->
      <div class="section">Équipement sélectionné</div>
      <div class="card" id="selectedCard">
        <div style="color:#71717a;font-size:12px;line-height:1.4;">
          Cliquez sur un équipement dans la vue 3D pour afficher ses grandeurs.
        </div>
      </div>

    </aside>
  </div>
</div>

<script>
// ─────────────────────────────────────────────────────────────────────
// Données injectées depuis Python
// ─────────────────────────────────────────────────────────────────────
const payload = __PAYLOAD_JSON__;

// ─────────────────────────────────────────────────────────────────────
// Utilitaires
// ─────────────────────────────────────────────────────────────────────
function fmt(v, d) {
  const n = Number(v || 0);
  return isNaN(n) ? "—" : n.toFixed(d == null ? 1 : d);
}
function fmtK(v) { return fmt(v / 1000, 1) + " kNm³/h"; }
function statusColour(code) {
  if (code === "err")     return "#ef4444";
  if (code === "warn")    return "#f59e0b";
  if (code === "running") return "#22c55e";
  return "#9ca3af";
}
function _sf(v, def) { const n = Number(v); return isNaN(n) ? def : n; }

const equip_labels = {
  air_filter:       "Filtre air 301FS01",
  drying_tower:     "Tour séchage 401AD02",
  turbo_blower:     "Turbosoufflante 401AC01/02",
  furnace:          "Four 401AF01",
  boiler:           "Chaudière 401AV01",
  converter:        "Convertisseur 401AD01",
  absorption_jd02:  "Absorption JD02 401AJ02",
  absorption_jd03:  "Absorption JD03 401AJ03",
};

// ─────────────────────────────────────────────────────────────────────
// Métriques affichées par équipement (panneau "sélectionné")
// ─────────────────────────────────────────────────────────────────────
function unitMetrics(id) {
  const af = payload.air_filter  || {};
  const dt = payload.drying_tower|| {};
  const tb = payload.turbo_blower|| {};
  const f  = payload.four        || {};
  const b  = payload.boiler      || {};
  const c  = payload.converter   || {};
  const j2 = payload.jd02        || {};
  const j3 = payload.jd03        || {};
  const t  = payload.tanks       || {};

  const map = {
    air_filter: [
      ["T sortie",          fmt(af.T_out, 1)    + " °C"],
      ["Perte de charge",   fmt(af.delta_P_mmWC,1) + " mmCE"],
      ["Débit air",         fmtK(af.Q_Nm3h)],
    ],
    drying_tower: [
      ["T gaz sortie",      fmt(dt.T_gas_out, 1) + " °C"],
      ["T acide sortie",    fmt(dt.T_acid_out,1) + " °C"],
      ["Efficacité abs.",   fmt(dt.eff, 2)       + " %"],
      ["H₂O résiduelle",    fmt(dt.w_gNm3, 4)   + " g/Nm³"],
      ["Conc. H₂SO₄",       fmt(dt.w_H2SO4, 2)  + " %"],
    ],
    turbo_blower: [
      ["T sortie",          fmt(tb.T_out, 1)         + " °C"],
      ["Vitesse rotation",  fmt(tb.N_rpm, 0)         + " rpm"],
      ["ΔP compresseur",    fmt(tb.delta_P_mmCE, 0)  + " mmCE"],
      ["Puissance arbre",   fmt(tb.W_shaft_kW, 0)    + " kW"],
      ["Marge pompage",     fmt(tb.surge_margin_pct,1)+ " %"],
    ],
    furnace: [
      ["T sortie four",     fmt(f.T_out, 1)         + " °C"],
      ["T flamme",          fmt(f.T_flamme, 1)       + " °C"],
      ["Débit soufre",      fmt(f.S_flow, 2)         + " kg/min"],
      ["Débit air",         fmtK(f.Air_flow)],
      ["SO₂ sortie",        fmt(f.SO2_pct, 2)        + " %"],
      ["O₂ sortie",         fmt(f.O2_pct, 2)         + " %"],
      ["η combustion",      fmt(f.eta_combustion, 1) + " %"],
    ],
    boiler: [
      ["T entrée",          fmt(b.T_in, 1)   + " °C"],
      ["T sortie",          fmt(b.T_out, 1)  + " °C"],
      ["Vapeur produite",   fmt(b.steam_flow, 2) + " t/h"],
      ["Puissance récup.",  fmt(b.power_mw, 2)   + " MW"],
      ["Bypass chaud.",     fmt(b.bypass_pct, 1) + " %"],
    ],
    converter: [
      ["Conv. finale τ",    fmt(c.tau_final_pct, 2) + " %"],
      ["T sortie lit 1",    fmt((c.T_out_lits||[])[0], 1) + " °C  τ=" + fmt((c.tau_lits||[])[0],2) + "%"],
      ["T sortie lit 2",    fmt((c.T_out_lits||[])[1], 1) + " °C  τ=" + fmt((c.tau_lits||[])[1],2) + "%"],
      ["T sortie lit 3",    fmt((c.T_out_lits||[])[2], 1) + " °C  τ=" + fmt((c.tau_lits||[])[2],2) + "%"],
      ["T sortie lit 4",    fmt((c.T_out_lits||[])[3], 1) + " °C  τ=" + fmt((c.tau_lits||[])[3],2) + "%"],
      ["ΔP lit 1→4 (kPa)", ((c.dp_lits||[]).map(v=>fmt(v,2)).join(" / "))],
    ],
    absorption_jd02: [
      ["T gaz entrée",      fmt(j2.T_gas_in, 1)    + " °C"],
      ["T gaz sortie",      fmt(j2.T_gas_out, 1)   + " °C"],
      ["T acide entrée",    fmt(j2.T_acid_in, 1)   + " °C"],
      ["T acide sortie",    fmt(j2.T_acid_out, 1)  + " °C"],
      ["Efficacité abs.",   fmt(j2.eff_abs, 2)      + " %"],
      ["SO₃ sortie",        fmt(j2.ppm_SO3_out, 2) + " ppm"],
      ["w H₂SO₄ sortie",   fmt(j2.w_H2SO4_out, 2) + " %"],
    ],
    absorption_jd03: [
      ["T gaz entrée",      fmt(j3.T_gas_in, 1)    + " °C"],
      ["T gaz sortie",      fmt(j3.T_gas_out, 1)   + " °C"],
      ["T acide entrée",    fmt(j3.T_acid_in, 1)   + " °C"],
      ["T acide sortie",    fmt(j3.T_acid_out, 1)  + " °C"],
      ["Efficacité abs.",   fmt(j3.eff_abs, 2)      + " %"],
      ["SO₃ sortie",        fmt(j3.ppm_SO3_out, 2) + " ppm"],
      ["w H₂SO₄ sortie",   fmt(j3.w_H2SO4_out, 2) + " %"],
    ],
    tank_sulfur_1: [
      ["Niveau", fmt((t.sulfur_1||{}).level_pct, 1) + " %"],
      ["Température", fmt((t.sulfur_1||{}).T_C, 1) + " °C"],
      ["Masse stockée", fmt((t.sulfur_1||{}).mass_t, 2) + " t"],
    ],
    tank_sulfur_2: [
      ["Niveau", fmt((t.sulfur_2||{}).level_pct, 1) + " %"],
      ["Température", fmt((t.sulfur_2||{}).T_C, 1) + " °C"],
      ["Masse stockée", fmt((t.sulfur_2||{}).mass_t, 2) + " t"],
    ],
    tank_acid: [
      ["Niveau", fmt((t.acid||{}).level_pct, 1) + " %"],
      ["Température", fmt((t.acid||{}).T_C, 1) + " °C"],
      ["Masse stockée", fmt((t.acid||{}).mass_t, 2) + " t"],
    ],
  };
  return map[id] || [];
}

// ─────────────────────────────────────────────────────────────────────
// Remplissage du panneau statut équipements
// ─────────────────────────────────────────────────────────────────────
function fillStatusPanel() {
  const status = payload.status || {};
  document.getElementById("statusCard").innerHTML =
    Object.keys(equip_labels).map(id => {
      const s = status[id] || {code:"off", label:"Arrêt"};
      return `<div class="unitStatus">
        <span style="font-size:11px;">${equip_labels[id]}</span>
        <span class="statusPill ${s.code}">${s.label}</span>
      </div>`;
    }).join("");
}

// ─────────────────────────────────────────────────────────────────────
// Remplissage du panneau traitement d'air (NOUVEAU)
// ─────────────────────────────────────────────────────────────────────
function fillAirTreatPanel() {
  const af = payload.air_filter   || {};
  const dt = payload.drying_tower || {};
  const tb = payload.turbo_blower || {};

  const surgeCls = _sf(tb.surge_margin_pct, 100) < 15 ? "err" :
                   _sf(tb.surge_margin_pct, 100) < 25 ? "warn" : "";
  const effCls   = _sf(dt.eff, 99) < 90 ? "warn" : "";

  document.getElementById("airTreatCard").innerHTML = `
    <div class="sub-lbl">Filtre air 301FS01</div>
    <div class="kv"><span class="lbl">T sortie</span>
      <span class="value">${fmt(af.T_out,1)} °C</span></div>
    <div class="kv"><span class="lbl">ΔP filtre</span>
      <span class="value">${fmt(af.delta_P_mmWC,1)} mmCE</span></div>
    <div class="kv"><span class="lbl">Débit air</span>
      <span class="value">${fmtK(af.Q_Nm3h)}</span></div>

    <div class="sub-lbl">Tour de séchage 401AD02</div>
    <div class="kv"><span class="lbl">T gaz sortie</span>
      <span class="value">${fmt(dt.T_gas_out,1)} °C</span></div>
    <div class="kv"><span class="lbl">T acide sortie</span>
      <span class="value">${fmt(dt.T_acid_out,1)} °C</span></div>
    <div class="kv"><span class="lbl">Efficacité abs.</span>
      <span class="value ${effCls}">${fmt(dt.eff,2)} %</span></div>
    <div class="kv"><span class="lbl">H₂O résiduelle</span>
      <span class="value">${fmt(dt.w_gNm3,4)} g/Nm³</span></div>
    <div class="kv"><span class="lbl">Conc. H₂SO₄</span>
      <span class="value">${fmt(dt.w_H2SO4,2)} %</span></div>

    <div class="sub-lbl">Turbosoufflante 401AC01/02</div>
    <div class="kv"><span class="lbl">T sortie</span>
      <span class="value">${fmt(tb.T_out,1)} °C</span></div>
    <div class="kv"><span class="lbl">Vitesse rotation</span>
      <span class="value">${fmt(tb.N_rpm,0)} rpm</span></div>
    <div class="kv"><span class="lbl">ΔP compresseur</span>
      <span class="value">${fmt(tb.delta_P_mmCE,0)} mmCE</span></div>
    <div class="kv"><span class="lbl">Puissance arbre</span>
      <span class="value">${fmt(tb.W_shaft_kW,0)} kW</span></div>
    <div class="kv"><span class="lbl">Marge pompage</span>
      <span class="value ${surgeCls}">${fmt(tb.surge_margin_pct,1)} %</span></div>
  `;
}

// ─────────────────────────────────────────────────────────────────────
// Remplissage du panneau bacs
// ─────────────────────────────────────────────────────────────────────
function fillTankPanel() {
  const t = payload.tanks || {};
  const rows = [
    ["Bac soufre 1 (401AS01)", t.sulfur_1, "#f59e0b"],
    ["Bac soufre 2 (401AS02)", t.sulfur_2, "#f59e0b"],
    ["Bac acide   (401AA01)",  t.acid,     "#22c55e"],
  ];
  document.getElementById("tankCard").innerHTML = rows.map(([label, d, col]) => {
    d = d || {level_pct:0, T_C:0, mass_t:0, alarm:false};
    const alarmBadge = d.alarm
      ? '<span style="color:#dc2626;font-weight:900;font-size:11px;margin-left:4px;">⚠ ALARME</span>'
      : '';
    const lvl = Math.min(100, Math.max(0, _sf(d.level_pct, 0)));
    return `
      <div style="margin-bottom:8px;">
        <div style="font-size:11px;font-weight:700;color:#374151;margin-bottom:3px;">
          ${label}${alarmBadge}
        </div>
        <div class="kv"><span class="lbl">Niveau</span>
          <span class="value">${fmt(d.level_pct,1)} %</span></div>
        <div class="tank-level-bar">
          <div class="tank-level-fill"
               style="width:${lvl}%;background:${d.alarm?'#ef4444':col};"></div>
        </div>
        <div class="kv" style="margin-top:3px;"><span class="lbl">Température</span>
          <span class="value">${fmt(d.T_C,1)} °C</span></div>
        <div class="kv"><span class="lbl">Masse stockée</span>
          <span class="value">${fmt(d.mass_t,2)} t</span></div>
      </div>`;
  }).join('<hr style="border:none;border-top:1px solid #e5e7eb;margin:6px 0;">');
}

// ─────────────────────────────────────────────────────────────────────
// Mise à jour du panneau "sélectionné"
// ─────────────────────────────────────────────────────────────────────
function updateSelectedCard(unit) {
  const card = document.getElementById("selectedCard");
  if (!card || !unit) return;
  const rows = unitMetrics(unit.id)
    .map(([a, b]) => `<div class="kv"><span class="lbl">${a}</span>
                       <span class="value">${b}</span></div>`)
    .join("");
  const s    = (payload.status || {})[unit.id] || {code:"off", label:""};
  const pill = s.label
    ? `<div class="kv"><span class="lbl">État</span>
        <span class="statusPill ${s.code}">${s.label}</span></div>`
    : "";
  card.innerHTML = `
    <div style="font-weight:900;font-size:12px;margin-bottom:6px;color:#111827;">
      ${unit.name}
    </div>${pill}${rows}`;
}

// ─────────────────────────────────────────────────────────────────────
// Horloge
// ─────────────────────────────────────────────────────────────────────
function updateClock() {
  const el = document.getElementById("clockDisplay");
  if (el) el.textContent = new Date().toLocaleTimeString("fr-FR");
}
updateClock();
setInterval(updateClock, 1000);

// ─────────────────────────────────────────────────────────────────────
// Scène Three.js
// ─────────────────────────────────────────────────────────────────────
function init3D() {
  const host = document.getElementById("canvasHost");
  if (!window.THREE || !window.THREE.OrbitControls) {
    host.innerHTML = '<div style="color:#111;padding:20px;font-size:14px;">'
      + 'Chargement Three.js en cours…</div>';
    return;
  }
  const THREE = window.THREE;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xcfd8e3);
  scene.fog = new THREE.Fog(0xcfd8e3, 70, 170);

  const w = Math.max(host.clientWidth, 600);
  const h = Math.max(host.clientHeight, 520);
  const camera = new THREE.PerspectiveCamera(48, w / h, 0.1, 600);
  camera.position.set(6, 20, 48);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  host.appendChild(renderer.domElement);

  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 1.5, 0);
  controls.enableDamping = true;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x707070, 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, 0.9);
  sun.position.set(-15, 32, 22);
  sun.castShadow = true;
  scene.add(sun);

  // Sol
  const floor = new THREE.Mesh(
    new THREE.BoxGeometry(96, 0.5, 30),
    new THREE.MeshStandardMaterial({ color: 0x7d8188, roughness: 0.88 }));
  floor.position.set(0, -2.25, 0);
  floor.receiveShadow = true;
  scene.add(floor);
  const grid = new THREE.GridHelper(96, 48, 0x4b5563, 0xa1a1aa);
  grid.position.set(0, -1.96, 0);
  scene.add(grid);

  const interactables = [];
  const particles = [];
  const beacons = [];

  function addTo(parent, mesh) {
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }

  function register(obj, id, name) {
    obj.userData.unit = { id, name };
    obj.traverse(c => {
      if (c.isMesh) {
        c.userData.unit = { id, name };
        interactables.push(c);
      }
    });
  }

  function statusColor(id) {
    const s = (payload.status || {})[id] || {};
    return statusColour(s.code);
  }

  function beacon(x, y, z, id, fixedColor) {
    const color = new THREE.Color(fixedColor || statusColor(id));
    const m = new THREE.Mesh(
      new THREE.SphereGeometry(0.22, 16, 16),
      new THREE.MeshStandardMaterial({
        color, emissive: color, emissiveIntensity: 0.6
      }));
    m.position.set(x, y, z);
    scene.add(m);
    beacons.push(m);
  }

  function labelSprite(text, x, y, z, color) {
    const canvas = document.createElement("canvas");
    canvas.width = 460; canvas.height = 115;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "rgba(28,30,38,.93)";
    ctx.fillRect(0, 0, 460, 115);
    ctx.strokeStyle = color || "#f5c542";
    ctx.lineWidth = 5;
    ctx.strokeRect(3, 3, 454, 109);
    ctx.fillStyle = "#fff";
    ctx.font = "bold 29px Segoe UI";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 230, 57);
    const tex = new THREE.CanvasTexture(canvas);
    const spr = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: tex, transparent: true }));
    spr.position.set(x, y, z);
    spr.scale.set(3.4, 0.85, 1);
    scene.add(spr);
  }

  function flowParticle(curve, color, speed, phase, size, parent) {
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(size || 0.13, 14, 14),
      new THREE.MeshStandardMaterial({
        color, emissive: color, emissiveIntensity: 0.4,
        transparent: true, opacity: 0.95
      }));
    (parent || scene).add(mesh);
    const t0 = ((phase || 0) % 1 + 1) % 1;
    mesh.position.copy(curve.getPointAt(t0));
    particles.push({ mesh, curve, t: t0, speed: speed || 0.0013 });
  }

  function tubePath(parent, points, radius, color, opacity) {
    const curve = new THREE.CatmullRomCurve3(
      points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
    const mesh = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 44, radius || 0.08, 12, false),
      new THREE.MeshStandardMaterial({
        color, emissive: color, emissiveIntensity: 0.2,
        transparent: true, opacity: opacity || 0.85
      }));
    addTo(parent, mesh);
    return curve;
  }

  function shellMat(color, opacity) {
    return new THREE.MeshStandardMaterial({
      color, transparent: true, opacity: opacity == null ? 0.5 : opacity,
      roughness: 0.3, metalness: 0.25,
      side: THREE.DoubleSide, depthWrite: false
    });
  }

  // ── Débit air (commun) ─────────────────────────────────────────
  const airFlow_Nm3h = _sf(payload.air_filter.Q_Nm3h,
                           _sf((payload.four || {}).Air_flow, 363934));
  const airSpeedBase = 0.0006 + (airFlow_Nm3h / 400000) * 0.0014;
  const airSizeBase  = 0.06   + (airFlow_Nm3h / 400000) * 0.10;
  const sFlow        = _sf((payload.four || {}).S_flow, 955);

  // ── Filtre d'air ───────────────────────────────────────────────
  function buildAirFilter(x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const sx = 2.6, sy = 2.0, sz = 2.0;
    const dp = _sf(payload.air_filter.delta_P_mmWC, 0);
    const r  = 0.86 + (dp / 150) * 0.14;
    const filterColor = new THREE.Color(
      r, 0.86 - (dp / 150) * 0.3, 0.76 - (dp / 150) * 0.4);
    const shell = new THREE.Mesh(
      new THREE.BoxGeometry(sx, sy, sz),
      new THREE.MeshStandardMaterial({
        color: filterColor, transparent: true, opacity: 0.65, roughness: 0.5
      }));
    shell.position.y = sy / 2;
    addTo(g, shell);
    [-0.6, 0, 0.6].forEach(px => {
      const plate = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, sy * 0.7, sz * 0.7),
        shellMat(0xe2e8f0, 0.3));
      plate.position.set(px, sy * 0.52, 0);
      addTo(g, plate);
    });
    const gasPath = tubePath(
      g, [[-sx * 0.5, sy * 0.5, 0], [0, sy * 0.45, 0], [sx * 0.5, sy * 0.55, 0]],
      0.09, 0x7dd3fc, 0.5);
    [0.1, 0.5, 0.85].forEach(p =>
      flowParticle(gasPath, 0x7dd3fc, airSpeedBase, p, airSizeBase, g));
    register(g, "air_filter", "Filtre air 301FS01");
    scene.add(g);
    labelSprite("Filtre air", x, sy + 1.7, z, statusColor("air_filter"));
    beacon(x - 1.0, sy + 1.2, z, "air_filter");
    return g;
  }

  // ── Tour de séchage ────────────────────────────────────────────
  function buildDryingTower(x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const height = 7.5, radius = 1.1;
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, height, 36, 1, true),
      shellMat(0xa8d8ff, 0.5));
    shell.position.y = height / 2;
    addTo(g, shell);
    const top = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 22, 12), shellMat(0xe2e8f0, 0.28));
    top.scale.y = 0.2; top.position.y = height;
    addTo(g, top);
    const bottom = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 22, 12), shellMat(0xe2e8f0, 0.24));
    bottom.scale.y = 0.16; bottom.position.y = 0;
    addTo(g, bottom);
    const eff = _sf((payload.drying_tower || {}).eff, 99);
    const intensity = Math.min(1, Math.max(0, eff / 99));
    const packColor = new THREE.Color(
      0.84, 0.77 + intensity * 0.15, 0.60 - intensity * 0.20);
    const packing = new THREE.Mesh(
      new THREE.CylinderGeometry(radius * 0.72, radius * 0.72, height * 0.6, 28, 1, true),
      new THREE.MeshStandardMaterial({
        color: packColor, transparent: true, opacity: 0.3 + intensity * 0.3,
        side: THREE.DoubleSide
      }));
    packing.position.y = height * 0.48;
    addTo(g, packing);
    const gasFlow = tubePath(
      g, [[0, 0.3, 0], [0, height * 0.5, 0], [0, height - 0.4, 0]],
      0.1, 0x7dd3fc, 0.45);
    [0.1, 0.5, 0.85].forEach(p =>
      flowParticle(gasFlow, 0x7dd3fc, airSpeedBase, p, airSizeBase, g));
    const acidFlow = tubePath(
      g, [[radius * 0.5, height - 0.3, 0], [radius * 0.3, height * 0.5, 0],
          [radius * 0.5, 0.3, 0]], 0.06, 0x16a34a, 0.5);
    [0.15, 0.55].forEach(p =>
      flowParticle(acidFlow, 0x4ade80, 0.001, p, 0.07, g));
    register(g, "drying_tower", "Tour séchage 401AD02");
    scene.add(g);
    labelSprite("Tour séchage", x, height + 1.3, z, statusColor("drying_tower"));
    beacon(x - radius * 0.9, height + 0.9, z, "drying_tower");
    return g;
  }

  // ── Turbosoufflante ────────────────────────────────────────────
  function buildTurboBlower(x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0.6, z);
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(1.1, 1.1, 0.9, 32, 1, true),
      shellMat(0xcbd5e1, 0.5));
    shell.rotation.x = Math.PI / 2;
    addTo(g, shell);
    const rotor = new THREE.Group();
    for (let i = 0; i < 6; i++) {
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(0.16, 0.8, 0.05),
        new THREE.MeshStandardMaterial({ color: 0x2563eb }));
      blade.rotation.z = (Math.PI * 2 * i) / 6;
      rotor.add(blade);
    }
    addTo(g, new THREE.Mesh(
      new THREE.CylinderGeometry(0.14, 0.14, 0.5, 16),
      new THREE.MeshStandardMaterial({ color: 0x4b5563, metalness: 0.6, roughness: 0.3 })));
    g.add(rotor);
    // Vitesse proportionnelle au débit réel
    const N_rpm = _sf((payload.turbo_blower || {}).N_rpm, 3000);
    g.userData.rotor = rotor;
    g.userData.rotorSpeed = 0.02 + (N_rpm / 10000) * 0.35;

    const airPath = tubePath(
      g, [[-1.6, 0, 0], [0, 0.05, 0], [1.6, 0.2, 0]], 0.08, 0x7dd3fc, 0.45);
    [0.1, 0.4, 0.7].forEach(p =>
      flowParticle(airPath, 0x7dd3fc, airSpeedBase, p, airSizeBase, g));
    register(g, "turbo_blower", "Turbosoufflante 401AC01/02");
    scene.add(g);
    labelSprite("Turbosoufflante", x, 2.6, z, statusColor("turbo_blower"));
    beacon(x - 1.0, 2.1, z, "turbo_blower");
    return g;
  }

  // ── Four ──────────────────────────────────────────────────────
  function buildFurnace(x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const len = 6.0, radius = 1.5;
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, len, 36, 1, true),
      shellMat(0xfdba74, 0.5));
    shell.rotation.z = Math.PI / 2;
    addTo(g, shell);
    [-len / 2, len / 2].forEach(px => {
      const cap = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 24, 14), shellMat(0xe2e8f0, 0.3));
      cap.scale.x = 0.2; cap.position.x = px;
      addTo(g, cap);
    });
    const hotCore = new THREE.Mesh(
      new THREE.CylinderGeometry(radius * 0.35, radius * 0.28, len * 0.82, 26),
      new THREE.MeshStandardMaterial({
        color: 0xff9f43, emissive: 0xff9f43, emissiveIntensity: 0.5,
        transparent: true, opacity: 0.3
      }));
    hotCore.rotation.z = Math.PI / 2;
    addTo(g, hotCore);
    const speed_f = 0.0006 + (sFlow / 1200) * 0.0016;
    const size_f  = 0.10   + (sFlow / 1200) * 0.08;
    const flame   = tubePath(
      g, [[-len * 0.4, 0, 0.2], [-len * 0.1, 0.2, -0.1],
          [len * 0.15, -0.1, 0.15], [len * 0.4, 0.1, 0]], 0.16, 0xff9f43, 0.55);
    [0.1, 0.4, 0.7].forEach(p =>
      flowParticle(flame, 0xff9f43, speed_f, p, size_f, g));
    register(g, "furnace", "Four 401AF01");
    scene.add(g);
    labelSprite("Four 401AF01", x, radius + 1.7, z, statusColor("furnace"));
    beacon(x - 2.0, radius + 1.2, z, "furnace");
    return g;
  }

  // ── Chaudière ─────────────────────────────────────────────────
  function buildBoiler(x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const len = 6.5, radius = 1.4;
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, len, 36, 1, true),
      shellMat(0xdbe4ec, 0.5));
    shell.rotation.z = Math.PI / 2;
    addTo(g, shell);
    [-len / 2, len / 2].forEach(px => {
      const cap = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 24, 14), shellMat(0xe5e7eb, 0.28));
      cap.scale.x = 0.2; cap.position.x = px;
      addTo(g, cap);
    });
    [-0.4, -0.1, 0.2, 0.5].forEach(dz => {
      const tube = new THREE.Mesh(
        new THREE.CylinderGeometry(0.04, 0.04, len * 0.7, 10),
        new THREE.MeshStandardMaterial({ color: 0xd7dee8, metalness: 0.6, roughness: 0.3 }));
      tube.rotation.z = Math.PI / 2;
      tube.position.set(0, -radius * 0.1, dz);
      addTo(g, tube);
    });
    const speed_b = 0.0006 + (sFlow / 1200) * 0.0012;
    const size_b  = 0.08   + (sFlow / 1200) * 0.08;
    const gasFlow = tubePath(
      g, [[-len * 0.4, 0.2, 0], [0, 0.15, 0], [len * 0.4, 0.1, 0]],
      0.12, 0xffa94d, 0.5);
    [0.1, 0.5, 0.85].forEach(p =>
      flowParticle(gasFlow, 0xffa94d, speed_b, p, size_b, g));
    const waterFlow = tubePath(
      g, [[len * 0.35, -0.25, 0.2], [0, -0.25, 0.2], [-len * 0.35, -0.25, 0.2]],
      0.07, 0x2563eb, 0.5);
    [0.2, 0.6].forEach(p =>
      flowParticle(waterFlow, 0x60a5fa, 0.0011, p, 0.08, g));
    register(g, "boiler", "Chaudière 401AV01");
    scene.add(g);
    labelSprite("Chaudière", x, radius + 1.7, z, statusColor("boiler"));
    beacon(x - 1.8, radius + 1.2, z, "boiler");
    return g;
  }

  // ── Convertisseur ──────────────────────────────────────────────
  function buildConverter(x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const height = 9.0, radius = 1.7;
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, height, 44, 1, true),
      shellMat(0xb39b74, 0.42));
    shell.position.y = height / 2;
    addTo(g, shell);
    [new THREE.SphereGeometry(radius, 26, 14), new THREE.SphereGeometry(radius, 26, 14)]
      .forEach((geo, ii) => {
        const cap = new THREE.Mesh(geo, shellMat(0xd2b37f, ii === 0 ? 0.26 : 0.22));
        cap.scale.y = ii === 0 ? 0.22 : 0.18;
        cap.position.y = ii === 0 ? height : 0;
        addTo(g, cap);
      });
    const tauLits = (payload.converter || {}).tau_lits || [0, 0, 0, 0];
    [0.8, 3.1, 5.4, 7.6].forEach((y, idx) => {
      const t_v = Math.min(Math.max((tauLits[idx] || 0) / 100, 0), 1);
      const bedColor = new THREE.Color().setHSL(0.33 - 0.33 * (1 - t_v), 0.55, 0.5);
      const bed = new THREE.Mesh(
        new THREE.CylinderGeometry(radius * 0.82, radius * 0.82, 0.5, 36),
        new THREE.MeshStandardMaterial({ color: bedColor, transparent: true, opacity: 0.5 }));
      bed.position.y = y;
      addTo(g, bed);
    });
    const speed_c = 0.0006 + (sFlow / 1200) * 0.0012;
    const size_c  = 0.09   + (sFlow / 1200) * 0.08;
    const flowCurve = tubePath(g, [
      [-1.8, 0.6, 0], [1.6, 1.0, 0], [1.5, 3.3, 0], [-1.4, 3.6, 0],
      [-1.3, 5.7, 0], [1.5, 6.0, 0], [1.4, 8.0, 0], [0, 8.7, 0]
    ], 0.16, 0xf5c542, 0.5);
    [0.05, 0.25, 0.45, 0.65, 0.85].forEach(p =>
      flowParticle(flowCurve, 0xf5c542, speed_c, p, size_c, g));
    register(g, "converter", "Convertisseur 401AD01");
    scene.add(g);
    labelSprite("Convertisseur", x, height + 1.4, z, statusColor("converter"));
    beacon(x - 1.6, height + 1.0, z, "converter");
    return g;
  }

  // ── Tours d'absorption ─────────────────────────────────────────
  function buildAbsorption(name, id, x, z, height, radius, color) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, height, 36, 1, true),
      shellMat(color, 0.5));
    shell.position.y = height / 2;
    addTo(g, shell);
    [true, false].forEach(isTop => {
      const cap = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 22, 12),
        shellMat(0xdcfce7, isTop ? 0.3 : 0.26));
      cap.scale.y = isTop ? 0.2 : 0.16;
      cap.position.y = isTop ? height : 0;
      addTo(g, cap);
    });
    const speed_a = 0.0006 + (sFlow / 1200) * 0.0010;
    const size_a  = 0.07   + (sFlow / 1200) * 0.08;
    const gasFlow = tubePath(
      g, [[0, 0.3, 0], [0, height * 0.5, 0], [0, height - 0.4, 0]],
      0.1, 0xfacc15, 0.45);
    [0.1, 0.5, 0.85].forEach(p =>
      flowParticle(gasFlow, 0xfacc15, speed_a, p, size_a, g));
    const acidFlow = tubePath(
      g, [[radius * 0.5, height - 0.3, 0], [radius * 0.3, height * 0.5, 0],
          [radius * 0.5, 0.3, 0]], 0.07, 0x16a34a, 0.5);
    [0.15, 0.55].forEach(p =>
      flowParticle(acidFlow, 0x4ade80, 0.001, p, 0.08, g));
    register(g, id, name);
    scene.add(g);
    labelSprite(name, x, height + 1.2, z, statusColor(id));
    beacon(x - radius * 0.9, height + 0.9, z, id);
    return g;
  }

  // ── Bacs de stockage ───────────────────────────────────────────
  function buildTank(name, id, x, z, height, radius, liquidColor, levelPct, alarm) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, height, 32, 1, true),
      shellMat(0xcbd5e1, 0.42));
    shell.position.y = height / 2;
    addTo(g, shell);
    const lid = new THREE.Mesh(
      new THREE.CylinderGeometry(radius * 1.02, radius * 1.02, 0.1, 32),
      shellMat(0xb8bdc5, 0.7));
    lid.position.y = height;
    addTo(g, lid);
    const level = Math.max(0.04, Math.min((levelPct || 0) / 100, 1.0));
    const fillH = Math.max(0.2, height * 0.92 * level);
    const fillColor = alarm ? 0xef4444 : liquidColor;
    const fill = new THREE.Mesh(
      new THREE.CylinderGeometry(radius * 0.86, radius * 0.86, fillH, 28),
      new THREE.MeshStandardMaterial({
        color: fillColor, emissive: fillColor,
        emissiveIntensity: alarm ? 0.4 : 0.18, transparent: true, opacity: 0.72
      }));
    fill.position.y = fillH / 2 + 0.1;
    addTo(g, fill);
    g.userData.fillMesh    = fill;
    g.userData.targetLevel = level;
    g.userData.currentLevel= level;
    g.userData.tankHeight  = height;
    g.userData.liquidColor = liquidColor;
    g.userData.isAlarm     = alarm;
    register(g, id, name);
    scene.add(g);
    labelSprite(name, x, height + 1.1, z, alarm ? "#ef4444" : "#9ca3af");
    beacon(x - radius * 0.9, height + 0.7, z, id, alarm ? "#ef4444" : "#9ca3af");
    return g;
  }

  // ── Construction de la chaîne ─────────────────────────────────
  buildAirFilter(-30, 0);
  buildDryingTower(-24, 0);
  buildTurboBlower(-18.5, 0);
  buildFurnace(-12, 0);
  buildBoiler(-4, 0);
  buildConverter(5, 0);
  buildAbsorption("Absorption JD02", "absorption_jd02", 12.5, 0, 7.0, 1.2, 0x86efac);
  buildAbsorption("Absorption JD03", "absorption_jd03", 18.5, 0, 7.4, 1.25, 0x4ade80);

  // ── Bacs ──────────────────────────────────────────────────────
  const T = payload.tanks || {};
  buildTank(
    "Bac soufre S1", "tank_sulfur_1", -28, -9, 4.6, 1.7, 0xf59e0b,
    _sf((T.sulfur_1 || {}).level_pct, 0), !!(T.sulfur_1 || {}).alarm);
  buildTank(
    "Bac soufre S2", "tank_sulfur_2", -22, -9, 4.6, 1.7, 0xf59e0b,
    _sf((T.sulfur_2 || {}).level_pct, 0), !!(T.sulfur_2 || {}).alarm);
  buildTank(
    "Bac acide",     "tank_acid",     -15, -9, 5.4, 1.9, 0x22c55e,
    _sf((T.acid     || {}).level_pct, 0), !!(T.acid     || {}).alarm);

  // ── Tuyauteries inter-équipements ─────────────────────────────
  const avgSp = 0.0012;
  function interPipe(pts, color) { return tubePath(scene, pts, 0.08, color, 0.7); }

  const pipes = [
    interPipe([[-28.7,1.3,0],[-26.3,1.1,0],[-24,1.3,0]],  0x7dd3fc),
    interPipe([[-22.9,1.0,0],[-20.7,0.7,0],[-18.5,0.6,0]], 0x7dd3fc),
    interPipe([[-17.4,0.6,0],[-15,0.9,0],[-12,1.2,0]],     0x7dd3fc),
    interPipe([[-9,1.8,0],[-6.5,1.6,0],[-4,1.4,0]],        0xffa94d),
    interPipe([[-0.7,1.0,0],[2.0,1.2,0],[3.6,1.0,0]],      0xf5c542),
    interPipe([[6.7,7.2,0],[9.5,5.0,0],[11.5,2.0,0]],      0xfacc15),
    interPipe([[13.7,1.8,0],[16.0,1.5,0],[17.3,1.4,0]],    0xfacc15),
  ];
  const pipeColors = [0x7dd3fc,0x7dd3fc,0x7dd3fc,0xffa94d,0xf5c542,0xfacc15,0xfacc15];
  pipes.forEach((c, i) =>
    [0.1, 0.45, 0.8].forEach(p =>
      flowParticle(c, pipeColors[i], avgSp, p, 0.09)));

  // ── Vues caméra ────────────────────────────────────────────────
  const views = {
    global:      { pos:new THREE.Vector3(0,18,46),   target:new THREE.Vector3(-3,2,0)},
    air_filter:  { pos:new THREE.Vector3(-30,5,8),   target:new THREE.Vector3(-30,1.2,0)},
    drying_tower:{ pos:new THREE.Vector3(-24,7,9),   target:new THREE.Vector3(-24,3.5,0)},
    turbo_blower:{ pos:new THREE.Vector3(-18.5,4,7), target:new THREE.Vector3(-18.5,0.8,0)},
    furnace:     { pos:new THREE.Vector3(-12,5,9),   target:new THREE.Vector3(-12,1.4,0)},
    boiler:      { pos:new THREE.Vector3(-4,5,9),    target:new THREE.Vector3(-4,1.4,0)},
    converter:   { pos:new THREE.Vector3(9,9,14),    target:new THREE.Vector3(5,4.5,0)},
    absorption:  { pos:new THREE.Vector3(18,8,14),   target:new THREE.Vector3(15.5,3.5,0)},
    tanks:       { pos:new THREE.Vector3(-22,9,-19), target:new THREE.Vector3(-22,2,-9)},
  };

  let transition = null;
  function setView(name) {
    const v = views[name] || views.global;
    transition = {
      start: performance.now(), dur: 650,
      fromPos: camera.position.clone(), toPos: v.pos.clone(),
      fromTarget: controls.target.clone(), toTarget: v.target.clone(),
    };
    document.querySelectorAll(".viewBtn").forEach(b =>
      b.classList.toggle("is-active", b.getAttribute("data-view") === name));
  }
  document.querySelectorAll(".viewBtn").forEach(b =>
    b.addEventListener("click", () => setView(b.getAttribute("data-view"))));
  setView("global");

  // ── Interaction souris ─────────────────────────────────────────
  const raycaster = new THREE.Raycaster();
  const pointer   = new THREE.Vector2();
  const tooltip   = document.getElementById("tooltip3d");

  function pick(event) {
    const r = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - r.left) / r.width)  * 2 - 1;
    pointer.y = -((event.clientY - r.top) / r.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(interactables, true);
    return hits.length ? hits[0].object : null;
  }

  renderer.domElement.addEventListener("mousemove", e => {
    const obj = pick(e);
    if (obj && obj.userData.unit) {
      renderer.domElement.style.cursor = "pointer";
      tooltip.style.display = "block";
      tooltip.style.left = Math.min(e.offsetX + 14,
        renderer.domElement.clientWidth - 250) + "px";
      tooltip.style.top  = Math.max(e.offsetY + 14, 12) + "px";
      const rows = unitMetrics(obj.userData.unit.id)
        .slice(0, 4)
        .map(([a, b]) => `${a} : <b>${b}</b>`)
        .join("<br>");
      tooltip.innerHTML = `<strong>${obj.userData.unit.name}</strong>${rows}`;
    } else {
      renderer.domElement.style.cursor = "default";
      tooltip.style.display = "none";
    }
  });

  renderer.domElement.addEventListener("click", e => {
    const obj = pick(e);
    if (obj && obj.userData.unit) {
      updateSelectedCard(obj.userData.unit);
      const vid = obj.userData.unit.id.startsWith("tank_")
        ? "tanks" : obj.userData.unit.id;
      if (views[vid]) setView(vid);
    }
  });

  // ── Boucle d'animation ─────────────────────────────────────────
  const t0 = performance.now();
  function animate() {
    const now = performance.now();

    // Transition caméra (easing cubique)
    if (transition) {
      const raw   = Math.min((now - transition.start) / transition.dur, 1);
      const eased = raw < 0.5
        ? 4 * raw * raw * raw
        : 1 - Math.pow(-2 * raw + 2, 3) / 2;
      camera.position.lerpVectors(transition.fromPos, transition.toPos, eased);
      controls.target.lerpVectors(transition.fromTarget, transition.toTarget, eased);
      if (raw >= 1) transition = null;
    }

    // Particules de flux
    particles.forEach(p => {
      p.t = (p.t + p.speed + 1) % 1;
      p.mesh.position.copy(p.curve.getPointAt(p.t));
    });

    // Rotation rotors turbosoufflante
    scene.traverse(obj => {
      if (obj.userData && obj.userData.rotor)
        obj.userData.rotor.rotation.z += obj.userData.rotorSpeed || 0.12;
    });

    // Lissage niveaux des bacs
    scene.traverse(obj => {
      if (obj.userData && obj.userData.fillMesh) {
        let cur    = obj.userData.currentLevel || 0;
        const tgt  = obj.userData.targetLevel  || 0;
        cur        = cur + (tgt - cur) * 0.04;
        obj.userData.currentLevel = cur;
        const h    = obj.userData.tankHeight || 5;
        const fillH = Math.max(0.2, h * 0.92 * cur);
        const fill  = obj.userData.fillMesh;
        // Reconstruire la géométrie proprement (évite artefacts de scale)
        fill.position.y = fillH / 2 + 0.1;
        fill.scale.y    = fillH / Math.max(0.2, h * 0.92);
      }
    });

    // Pulsation des balises
    const elapsed = (now - t0) / 1000;
    beacons.forEach((b, i) =>
      b.scale.setScalar(1 + 0.16 * Math.sin(elapsed * 2.5 + i * 0.65)));

    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }
  animate();

  // Resize
  function resize() {
    const nw = Math.max(host.clientWidth, 600);
    const nh = Math.max(host.clientHeight, 520);
    camera.aspect = nw / nh;
    camera.updateProjectionMatrix();
    renderer.setSize(nw, nh);
  }
  window.addEventListener("resize", resize);
  if (window.ResizeObserver) new ResizeObserver(resize).observe(host);
}

// ─────────────────────────────────────────────────────────────────────
// Initialisation des panneaux
// ─────────────────────────────────────────────────────────────────────
fillStatusPanel();
fillAirTreatPanel();
fillTankPanel();

const score = payload.global_score || 0;
document.getElementById("globalScore").textContent = score.toFixed(1) + " / 100";
document.getElementById("scoreFill").style.width =
  Math.min(100, Math.max(0, score)) + "%";

try { init3D(); } catch (e) { console.error("Erreur init3D :", e); }
</script>
</body>
</html>
"""