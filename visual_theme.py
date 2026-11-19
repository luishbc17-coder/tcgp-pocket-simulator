"""Presentation-only helpers for TCG Pocket Lab v0.9.5.

Keep this module free from Streamlit and battle engine imports so user-facing
markup is independently testable. Never trust deck/card display strings as HTML.
"""
from __future__ import annotations
from html import escape

VERSION = '0.9.12'
ENERGY_META = {
    'water': ('💧', 'Água'),
    'fire': ('🔥', 'Fogo'),
    'grass': ('🌿', 'Planta'),
    'lightning': ('⚡', 'Elétrico'),
    'psychic': ('🔮', 'Psíquico'),
    'fighting': ('🥊', 'Lutador'),
    'darkness': ('🌙', 'Sombrio'),
    'metal': ('⚙️', 'Metal'),
}

CSS = r"""
<style>
/* V0.9.3 -- design changes are scoped: the native Streamlit controls remain accessible. */
:root { --lab-accent: #8d7cf5; --lab-cyan: #72d6d4; --lab-muted: #98a2bc; }
.block-container { max-width: 1180px; padding-top: 2.1rem; padding-bottom: 4rem; }
[data-testid="stAppViewContainer"] {
  background-image: radial-gradient(circle at 12% -12%, rgba(120,99,236,.08), transparent 33%),
                    radial-gradient(circle at 92% 6%, rgba(88,197,197,.06), transparent 26%);
}
/* The hero uses its own dark palette and remains legible in both Streamlit themes. */
.lab-hero {
  position:relative; overflow:hidden; isolation:isolate; display:grid;
  grid-template-columns:minmax(0, 1fr) 190px; gap:20px; align-items:center;
  background:radial-gradient(circle at 72% 10%, rgba(100,218,222,.22), transparent 43%),
             linear-gradient(130deg, #13172c 0%, #212b56 52%, #29204f 100%);
  border:1px solid rgba(167,165,241,.30); border-radius:24px;
  padding:clamp(20px, 3vw, 34px); color:#f9fbff; margin-bottom:15px;
  box-shadow:0 16px 38px rgba(31,31,70,.14);
}
.lab-hero:before { content:""; position:absolute; z-index:-1; width:260px; height:260px;
  border:1px solid rgba(221,230,255,.11);border-radius:100%;right:-70px;top:-140px; }
.lab-eyebrow { display:flex; align-items:center; gap:9px; color:#c0c9ef;
  font-size:11px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; }
.lab-live-dot {width:7px;height:7px;display:inline-block;border-radius:50%;background:#72d6d4;
  box-shadow:0 0 0 4px rgba(114,214,212,.13);}
.lab-hero h1 {margin:.9rem 0 .75rem;font-size:clamp(1.7rem, 3.9vw, 2.9rem)!important;
  font-weight:800;line-height:1.11;letter-spacing:-.04em;color:#fff;}
.lab-hero h1 span {color:#a99bff;}
.lab-hero p {max-width:620px;font-size:.91rem;line-height:1.58;margin:0;color:#d5ddf0;}
.lab-hero-tags {display:flex;gap:8px;flex-wrap:wrap;margin-top:18px;}
.lab-hero-tags span {font-size:.72rem; font-weight:650; color:#e6eaf9;
  border:1px solid rgba(209,218,255,.21); background:rgba(255,255,255,.065);
  padding:7px 10px; border-radius:100px;}
.lab-card-art {height:154px;position:relative;filter:drop-shadow(0 10px 17px rgba(0,0,0,.18));}
.lab-art-card {position:absolute; width:104px;height:141px;left:45px;top:9px;
  border-radius:12px; border:2px solid rgba(221,213,255,.9);
  background:linear-gradient(135deg,#8170ef 0%,#433e92 43%,#22274e 100%);
  box-shadow:inset 0 0 0 5px rgba(255,255,255,.09),0 9px 19px rgba(0,0,0,.17);transform:rotate(9deg);}
.lab-art-card.secondary {transform:rotate(-13deg);left:17px;top:0;
  background:linear-gradient(135deg,#60c7c8,#293f7f 65%,#1e3157);}
.lab-art-card.front {display:flex;align-items:center;justify-content:center;color:#f9faff;
  font-size:54px;font-weight:800;}
.lab-art-card.front:after {content:"";position:absolute;inset:14px;border:1px solid rgba(255,255,255,.27);border-radius:8px;}
.lab-stat-strip {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 16px;}
.lab-stat {padding:14px 16px;border-radius:15px;
  background:color-mix(in srgb, var(--secondary-background-color) 80%, var(--background-color));
  border:1px solid rgba(133,143,179,.19);min-width:0;}
.lab-stat b {font-size:1.2rem;line-height:1.3;font-weight:800;letter-spacing:-.025em;
  color:var(--text-color);display:block;}
.lab-stat span {color:color-mix(in srgb,var(--text-color) 66%,var(--background-color));
  font-size:.74rem;line-height:1.4;display:block;margin-top:3px;}
.lab-section {margin:3px 0 15px;}
.lab-section .lab-section-kicker {font-size:10px;letter-spacing:.15em;font-weight:800;
  color:#8d7cf5;text-transform:uppercase;}
.lab-section h2 {font-size:clamp(1.18rem,2vw,1.5rem);letter-spacing:-.025em;
  margin:4px 0 4px;font-weight:800;line-height:1.2;color:var(--text-color);}
.lab-section p {font-size:.83rem;line-height:1.5;opacity:.73;margin:0;}
.lab-card-name {font-size:.9rem;font-weight:800;color:var(--text-color);
  margin-top:7px;line-height:1.3;min-height:2.25em;overflow-wrap:anywhere;}
.lab-card-meta {display:flex;align-items:center;justify-content:space-between;gap:4px;
  margin:5px 0 8px;min-height:24px;}
.lab-card-meta span {font-size:.66rem;line-height:1.3;color:color-mix(in srgb,var(--text-color) 70%,var(--background-color));}
.lab-card-count {padding:3px 6px;border-radius:7px;background:rgba(141,124,245,.15);
  border:1px solid rgba(141,124,245,.29);font-weight:800!important;white-space:nowrap;}
.lab-card-count.empty {background:transparent;border-color:rgba(130,140,170,.14);font-weight:500!important;}
.lab-deck-summary {margin:4px 0 17px;padding:17px 18px;border:1px solid rgba(141,124,245,.25);
  background:linear-gradient(125deg,rgba(141,124,245,.08),rgba(114,214,212,.035));border-radius:18px;}
.lab-deck-summary-header {display:flex;justify-content:space-between;align-items:baseline;gap:10px;}
.lab-deck-summary-header strong {font-size:1.12rem;letter-spacing:-.018em;color:var(--text-color);}
.lab-deck-summary-header span {font-size:.86rem;font-weight:800;color:var(--text-color);}
.lab-deck-track {background:rgba(134,135,178,.19);border-radius:15px;height:9px;overflow:hidden;margin:12px 0 13px;}
.lab-deck-fill {height:100%;border-radius:15px;background:linear-gradient(90deg,#8273ed,#68cbd4);}
.lab-deck-chips {display:flex;flex-wrap:wrap;gap:7px;align-items:center;}
.lab-chip {font-size:.72rem;font-weight:680;padding:6px 10px;border:1px solid rgba(138,148,182,.24);
  border-radius:100px;color:var(--text-color);background:rgba(127,137,169,.055);}
.lab-chip.energy {background:rgba(141,124,245,.09);border-color:rgba(141,124,245,.27);}
.lab-chip.ready {border-color:rgba(74,176,151,.40);color:#3ba78d;}
.lab-duel {display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:stretch;
  gap:12px;margin:6px 0 13px;}
.lab-duel-side {min-width:0;padding:14px 15px;border:1px solid rgba(143,149,185,.20);
 background:color-mix(in srgb,var(--secondary-background-color) 77%,var(--background-color));border-radius:16px;}
.lab-duel-side small {font-size:.65rem;letter-spacing:.13em;font-weight:800;color:#9284e6;display:block;margin-bottom:8px;}
.lab-duel-side strong {color:var(--text-color);font-size:.94rem;line-height:1.25;display:block;overflow-wrap:anywhere;}
.lab-duel-side span {font-size:.7rem;color:color-mix(in srgb,var(--text-color) 68%,var(--background-color));display:block;margin-top:7px;}
.lab-duel-vs {align-self:center;color:#8a7ef5;font-weight:900;font-size:.9rem;letter-spacing:.08em;}
.lab-results {border:1px solid rgba(144,155,190,.22);border-radius:18px;padding:16px 18px;margin:9px 0 12px;
 background:color-mix(in srgb,var(--secondary-background-color) 67%,var(--background-color));}
.lab-results-top {display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:13px;}
.lab-results-top strong {font-size:1rem;line-height:1.35;}
.lab-results-top span {font-size:.7rem;opacity:.7;}
.lab-result-row {display:grid;grid-template-columns:minmax(0,1fr) 75px;gap:9px;margin:10px 0;align-items:center;}
.lab-result-row .lab-result-label {font-size:.8rem;font-weight:680;overflow-wrap:anywhere;}
.lab-result-row .lab-result-num {text-align:right;font-size:.85rem;font-weight:800;font-variant-numeric:tabular-nums;}
.lab-result-bar {height:10px;border-radius:10px;background:rgba(139,145,173,.18);overflow:hidden;grid-column:1/3;}
.lab-result-bar span {height:100%;display:block;background:linear-gradient(90deg,#8173ed,#ada2ff);border-radius:10px;}
.lab-result-bar.alt span {background:linear-gradient(90deg,#339eae,#74d7d4);}
.lab-results-note {margin-top:11px;font-size:.7rem;line-height:1.45;opacity:.69;}
/* Stable mobile navigation: a single row which can scroll on narrow phones. */
[class*='st-key-lab_navigation_v0933'] [role='radiogroup'] {
  display:flex; flex-wrap:nowrap!important; overflow-x:auto; scrollbar-width:thin;
  padding:2px 0 7px; gap:5px; overscroll-behavior-x:contain;
}
[class*='st-key-lab_navigation_v0933'] [role='radiogroup'] label {
  flex:0 0 auto; min-height:40px; padding:3px 6px; white-space:nowrap;
}
/* Native tabs stay scrollable on smaller phones and have larger touch targets. */
[data-testid="stTabs"] [data-baseweb="tab-list"] {overflow-x:auto;overflow-y:hidden;
  scrollbar-width:thin;gap:6px;padding:2px 1px 6px;}
[data-testid="stTabs"] button[data-baseweb="tab"] {white-space:nowrap;border-radius:10px 10px 0 0;
  padding:10px 13px;font-weight:650;}
[data-testid="stTabs"] [aria-selected="true"] {color:#8976ee!important;}
[data-testid="stMetric"] {border:1px solid rgba(138,148,179,.16);padding:11px 14px;border-radius:14px;
 background:color-mix(in srgb,var(--secondary-background-color) 78%,var(--background-color));}
[data-testid="stButton"] button {border-radius:11px;min-height:38px;}
[data-testid="stGrid"] [data-testid="stImage"] img {border-radius:9px;}
[data-testid="stGrid"] [data-testid="stButton"] button {min-height:38px;padding:5px 7px;}
[data-testid="stFileUploader"] {border-radius:13px;}
@media(max-width:700px){
 /* The Cloud header and mobile browser toolbar can otherwise mask the top row.
    Keep a safe top gutter even when Streamlit changes its container class. */
 [data-testid="stMainBlockContainer"], .block-container {
   padding-top:max(2.6rem,calc(env(safe-area-inset-top,0px) + 1.3rem))!important;
   padding-left:.78rem!important;padding-right:.78rem!important;
 }
 [data-testid="stMain"] {scroll-padding-top:2.7rem;}
 html {scroll-padding-top:2.7rem;}
 .lab-hero {grid-template-columns:1fr;padding:16px 18px;border-radius:17px;gap:0;margin-top:3px;}
 .lab-eyebrow {font-size:9px;letter-spacing:.09em;}
 .lab-hero-tags span:last-child {display:none;}
 .lab-hero h1 {font-size:1.48rem!important;margin:8px 0 8px;}
 .lab-hero p {font-size:.76rem;line-height:1.42;}
 .lab-card-art {display:none;}
 .lab-hero-tags {margin-top:10px;gap:5px;}
 .lab-hero-tags span {font-size:.62rem;padding:5px 7px;}
 .lab-stat-strip {gap:6px;margin-bottom:12px;}
 .lab-stat {padding:9px 8px;border-radius:12px;}
 .lab-stat b {font-size:.95rem;}
 .lab-stat span {font-size:.60rem;}
 .lab-deck-summary {padding:14px;border-radius:15px;}
 .lab-duel {gap:5px;}
 .lab-duel-side {padding:11px 9px;border-radius:12px;}
 .lab-duel-side strong {font-size:.78rem;}
 .lab-duel-side span {font-size:.63rem;}
 .lab-duel-vs {font-size:.7rem;}
 .lab-card-name {font-size:.78rem;}
 .lab-card-meta span {font-size:.61rem;}
 [data-testid="stGrid"] [data-testid="stButton"] button {min-height:40px;}
}
/* The on-demand status badge is informational; actual action buttons remain native. */
.lab-coverage-pill {display:inline-block;border-radius:100px;padding:5px 9px;margin:3px 0 8px;
  font-size:.69rem;font-weight:750;border:1px solid rgba(141,124,245,.26);
  background:rgba(141,124,245,.08);color:var(--text-color);}
.lab-coverage-pill.supported {border-color:rgba(72,176,139,.38);background:rgba(72,176,139,.10);}
.lab-coverage-pill.blocked {border-color:rgba(222,153,65,.36);background:rgba(222,153,65,.10);}
.lab-coverage-pill.missing {border-color:rgba(187,87,87,.38);background:rgba(187,87,87,.09);}
.lab-library-summary {border:1px solid rgba(141,124,245,.23);border-radius:15px;
 padding:10px 13px;margin:7px 0 12px;background:rgba(141,124,245,.055);}
.lab-library-summary strong {font-size:.82rem;color:var(--text-color);display:block;}
.lab-library-summary span {font-size:.71rem;color:var(--text-color);opacity:.78;display:block;margin-top:5px;}
@media(prefers-reduced-motion:reduce){*,*:before,*:after {animation-duration:.01ms!important;transition-duration:.01ms!important;}}

/* Meta comparison cards avoid clipped horizontal tables on Android. */
.lab-gauntlet-summary {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0;}
.lab-gauntlet-stat {min-width:0;border:1px solid rgba(141,124,245,.23);border-radius:13px;
 padding:12px 11px;background:rgba(141,124,245,.055);}
.lab-gauntlet-stat b {display:block;font-size:1.35rem;line-height:1.2;color:var(--text-color);}
.lab-gauntlet-stat span {display:block;margin-top:4px;color:var(--text-color);opacity:.72;font-size:.72rem;line-height:1.25;}
.lab-gauntlet-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:12px 0 16px;}
.lab-gauntlet-item {min-width:0;padding:14px;border:1px solid rgba(141,124,245,.22);border-radius:14px;
 background:color-mix(in srgb, var(--secondary-background-color) 85%, var(--background-color));}
.lab-gauntlet-name {font-size:.85rem;font-weight:750;color:var(--text-color);overflow-wrap:anywhere;line-height:1.3;}
.lab-gauntlet-bottom {display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px;align-items:center;margin-top:10px;}
.lab-gauntlet-badge {font-size:.67rem;font-weight:700;border-radius:30px;padding:4px 8px;
 border:1px solid rgba(138,148,179,.26);color:var(--text-color);}
.lab-gauntlet-badge.ready {background:rgba(72,176,139,.11);border-color:rgba(72,176,139,.33);}
.lab-gauntlet-badge.blocked {background:rgba(213,146,77,.10);border-color:rgba(213,146,77,.31);}
.lab-gauntlet-progress {font-size:.72rem;opacity:.72;color:var(--text-color);}
@media(max-width:700px){.lab-gauntlet-grid{grid-template-columns:1fr;}.lab-gauntlet-summary{gap:5px;}
 .lab-gauntlet-stat{padding:10px 7px;}.lab-gauntlet-stat b{font-size:1.12rem;}
 .lab-gauntlet-stat span{font-size:.63rem;}.lab-gauntlet-item{padding:12px;}}


/* Meta Matrix: compact ranking, match cards and horizontally contained matrix. */
.lab-matrix-lead {display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0 14px;}
.lab-matrix-hint {border:1px solid rgba(141,124,245,.26);background:rgba(141,124,245,.075);
  border-radius:999px;padding:6px 10px;font-size:.73rem;font-weight:680;color:var(--text-color);}
.lab-rank-list {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0;}
.lab-rank-card {border:1px solid rgba(141,124,245,.22);border-radius:17px;padding:14px;
  background:color-mix(in srgb,var(--secondary-background-color) 81%,var(--background-color));min-width:0;}
.lab-rank-top {display:flex;gap:12px;align-items:center;min-width:0;}
.lab-rank-pos {flex:0 0 41px;height:41px;border-radius:12px;display:grid;place-items:center;
  color:#c6bcff;background:rgba(141,124,245,.14);border:1px solid rgba(141,124,245,.28);
  font-weight:850;font-size:.97rem;}
.lab-rank-name {font-size:.91rem;line-height:1.3;font-weight:790;color:var(--text-color);overflow-wrap:anywhere;}
.lab-rank-foot {display:flex;justify-content:space-between;gap:8px;align-items:baseline;margin-top:12px;}
.lab-rank-foot strong {font-size:1.36rem;color:var(--text-color);font-variant-numeric:tabular-nums;letter-spacing:-.02em;}
.lab-rank-foot span {font-size:.7rem;color:var(--text-color);opacity:.7;line-height:1.4;text-align:right;}
.lab-rank-meter {height:6px;border-radius:9px;margin-top:10px;background:rgba(134,135,178,.2);overflow:hidden;}
.lab-rank-meter > span {display:block;height:100%;border-radius:9px;background:linear-gradient(90deg,#8373ea,#68b7c7);}
.lab-matrix-pairs {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:10px 0;}
.lab-pair {border:1px solid rgba(141,124,245,.18);border-radius:15px;padding:13px;min-width:0;
  background:color-mix(in srgb,var(--secondary-background-color) 82%,var(--background-color));}
.lab-pair-heading {font-size:.79rem;line-height:1.4;color:var(--text-color);overflow-wrap:anywhere;}
.lab-pair-heading b {font-weight:800;}
.lab-pair-score {display:flex;justify-content:space-between;gap:10px;margin:12px 0 9px;
  font-weight:820;font-size:1.08rem;color:var(--text-color);font-variant-numeric:tabular-nums;}
.lab-pair-bar {height:9px;display:flex;border-radius:9px;overflow:hidden;background:rgba(134,135,178,.2);}
.lab-pair-bar .left {background:#8778ed}.lab-pair-bar .draw {background:#8f97a8}.lab-pair-bar .right {background:#69c7d0}
.lab-pair-detail {font-size:.69rem;color:var(--text-color);opacity:.7;margin-top:9px;line-height:1.4;}
.lab-pair.pending {border-style:dashed;}
.lab-matrix-scroll {width:100%;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:thin;
  border:1px solid rgba(141,124,245,.26);border-radius:15px;margin:12px 0;}
.lab-matrix-table {width:100%;min-width:630px;border-collapse:separate;border-spacing:0;
  color:var(--text-color);font-size:.76rem;}
.lab-matrix-table th,.lab-matrix-table td {padding:12px 9px;text-align:center;
  border-right:1px solid rgba(144,147,186,.13);border-bottom:1px solid rgba(144,147,186,.13);}
.lab-matrix-table th {font-weight:850;background:color-mix(in srgb,var(--secondary-background-color) 86%,var(--background-color));}
.lab-matrix-table .head {position:sticky;left:0;z-index:1;min-width:56px;text-align:left;}
.lab-matrix-table td.score {font-weight:780;font-variant-numeric:tabular-nums;
  background:rgba(100,180,190,calc(var(--heat,0) * .21));}
.lab-matrix-table td.na {color:var(--text-color);opacity:.52;}
.lab-matrix-legend {font-size:.74rem;line-height:1.6;color:var(--text-color);opacity:.8;}
@media(max-width:700px){.lab-rank-list,.lab-matrix-pairs{grid-template-columns:1fr;}
  .lab-rank-card{padding:12px;}.lab-rank-foot strong{font-size:1.27rem;}
  .lab-matrix-scroll{margin-left:0;margin-right:0;}}

.lab-score-main {display:flex;flex-direction:column;align-items:flex-start;gap:3px;min-width:0;}
.lab-ci {display:block;font-size:.69rem;color:var(--lab-muted);line-height:1.4;}
.lab-insight {border:1px solid rgba(141,124,245,.23);border-radius:14px;padding:12px 14px;
  background:rgba(141,124,245,.055);margin:8px 0;}
.lab-insight strong {display:block;font-size:.95rem;}
@media(max-width:700px){.lab-ci{font-size:.68rem;} .lab-matrix-legend{font-size:.7rem;}}
</style>
"""


