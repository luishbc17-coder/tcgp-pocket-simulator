"""Audited, bounded round-robin meta matrix for TCG Pocket Lab v0.9.5.

Every unordered pair appears once. Results are technical heuristics rather
than metagame probabilities. A pair failing compatibility or auditing never
contributes synthetic wins to the ranking; incomplete matrices are unranked.
"""
from __future__ import annotations

from itertools import combinations
from typing import Callable

from battle_engine import RuleError, UnsupportedEffect
from matchup_compatibility import inspect_deck, load_compiled_deck
from deck_identity import describe_selection
from batch_runner import run_technical_batch
from gameplay_catalog import evolution_line_map
from meta_decks import DECKS as REGISTERED_DECKS

MAX_MATRIX_DECKS = 26
MAX_GAMES_PER_PAIR = 100
MAX_TOTAL_MATRIX_GAMES = 2500


def build_matrix_plan(presets: dict[str, dict], core: list[dict],
                      gameplay: list[dict]) -> dict:
    """Check all distinct pairings without simulating anything."""
    if not isinstance(presets, dict) or not 2 <= len(presets) <= MAX_MATRIX_DECKS:
        raise ValueError(f'Selecione entre 2 e {MAX_MATRIX_DECKS} decks diferentes')
    rows = []
    signatures = {}
    for slug, deck in presets.items():
        diag = inspect_deck(deck, core, gameplay)
        identity = describe_selection(deck, deck.get('name', slug))
        signatures[slug] = identity['signature']
        reasons = list(diag['issues'])
        if deck.get('simulation_blocked_reason'):
            reasons.append(deck['simulation_blocked_reason'])
        reasons.extend(f"{card['name']}: {card['reason']}"
                       for card in diag['cards'] if card['status'] == 'bloqueada')
        rows.append({'slug':slug, 'name':deck.get('name',slug),
                     'signature':identity['signature'],
                     'energy_types':list(deck.get('energy_types', [])),
                     'supported':diag['supported'], 'total':diag['total'],
                     'ready':bool(diag['technical_demo_ready']) and not bool(deck.get('simulation_blocked_reason')), 
                     'reasons':reasons[:12]})
    lookup = {r['slug']: r for r in rows}
    pairs = []
    for left_slug, right_slug in combinations(presets, 2):
        left = lookup[left_slug]
        right = lookup[right_slug]
        reasons = []
        if not left['ready']:
            reasons += [f"{left['name']}: {msg}" for msg in left['reasons']]
        if not right['ready']:
            reasons += [f"{right['name']}: {msg}" for msg in right['reasons']]
        duplicate = signatures[left_slug] == signatures[right_slug]
        if duplicate:
            reasons.append('As duas listas têm a mesma composição e energia')
        status = 'blocked' if reasons else 'ready'
        pairs.append({'left_slug':left_slug, 'right_slug':right_slug,
                      'left_name':left['name'], 'right_name':right['name'],
                      'left_signature':signatures[left_slug],
                      'right_signature':signatures[right_slug],
                      'status':status, 'reasons':reasons[:14],
                      'duplicate':duplicate})
    return {'decks':rows, 'pairs':pairs,
            'total_pairs':len(pairs),
            'ready_pairs':sum(x['status']=='ready' for x in pairs),
            'blocked_pairs':sum(x['status']=='blocked' for x in pairs)}


def summarize_matrix(plan: dict, pairs: list[dict]) -> dict:
    """Pure score computation. Score is win + 0.5 draw, not win percentage."""
    stats = {d['slug']: {'slug':d['slug'], 'name':d['name'],
              'wins':0, 'losses':0, 'draws':0, 'games':0, 'score':0.0,
              'played_pairs':0, 'expected_pairs':len(plan['decks'])-1}
             for d in plan['decks']}
    first_wins = second_wins = draws = 0
    complete = 0
    for pair in pairs:
        if pair['status'] != 'completed':
            continue
        complete += 1
        wins = pair['outcomes']
        n = pair['completed']
        left, right = stats[pair['left_slug']], stats[pair['right_slug']]
        for entry, w, l in ((left,wins['left'],wins['right']),
                            (right,wins['right'],wins['left'])):
            entry['wins'] += w
            entry['losses'] += l
            entry['draws'] += wins['draw']
            entry['score'] += w + 0.5 * wins['draw']
            entry['games'] += n
            entry['played_pairs'] += 1
        spl = pair['first_player_splits']
        first_wins += spl['left_first']['left'] + spl['right_first']['right']
        second_wins += spl['left_first']['right'] + spl['right_first']['left']
        draws += spl['left_first']['draw'] + spl['right_first']['draw']
    full = (complete == plan['total_pairs'] and
            all(x['status'] == 'completed' for x in pairs))
    rankings = []
    for row in stats.values():
        n = row['games']
        row['score_pct'] = round(100 * row['score'] / n, 2) if n else None
        row['win_pct'] = round(100 * row['wins'] / n, 2) if n else None
        row['complete_coverage'] = row['played_pairs'] == row['expected_pairs']
        row['rank'] = None
        rankings.append(row)
    rankings.sort(key=lambda r: (-(r['score_pct'] if r['score_pct'] is not None else -1),
                                  -r['wins'],r['name'].casefold()))
    if full:
        for index, row in enumerate(rankings, 1):
            row['rank'] = (next((prev['rank'] for prev in rankings[:index-1]
                                if prev['score_pct'] == row['score_pct']), index))
    total_decided = first_wins + second_wins + draws
    return {
        'ranking':rankings, 'ranking_complete':full,
        'completed_pairs':complete, 'total_pairs':plan['total_pairs'],
        'first_player':{'first_wins':first_wins, 'second_wins':second_wins,
                        'draws':draws, 'games':total_decided,
                        'first_win_pct':round(first_wins*100/total_decided,2)
                        if total_decided else None,
                        'second_win_pct':round(second_wins*100/total_decided,2)
                        if total_decided else None},
    }


