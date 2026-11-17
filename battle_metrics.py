"""Explainable event counters for the audited 0.9 technical simulator.

Only aggregate actual, logged actions. A line without a matching event is never
silently interpreted as a move; the log protocol may be expanded in future.
"""
from __future__ import annotations
from collections import Counter
import re

ATTACK = re.compile(r'^P([01]) (.+?) uses (.+?), (\d+) damage')
DIVING = re.compile(r'^P([01]) (.+?) Diving Icicles: discards')
TRAINER = re.compile(r'^P([01]) plays (.+)$')
ENERGY = re.compile(r'^P([01]) ([^:]+): \+1 (grass|fire|water|lightning|psychic|fighting|darkness|metal|colorless) to ')
TURN = re.compile(r'^Turn \d+, P([01])$')
EVOLUTION = re.compile(r'^P([01]) (?:evolves |Rare Candy:)')
KO = re.compile(r'^P[01] (?:Active|Bench|bench)?\s?KO .+; P([01]) score (\d+)$')


def count_logged_actions(events: list[str]) -> dict[int, dict]:
    stats = {0: Counter(), 1: Counter()}
    attacks = {0: Counter(), 1: Counter()}
    trainers = {0: Counter(), 1: Counter()}
    attacks_by_pokemon={0:Counter(),1:Counter()}
    damage_by_pokemon={0:Counter(),1:Counter()}
    damage_by_attack={0:Counter(),1:Counter()}
    last_turn_owner = None
    last_turn_attacked = False
    last_score = {0:0,1:0}

    def finish_turn():
        if last_turn_owner is not None and not last_turn_attacked:
            stats[last_turn_owner]['turns_without_attack'] += 1

    for event in events:
        match = TURN.match(event)
        if match:
            finish_turn()
            last_turn_owner = int(match.group(1))
            last_turn_attacked = False
            stats[last_turn_owner]['turns'] += 1
            continue
        match = ATTACK.match(event)
        if match:
            side, pokemon, name, damage = match.groups()
            side = int(side)
            stats[side]['attacks'] += 1
            attacks[side][name] += 1
            attacks_by_pokemon[side][pokemon] += 1
            # This is the logged attack amount, not net effective damage: KO
            # overkill, Bench effects and damage prevention are not inferred.
            damage_by_pokemon[side][pokemon] += int(damage)
            damage_by_attack[side][name] += int(damage)
            last_turn_attacked = True
            continue
        match = DIVING.match(event)
        if match:
            side,pokemon=int(match.group(1)),match.group(2)
            stats[side]['attacks'] += 1
            attacks[side]['Diving Icicles'] += 1
            attacks_by_pokemon[side][pokemon] += 1
            # Attack damage is targeted and may be prevented; do not infer
            # actual effective damage from this discarding log.
            last_turn_attacked=True
            continue
        match = TRAINER.match(event)
        if match:
            side = int(match.group(1))
            stats[side]['trainers'] += 1
            trainers[side][match.group(2)] += 1
            continue
        match = ENERGY.match(event)
        if match:
            side, source, _energy = match.groups()
            stats[int(side)]['energy_attached'] += 1
            if source == 'manual energy':
                stats[int(side)]['manual_energy'] += 1
            else:
                stats[int(side)]['effect_energy'] += 1
            continue
        match = EVOLUTION.match(event)
        if match:
            side = int(match.group(1))
            stats[side]['evolutions'] += 1
            if 'Rare Candy:' in event:
                stats[side]['rare_candy'] += 1
            continue
        if event.startswith('Greninja — Water Shuriken:'):
            target = re.search(r'to P([01])', event)
            if target:
                stats[1-int(target.group(1))]['water_shuriken'] += 1
            continue
        if 'Darkrai ex — Nightmare Aura:' in event:
            target = re.search(r'to P([01])', event)
            if target:
                stats[1-int(target.group(1))]['nightmare_aura'] += 1
            continue
        if event.startswith('Deceptive Needle:'):
            target = re.search(r'to P([01])', event)
            if target:
                stats[1-int(target.group(1))]['deceptive_needle'] += 1
            continue
        match = KO.match(event)
        if match:
            side, score = int(match.group(1)), int(match.group(2))
            stats[side]['knockouts'] += 1
            stats[side]['points_scored'] += max(0,score-last_score[side])
            last_score[side]=score
            continue
        if event.startswith(('P0 retreats into ', 'P1 retreats into ')):
            stats[int(event[1])]['retreats'] += 1
            continue
        if ' switches P' in event and event.startswith(('P0 ', 'P1 ')):
            stats[int(event[1])]['switch_effects'] += 1
            continue
    finish_turn()
    return {side: {
        'counts': dict(stats[side]),
        'attacks_by_name': dict(attacks[side]),
        'trainers_by_name': dict(trainers[side]),
        'attacks_by_pokemon': dict(attacks_by_pokemon[side]),
        'reported_damage_by_pokemon': dict(damage_by_pokemon[side]),
        'reported_damage_by_attack': dict(damage_by_attack[side]),
    } for side in (0, 1)}


def merge_telemetry(accumulator: dict, game_stats: dict[int, dict], reverse: bool) -> None:
    for named_side in ('left', 'right'):
        player = (1 if reverse else 0) if named_side == 'left' else (0 if reverse else 1)
        src = game_stats[player]
        for field in ('counts', 'attacks_by_name', 'trainers_by_name', 'attacks_by_pokemon', 'reported_damage_by_pokemon', 'reported_damage_by_attack'):
            accumulator[named_side][field].update(src[field])


def new_telemetry() -> dict:
    return {side:{k:Counter() for k in ('counts','attacks_by_name','trainers_by_name','attacks_by_pokemon','reported_damage_by_pokemon','reported_damage_by_attack')}
            for side in ('left','right')}


def serialize_telemetry(data: dict) -> dict:
    return {side:{field:dict(values) for field,values in parts.items()}
            for side,parts in data.items()}


def duration_distribution(rounds: list[dict]) -> dict[str, int]:
    bins = Counter()
    for r in rounds:
        n = r['half_turns']
        group = ('1–5' if n <= 5 else '6–10' if n <= 10 else
                 '11–15' if n <= 15 else '16–20' if n <= 20 else '21+')
        bins[group] += 1
    return {name: bins[name] for name in ('1–5','6–10','11–15','16–20','21+')}
