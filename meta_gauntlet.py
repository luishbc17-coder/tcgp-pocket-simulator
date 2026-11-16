"""One-deck-versus-meta technical gauntlet for TCG Pocket Lab v0.9.3.

A blocked opponent MUST NOT receive a simulated win rate. Do not treat these
technical counts as competitive estimates. Every completed pair is audited by
run_technical_batch, which balances first player and seating.
"""
from __future__ import annotations
from collections import Counter
from typing import Callable

from battle_engine import RuleError, UnsupportedEffect
from matchup_compatibility import inspect_deck, load_compiled_deck
from deck_identity import describe_selection, compare_decks
from batch_runner import run_technical_batch
from gameplay_catalog import evolution_line_map

MAX_GAMES_PER_OPPONENT = 250
MAX_TOTAL_GAMES = 2500


def build_gauntlet_plan(player_payload: dict, opponents: dict[str, dict],
                        core: list[dict], gameplay: list[dict],
                        include_mirror: bool = False) -> dict:
    """Return annotated opponents; no game execution, no invented outcomes."""
    player = inspect_deck(player_payload, core, gameplay)
    player_identity = describe_selection(player_payload, 'Meu deck')
    rows = []
    for slug, deck in opponents.items():
        opponent = inspect_deck(deck, core, gameplay)
        comparison = compare_decks(player_identity, describe_selection(deck, deck.get('name', slug)))
        mirror = comparison['is_mirror']
        reasons = []
        if not player['technical_demo_ready']:
            reasons.append('Seu deck não está completamente suportado pelo motor')
        if not opponent['technical_demo_ready']:
            reasons.extend(opponent['issues'])
            reasons.extend(f"{card['name']}: {card['reason']}" for card in opponent['cards']
                           if card['status'] == 'bloqueada')
        if mirror and not include_mirror:
            status = 'mirror'
        elif reasons:
            status = 'blocked'
        else:
            status = 'ready'
        rows.append({'slug': slug, 'name': deck.get('name', slug),
                     'status': status, 'mirror': mirror,
                     'supported': opponent['supported'], 'total': opponent['total'],
                     'reasons': reasons[:12], 'signature': describe_selection(deck, slug)['signature']})
    return {'player': player, 'player_signature': player_identity['signature'],
            'opponents': rows,
            'ready': sum(r['status'] == 'ready' for r in rows),
            'blocked': sum(r['status'] == 'blocked' for r in rows),
            'mirrors_skipped': sum(r['status'] == 'mirror' for r in rows)}


def run_meta_gauntlet(player_payload: dict, opponents: dict[str, dict],
                      core: list[dict], gameplay: list[dict],
                      games_per_opponent: int = 100, seed: int = 20261116,
                      agent_mode: str = 'tactical', include_mirror: bool = False,
                      progress: Callable[[int, int], None] | None = None) -> dict:
    """Run every allowed opponent and return per-rival results and blockers.

    A fresh compiled deck is loaded for each opponent. Seeds have a
    deterministic, per-opponent offset to avoid replaying identical RNG streams.
    """
    if type(games_per_opponent) is not int or not 1 <= games_per_opponent <= MAX_GAMES_PER_OPPONENT:
        raise ValueError(f'Partidas por adversário devem ser 1–{MAX_GAMES_PER_OPPONENT}')
    if type(seed) is not int or seed < 0:
        raise ValueError('Semente deve ser um inteiro não negativo')
    if agent_mode not in ('baseline', 'tactical'):
        raise ValueError('Política de IA inválida')
    if games_per_opponent * len(opponents) > MAX_TOTAL_GAMES:
        raise ValueError(f'Limite: {MAX_TOTAL_GAMES} partidas por execução')
    plan = build_gauntlet_plan(player_payload, opponents, core, gameplay, include_mirror)
    runnable = [r for r in plan['opponents'] if r['status'] == 'ready']
    total = len(runnable) * games_per_opponent
    result = []
    totals = Counter()
    rounds_done = 0
    line_map = evolution_line_map(gameplay) if runnable else {}
    for position, row in enumerate(plan['opponents']):
        if row['status'] != 'ready':
            result.append({**row, 'completed': 0, 'failed': 0,
                           'outcomes': None, 'win_rate': None})
            continue
        deck = opponents[row['slug']]
        # Stable seeds tied to the index in the *full* field, even when
        # other decks become eligible in subsequent versions.
        pair_seed = seed + position * (MAX_GAMES_PER_OPPONENT + 1)
        try:
            report = run_technical_batch(
                load_compiled_deck(player_payload, gameplay),
                load_compiled_deck(deck, gameplay),
                energy_left=tuple(player_payload['energy_types']),
                energy_right=tuple(deck['energy_types']),
                line_map=line_map, games=games_per_opponent, seed=pair_seed,
                agent_mode=agent_mode, keep_replay=False,
                left_payload=player_payload, right_payload=deck,
                progress=(lambda n, _expected, previous=rounds_done:
                          progress(previous+n, total)) if progress else None)
            completed = report['completed']
            if completed < games_per_opponent or report['failed']:
                state = 'partial'
            else:
                state = 'completed'
            totals.update(report['outcomes'])
            result.append({**row, 'status': state,
                           'seed': pair_seed, 'completed': completed,
                           'failed': report['failed'], 'errors': report['errors'],
                           'outcomes': report['outcomes'],
                           'win_rate': round(100 * report['outcomes']['left'] / completed, 2)
                           if completed else None,
                           'first_player_splits': report['first_player_splits'],
                           'seating_splits': report['seating_splits'],
                           'average_half_turns': report['average_half_turns'],
                           'checked_actions': report['checked_actions'],
                           'rounds': report['rounds']})
        except (RuleError, UnsupportedEffect, ValueError, TypeError, IndexError) as exc:
            result.append({**row, 'status': 'error', 'completed': 0,
                           'failed': 1, 'outcomes': None, 'win_rate': None,
                           'errors': [{'type': type(exc).__name__, 'message': str(exc)}]})
        rounds_done += games_per_opponent
        if progress:
            progress(rounds_done, total)
    completed = sum(row['completed'] for row in result)
    return {
        'kind': 'technical_meta_gauntlet', 'version': '0.9.3',
        'validated_competitive': False,
        'disclaimer': ('Dados técnicos de políticas heurísticas e efeitos parciais, '
                       'não probabilidades reais de vitória no metagame.'),
        'player': player_payload, 'agent_mode': agent_mode,
        'seed': seed, 'games_per_opponent': games_per_opponent,
        'plan': plan, 'results': result,
        'completed': completed,
        'failed': sum(row.get('failed', 0) for row in result),
        'ready_pairs': len(runnable),
        'outcomes': {key: totals[key] for key in ('left','right','draw')},
        'overall_win_rate': round(100 * totals['left']/completed, 2) if completed else None,
        'overall_rate_note': ('Média ponderada somente dos confrontos executados; '
                              'não é uma taxa contra todo o meta.'),
    }