def safe(value: object) -> str:
    return escape(str(value), quote=True)


def is_pokemon(card: dict) -> bool:
    # The core catalog labels Pokémon as 'Pokémon'. Other categories are trainers.
    return str(card.get('type', '')).casefold() in ('pokémon', 'pokemon')


def deck_breakdown(counts: dict, by_id: dict) -> dict:
    summary = {'pokemon': 0, 'trainers': 0, 'unknown': 0}
    for cid, qty in counts.items():
        if cid not in by_id:
            summary['unknown'] += qty
        elif is_pokemon(by_id[cid]):
            summary['pokemon'] += qty
        else:
            summary['trainers'] += qty
    return summary


def energy_chips(energy_types) -> str:
    chips = []
    for energy in energy_types:
        icon, label = ENERGY_META.get(energy, ('◆', str(energy)))
        chips.append(f'<span class="lab-chip energy">{safe(icon)} {safe(label)}</span>')
    return ''.join(chips) or '<span class="lab-chip">Selecione a energia</span>'


def hero(catalog_count: int, deck_count: int) -> str:
    catalog_label = f'{int(catalog_count):,}'.replace(',', '.')
    return f'''<section class="lab-hero" aria-label="TCG Pocket Lab">
       <div><div class="lab-eyebrow"><i class="lab-live-dot" aria-hidden="true"></i>
       TCG POCKET LAB <span style="opacity:.55">/ BETA {VERSION}</span></div>
       <h1>Seu deck.<br><span>Seu laboratório.</span></h1>
       <p>Monte uma lista com as cartas do Pocket, investigue habilidades e teste
       estratégias com simulações auditadas.</p>
       <div class="lab-hero-tags"><span>✦ IA tática</span>
       <span>◈ Replays por semente</span><span>◇ Dados experimentais</span></div></div>
       <div class="lab-card-art" aria-hidden="true"><div class="lab-art-card secondary"></div>
       <div class="lab-art-card front">✦</div></div></section>
       <div class="lab-stat-strip" aria-label="Visão geral">
         <div class="lab-stat"><b>{catalog_label}</b><span>Cartas no catálogo</span></div>
         <div class="lab-stat"><b>{int(deck_count)} / 20</b><span>Seu deck</span></div>
         <div class="lab-stat"><b>v{VERSION}</b><span>Laboratório beta</span></div>
       </div>'''


