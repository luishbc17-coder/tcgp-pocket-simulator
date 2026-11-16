"""On-demand, conservative compatibility statuses for the v0.9.2 card browser.

A card being present in the catalog is not equivalent to a runnable effect.
The decision is delegated to the *existing* exact-text battle compiler, not
inferred from the card's name or attack damage.
"""
from __future__ import annotations

from gameplay_catalog import compile_card
from battle_engine import UnsupportedEffect, RuleError


def build_support_index(core_cards: list[dict], gameplay_cards: list[dict]) -> dict[str, dict]:
    """Classify each core ID as supported, blocked, or missing from gameplay."""
    source = {str(card.get('id')): card for card in gameplay_cards if card.get('id')}
    result = {}
    for card in core_cards:
        cid = str(card['id'])
        raw = source.get(cid)
        if raw is None:
            result[cid] = {'status': 'missing', 'reason': 'Sem registro na base de jogabilidade.'}
            continue
        try:
            compile_card(raw)
        except (UnsupportedEffect, RuleError, ValueError, TypeError, KeyError, IndexError) as exc:
            result[cid] = {'status': 'blocked', 'reason': str(exc)[:240]}
        else:
            result[cid] = {'status': 'supported', 'reason': 'Reconhecida pelo motor atual.'}
    return result


def coverage_summary(card_counts: dict[str, int], index: dict[str, dict]) -> dict:
    """Count copies, not just distinct IDs; do not imply full-deck legality."""
    total = sum(card_counts.values())
    supported = sum(n for cid, n in card_counts.items()
                    if index.get(cid, {}).get('status') == 'supported')
    missing = [cid for cid in card_counts
               if index.get(cid, {}).get('status') == 'missing' or cid not in index]
    blocked = [cid for cid in card_counts
               if index.get(cid, {}).get('status') == 'blocked']
    return {'total': total, 'supported': supported,
            'unsupported': total-supported, 'missing_ids': missing, 'blocked_ids': blocked,
            'candidate_for_technical_test': total == 20 and supported == 20}
