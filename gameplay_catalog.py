"""Audit and conservative adapter for PocketDecks v5 gameplay payload.

The provider documents this as a community data source, NOT an official game
rules engine. We only compile explicitly supported text into executable cards.
"""
from __future__ import annotations
from collections import Counter
import re
from typing import Iterable
from battle_engine import Attack, Card, UnsupportedEffect, parse_cost, RuleError

GAMEPLAY_URL = (
    'https://raw.githubusercontent.com/PocketDecks/pokemon-tcg-pocket-cards/'
    'refs/heads/main/data/v5/cards.gameplay.min.json'
)


def audit_core_cards(cards: list[dict]) -> dict:
    ids = [str(c.get('id', '')) for c in cards]
    stages = Counter(c.get('stage') or 'N/A' for c in cards)
    sets = Counter(c.get('set') for c in cards if c.get('set'))
    issues = []
    duplicate_count = len(ids) - len(set(ids))
    if duplicate_count:
        issues.append(f'{duplicate_count} IDs repetidos')
    if any(not c.get('name') or not c.get('id') for c in cards):
        issues.append('Cartas sem nome ou ID')
    if not sets:
        issues.append('Nenhuma expansão identificada (set_code ausente?)')
    return {
        'records': len(cards),
        'unique_ids': len(set(ids)),
        'duplicates': duplicate_count,
        'expansions': len(sets),
        'by_stage': dict(stages),
        'missing_images': sum(not c.get('image') for c in cards),
        'issues': issues,
    }


def audit_gameplay_records(gameplay: list[dict], core: list[dict] | None = None) -> dict:
    if not isinstance(gameplay, list):
        raise ValueError('O gameplay precisa ser uma lista JSON')
    ids = [r.get('id') for r in gameplay]
    duplicates = len(ids) - len(set(ids))
    pokemon = [r for r in gameplay if r.get('type') == 'Pokémon']
    trainers = [r for r in gameplay if r.get('type') == 'Trainer']
    issues = []
    if duplicates:
        issues.append(f'{duplicates} IDs repetidos no gameplay')
    if len(gameplay) < 100:
        issues.append('Gameplay com menos de 100 registros; provável falha de carga')
    if any('set_code' not in r for r in gameplay):
        issues.append('Há cartas sem set_code')
    if any(not isinstance(r.get('health'), int) or not isinstance(r.get('attacks'), dict)
           for r in pokemon):
        issues.append('Pokémon com atributos de batalha incompletos')
    if any(not isinstance(r.get('card_text'), str) for r in trainers
           if not r.get('stage')):
        issues.append('Treinador sem texto mecânico')
    core_ids = set(x['id'] for x in (core or []) if x.get('id'))
    game_ids = set(ids)
    if core is not None and core_ids != game_ids:
        issues.append(f'IDs divergentes: {len(core_ids - game_ids)} só no core, '
                      f'{len(game_ids - core_ids)} só no gameplay')
    return {'records': len(gameplay), 'pokemon': len(pokemon),
            'trainers': len(trainers), 'unique_ids': len(game_ids),
            'duplicates': duplicates,
            'missing_from_gameplay': len(core_ids - game_ids),
            'extra_gameplay_ids': len(game_ids - core_ids) if core is not None else None,
            'issues': issues}


def _text(s):
    return ' '.join(str(s or '').split()).casefold().strip().rstrip('.')


def _recognize_trainer(r: dict):
    name = r['name']
    text = _text(r.get('card_text'))
    if name == "Professor's Research" and text == 'draw 2 cards':
        return 'research'
    if name == 'Poké Ball' and text in (
        'put 1 random basic pokemon from your deck into your hand',
        'put 1 random basic pokémon from your deck into your hand'):
        return 'pokeball'
    if name == 'Rare Candy' and (
        text.startswith('choose 1 of your basic pokémon in play.')
        and 'stage 2' in text and 'skipping the stage 1' in text
        and "can't use this card during your first turn" in text):
        return 'rare_candy'
    raise UnsupportedEffect(f'{name}: texto de treinador não implementado')


