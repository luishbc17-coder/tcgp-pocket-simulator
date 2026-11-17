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
from strategic_agent import StrategicAgent, StrategicAgentV097
from planning_agent import PlanningAgentV098, PlanningAgentV099, PlanningAgentV0910
from battle_metrics import count_logged_actions, new_telemetry, serialize_telemetry
from matrix_insights import score_interval
from duel_insights import duel_efficiency

POLICIES = {'baseline':RuleAgent, 'tactical':TacticalAgent,
            'strategic':StrategicAgentV097, 'strategic_v096':StrategicAgent, 'planning':PlanningAgentV0910, 'planning_v099':PlanningAgentV099, 'planning_v098':PlanningAgentV098}
MAX_HEAD_TO_HEAD_GAMES = 400


def duel_policies(cards: list[Card], energy_types: tuple[str,...],
                  line_map: dict[str,str] | None = None,
                  policy_a: str = 'tactical',policy_b: str = 'strategic',
                  games: int = 100, seed: int = 20261116,
                  progress: Callable[[int,int],None] | None = None,
                  keep_replay: bool = False, benchmark_split: str = 'development',
                  deck_name: str | None = None) -> dict:
    if policy_a not in POLICIES or policy_b not in POLICIES or policy_a == policy_b:
        raise ValueError('Escolha duas políticas de IA diferentes e reconhecidas')
    if type(games) is not int or not 4 <= games <= MAX_HEAD_TO_HEAD_GAMES or games % 4:
        raise ValueError('Use um número de partidas múltiplo de 4 entre 4 e 400')
    if type(seed) is not int or seed < 0:
        raise ValueError('Semente deve ser um inteiro não negativo')
    if deck_name is not None and (not isinstance(deck_name,str) or not deck_name.strip()):
        raise ValueError('Nome do deck deve ser texto não vazio')
    if benchmark_split not in ('development', 'holdout'):
        raise ValueError('Conjunto de teste deve ser development ou holdout')
    effective_seed = seed + (10000000 if benchmark_split == 'holdout' else 0)
    energy_types=tuple(energy_types)
    validate_deck(cards,energy_types)
    if len(energy_types)!=1:
        raise UnsupportedEffect('Zona de Energia multicolorida ainda não implementada')
    verify_engine_compatibility()
    rounds=[];errors=[];wins=Counter();sides={'a_first':Counter(),'b_first':Counter()}
    seating={'a_p0':Counter(),'a_p1':Counter()}
    telemetry=new_telemetry(); trace=None;total_checked=0;total_turns=0
    decision_counts = {'a':Counter(),'b':Counter()}
    decision_samples=[]
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
                                 seed=effective_seed+idx,force_first=first,
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
                for field in ('attacks_by_pokemon','reported_damage_by_pokemon','reported_damage_by_attack'):
                    telemetry[key][field].update(stats[side][field])
            # Structured decisions contain only own-public and public-board facts.
            for label, agent in zip(('a','b'),agents):
                notes = getattr(agent, 'decision_records', [])
                decision_counts[label].update(row['decision'] for row in notes)
                if idx < 4:  # bounded examples; do not multiply JSON size by games
                    decision_samples.extend({'round':idx+1,'policy':label,**row}
                                            for row in notes[:12])
            # The unmodified reference agents expose no internal decision
            # scores. Preserve observed logs symmetrically, without inventing
            # a score or intention for those policies.
            if idx < 4:
                for event in battle.log:
                    if len(decision_samples) >= 80: break
                    if event.startswith(('P0 ','P1 ')) and (' uses ' in event or
                           ' retreats into ' in event or 'manual energy:' in event):
                        side=int(event[1]); label='a' if side==a_side else 'b'
                        if not getattr(agents[0 if label=='a' else 1], 'decision_records',None):
                            decision_samples.append({'round':idx+1,'policy':label,
                               'decision':'observed_action','observed_event':event,
                               'reason':'A política não expõe pontuação interna nesta versão'})
            rounds.append({'round':idx+1,'seed':effective_seed+idx,'a_side':a_side,
                           'first_player':first,'winner':battle.winner,
                           'outcome':outcome,'half_turns':battle.turn})
            if keep_replay and idx==0:
                trace={'seed':effective_seed,'events':list(battle.log),'snapshots':battle.trace,
                       'decision_records':{'a':getattr(agents[0],'decision_records',[]),
                                           'b':getattr(agents[1],'decision_records',[])},
                       'a_side':a_side,'first_player':first,'winner':battle.winner}
        except (RuleError,ValueError,IndexError,AssertionError,TypeError,AttributeError,RuntimeError) as ex:
            errors.append({'round':idx+1,'seed':effective_seed+idx,'type':type(ex).__name__,
                           'message':str(ex)[:400],
                           'recent_events':battle.log[-10:] if battle else []})
            break  # Never turn a failed round into a loss or extrapolate wins.
        if progress and ((idx+1)%25==0 or idx+1==games):
            progress(idx+1,games)
    completed=sum(wins.values());complete=completed==games and not errors
    ci=score_interval(wins['a'],wins['b'],wins['draw']) if complete else None
    scenario_intervals = {key:score_interval(value['a'],value['b'],value['draw'])
                          for key,value in sides.items()} if complete else None
    return {'kind':'technical_policy_duel','version':'0.9.10','validated_competitive':False,
            'disclaimer':'Benchmark de políticas heurísticas com baralho espelhado, não prova de força contra humanos ou no meta.',
            'policy_a':policy_a,'policy_b':policy_b,'seed':seed,
            'deck_name':deck_name or 'Baralho espelhado (nome não informado)',
            'effective_seed': effective_seed, 'benchmark_split':benchmark_split,
            'seed_note':'Conjuntos development e holdout usam faixas de sementes sem sobreposição; sementes iguais não garantem estados RNG idênticos após decisões distintas.',
            'configured':games,'completed':completed,'failed':len(errors),'errors':errors,
            'outcomes':{key:wins[key] for key in ('a','b','draw')},
            'a_score_interval':ci, 'scenario_intervals':scenario_intervals,
            'first_player_splits':{label:{key:count[key] for key in ('a','b','draw')}
                                   for label,count in sides.items()},
            'seating_splits':{label:{key:count[key] for key in ('a','b','draw')}
                             for label,count in seating.items()},
            'rounds':rounds,'checked_actions':total_checked,
            'average_half_turns':round(total_turns/completed,2) if completed else None,
            'telemetry':serialize_telemetry(telemetry),
            'efficiency':duel_efficiency(serialize_telemetry(telemetry)),
            'attacker_efficiency_note':'Dano reportado é nominal do evento de ataque; não equivale necessariamente a dano efetivo, e nocautes/pontos não são atribuídos individualmente a Pokémon.',
            'decision_audit':{'coverage':{
                     'a':'structured' if hasattr(POLICIES[policy_a], '_note') else 'observed_only',
                     'b':'structured' if hasattr(POLICIES[policy_b], '_note') else 'observed_only'},
                     'counts':{k:dict(v) for k,v in decision_counts.items()},
                              'examples':decision_samples[:80]},
            'second_player_advantage':{
                'a_second':{k:sides['b_first'][k] for k in ('a','b','draw')},
                'b_second':{k:sides['a_first'][k] for k in ('a','b','draw')}},
            'sample_replay':trace,'elapsed_seconds':round(monotonic()-started,3)}
