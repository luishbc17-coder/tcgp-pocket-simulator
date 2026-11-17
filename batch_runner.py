"""Bounded, replayable technical matchup runs for TCG Pocket Lab v0.9.

Never present these results as verified metagame probabilities: the v0.8.x
agent is heuristic and this engine does not model all real-game interactions.
"""
from __future__ import annotations
from collections import Counter
import inspect
from time import monotonic
from typing import Callable
import battle_engine
from battle_engine import Battle, Card, RuleAgent, RuleError, UnsupportedEffect, validate_deck
from battle_audit import AuditedBattle, StateInvariantError, snapshot
from deck_identity import describe_compiled, compare_decks
from tactical_agent import TacticalAgent
from strategic_agent import StrategicAgentV097
from planning_agent import PlanningAgentV099
from battle_metrics import count_logged_actions, merge_telemetry, new_telemetry, serialize_telemetry, duration_distribution

MAX_BATCH_GAMES = 1_000


def verify_engine_compatibility() -> None:
    """Fail before running matches if Streamlit has mixed old/new Python modules.

    A stale battle_engine.py previously produced a redacted TypeError from
    AuditedBattle.__init__ when force_first was passed. Do not silently use
    the old engine: a different implementation invalidates the batch audit.
    """
    expected_api = 2
    version = getattr(battle_engine, 'ENGINE_API_VERSION', None)
    parameters = inspect.signature(Battle.__init__).parameters
    if version != expected_api or 'force_first' not in parameters:
        raise RuleError(
            'Versões incompatíveis do motor de partidas: o lote v0.8.3.1 '
            'requer battle_engine.py e battle_audit.py da mesma atualização. '
            'Substitua os quatro arquivos do hotfix no GitHub e reinicie o '
            'Streamlit em Manage app → Reboot app.'
        )



