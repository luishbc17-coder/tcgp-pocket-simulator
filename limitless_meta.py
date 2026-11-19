"""Dated, user-inspectable reference from Play Limitless TCG Pocket.

The historical sample is deliberately NOT a live feed. It is an external
population reference, not an outcome produced by the local battle simulator.
A list's source eligibility is orthogonal to battle-engine compatibility.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import date
from math import sqrt
from typing import Any

REFERENCE_URL = 'https://play.limitlesstcg.com/decks?game=POCKET'
SNAPSHOT = {
    'kind': 'external_metagame_snapshot', 'provider': 'Play Limitless',
    'game': 'POCKET', 'observed_on': '2026-11-19',
    'source_url': REFERENCE_URL, 'scope_note':
    'Tabela de decks do Limitless consultada em 19/11/2026; os filtros/período do site podem mudar. ' 
    'Esta amostra retém os 15 arquétipos mais frequentes no resultado consultado.',
    'population': {'tournaments': 75, 'players': 8828, 'matches_or_games': 27122},
    'archetypes': [
        {'slug': 'charizard_entei', 'name': 'Mega Charizard Y ex / Entei ex', 'count': 1087, 'share_pct': 12.31, 'observed_win_pct': 50.49},
        {'slug': 'suicune_baxcalibur', 'name': 'Suicune ex / Baxcalibur', 'count': 669, 'share_pct': 7.58, 'observed_win_pct': 51.64},
        {'slug': 'umbreon_hydreigon', 'name': 'Umbreon / Hydreigon', 'count': 534, 'share_pct': 6.05, 'observed_win_pct': 46.89},
        {'slug': 'hoopa_mega_absol', 'name': 'Hoopa ex / Mega Absol ex', 'count': 530, 'share_pct': 6.00, 'observed_win_pct': 53.97},
        {'slug': 'mega_lucario_lucario', 'name': 'Mega Lucario ex / Lucario', 'count': 444, 'share_pct': 5.03, 'observed_win_pct': 50.91},
        {'slug': 'vespiquen_shuckle', 'name': 'Vespiquen ex / Shuckle ex', 'count': 440, 'share_pct': 4.98, 'observed_win_pct': 53.69},
        {'slug': 'mega_altaria_greninja', 'name': 'Mega Altaria ex / Greninja', 'count': 402, 'share_pct': 4.55, 'observed_win_pct': 53.79},
        {'slug': 'greninja_ex_mega_greninja', 'name': 'Mega Greninja ex / Greninja ex', 'count': 397, 'share_pct': 4.50, 'observed_win_pct': 43.54},
        {'slug': 'altaria_espeon', 'name': 'Mega Altaria ex / Espeon', 'count': 370, 'share_pct': 4.19, 'observed_win_pct': 54.25},
        {'slug': 'magnezone_miraidon', 'name': 'Magnezone / Miraidon ex', 'count': 358, 'share_pct': 4.06, 'observed_win_pct': 54.54},
        {'slug': 'giratina_dragonair', 'name': 'Giratina ex / Dragonair', 'count': 334, 'share_pct': 3.78, 'observed_win_pct': 49.76},
        {'slug': 'mega_manectric_heliolisk', 'name': 'Mega Manectric ex / Heliolisk', 'count': 312, 'share_pct': 3.53, 'observed_win_pct': 50.81},
        {'slug': 'mega_mewtwo_x_mew', 'name': 'Mega Mewtwo X ex / Mew ex', 'count': 249, 'share_pct': 2.82, 'observed_win_pct': 48.46},
        {'slug': 'mega_sceptile_greninja', 'name': 'Mega Sceptile ex / Greninja', 'count': 206, 'share_pct': 2.33, 'observed_win_pct': 51.88},
        {'slug': 'hydreigon_mega_absol', 'name': 'Hydreigon / Mega Absol ex', 'count': 188, 'share_pct': 2.13, 'observed_win_pct': 54.37},
    ],
}


def default_snapshot() -> dict:
    return deepcopy(SNAPSHOT)


def validate_snapshot(raw: Any) -> dict:
    """Strict schema, bounded size, no inferred matches for unknown slugs."""
    if not isinstance(raw, dict) or raw.get('provider') != 'Play Limitless' or raw.get('game') != 'POCKET':
        raise ValueError('Snapshot deve identificar Play Limitless / POCKET.')
    if raw.get('source_url') != REFERENCE_URL:
        raise ValueError('Fonte do snapshot não corresponde ao endereço oficial configurado.')
    observed_on = raw.get('observed_on')
    try:
        if (not isinstance(observed_on, str) or len(observed_on) != 10
                or date.fromisoformat(observed_on).isoformat() != observed_on):
            raise ValueError('Data da coleta ausente ou inválida.')
    except (TypeError, ValueError) as exc:
        raise ValueError('Data da coleta ausente ou inválida.') from exc
    rows = raw.get('archetypes')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError('Informe entre 1 e 200 arquétipos.')
    seen = set()
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError('Arquétipo inválido.')
        slug, label, share = r.get('slug'), r.get('name'), r.get('share_pct')
        if not isinstance(slug, str) or not slug or len(slug)>90 or slug in seen:
            raise ValueError('Identificador duplicado ou inválido no snapshot.')
        seen.add(slug)
        if not isinstance(label, str) or not label.strip() or len(label) > 160:
            raise ValueError('Nome do arquétipo inválido.')
        if type(share) not in (float, int) or not (0 <= share <= 100):
            raise ValueError('Participação do arquétipo inválida.')
        for key in ('count', 'observed_win_pct'):
            value = r.get(key)
            if value is None: continue
            if key == 'count' and (type(value) is not int or value < 0):
                raise ValueError('Contagem inválida.')
            if key == 'observed_win_pct' and (type(value) not in (float, int) or not 0 <= value <= 100):
                raise ValueError('Win rate externo inválido.')
    if sum(r['share_pct'] for r in rows) > 100.001:
        raise ValueError('Somatório das participações não pode ultrapassar 100%.')
    return deepcopy(raw)


def evaluate_reference_coverage(results: list[dict], snapshot: dict | None = None) -> dict:
    """Weighted result only for compatible, completed *observed* local games.

    Report explicitly how little of the true external population is covered.
    If there's no coverage, no phantom denominator or 0% win rate is emitted.
    """
    snapshot = validate_snapshot(snapshot or SNAPSHOT)
    by_slug = {r['slug']: r for r in snapshot['archetypes']}
    rows, participating_share = [], 0.0
    seen_results = set()
    eligible_share = 0.0
    weighted_score = 0.0
    variance = 0.0
    for result in results:
        slug = result.get('slug')
        if slug in seen_results:
            raise ValueError('Um mesmo arquétipo não pode ser contado duas vezes.')
        seen_results.add(slug)
        ref = by_slug.get(slug)
        if ref is None:
            continue
        share = float(ref['share_pct'])
        participating_share += share
        n = result.get('completed', 0)
        outcomes = result.get('outcomes')
        valid = (result.get('status') == 'completed' and type(n) is int and n > 0
                 and isinstance(outcomes, dict) and sum(outcomes.get(k, 0) for k in ('left','right','draw')) == n)
        row = {'slug': ref['slug'], 'name': ref['name'], 'share_pct': share,
               'status': result.get('status'), 'completed': n if valid else 0,
               'local_score_pct': None, 'external_archetype_win_pct': ref.get('observed_win_pct')}
        if valid:
            p = (outcomes['left'] + outcomes['draw']/2) / n
            row['local_score_pct'] = round(100*p,2)
            eligible_share += share
            weighted_score += share * p
            # conservative plug-in only; sampling error across matchups isn't independent in practice.
            variance += (share ** 2) * p*(1-p)/n
        rows.append(row)
    if eligible_share:
        mean = weighted_score / eligible_share
        error = 1.96 * sqrt(variance)/eligible_share
        approximate_ci = [round(100 * max(0, mean-error),2),round(100 * min(1,mean+error),2)]
    else:
        mean, approximate_ci = None, None
    sample_share = sum(float(r['share_pct']) for r in snapshot['archetypes'])
    return {'kind': 'partial_limitless_weighted_benchmark',
            'source_url': snapshot['source_url'], 'observed_on': snapshot.get('observed_on'),
            'represented_share_pct': round(sample_share,2),
            'selected_share_pct': round(participating_share,2),
            'completed_share_pct': round(eligible_share,2),
            'missing_or_blocked_share_pct': round(max(0,participating_share-eligible_share),2),
            'external_meta_share_not_simulated_pct': round(max(0,100-eligible_share),2),
            'conditional_score_pct': round(100*mean,2) if mean is not None else None,
            'approximate_95pct_interval': approximate_ci,
            'matchups': rows,
            'warning': ('Resultado condicionado APENAS aos confrontos concluídos e seus pesos de participação. '
                        'Não representa win rate contra 100% do meta; intervalo aproximado e duelos heurísticos. '
                        'Win rate externo de cada arquétipo NÃO é o win rate do deck testado.')}