def section(title: str, subtitle: str = '', kicker: str = 'LABORATÓRIO') -> str:
    return (f'<header class="lab-section"><div class="lab-section-kicker">{safe(kicker)}</div>'
            f'<h2>{safe(title)}</h2><p>{safe(subtitle)}</p></header>')


def card_caption(card: dict, selected: int) -> str:
    # Native image and controls live outside HTML, retaining accessibility.
    return (f'<div class="lab-card-name">{safe(card.get("name", ""))}</div>'
            f'<div class="lab-card-meta"><span>{safe(card.get("set", ""))} · '
            f'#{safe(card.get("number", ""))}</span>'
            f'<span class="lab-card-count {"empty" if selected == 0 else ""}">'
            f'{selected}/2</span></div>')


def deck_overview(counts: dict, by_id: dict, energy_types) -> str:
    total = sum(counts.values())
    parts = deck_breakdown(counts, by_id)
    percent = min(100, max(0, 100 * total / 20))
    chips = (f'<span class="lab-chip">♟ {parts["pokemon"]} Pokémon</span>'
             f'<span class="lab-chip">▤ {parts["trainers"]} Treinadores</span>')
    if parts['unknown']:
        chips += f'<span class="lab-chip">{parts["unknown"]} não encontradas</span>'
    chips += energy_chips(energy_types)
    # Do not claim legal deck simply because the card count is twenty.
    status = '20 cartas selecionadas' if total == 20 else f'Faltam {max(0, 20-total)} cartas'
    return f'''<section class="lab-deck-summary" aria-label="Composição do deck">
      <div class="lab-deck-summary-header"><strong>{safe(status)}</strong>
      <span>{total} / 20</span></div>
      <div class="lab-deck-track" role="progressbar" aria-label="Cartas no deck"
           aria-valuenow="{min(20,max(0,total))}" aria-valuemin="0" aria-valuemax="20">
           <div class="lab-deck-fill" style="width:{percent:.2f}%"></div></div>
      <div class="lab-deck-chips">{chips}</div></section>'''


