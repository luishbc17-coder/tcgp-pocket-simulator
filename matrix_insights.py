"""Pure statistical summaries for exploratory Pocket Lab matrices, v0.9.5.

Intervals are approximate Wilson score intervals treating draws as half wins;
this is *not* a confidence interval for real-world metagame performance.
"""
from __future__ import annotations
from math import sqrt

Z95 = 1.959963984540054


def score_interval(wins: int, losses: int, draws: int = 0) -> dict:
    if any(type(x) is not int or x < 0 for x in (wins, losses, draws)):
        raise ValueError('Vitórias, derrotas e empates devem ser inteiros não negativos')
    n = wins + losses + draws
    if not n:
        return {'n': 0, 'score_pct': None, 'lower_pct': None, 'upper_pct': None,
                'half_width_pct': None, 'small_sample': True}
    p = (wins + draws / 2) / n
    z2 = Z95**2
    divisor = 1 + z2 / n
    center = (p + z2/(2*n)) / divisor
    margin = (Z95 * sqrt(p*(1-p)/n + z2/(4*n*n))) / divisor
    lower = max(0.0,100 * (center - margin))
    upper = min(100.0,100 * (center + margin))
    return {'n':n, 'score_pct':round(100*p,2), 'lower_pct':round(lower,2),
            'upper_pct':round(upper,2), 'half_width_pct':round((upper-lower)/2,2),
            'small_sample':n < 100}


def matrix_intervals(report:dict) -> dict:
    """Return intervals only for completed pairs, and for scored deck rows."""
    pairs={}
    for row in report['pairs']:
        if row['status'] != 'completed' or row.get('failed',0):
            continue
        o=row['outcomes']
        key=(row['left_slug'],row['right_slug'])
        pairs[key] = {'left':score_interval(o['left'],o['right'],o['draw']),
                      'right':score_interval(o['right'],o['left'],o['draw'])}
    ranking={}
    for row in report['summary']['ranking']:
        if row['games']:
            ranking[row['slug']]=score_interval(row['wins'],row['losses'],row['draws'])
    return {'pairs':pairs,'ranking':ranking}


def compare_matrix_policies(baseline:dict, tactical:dict) -> dict:
    """Match two fully completed matrices using identical field, seeds, and size.

    Comparisons are descriptive only: policies can produce different RNG
    trajectories even when initial random seeds match.
    """
    for report in (baseline,tactical):
        if not report['summary']['ranking_complete'] or report['failed']:
            raise ValueError('A comparação exige duas matrizes completas e sem erros')
    if baseline['agent_mode'] != 'baseline' or tactical['agent_mode'] != 'tactical':
        raise ValueError('Ordem de políticas inválida')
    if baseline['seed'] != tactical['seed'] or baseline['games_per_pair'] != tactical['games_per_pair']:
        raise ValueError('As sementes e a quantidade de partidas devem coincidir')
    def identities(report):
        return [(d['slug'],d['signature']) for d in report['plan']['decks']]
    if identities(baseline) != identities(tactical):
        raise ValueError('Decks distintos: comparação recusada')
    def completed_pairs(report):
        return [(r['left_slug'],r['right_slug'],r['completed']) for r in report['pairs']]
    if completed_pairs(baseline) != completed_pairs(tactical):
        raise ValueError('Confrontos diferentes: comparação recusada')
    b={r['slug']:r for r in baseline['summary']['ranking']}
    t={r['slug']:r for r in tactical['summary']['ranking']}
    rows=[]
    for slug in b:
        rows.append({'slug':slug,'name':b[slug]['name'],
                     'classic_score_pct':b[slug]['score_pct'],
                     'tactical_score_pct':t[slug]['score_pct'],
                     'delta_pp':round(t[slug]['score_pct']-b[slug]['score_pct'],2),
                     'classic_interval':score_interval(b[slug]['wins'],b[slug]['losses'],b[slug]['draws']),
                     'tactical_interval':score_interval(t[slug]['wins'],t[slug]['losses'],t[slug]['draws'])})
    rows.sort(key=lambda x:-x['tactical_score_pct'])
    return {'kind':'technical_matrix_policy_comparison','version':'0.9.5',
            'validated_competitive':False,
            'warning':'Comparação descritiva: as decisões de IA modificam a sequência aleatória, mesmo com as mesmas sementes.',
            'seed':baseline['seed'],'games_per_pair':baseline['games_per_pair'],
            'rows':rows,'classic_first_player':baseline['summary']['first_player'],
            'tactical_first_player':tactical['summary']['first_player']}


def interesting_rounds(report:dict, limit=8) -> list[dict]:
    """Identify shortest logged rounds across all finished pairs, no fabrication."""
    candidates=[]
    for pair in report['pairs']:
        if pair['status']!='completed':
            continue
        for round_data in pair.get('rounds',[]):
            candidates.append({'left_slug':pair['left_slug'],
                'right_slug':pair['right_slug'],'left_name':pair['left_name'],
                'right_name':pair['right_name'],'round':round_data['round'],
                'half_turns':round_data['half_turns'],'seed':round_data['seed']})
    return sorted(candidates,key=lambda r:(r['half_turns'],r['seed']))[:limit]
