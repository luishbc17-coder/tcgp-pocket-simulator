"""State validation and reproducible traces for TCG Pocket Lab v0.8.3.1.

These checks test internal consistency. They are NOT a certification that the
rules match Pokemon TCG Pocket or that a strategic policy is competitive.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from battle_engine import Battle, InPlay, MAX_TURNS, RuleError


class StateInvariantError(RuleError):
    pass


def inspect_state(game: Battle) -> list[str]:
    """Return contradictions visible in the current game state."""
    issues = []
    if len(game.players) != 2 or game.current not in (0, 1) or game.first not in (0, 1):
        issues.append('Player/first/current indices out of range')
        return issues
    if not (0 <= game.turn <= MAX_TURNS):
        issues.append(f'Invalid turn number {game.turn}')
    if game.winner not in (None, 0, 1):
        issues.append(f'Invalid winner {game.winner}')
    if not game.finished and game.winner is not None:
        issues.append('Winner declared before game completion')
    # A tie can occur before the turn cap when both sides satisfy win conditions.
    seen = set()
    for i, player in enumerate(game.players):
        if not (0 <= len(player.bench) <= 3):
            issues.append(f'P{i} bench exceeds 3 or is invalid')
        if len(player.hand) > 10:
            issues.append(f'P{i} hand exceeds 10')
        if player.points < 0:
            issues.append(f'P{i} points negative')
        if player.turns_taken < 0:
            issues.append(f'P{i} turns_taken negative')
        if player.active is None and not game.finished:
            issues.append(f'P{i} has no Active before game end')
        for pokemon in player.all_in_play():
            ident = id(pokemon)
            if ident in seen:
                issues.append(f'P{i} same in-play object in multiple slots')
            seen.add(ident)
            if pokemon.card.kind != 'pokemon' or pokemon.card.hp <= 0:
                issues.append(f'P{i} invalid Pokemon in play')
            if pokemon.damage < 0:
                issues.append(f'P{i} negative damage on {pokemon.card.name}')
            if pokemon.damage >= pokemon.max_hp:
                issues.append(f'P{i} KO Pokemon remained in play: {pokemon.card.name}')
            if pokemon.card.stage not in (0,1,2):
                issues.append(f'P{i} invalid stage on {pokemon.card.name}')
            if pokemon.tool is not None and pokemon.tool.kind != 'tool':
                issues.append(f'P{i} non-tool attached as tool')
            if pokemon.status not in ('', 'asleep'):
                issues.append(f'P{i} unknown status on {pokemon.card.name}')
            if pokemon.entered_at > game.turn or pokemon.evolved_at > game.turn:
                issues.append(f'P{i} future evolution/entry timestamp')
            if any(e not in ('grass','fire','water','lightning','psychic','fighting','darkness','metal','colorless')
                   for e in pokemon.energy):
                issues.append(f'P{i} invalid energy attached')
        if not game.finished and player.points >= 3:
            issues.append(f'P{i} reached 3 points without end')
    if game.finished and game.winner is not None:
        loser = game.players[1 - game.winner]
        winner = game.players[game.winner]
        if winner.points < 3 and loser.active is not None:
            issues.append('Winner lacks 3 points and opponent still has Active')
    return issues


def assert_state(game: Battle, context='') -> None:
    errors = inspect_state(game)
    if errors:
        raise StateInvariantError(f'{context}: ' + '; '.join(errors))


def snapshot(game: Battle, action: str) -> dict:
    def pokemon_state(p: InPlay | None):
        if p is None:
            return None
        return {
            'id': p.card.id, 'name': p.card.name, 'tags': list(p.card.tags),
            'pre_evolutions': [c.name for c in p.pre_evolutions],
            'max_hp': p.max_hp, 'damage': p.damage,
            'hp_remaining': p.max_hp - p.damage,
            'energy': list(p.energy), 'status': p.status,
            'tool': p.tool.name if p.tool else None,
            'mirror_shot_pending': p.mirror_shot_pending,
            'entered_at': p.entered_at, 'evolved_at': p.evolved_at,
        }
    return {
        'action': action, 'half_turn': game.turn, 'active_player': game.current,
        'first_player': game.first, 'in_turn': game._in_turn,
        'finished': game.finished, 'winner': game.winner,
        'stadium': game.stadium.name if game.stadium else None,
        'players': [{
            'points': p.points, 'turns_taken': p.turns_taken,
            'hand_count': len(p.hand), 'deck_count': len(p.deck),
            'discarded_energy': dict(p.energy_discard),
            'active': pokemon_state(p.active),
            'bench': [pokemon_state(c) for c in p.bench],
        } for p in game.players],
    }


class AuditedBattle(Battle):
    """Check core invariants after each public action, optionally store snapshots."""
    AUDIT_ACTIONS = (
        'begin_turn', 'bench_basic', 'evolve', 'rare_candy', 'attach',
        'use_ability', 'equip_tool', 'play_stadium', 'use_stadium', 'play_trainer', 'retreat', 'attack', 'end_turn'
    )

    def __init__(self, *args, collect_trace=False, **kwargs):
        try:
            super().__init__(*args, **kwargs)
        except TypeError as exc:
            # The 0.8.3 deployment exposed a raw TypeError here when an older
            # battle_engine module was imported alongside the new batch runner.
            raise RuleError(
                'Erro de compatibilidade na inicialização da partida. '
                'Verifique se battle_engine.py está atualizado; reinicie o '
                'app no Streamlit Cloud. Causa: '
                f'{type(exc).__name__}: {exc}'
            ) from exc
        self.trace = [] if collect_trace else None
        self.checked_actions = 0
        self._audit_action('setup')

    def _audit_action(self, name):
        assert_state(self, name)
        self.checked_actions += 1
        if self.trace is not None:
            self.trace.append(snapshot(self, name))


def _add_audit_wrappers():
    # Each entry point delegates to the original implementation and checks the
    # complete public-action boundary. The original Battle remains unmodified.
    for name in AuditedBattle.AUDIT_ACTIONS:
        original = getattr(Battle, name)
        def wrapped(self, *args, _action=name, _base=original, **kwargs):
            result = _base(self, *args, **kwargs)
            self._audit_action(_action)
            return result
        wrapped.__name__ = name
        setattr(AuditedBattle, name, wrapped)

_add_audit_wrappers()