def matchup_preview(left: dict, right: dict) -> str:
    def panel(side, label):
        name = side.get('recognized_name') or side.get('name') or label
        energy = ', '.join(ENERGY_META.get(x, ('', x))[1] for x in side.get('energy_types', []))
        signature = str(side.get('signature', ''))[:10]
        return (f'<div class="lab-duel-side"><small>{safe(label)}</small><strong>{safe(name)}</strong>'
                f'<span>{safe(energy)} · {safe(signature)}</span></div>')
    return (f'<div class="lab-duel" aria-label="Decks do confronto">'
            f'{panel(left,"MEU DECK")}<div class="lab-duel-vs">VS</div>'
            f'{panel(right,"ADVERSÁRIO")}</div>')


def result_bars(left_name: str, right_name: str, outcomes: dict, completed: int) -> str:
    n = max(0, int(completed))
    a = int(outcomes.get('left', 0))
    b = int(outcomes.get('right', 0))
    draws = int(outcomes.get('draw', 0))
    if not n:
        return '<div class="lab-results">Nenhuma partida concluída.</div>'
    rows = ''
    for name, count, suffix in [(left_name, a, ''), (right_name, b, 'alt')]:
        percentage = 100.0 * count / n
        rows += (f'<div class="lab-result-row"><span class="lab-result-label">{safe(name)}</span>'
                 f'<span class="lab-result-num">{percentage:.1f}%</span>'
                 f'<div class="lab-result-bar {suffix}" role="img" '
                 f'aria-label="{safe(name)}: {count} vitórias em {n} partidas">'
                 f'<span style="width:{percentage:.2f}%"></span></div></div>')
    draw_label = f'{draws} empate' if draws == 1 else f'{draws} empates'
    return (f'<section class="lab-results"><div class="lab-results-top"><strong>Resultado do lote</strong>'
            f'<span>{n} partidas · {draw_label}</span></div>{rows}'
            '<div class="lab-results-note">Percentuais exclusivos deste motor experimental; '
            'não representam chances reais de vitória.</div></section>')


