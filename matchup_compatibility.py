"""Conservative, source-aligned deck vs deck compatibility inspector.

All reports are about *implemented handlers*, NOT proof of official game
fidelity. Caller must load the game data from the PocketDecks gameplay feed.
"""
from __future__ import annotations
from collections import Counter
from typing import Any

from battle_engine import RuleError, UnsupportedEffect, validate_deck
from gameplay_catalog import compile_card

VALID_ENERGIES = {'grass','fire','water','lightning','psychic','fighting','darkness','metal'}


def parse_payload(value: Any) -> dict:
    """Accept the JSON deck exports from v0.4+, reject unsafe/invalid shapes."""
    if not isinstance(value, dict):
        raise ValueError('O arquivo deve conter um objeto JSON.')
    cards = value.get('cards')
    if not isinstance(cards, dict) or len(cards) > 20:
        raise ValueError('O campo cards deve ser um objeto com no máximo 20 IDs.')
    if any(not isinstance(k,str) or not k or type(n) is not int or not (1 <= n <= 2)
           for k,n in cards.items()):
        raise ValueError('IDs ou quantidades inválidos; use de 1 a 2 por ID.')
    if sum(cards.values()) > 20:
        raise ValueError('O deck tem mais de 20 cartas.')
    energy = value.get('energy_types')
    if not isinstance(energy, list) or not (1 <= len(energy) <= 3):
        raise ValueError('Selecione de 1 a 3 tipos de energia.')
    if len(set(map(str, energy))) != len(energy) or any(not isinstance(e,str) or not e for e in energy):
        raise ValueError('Configuração de energia inválida ou duplicada.')
    name = value.get('name', 'Deck sem nome')
    if not isinstance(name, str):
        raise ValueError('O nome do deck deve ser um texto.')
    return {'name': name[:100], 'cards': dict(cards), 'energy_types': list(energy),
            'format': str(value.get('format','tcgp-lab-import'))[:64]}


def inspect_deck(raw: dict, core: list[dict], gameplay: list[dict]) -> dict:
    """Return JSON-serializable report without silently substituting effects."""
    payload = parse_payload(raw)
    ids = {c['id']:c for c in core}
    battle_ids = {c['id']:c for c in gameplay if c.get('id')}
    rows: list[dict] = []
    blocks: list[str] = []
    notes: list[str] = []
    compiled = []
    unpayable_attackers = []
    cards = payload['cards']
    energy = payload['energy_types']
    card_count = sum(cards.values())
    if card_count != 20:
        blocks.append(f'Deck incompleto: {card_count}/20 cartas.')
    if len(energy) != 1:
        blocks.append('Zona de energia com vários tipos: ainda não implementada no motor.')
    if any(e not in VALID_ENERGIES for e in energy):
        blocks.append('Tipo de energia indisponível no motor: ' + ', '.join(e for e in energy if e not in VALID_ENERGIES))

    by_name = Counter()
    basics = 0
    for cid, n in cards.items():
        core_card = ids.get(cid)
        name = (core_card or battle_ids.get(cid) or {}).get('name',cid)
        if core_card:
            by_name[name.casefold()] += n
            if core_card.get('type') == 'Pokémon' and core_card.get('stage') == 'Basic':
                basics += n
        if not core_card:
            why = 'ID não encontrado no catálogo de construção (core).'
        elif cid not in battle_ids:
            why = 'Carta ausente no catálogo de jogabilidade.'
        else:
            try:
                card = compile_card(battle_ids[cid])
                compiled.extend([card] * n)
                if card.kind == 'pokemon' and card.attacks:
                    for attack in card.attacks:
                        missing = sorted({t for t in attack.cost if t != 'colorless' and t not in energy})
                        if missing:
                            unpayable_attackers.append(f'{name}: {attack.name} requer {", ".join(missing)}')
                why = ''
            except (UnsupportedEffect, ValueError, KeyError, TypeError) as ex:
                why = str(ex)
        raw_card = battle_ids.get(cid) or {}
        source_details = {'type':raw_card.get('type'), 'subtype':raw_card.get('subtype'),
                          'stage':raw_card.get('stage'), 'ability':raw_card.get('ability'),
                          'attacks':raw_card.get('attacks'),
                          'card_text':raw_card.get('card_text')}
        rows.append({'id':cid,'name':name,'quantity':n,
                     'status':'suportada pelo código' if not why else 'bloqueada',
                     'reason':why, 'source_details': source_details if why else None})
    if basics == 0:
        blocks.append('Nenhum Pokémon Básico identificado.')
    if any(n > 2 for n in by_name.values()):
        blocks.append('Mais de duas cópias de um mesmo nome, inclusive artes alternativas.')

    if not any(r['status']=='bloqueada' for r in rows) and card_count==20:
        try:
            validate_deck(compiled,tuple(energy))
        except (RuleError, TypeError, ValueError) as ex:
            blocks.append(f'Verificação estrutural do motor: {ex}')

    if unpayable_attackers:
        notes.append('A energia escolhida não permite pagar: ' + '; '.join(unpayable_attackers))
    supported = sum(r['quantity'] for r in rows if r['status']=='suportada pelo código')
    ready = supported == 20 and not blocks
    if ready:
        notes.append('Elegível somente a um duelo técnico, não a uma estimativa competitiva.')
    else:
        notes.append('Não execute partidas com efeitos omitidos ou inventados.')
    return {'name':payload['name'],'energy_types':energy,'total':card_count,
            'supported':supported,'unsupported':card_count-supported,'issues':blocks,
            'notes':notes,'cards':rows,'technical_demo_ready':ready}


def inspect_matchup(left: dict, right: dict, core: list[dict], gameplay: list[dict]) -> dict:
    a=inspect_deck(left, core, gameplay)
    b=inspect_deck(right, core, gameplay)
    return {'player':a,'opponent':b,
            'technical_demo_ready':a['technical_demo_ready'] and b['technical_demo_ready'],
            'competitive_simulation_ready':False,
            'disclaimer':'Compatibilidade de código não equivale a fidelidade às regras oficiais.'}


def load_compiled_deck(payload: dict, gameplay: list[dict]):
    """For a technical one-game trace after inspect_matchup says ready."""
    source={c['id']:c for c in gameplay}
    return [compile_card(source[cid]) for cid,n in payload['cards'].items() for _ in range(n)]
