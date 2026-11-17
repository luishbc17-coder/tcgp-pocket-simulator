"""Replay one exact recorded v0.9.5 matrix round with an audited trace.

Never invents intermediate states from the summary. Re-executes from the
recorded seed and original seating and compares the recorded outcome.
"""
from __future__ import annotations
from battle_audit import AuditedBattle
from batch_runner import verify_engine_compatibility
from battle_engine import RuleAgent
from tactical_agent import TacticalAgent
from strategic_agent import StrategicAgent
from matchup_compatibility import load_compiled_deck
from gameplay_catalog import evolution_line_map
from deck_identity import describe_selection


def replay_matrix_round(report:dict, presets:dict[str,dict],
                        gameplay:list[dict], left_slug:str, right_slug:str,
                        round_number:int) -> dict:
    if not isinstance(report,dict) or report.get('kind')!='technical_meta_matrix':
        raise ValueError('Relatório não é uma matriz técnica')
    if type(round_number) is not int:
        raise ValueError('Número da rodada inválido')
    pair=next((x for x in report['pairs']
               if (x['left_slug'],x['right_slug'])==(left_slug,right_slug)),None)
    if pair is None or pair['status']!='completed':
        raise ValueError('Confronto não concluído ou inexistente no relatório')
    row=next((r for r in pair['rounds'] if r['round']==round_number),None)
    if row is None:
        raise ValueError('Rodada não encontrada no relatório')
    if left_slug not in presets or right_slug not in presets:
        raise ValueError('Deck original não disponível')
    left=presets[left_slug];right=presets[right_slug]
    lid=describe_selection(left,left.get('name',left_slug))['signature']
    rid=describe_selection(right,right.get('name',right_slug))['signature']
    if pair['left_signature']!=lid or pair['right_signature']!=rid:
        raise ValueError('O deck mudou desde a simulação original')
    a,b=(left,right) if row['p0_deck']==lid else (right,left)
    if row['p0_deck'] not in (lid,rid) or row['p1_deck'] != (rid if row['p0_deck']==lid else lid):
        raise ValueError('Assentos e assinaturas do relatório não correspondem')
    mode=report['agent_mode']
    if mode not in ('baseline','tactical','strategic'):
        raise ValueError('Política do relatório não suportada')
    verify_engine_compatibility()
    battle=AuditedBattle(load_compiled_deck(a,gameplay),load_compiled_deck(b,gameplay),
                         tuple(a['energy_types']),tuple(b['energy_types']),
                         seed=row['seed'],force_first=row['first_player'],
                         collect_trace=True)
    agent={'baseline':RuleAgent,'tactical':TacticalAgent,'strategic':StrategicAgent}[mode](evolution_line_map(gameplay))
    while not battle.finished:
        agent.play_turn(battle)
    left_side=0 if row['p0_deck']==lid else 1
    outcome=('draw' if battle.winner is None else
             'left' if battle.winner==left_side else 'right')
    matched=(outcome==row['outcome'] and battle.winner==row['winner']
             and battle.turn==row['half_turns'])
    return {'kind':'technical_matrix_round_replay','version':'0.9.5',
            'validated_competitive':False,'left':pair['left_name'],
            'right':pair['right_name'],'round':round_number,'seed':row['seed'],
            'agent_mode':mode,'original':{'outcome':row['outcome'],
                'winner':row['winner'],'half_turns':row['half_turns']},
            'replayed':{'outcome':outcome,'winner':battle.winner,
                'half_turns':battle.turn},
            'matches_record':matched,
            'checked_actions':battle.checked_actions,
            'energy_p0':list(a['energy_types']),'energy_p1':list(b['energy_types']),
            'events':list(battle.log),'snapshots':battle.trace}