def status_pill(status: str) -> str:
    labels = {'supported': '✓ Efeito reconhecido', 'blocked': '◌ Efeito pendente',
              'missing': '! Dados indisponíveis'}
    state = status if status in labels else 'missing'
    return (f'<span class="lab-coverage-pill {state}">'
            f'{safe(labels[state])}</span>')


def library_summary(name: str, energy_types: list[str], stage: str, count: int) -> str:
    title = safe(name)
    energy = ', '.join(ENERGY_META.get(e, ('', e))[1] for e in energy_types)
    phase = ('Já testado tecnicamente (sem validação competitiva)' if stage == 'technical_tested'
             else 'Lista disponível; efeitos ainda não validados')
    return (f'<div class="lab-library-summary"><strong>{title}</strong>'
            f'<span>{safe(energy)} · {int(count)} cartas · {safe(phase)}</span></div>')


def gauntlet_status_summary(plan: dict) -> str:
    values = [('Compatíveis', plan['ready']), ('Pendentes', plan['blocked']),
              ('Espelhados', plan['mirrors_skipped'])]
    return '<div class="lab-gauntlet-summary">' + ''.join(
        f'<div class="lab-gauntlet-stat"><b>{int(n)}</b><span>{safe(label)}</span></div>'
        for label,n in values) + '</div>'


