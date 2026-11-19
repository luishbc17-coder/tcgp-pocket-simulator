"""Batch-evaluate off-meta candidates fairly against the SAME eligible field.

No rankings are issued when the comparisons have different eligible opponents,
missing games, or zero real simulation coverage. Source Limitless statistics are
never used as simulated outcomes.
"""
from __future__ import annotations
from copy import deepcopy
from matchup_compatibility import inspect_deck
from meta_gauntlet import build_gauntlet_plan, run_meta_gauntlet
from limitless_meta import default_snapshot, validate_snapshot, evaluate_reference_coverage

MAX_CANDIDATES = 5
MAX_CANDIDATE_GAMES = 1200


def evaluate_candidate_field(candidates: list[dict], opponents: dict[str,dict],
                             core: list[dict], gameplay: list[dict],
                             games_per_opponent: int = 40, seed: int = 77531041,
                             snapshot: dict | None = None) -> dict:
    if not isinstance(candidates,list) or not 1<=len(candidates)<=MAX_CANDIDATES:
        raise ValueError('Selecione de 1 a 5 candidatas.')
    if type(games_per_opponent) is not int or not 1<=games_per_opponent<=100:
        raise ValueError('Máximo de 100 partidas por adversário nesta avaliação.')
    if type(seed) is not int or not 0<=seed<=2_000_000_000:
        raise ValueError('Semente inválida.')
    if not isinstance(opponents,dict) or not opponents or len(opponents)>15:
        raise ValueError('Informe de 1 a 15 adversários.')
    snapshot=validate_snapshot(snapshot or default_snapshot())
    if len(candidates)*len(opponents)*games_per_opponent>MAX_CANDIDATE_GAMES:
        raise ValueError(f'O lote excede {MAX_CANDIDATE_GAMES} partidas possíveis.')
    rows=[]
    seen_signatures=set()
    for i,candidate in enumerate(candidates):
        if not isinstance(candidate,dict) or not isinstance(candidate.get('deck'),dict):
            raise ValueError('Candidata inválida.')
        deck=candidate['deck']
        cards=deck.get('cards',{})
        signature=(tuple(sorted(cards.items())),tuple(deck.get('energy_types',[])))
        if signature in seen_signatures:
            raise ValueError('Candidatas com composições idênticas não podem ser contadas duas vezes.')
        seen_signatures.add(signature)
        inspection=inspect_deck(deck,core,gameplay)
        blocker=deck.get('simulation_blocked_reason')
        if blocker or not inspection['technical_demo_ready']:
            rows.append({'candidate_id':candidate.get('id',f'candidate_{i+1}'),
                         'name':deck.get('name','Candidata sem nome'),
                         'status':'blocked','reason':blocker or '; '.join(inspection['issues']),
                         'completed':0,'technical_weighted_score_pct':None,
                         'covered_meta_share_pct':0.0,'rivals_completed':[],
                         'report':None,'rank':None})
            continue
        plan=build_gauntlet_plan(deck,opponents,core,gameplay)
        if not plan['ready']:
            rows.append({'candidate_id':candidate.get('id',f'candidate_{i+1}'),
                         'name':deck.get('name','Candidata sem nome'),
                         'status':'no_compatible_rivals',
                         'reason':'Nenhum adversário selecionado é simulável.',
                         'completed':0,'technical_weighted_score_pct':None,
                         'covered_meta_share_pct':0.0,'rivals_completed':[],
                         'report':None,'rank':None})
            continue
        report=run_meta_gauntlet(deck,opponents,core,gameplay,
                                 games_per_opponent=games_per_opponent,
                                 seed=seed,agent_mode='planning')
        coverage=evaluate_reference_coverage(report['results'],snapshot)
        report['limitless_reference']=coverage
        finished=sorted(r['slug'] for r in report['results'] if r['status']=='completed'
                        and r['completed']==games_per_opponent)
        rows.append({'candidate_id':candidate.get('id',f'candidate_{i+1}'),
                     'name':deck.get('name','Candidata sem nome'),
                     'status':'completed' if finished and report['failed']==0 else 'partial',
                     'reason':None,'completed':report['completed'],
                     'technical_weighted_score_pct':coverage['conditional_score_pct'],
                     'covered_meta_share_pct':coverage['completed_share_pct'],
                     'rivals_completed':finished,'report':report,'rank':None})
    eligible=[row for row in rows if row['status']=='completed'
              and row['technical_weighted_score_pct'] is not None]
    fields={tuple(row['rivals_completed']) for row in eligible}
    comparable=(len(eligible)>=2 and len(fields)==1 and all(row['completed'] ==
                 len(row['rivals_completed'])*games_per_opponent for row in eligible))
    if comparable:
        for rank,row in enumerate(sorted(eligible,key=lambda r:(-r['technical_weighted_score_pct'],r['name'])),1):
            row['rank']=rank
    return {'kind':'offmeta_candidate_gauntlet','version':'0.9.14',
            'reference':{'provider':'Play Limitless','observed_on':snapshot.get('observed_on'),
                         'source_url':snapshot['source_url']},
            'ranked':comparable,'games_per_opponent':games_per_opponent,'seed':seed,
            'candidates':rows,'total_completed':sum(r['completed'] for r in rows),
            'warnings':('Classificação apenas técnica, condicional à parte do meta coberta. '
                        'Candidatas com adversários distintos NÃO são ranqueadas. '
                        'Nenhum resultado externo é substituído por vitória simulada. '
                        'Sementes iguais não garantem estados RNG idênticos após ações divergentes.')}