def run_technical_batch(left: list[Card], right: list[Card],
                        energy_left=('psychic',), energy_right=('darkness',),
                        line_map: dict[str, str] | None = None,
                        games: int = 100, seed: int = 20261116,
                        progress: Callable[[int, int], None] | None = None,
                        keep_replay: bool = True,
                        left_payload: dict | None = None,
                        right_payload: dict | None = None,
                        agent_mode: str = 'baseline') -> dict:
    """Fair, deterministic experiment: two seating orders and first-player balance.

    The unaltered original decks are always 'left' and 'right'; if a round
    reverses seating, winners are mapped back to original deck names.
    Each round is independently seeded; invalid rounds are reported separately.
    """
    if type(games) is not int or not 1 <= games <= MAX_BATCH_GAMES:
        raise ValueError(f'games must be 1..{MAX_BATCH_GAMES}')
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    if agent_mode not in ('baseline', 'tactical', 'strategic', 'planning'):
        raise ValueError('agent_mode must be baseline, tactical, strategic or planning')
    verify_engine_compatibility()
    left_e, right_e = tuple(energy_left), tuple(energy_right)
    validate_deck(left, left_e)
    validate_deck(right, right_e)
    if len(left_e) != 1 or len(right_e) != 1:
        raise UnsupportedEffect('Multicolor Energy Zone is unsupported')

    left_identity = describe_compiled(left, left_e, left_payload, fallback_name='Meu deck')
    right_identity = describe_compiled(right, right_e, right_payload, fallback_name='Adversário')
    matchup = compare_decks(left_identity, right_identity)

    counts = Counter()
    splits = {'left_first': Counter(), 'right_first': Counter()}
    seat_splits = {'left_as_p0': Counter(), 'left_as_p1': Counter()}
    errors = []
    rounds = []
    total_actions = 0
    total_turns = 0
    replay = None
    agent = {'baseline':RuleAgent,'tactical':TacticalAgent,'strategic':StrategicAgentV097,'planning':PlanningAgentV099}[agent_mode](line_map or {})
    telemetry = new_telemetry()
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
            rounds.append({
                'round': idx + 1, 'seed': seed + idx,
                'p0_deck': left_identity['signature'] if not reverse else right_identity['signature'],
                'p1_deck': right_identity['signature'] if not reverse else left_identity['signature'],
                'first_player': first_side, 'winner': battle.winner,
                'outcome': outcome, 'half_turns': battle.turn,
            })
            total_actions += battle.checked_actions
            total_turns += battle.turn
            merge_telemetry(telemetry, count_logged_actions(battle.log), reverse)
            if keep_replay and idx == 0:
                replay = {
                    'seed': seed, 'round': idx + 1, 'winner': battle.winner,
                    'agent_mode': agent_mode,
                    'first_player': battle.first, 'turns': battle.turn,
                    'events': list(battle.log), 'snapshots': battle.trace,
                    'energy_p0': list(ea), 'energy_p1': list(eb),
                    'p0_deck': left_identity if not reverse else right_identity,
                    'p1_deck': right_identity if not reverse else left_identity,
                    'left_deck': left_identity, 'right_deck': right_identity,
                    'note': 'Technical prototype replay, not a certified real-game match.'
                }
        except (RuleError, ValueError, IndexError, AssertionError, TypeError) as ex:
            errors.append({'round': idx + 1, 'seed': seed + idx,
                           'type': type(ex).__name__, 'message': str(ex),
                           'p0_deck': left_identity['signature'] if not reverse else right_identity['signature'],
                           'p1_deck': right_identity['signature'] if not reverse else left_identity['signature'],
                           'first_player': first_side,
                           'events': battle.log[-25:] if battle else []})
            if isinstance(ex, TypeError) or len(errors) >= 10:
                # TypeErrors indicate an implementation/schema mismatch, not a loss.
                # Do not fabricate further wins/losses or repeat a broken round.
                break
        if progress and ((idx + 1) % 25 == 0 or idx + 1 == games):
            progress(idx + 1, games)
    valid = sum(counts.values())
    attempted = valid + len(errors)
    return {
        'kind': 'technical_prototype_batch',
        'version': '0.9.0',
        'agent_mode': agent_mode,
        'decks': {'left': left_identity, 'right': right_identity},
        'matchup': matchup,
        'rounds': rounds,
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
        'telemetry': serialize_telemetry(telemetry),
        'duration_distribution': duration_distribution(rounds),
        'seed': seed, 'errors': errors, 'sample_replay': replay,
        'elapsed_seconds': round(monotonic()-start_time, 3),
    }


def compare_policies(left: list[Card], right: list[Card],
                     energy_left=('psychic',), energy_right=('darkness',),
                     line_map: dict[str,str] | None = None,
                     games: int = 100, seed: int = 20261116,
                     left_payload: dict | None = None,
                     right_payload: dict | None = None) -> dict:
    """A/B diagnostic on the same deck lists and initial seeds, NOT a causal test.

    Both opponents use the same policy within each run; AI moves alter the
    subsequent RNG consumption, so trajectories are *not* matched outcomes.
    Compare telemetry and failure counts, never treat outcome deltas as skill.
    """
    opts = dict(energy_left=energy_left, energy_right=energy_right,
                line_map=line_map, games=games, seed=seed,
                left_payload=left_payload, right_payload=right_payload,
                keep_replay=False)
    baseline = run_technical_batch(left, right, agent_mode='baseline', **opts)
    tactical = run_technical_batch(left, right, agent_mode='tactical', **opts)
    return {
        'kind': 'technical_policy_comparison', 'version': '0.9.0',
        'validated_competitive': False,
        'disclaimer': ('Comparação de comportamento, não medição causal de força: '
                       'as jogadas alteram a trajetória aleatória subsequente.'),
        'games_per_policy': games, 'seed': seed,
        'decks': baseline['decks'], 'matchup': baseline['matchup'],
        'policies': {
            mode: {
                'completed': r['completed'], 'failed': r['failed'],
                'outcomes': r['outcomes'], 'average_half_turns': r['average_half_turns'],
                'telemetry': r['telemetry'], 'duration_distribution':r['duration_distribution'],
                'errors':r['errors'],
            } for mode,r in [('baseline',baseline),('tactical',tactical)]
        },
    }
