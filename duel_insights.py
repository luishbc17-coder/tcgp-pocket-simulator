"""Observed, normalized duel diagnostics. No attribution of causal strength.

Reports maintain separation between observed events and unobserved intent,
and do not mistake gross attack-log damage for net effective damage.
"""
from __future__ import annotations


def duel_efficiency(telemetry: dict) -> dict:
    result={}
    for side in ('left','right'):
        row=telemetry[side]
        counts=row['counts']
        attacks=int(counts.get('attacks',0))
        turns=int(counts.get('turns',0))
        points=int(counts.get('points_scored',0))
        kos=int(counts.get('knockouts',0))
        dmg=sum(row.get('reported_damage_by_pokemon',{}).values())
        def div(n,den):
            return round(100*n/den,2) if den else None
        attackers=[]
        for mon,n in sorted(row.get('attacks_by_pokemon',{}).items(),
                            key=lambda item:(-item[1],item[0])):
            gross=row.get('reported_damage_by_pokemon',{}).get(mon,0)
            attackers.append({'pokemon':mon,'attacks':n,'reported_damage':gross,
                              'reported_damage_per_attack':round(gross/n,2) if n else None})
        result[side]={
            'turns':turns,'attacks':attacks,'knockouts':kos,'points':points,
            'gross_reported_attack_damage':dmg,
            'attack_turn_pct':div(attacks,turns),
            'turns_without_attack_pct':div(counts.get('turns_without_attack',0),turns),
            'knockouts_per_100_attacks':div(kos,attacks),
            'points_per_100_attacks':div(points,attacks),
            'energy_per_100_turns':div(counts.get('energy_attached',0),turns),
            'gross_damage_per_attack':round(dmg/attacks,2) if attacks else None,
            'attackers':attackers,
        }
    return {'a':result['left'],'b':result['right'],
      'limitations':[
        'Dano do log é nominal; inclui excesso sobre HP, pode omitir danos de ataques direcionados e não prova dano efetivo.',
        'Nocautes e pontos foram contabilizados por jogador, não atribuídos a uma carta específica.',
        'Confronto espelhado compara políticas somente dentro do motor parcial.',
        'Sementes iguais não asseguram distribuição idêntica de aleatoriedade após ações diferentes.',
      ]}