def gauntlet_cards(opponents: list[dict]) -> str:
    status = {'ready': ('Simulável','ready'), 'blocked': ('Pendente','blocked'),
              'mirror': ('Espelhado','mirror')}
    tiles = []
    for row in opponents:
        label, cls = status.get(row.get('status'), ('Indefinido','blocked'))
        tiles.append(
            '<div class="lab-gauntlet-item">'
            f'<div class="lab-gauntlet-name">{safe(row.get("name", "Deck"))}</div>'
            '<div class="lab-gauntlet-bottom">'
            f'<span class="lab-gauntlet-badge {cls}">{label}</span>'
            f'<span class="lab-gauntlet-progress">{int(row.get("supported",0))}/{int(row.get("total",0))} cartas</span>'
            '</div></div>'
        )
    return '<div class="lab-gauntlet-grid">'+''.join(tiles)+'</div>'


# === v0.9.5 meta-matrix presentation (the pure calculations live elsewhere) ===
def matrix_rank_cards(ranking: list[dict]) -> str:
    """Render completed and incomplete ranks without unescaped deck names."""
    tiles = []
    for entry in ranking:
        rank = f"#{entry['rank']}" if entry.get('rank') is not None else '—'
        score = (f"{float(entry['score_pct']):.1f}%"
                 if entry.get('score_pct') is not None else '—')
        value = float(entry.get('score_pct') or 0)
        ci_text = (f'<small class="lab-ci">IC 95% aprox.: {float(entry["ci_lower"]):.1f}–{float(entry["ci_upper"]):.1f}%</small>'
                   if entry.get('ci_lower') is not None and entry.get('ci_upper') is not None else '')
        tiles.append(
            '<article class="lab-rank-card">'
            '<div class="lab-rank-top">'
            f'<span class="lab-rank-pos">{safe(rank)}</span>'
            f'<span class="lab-rank-name">{safe(entry["name"])}</span></div>'
            '<div class="lab-rank-foot">'
            '<div class="lab-score-main">'
            f'<strong>{safe(score)}</strong>'
            f'{ci_text}'
            '</div>'
            f'<span>{int(entry["wins"])}V · {int(entry["losses"])}D · {int(entry["draws"])}E<br>'
            f'{int(entry["played_pairs"])}/{int(entry["expected_pairs"])} confrontos</span></div>'
            f'<div class="lab-rank-meter"><span style="width:{max(0,min(100,value)):.2f}%"></span></div>'
            '</article>')
    return '<div class="lab-rank-list">' + ''.join(tiles) + '</div>'