def _recognize_attack(r: dict, raw_attack: dict):
    name = raw_attack.get('name')
    damage = raw_attack.get('damage')
    effect = _text(raw_attack.get('effect'))
    if name is None:
        return None
    if not isinstance(damage, int) or damage < 0:
        raise UnsupportedEffect(f'{r["name"]} / {name}: dano dinâmico ou desconhecido')
    cost = parse_cost(raw_attack.get('cost'))
    if not effect:
        return Attack(name, cost, damage)
    # Curated single effect, checked by name, base damage and the full known text.
    if (r['name'] == 'Mega Swampert ex' and name == 'Strong-Armed Destroyer'
        and damage == 150 and raw_attack.get('cost') == 'WWW'
        and effect == 'discard 2 random energy from among the energy attached to all pokémon (both yours and your opponent\'s)'):
        return Attack(name, cost, damage, 'discard_2_global_random')
    raise UnsupportedEffect(f'{r["name"]} / {name}: efeito de ataque não implementado')


def compile_card(raw: dict) -> Card:
    """Fail closed: no silent approximation of abilities, tools or card text."""
    if not isinstance(raw, dict) or not raw.get('id') or not raw.get('name'):
        raise UnsupportedEffect('Incomplete card identity')
    if raw.get('stage') and raw.get('type') == 'Trainer':
        raise UnsupportedEffect(f'{raw["name"]}: fóssil/jogabilidade especial pendente')
    if raw.get('type') == 'Trainer':
        subtype = str(raw.get('subtype', '')).lower()
        if subtype == 'supporter':
            kind = 'supporter'
        elif subtype == 'item':
            kind = 'item'
        else:
            raise UnsupportedEffect(f'{raw["name"]}: tipo {subtype} não implementado')
        return Card(raw['id'], raw['name'], kind, effect=_recognize_trainer(raw))
    if raw.get('type') != 'Pokémon':
        raise UnsupportedEffect(f'{raw["name"]}: categoria desconhecida')
    ability = raw.get('ability') or {}
    if ability.get('exists'):
        raise UnsupportedEffect(f'{raw["name"]}: habilidade não implementada')
    stage_map = {'Basic': 0, 'Stage 1': 1, 'Stage 2': 2}
    if raw.get('stage') not in stage_map:
        raise UnsupportedEffect(f'{raw["name"]}: estágio desconhecido')
    element = str(raw.get('subtype', '')).casefold()
    if element not in ('grass','fire','water','lightning','psychic','fighting',
                       'darkness','metal','dragon','colorless'):
        raise UnsupportedEffect(f'{raw["name"]}: tipo desconhecido {element}')
    attacks = raw.get('attacks') or {}
    if not isinstance(attacks, dict):
        raise UnsupportedEffect(f'{raw["name"]}: formato de ataques inválido')
    out = []
    for slot in ('1', '2'):
        candidate = attacks.get(slot)
        if not candidate:
            continue
        attack = _recognize_attack(raw,candidate)
        if attack:
            out.append(attack)
    if not out:
        # Some playable Pokémon don't attack (e.g. Fossils), not yet supported.
        raise UnsupportedEffect(f'{raw["name"]}: sem ataques suportados')
    hp = raw.get('health')
    if type(hp) is not int or hp <= 0:
        raise UnsupportedEffect(f'{raw["name"]}: HP inválido')
    points = raw.get('points')
    if points not in (1,2,3):
        raise UnsupportedEffect(f'{raw["name"]}: pontuação inválida')
    retreat = raw.get('retreat')
    if type(retreat) is not int or retreat < 0:
        raise UnsupportedEffect(f'{raw["name"]}: recuo inválido')
    return Card(raw['id'],raw['name'],'pokemon',stage_map[raw['stage']],
                raw.get('evolves_from') or '',hp,points,
                element,str(raw.get('weakness') or '').casefold(),retreat,
                tuple(out))


def compile_deck(counts: dict[str,int], gameplay: list[dict]) -> tuple[list[Card], list[str]]:
    lookup = {r['id']: r for r in gameplay}
    output, errors = [], []
    for card_id, n in counts.items():
        if type(n) is not int or n not in (1,2):
            errors.append(f'{card_id}: quantidade inválida')
            continue
        if card_id not in lookup:
            errors.append(f'{card_id}: não encontrado no catálogo gameplay')
            continue
        try:
            card = compile_card(lookup[card_id])
            output.extend([card] * n)
        except UnsupportedEffect as ex:
            errors.append(str(ex))
    if sum(counts.values()) != 20:
        errors.append('O deck precisa ter exatamente 20 cartas')
    return output, errors


def evolution_line_map(gameplay: list[dict]) -> dict[str,str]:
    return {str(r.get('name','')).casefold(): str(r['evolves_from'])
            for r in gameplay if r.get('stage') == 'Stage 1' and r.get('evolves_from')}