def run_meta_matrix(presets: dict[str, dict], core: list[dict],
                    gameplay: list[dict], games_per_pair: int = 25,
                    seed: int = 20261116, agent_mode: str = 'tactical',
                    progress: Callable[[int, int], None] | None = None) -> dict:
    """Compute a complete technical round robin, with explicit blocked pairs."""
    if type(games_per_pair) is not int or not 1 <= games_per_pair <= MAX_GAMES_PER_PAIR:
        raise ValueError(f'Partidas por confronto devem ser 1–{MAX_GAMES_PER_PAIR}')
    if type(seed) is not int or seed < 0:
        raise ValueError('Semente deve ser um inteiro não negativo')
    if agent_mode not in ('baseline', 'tactical', 'strategic', 'planning'):
        raise ValueError('Política de IA inválida')
    plan = build_matrix_plan(presets, core, gameplay)
    if plan['ready_pairs'] * games_per_pair > MAX_TOTAL_MATRIX_GAMES:
        raise ValueError('Excesso de partidas na matriz')
    line_map = evolution_line_map(gameplay) if plan['ready_pairs'] else {}
    total = plan['ready_pairs'] * games_per_pair
    completed_before = 0
    slugs = list(REGISTERED_DECKS) + sorted(slug for slug in presets if slug not in REGISTERED_DECKS)
    results = []
    for pair in plan['pairs']:
        if pair['status'] != 'ready':
            results.append({**pair, 'completed':0, 'failed':0,
                            'outcomes':None, 'score_left_pct':None,
                            'score_right_pct':None})
            continue
        i = slugs.index(pair['left_slug'])
        j = slugs.index(pair['right_slug'])
        # A unique stable offset for every distinct pair. Does not depend on
        # whether preceding pairs were blocked.
        i, j = sorted((i,j))
        # Preserve v0.9.4 seeds for the original seven decks. Adding four
        # archetypes must not silently change the replay of an old matchup.
        # New pairs use a disjoint offset space, independent of chosen subset.
        slot = (i * 7 + j if j < 7 else
                49 + i * 11 + j if j < 11 else
                512 + i * 32 + j)
        pair_seed = seed + slot * (MAX_GAMES_PER_PAIR + 1)
        left = presets[pair['left_slug']]
        right = presets[pair['right_slug']]
        try:
            batch = run_technical_batch(
                load_compiled_deck(left, gameplay),
                load_compiled_deck(right, gameplay),
                energy_left=tuple(left['energy_types']),
                energy_right=tuple(right['energy_types']),
                line_map=line_map, games=games_per_pair, seed=pair_seed,
                agent_mode=agent_mode, keep_replay=False,
                left_payload=left, right_payload=right,
                progress=(lambda n, _target, previous=completed_before:
                          progress(previous+n,total)) if progress else None)
            n = batch['completed']
            outcomes = batch['outcomes']
            complete = (n == games_per_pair and batch['failed']==0)
            results.append({**pair, 'status':'completed' if complete else 'partial',
                            'seed':pair_seed, 'completed':n,
                            'failed':batch['failed'], 'errors':batch['errors'],
                            'outcomes':outcomes,
                            'score_left_pct':round(100*(outcomes['left']+0.5*outcomes['draw'])/n,2)
                            if complete else None,
                            'score_right_pct':round(100*(outcomes['right']+0.5*outcomes['draw'])/n,2)
                            if complete else None,
                            'first_player_splits':batch['first_player_splits'],
                            'seating_splits':batch['seating_splits'],
                            'average_half_turns':batch['average_half_turns'],
                            'checked_actions':batch['checked_actions'],
                            'rounds':batch['rounds']})
        except (RuleError, UnsupportedEffect, ValueError, IndexError,
                AssertionError, TypeError, AttributeError, RuntimeError) as exc:
            results.append({**pair, 'status':'error', 'seed':pair_seed,
                            'completed':0, 'failed':1, 'outcomes':None,
                            'score_left_pct':None, 'score_right_pct':None,
                            'errors':[{'type':type(exc).__name__,
                                       'message':str(exc)[:500]}]})
        completed_before += games_per_pair
        if progress:
            progress(completed_before, total)
    summary = summarize_matrix(plan, results)
    return {
        'kind':'technical_meta_matrix', 'version':'0.9.8',
        'validated_competitive':False,
        'disclaimer':('Resultados de IA heurística em motor parcial, com mesmo peso por adversário; '
                      'não são probabilidades reais do metagame nem ranking oficial.'),
        'agent_mode':agent_mode, 'seed':seed,
        'games_per_pair':games_per_pair, 'plan':plan,
        'pairs':results, 'summary':summary,
        'completed':sum(p['completed'] for p in results),
        'failed':sum(p.get('failed',0) for p in results),
    }