def matrix_pair_cards(pairs: list[dict]) -> str:
    tiles = []
    for row in pairs:
        left, right = safe(row['left_name']),safe(row['right_name'])
        if row['status'] == 'completed':
            n = row['completed']
            out = row['outcomes']
            widths = [round(100*out[key]/n,3) for key in ('left','draw','right')]
            tiles.append(
                '<article class="lab-pair">'
                f'<div class="lab-pair-heading"><b>{left}</b> × <b>{right}</b></div>'
                f'<div class="lab-pair-score"><span>{float(row["score_left_pct"]):.1f}%</span>'
                f'<span>{float(row["score_right_pct"]):.1f}%</span></div>'
                '<div class="lab-pair-bar" aria-hidden="true">'
                f'<span class="left" style="width:{widths[0]}%"></span>'
                f'<span class="draw" style="width:{widths[1]}%"></span>'
                f'<span class="right" style="width:{widths[2]}%"></span></div>'
                f'<div class="lab-pair-detail">{int(out["left"])}–{int(out["right"])} vitórias'
                f' · {int(out["draw"])} empates · {int(n)} partidas</div></article>')
        else:
            status = {'blocked':'Pendente','partial':'Parcial','error':'Erro'}.get(row['status'],'Indisponível')
            reason = '; '.join(row.get('reasons',[])[:2]) or (row.get('errors') or [{}])[0].get('message','')
            tiles.append('<article class="lab-pair pending">'
                f'<div class="lab-pair-heading"><b>{left}</b> × <b>{right}</b></div>'
                f'<div class="lab-pair-detail">{safe(status)} · {safe(reason)}</div></article>')
    return '<div class="lab-matrix-pairs">' + ''.join(tiles) + '</div>'


