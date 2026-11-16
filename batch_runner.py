"""Bounded, replayable technical matchup runs for TCG Pocket Lab v0.8.3.

Never present these results as verified metagame probabilities: the v0.8.x
agent is heuristic and this engine does not model all real-game interactions.
"""
from __future__ import annotations
from collections import Counter
from time import monotonic
from typing import Callable
from battle_engine import Card, RuleAgent, RuleError, UnsupportedEffect, validate_deck
from battle_audit import AuditedBattle, StateInvariantError, snapshot

MAX_BATCH_GAMES = 1_000


def run_technical_batch(left: list[Card], right: list[Card],
                        energy_left=('psychic',), energy_right=('darkness',),
                        line_map: dict[str, str] | None = None,
                        games: int = 100, seed: int = 20261116,
                        progress: Callable[[int, int], None] | None = None,
                        keep_replay: bool = True) -> dict:
    """Fair, deterministic experiment: two seating orders and first-player balance.

    The unaltered original decks are always 'left' and 'right'; if a round
    reverses seating, winners are mapped back to original deck names.
    Each round is independently seeded; invalid rounds are reported separately.
    """
    if type(games) is not int or not 1 <= games <= MAX_BATCH_GAMES:
        raise ValueError(f'games must be 1..{MAX_BATCH_GAMES}')
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    left_e, right_e = tuple(energy_left), tuple(energy_right)
    validate_deck(left, left_e)
    validate_deck(right, right_e)
    if len(left_e) != 1 or len(right_e) != 1:
        raise UnsupportedEffect('Multicolor Energy Zone is unsupported')

    counts = Counter()
    splits = {'left_first': Counter(), 'right_first': Counter()}
    seat_splits = {'left_as_p0': Counter(), 'left_as_p1': Counter()}
    errors = []
    total_actions = 0
    total_turns = 0
    replay = None
    agent = RuleAgent(line_map or {})
    start_time = monotonic()
    for idx in range(games):
        reverse = (idx // 2) % 2 == 1
        left_goes_first = idx % 2 == 0
        left_side = 1 if reverse else 0
        first_side = left_side if left_goes_first else 1 - left_side
        a, b = (right, left) if reverse else (left, right)
        ea, eb = (right_e, left_e) if reverse else (left_e, right_e)
        battle = None
        try:
            battle = AuditedBattle(a, b, ea, eb, seed=seed + idx,
                                   force_first=first_side,
                                   collect_trace=keep_replay and idx == 0)
            while not battle.finished:
                agent.play_turn(battle)
            if battle.winner is None:
                outcome = 'draw'
            elif battle.winner == left_side:
                outcome = 'left'
            else:
                outcome = 'right'
            counts[outcome] += 1
            splits['left_first' if left_goes_first else 'right_first'][outcome] += 1
            seat_splits['left_as_p1' if reverse else 'left_as_p0'][outcome] += 1
            total_actions += battle.checked_actions
            total_turns += battle.turn
            if keep_replay and idx == 0:
                replay = {
                    'seed': seed, 'winner': battle.winner,
                    'first_player': battle.first, 'turns': battle.turn,
                    'events': list(battle.log), 'snapshots': battle.trace,
                    'energy_p0': list(ea), 'energy_p1': list(eb),
                    'note': 'Technical prototype replay, not a certified real-game match.'
                }
        except (RuleError, ValueError, IndexError, AssertionError) as ex:
            errors.append({'round': idx + 1, 'seed': seed + idx,
                           'type': type(ex).__name__, 'message': str(ex),
                           'events': battle.log[-25:] if battle else []})
            if len(errors) >= 10:
                break  # fail closed on systemic errors, not thousands of invalid rounds
        if progress and ((idx + 1) % 25 == 0 or idx + 1 == games):
            progress(idx + 1, games)
    valid = sum(counts.values())
    attempted = valid + len(errors)
    return {
        'kind': 'technical_prototype_batch',
        'validated_competitive': False,
        'disclaimer': ('Contagens de um agente heurístico em motor parcial. '
                       'NÃO são probabilidades reais de vitória do metagame.'),
        'configured': games, 'attempted': attempted, 'completed': valid,
        'failed': len(errors), 'aborted_early': attempted < games,
        'outcomes': {k:counts[k] for k in ('left','right','draw')},
        'first_player_splits': {
            k:{o:splits[k][o] for o in ('left','right','draw')}
            for k in ('left_first','right_first')},
        'seating_splits': {
            k:{o:seat_splits[k][o] for o in ('left','right','draw')}
            for k in ('left_as_p0','left_as_p1')},
        'average_half_turns': round(total_turns / valid, 3) if valid else None,
        'checked_actions': total_actions,
        'seed': seed, 'errors': errors, 'sample_replay': replay,
        'elapsed_seconds': round(monotonic()-start_time, 3),
    }
