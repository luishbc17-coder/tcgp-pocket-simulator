"""Verified 20-card sample baselines for TWO Pocket archetypes (2026-11-16).

IDs are the lowercase PocketDecks v5 IDs, NOT the display-style P-A-005.
These are community consensus samples; they are not a particular tournament winner.
Only include decks whose full 20-card list was checked against a dated source.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy

DECKS = {
    'mega_altaria_greninja': {
        'name': 'Mega Altaria ex / Greninja',
        'energy_types': ['psychic'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/mega-altaria-ex-b1-greninja-a1',
        'source_checked': '2026-11-16',
        'sample_through': '2026-11-15',
        'description': 'Lista representativa; Greninja é usado pela habilidade Water Shuriken.',
        'cards': {
            'a1-089': 2,  # Greninja
            'b1-196': 2,  # Swablu
            'b1-109': 2,  # Chingling
            'a1-087': 2,  # Froakie
            'b1-102': 1,  # Mega Altaria ex
            'pa-005': 2,  # Poké Ball
            'pa-007': 2,  # Professor's Research
            'b1-225': 2, # Copycat
            'a3-144': 2, # Rare Candy
            'b3-148': 2, # Lucky Egg
            'a2-150': 1, # Cyrus
        },
    },
    'hoopa_mega_absol': {
        'name': 'Hoopa ex / Mega Absol ex',
        'energy_types': ['darkness'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/hoopa-ex-b4-mega-absol-ex-b1',
        'source_checked': '2026-11-16',
        'sample_through': '2026-11-14',
        'description': 'Lista representativa; Hoopa ex pressiona o banco e Mega Absol ex interrompe apoiadores.',
        'cards': {
            'b4-103': 2, # Hoopa ex
            'b1-151': 1, # Mega Absol ex
            'a2-110': 1, # Darkrai ex
            'pa-005': 2, # Poké Ball
            'a2-150': 2, # Cyrus
            'b2-145': 2, # Lucky Ice Pop
            'b4-148': 2, # Deceptive Needle
            'pa-007': 2, # Professor's Research
            'b3-147': 1, # Field Blower
            'pa-002': 1, # X Speed
            'a2b-070': 1, # Pokémon Center Lady
            'a3a-064': 1, # Repel
            'a2-155': 1, # Mars
            'b1-225': 1, # Copycat
        },
    },
}


def get_preset(slug: str) -> dict:
    if slug not in DECKS:
        raise KeyError(f'Preset não verificado: {slug}')
    d = deepcopy(DECKS[slug])
    if sum(d['cards'].values()) != 20:
        raise RuntimeError('Preset com quantidade de cartas incorreta')
    if not all(type(n) is int and 1 <= n <= 2 for n in d['cards'].values()):
        raise RuntimeError('Quantidade por carta inválida')
    return {'format': 'tcgp-lab-v0.8', **d}


def verify_presets(core_cards: list[dict]) -> dict[str, dict]:
    """Keep remote data mismatches visible; never replace a missing ID by name."""
    lookup = {card['id']:card for card in core_cards}
    out = {}
    for slug in DECKS:
        deck = get_preset(slug)
        missing = [cid for cid in deck['cards'] if cid not in lookup]
        repeated_names = Counter()
        for cid, count in deck['cards'].items():
            if cid in lookup:
                repeated_names[lookup[cid]['name'].casefold()] += count
        bad_names = {name:n for name,n in repeated_names.items() if n > 2}
        out[slug] = {
            'name': deck['name'], 'total': sum(deck['cards'].values()),
            'missing_ids': missing, 'duplicate_names': bad_names,
            'ready_to_inspect': not missing and not bad_names,
        }
    return out