def matrix_heatmap(report: dict) -> str:
    """Diagonal is not a simulated result. Cells use score % (draw = half)."""
    decks = report['plan']['decks']
    scores = {}
    for row in report['pairs']:
        if row['status'] == 'completed':
            scores[(row['left_slug'],row['right_slug'])]=row['score_left_pct']
            scores[(row['right_slug'],row['left_slug'])]=row['score_right_pct']
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    head = ''.join(f'<th scope="col">{letters[i]}</th>' for i in range(len(decks)))
    table_width=max(630, 70*(len(decks)+1))
    rows=[]
    for i,d in enumerate(decks):
        cells=[]
        for j,e in enumerate(decks):
            score = scores.get((d['slug'],e['slug']))
            if i == j:
                cells.append('<td class="na" title="Mesmo deck — não simulado">×</td>')
            elif score is None:
                cells.append('<td class="na" title="Confronto sem resultado completo">—</td>')
            else:
                color = max(0,min(1,score/100))
                cells.append(f'<td class="score" style="--heat:{color:.3f}" '
                             f'title="{safe(d["name"])} contra {safe(e["name"])}">{float(score):.1f}%</td>')
        rows.append(f'<tr><th class="head" scope="row">{letters[i]}</th>{"".join(cells)}</tr>')
    legend = ' · '.join(f'<b>{letters[i]}</b> {safe(d["name"])}' for i,d in enumerate(decks))
    return ('<div class="lab-matrix-scroll" role="region" aria-label="Matriz de confronto — deslize para os lados">'
            f'<table class="lab-matrix-table" style="min-width:{table_width}px"><thead><tr><th class="head">Deck</th>'
            f'{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="lab-matrix-legend">{legend}</div>')
