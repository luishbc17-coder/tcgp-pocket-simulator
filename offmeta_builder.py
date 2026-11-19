"""Safe, deterministic off-meta deck hypotheses built around a requested card.

Not a trained generator. Candidate construction does not claim that the chosen
energy, strategy or mechanics are competitive, or that the card is simulated.
Every output is exactly 20 cards; the battle engine separately decides readiness.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from typing import Any

GENERATOR_VERSION = '0.9.14'


def _valid_deck(cards: dict[str, int], names: dict[str, str], favourite_id: str) -> bool:
    if sum(cards.values()) != 20 or not 1 <= cards.get(favourite_id,0) <= 2:
        return False
    if any(type(n) is not int or not 1 <= n <= 2 for n in cards.values()):
        return False
    counts = Counter()
    for cid,n in cards.items():
        counts[names.get(cid,cid).casefold()] += n
    return max(counts.values(),default=0) <= 2


def _insert_favourite(cards: dict[str, int], favourite: dict, names: dict[str,str],
                      desired: int, core_index: dict) -> dict | None:
    """Replace flex trainers without dismantling existing evolution lines.

    If a tournament preset already contains another art of the same name,
    transfer its slots to the chosen ID before adding any extra copy.
    """
    result = dict(cards)
    favourite_id, label = favourite['id'], favourite['name']
    same = [cid for cid in result if names.get(cid,cid).casefold()==label.casefold() and cid!=favourite_id]
    for cid in same:
        result[favourite_id]=result.get(favourite_id,0)+result.pop(cid)
    held = result.get(favourite_id,0)
    if held > 2:
        return None
    for _ in range(max(0,desired-held)):
        flexible = [cid for cid in result if cid!=favourite_id
                    and (core_index.get(cid,{}).get('type')!='Pokémon')]
        flexible.sort(key=lambda cid:(
            cid in ('pa-005','pa-007','a3-144'),
            result[cid]>=2,
            cid))
        if not flexible:
            return None
        donor=flexible[0]
        result[donor]-=1
        if result[donor]==0: del result[donor]
        result[favourite_id]=result.get(favourite_id,0)+1
    return result if _valid_deck(result,names,favourite_id) else None


def generate_favorite_candidates(favourite_id: str, core: list[dict],
                                 presets: dict[str, dict], current: dict | None = None,
                                 max_candidates: int = 5) -> list[dict]:
    """Create reproducible *hypotheses*. No future cards, no fake winrates.

    When there is a known archetype containing the favourite, preserve its
    existing evolution line. A novel Evolution with no supporting template is
    refused instead of inventing its necessary Basic/Stage-1 cards.
    """
    if type(max_candidates) is not int or not 1 <= max_candidates <= 10:
        raise ValueError('Escolha entre 1 e 10 candidatos.')
    index={c['id']:c for c in core}
    if favourite_id not in index:
        raise ValueError('Carta favorita não encontrada no catálogo.')
    favourite=index[favourite_id]
    if favourite.get('type')!='Pokémon':
        # Trainers may be treated as favourite too, because users choose cards.
        pass
    names={cid:c['name'] for cid,c in index.items()}
    source=[]
    if current and isinstance(current.get('cards'),dict) and sum(current['cards'].values())==20:
        source.append(('personalizado',current,'Seu deck atual'))
    matching=[]
    others=[]
    for slug, raw in presets.items():
        if not isinstance(raw,dict) or not isinstance(raw.get('cards'),dict):
            continue
        row=(slug,raw,raw.get('name',slug))
        if any(names.get(cid, '').casefold()==favourite['name'].casefold() for cid in raw['cards']):
            matching.append(row)
        else:
            others.append(row)
    source.extend(matching)
    # Avoid inventing a complete evolutionary chain when the named card is
    # absent from every known list and there is no personal deck containing it.
    stage=str(favourite.get('stage') or '').lower()
    if stage not in ('basic','none','', '0') and not matching and not any(
            names.get(cid,'').casefold()==favourite['name'].casefold()
            for _,d,_ in source for cid in d['cards']):
        return []
    if stage in ('basic','none','', '0') or favourite.get('type')!='Pokémon':
        source.extend(others)
    result=[]
    seen=set()
    for slug, raw, title in source:
        if len(result)>=max_candidates:
            break
        for desired in (2,1,2,2,2):
            if len(result)>=max_candidates:
                break
            counts=_insert_favourite(raw['cards'],favourite,names,desired,index)
            if counts is None:
                continue
            # Offer distinct, legally sized flex-card options from already
            # registered supporters/items. Stage chains are never changed.
            # Rather than infer strength, use a deterministic flex order; tests
            # and later simulations decide which candidate is worth keeping.
            variation_index = (0 if desired==1 else
                               sum(1 for previous in result if previous['source_slug']==slug))
            if variation_index>=1:
                safe_pool=('pa-002','b1-225','a2-150','b2-145','a2b-070',
                           'b3-147','a3-144','b1-226','a2-155')
                donor_options=[cid for cid in sorted(counts) if cid != favourite_id
                    and index.get(cid,{}).get('type') != 'Pokémon'
                    and cid not in ('pa-005','pa-007')]
                changed=False
                for add in safe_pool[(variation_index-1)%len(safe_pool):]+safe_pool[:(variation_index-1)%len(safe_pool)]:
                    if add not in index or index[add].get('type')=='Pokémon':
                        continue
                    if sum(n for cid,n in counts.items()
                           if names.get(cid,cid).casefold()==names.get(add,add).casefold())>=2:
                        continue
                    donor=next((cid for cid in donor_options if cid!=add),None)
                    if donor is None:continue
                    counts[donor]-=1
                    if counts[donor]<=0:del counts[donor]
                    counts[add]=counts.get(add,0)+1
                    changed=True
                    break
                if not changed:
                    continue
                if not _valid_deck(counts,names,favourite_id):
                    continue
            signature=(tuple(sorted(counts.items())),tuple(raw.get('energy_types',[])))
            if signature in seen:
                continue
            seen.add(signature)
            base_count=sum(raw['cards'].values())
            if base_count!=20:
                continue
            deck={'format':'tcgp-lab-v0.9.14','name':f'{favourite["name"]} · hipótese {len(result)+1}',
                  'energy_types':list(raw.get('energy_types',[])), 'cards':counts,
                  'generated_from':slug, 'favorite_card_id':favourite_id,
                  'candidate_status':'experimental_unverified'}
            if raw.get('simulation_blocked_reason') or raw.get('release_stage') == 'catalog_only':
                deck['simulation_blocked_reason'] = (raw.get('simulation_blocked_reason') or
                    'Lista de origem ainda não homologada para simulações; consulte a compatibilidade.')
            result.append({'id':f'candidate_{len(result)+1}',
                           'label':f'Opção {len(result)+1} — {title}',
                           'source_slug':slug,'source_name':title,
                           'favorite_copies':counts[favourite_id],
                           'changes_from_source':sum(abs(counts.get(cid,0)-raw['cards'].get(cid,0))
                                                     for cid in set(counts)|set(raw['cards']))//2,
                           'deck':deck,
                           'caution':('Construção heurística; ainda não otimizada por simulação. '
                                      'A compatibilidade com as regras deve ser verificada antes de jogar.')})
    return result
