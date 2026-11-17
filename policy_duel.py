"""Direct, seat-balanced head-to-head comparison of two AI policies (v0.9.6).

Both agents pilot the *same* verified 20-card deck, isolating deck choice.
First player and seating alternate across blocks of four rounds. This tests
performance *inside this prototype only*, not against human players.
"""
from __future__ import annotations
from collections import Counter
from typing import Callable
from time import monotonic

from battle_audit import AuditedBattle
from battle_engine import Card, RuleAgent, RuleError, UnsupportedEffect, validate_deck
from batch_runner import verify_engine_compatibility
from tactical_agent import TacticalAgent
from strategic_agent import StrategicAgent
from battle_metrics import count_logged_actions, new_telemetry, serialize_telemetry
from matrix_insights import score_interval

POLICIES = {'baseline':RuleAgent, 'tactical':TacticalAgent, 'strategic':StrategicAgent}
MAX_HEAD_TO_HEAD_GAMES = 400


def duel_policies(cards: list[Card], energy_types: tuple[str,...],
                  line_map: dict[str,str] | None = None,
                  policy_a: str = 'tactical',policy_b: str = 'strategic',
                  games: int = 100, seed: int = 20261116,
                  progress: Callable[[int,int],None] | None = None,
                  keep_replay: bool = False) -> dict:
    if policy_a not in POLICIES or policy_b not in POLICIES or policy_a == policy_b:
        raise ValueError('Escolha duas políticas de IA diferentes e reconhecidas')
    if type(games) is not int or not 4 <= games <= MAX_HEAD_TO_HEAD_GAMES or games % 4:
        raise ValueError('Use um número de partidas múltiplo de 4 entre 4 e 400')
    if type(seed) is not int or seed < 0:
        raise ValueError('Semente deve ser um inteiro não negativo')
    energy_types=tuple(energy_types)
    validate_deck(cards,energy_types)
    if len(energy_types)!=1:
        raise UnsupportedEffect('Zona de Energia multicolorida ainda não implementada')
    verify_engine_compatibility()
    rounds=[];errors=[];wins=Counter();sides={'a_first':Counter(),'b_first':Counter()}
    seating={'a_p0':Counter(),'a_p1':Counter()}
    telemetry=new_telemetry(); trace=None;total_checked=0;total_turns=0
    started=monotonic()
    for idx in range(games):
        # Four equally frequent combinations: A-P0 first, A-P0 second,
        # A-P1 first, A-P1 second. Independent per-game RNG seed.
        a_side = 0 if (idx % 4)<2 else 1
        first = a_side if idx%2==0 else 1-a_side
        agents=(POLICIES[policy_a](line_map or {}),POLICIES[policy_b](line_map or {}))
        battle=None
        try:
            battle=AuditedBattle(cards,cards,energy_types,energy_types,
                                 seed=seed+idx,force_first=first,
                                 collect_trace=keep_replay and idx==0)
            while not battle.finished:
                agents[0 if battle.current==a_side else 1].play_turn(battle)
            outcome='draw' if battle.winner is None else 'a' if battle.winner==a_side else 'b'
            wins[outcome]+=1
            sides['a_first' if first==a_side else 'b_first'][outcome]+=1
            seating['a_p0' if a_side==0 else 'a_p1'][outcome]+=1
            total_checked+=battle.checked_actions;total_turns+=battle.turn
            stats=count_logged_actions(battle.log)
            for key,side in [('left',a_side),('right',1-a_side)]:
                telemetry[key]['counts'].update(stats[side]['counts'])
                telemetry[key]['attacks_by_name'].update(stats[side]['attacks_by_name'])
                telemetry[key]['trainers_by_name'].update(stats[side]['trainers_by_name'])
            rounds.append({'round':idx+1,'seed':seed+idx,'a_side':a_side,
                           'first_player':first,'winner':battle.winner,
                           'outcome':outcome,'half_turns':battle.turn})
            if keep_replay and idx==0:
                trace={'seed':seed,'events':list(battle.log),'snapshots':battle.trace,
                       'a_side':a_side,'first_player':first,'winner':battle.winner}
        except (RuleError,ValueError,IndexError,AssertionError,TypeError,AttributeError,RuntimeError) as ex:
            errors.append({'round':idx+1,'seed':seed+idx,'type':type(ex).__name__,
                           'message':str(ex)[:400],
                           'recent_events':battle.log[-10:] if battle else []})
            break  # Never turn a failed round into a loss or extrapolate wins.
        if progress and ((idx+1)%25==0 or idx+1==games):
            progress(idx+1,games)
    completed=sum(wins.values());complete=completed==games and not errors
    ci=score_interval(wins['a'],wins['b'],wins['draw']) if complete else None
    return {'kind':'technical_policy_duel','version':'0.9.6','validated_competitive':False,
            'disclaimer':'Benchmark de políticas heurísticas com baralho espelhado, não prova de força contra humanos ou no meta.',
            'policy_a':policy_a,'policy_b':policy_b,'seed':seed,
            'configured':games,'completed':completed,'failed':len(errors),'errors':errors,
            'outcomes':{key:wins[key] for key in ('a','b','draw')},
            'a_score_interval':ci,
            'first_player_splits':{label:{key:count[key] for key in ('a','b','draw')}
                                   for label,count in sides.items()},
            'seating_splits':{label:{key:count[key] for key in ('a','b','draw')}
                             for label,count in seating.items()},
            'rounds':rounds,'checked_actions':total_checked,
            'average_half_turns':round(total_turns/completed,2) if completed else None,
            'telemetry':serialize_telemetry(telemetry),
            'sample_replay':trace,'elapsed_seconds':round(monotonic()-started,3)}
