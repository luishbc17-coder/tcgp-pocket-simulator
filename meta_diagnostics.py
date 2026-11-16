"""Safe scoped evidence for troubleshooting PocketDecks effect-recognition drift.

Only card mechanics in the public gameplay feed are exported. No user deck,
private session state, or gameplay simulator internals are included.
"""
from __future__ import annotations
from gameplay_catalog import compile_card
from battle_engine import UnsupportedEffect


def blocked_catalog_diagnostics(plan: dict, opponents: dict, gameplay: list[dict]) -> dict:
    """Collect exact *actual* source text of incompatible cards in blocked presets."""
    lookup = {r.get('id'):r for r in gameplay if isinstance(r, dict) and r.get('id')}
    blocked = []
    seen = set()
    for row in plan.get('opponents', []):
        if row.get('status') != 'blocked':
            continue
        deck = opponents.get(row.get('slug'), {})
        for cid in deck.get('cards', {}):
            if cid in seen:
                continue
            raw = lookup.get(cid)
            if not raw:
                blocked.append({'id':cid,'name':'Carta ausente no catálogo',
                                'reason':'ID não encontrado no gameplay'})
                seen.add(cid)
                continue
            try:
                compile_card(raw)
            except (UnsupportedEffect, ValueError, KeyError, TypeError) as exc:
                seen.add(cid)
                entry = {
                    'id': cid, 'name':raw.get('name'),
                    'reason': str(exc), 'type': raw.get('type'),
                    'subtype':raw.get('subtype'),
                    'card_text':raw.get('card_text'),
                    'ability': raw.get('ability'),
                    'attacks':raw.get('attacks'),
                }
                blocked.append(entry)
    return {'kind':'public_card_effect_diagnostics','version':'0.9.3.1',
            'source':'PocketDecks cards.gameplay.min.json (instância atual do aplicativo)',
            'blocked_cards':blocked}
