"""Stable, inspectable deck identity for audited TCG Pocket Lab experiments.

Identity is based on card *IDs and quantities* and Energy Zone types, never on
self-reported names. Display names are annotations and can differ for same list.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
import json
from meta_decks import DECKS


def _signature(cards: dict[str, int], energy_types) -> str:
    body = {'cards': sorted(cards.items()), 'energy_types': sorted(energy_types)}
    return sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def _recognized_preset(cards: dict[str, int], energy_types) -> tuple[str | None, str | None]:
    for slug, deck in DECKS.items():
        if cards == deck['cards'] and sorted(energy_types) == sorted(deck['energy_types']):
            return slug, deck['name']
    return None, None


def describe_selection(payload: dict, fallback_name: str = 'Deck sem nome') -> dict:
    """Present an imported/selected deck, prior to compilation against gameplay data."""
    if not isinstance(payload, dict) or not isinstance(payload.get('cards'), dict):
        raise ValueError('Deck sem campo cards válido.')
    counts = payload['cards']
    energies = payload.get('energy_types')
    if not isinstance(energies, list) or not energies:
        raise ValueError('Deck sem energia válida.')
    if any(not isinstance(cid, str) or type(qty) is not int or qty < 1 for cid, qty in counts.items()):
        raise ValueError('Deck com ID ou quantidade inválidos.')
    if any(not isinstance(e, str) for e in energies):
        raise ValueError('Tipos de energia inválidos.')
    ordered_counts = dict(sorted(counts.items()))
    slug, recognized_name = _recognized_preset(ordered_counts, energies)
    supplied_name = str(payload.get('name') or fallback_name).strip()[:100]
    return {
        'name': supplied_name,
        'recognized_preset': slug,
        'recognized_name': recognized_name,
        'energy_types': list(energies),
        'card_count': sum(counts.values()),
        'cards': ordered_counts,
        'signature': _signature(ordered_counts, energies),
    }


def describe_compiled(cards: list, energy_types, payload: dict | None = None,
                      fallback_name: str = 'Deck sem nome') -> dict:
    """Bind *actual compiled cards* to the claimed deck; reject identity mismatch.

    Prevents a report from saying Hoopa played when it actually compiled an
    Altaria list, even if the UI accidentally supplied inconsistent arguments.
    """
    counts = dict(sorted(Counter(c.id for c in cards).items()))
    compiled_energy = list(energy_types)
    computed = describe_selection({'cards': counts, 'energy_types': compiled_energy,
                                   'name': fallback_name}, fallback_name)
    if payload is not None:
        selected = describe_selection(payload, fallback_name)
        if selected['signature'] != computed['signature']:
            raise ValueError(
                'Deck selecionado difere do compilado para o motor. '
                'Reabra os decks e tente novamente; lote não iniciado.'
            )
        computed['name'] = selected['name']
    computed['verified_against_compiled'] = True
    return computed


def compare_decks(left: dict, right: dict) -> dict:
    same_cards = left['cards'] == right['cards']
    mirror = same_cards and sorted(left['energy_types']) == sorted(right['energy_types'])
    if mirror:
        warning = ('Confronto espelhado: ambos os lados usam as mesmas 20 cartas '
                   'e os mesmos tipos de energia. Os resultados NÃO comparam '
                   'Mega Altaria/Greninja com Hoopa/Mega Absol.')
    elif same_cards:
        warning = ('Mesmas cartas nos dois lados, mas energias diferentes. '
                   'Confirme se essa comparação era intencional.')
    else:
        warning = ''
    return {
        'is_mirror': mirror,
        'same_card_list': same_cards,
        'warning': warning,
        'left_signature': left['signature'],
        'right_signature': right['signature'],
    }
