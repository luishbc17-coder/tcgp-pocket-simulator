"""Format-independent deck management. Does not claim to simulate games."""
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from engine import Card, validate_deck

@dataclass(frozen=True)
class CatalogEntry:
    card: Card
    verified: bool = False
    source: str = ''

class Catalog:
    def __init__(self, entries):
        self.entries = {e.card.id: e for e in entries}
        if len(self.entries) != len(entries):
            raise ValueError('Duplicate card IDs')

    @classmethod
    def from_json(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls([CatalogEntry(Card(**item['card']), item.get('verified', False), item.get('source', '')) for item in data['cards']])

    def search(self, query='', kind=None):
        return [e for e in self.entries.values() if query.casefold() in e.card.name.casefold() and (kind is None or e.card.kind == kind)]

    def resolve(self, deck, require_verified=False):
        cards = []
        for card_id, count in deck['cards'].items():
            if card_id not in self.entries:
                raise ValueError(f'Unknown card ID: {card_id}')
            entry = self.entries[card_id]
            if require_verified and not entry.verified:
                raise ValueError(f'Unverified card: {card_id}')
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ValueError(f'Invalid count: {card_id}')
            cards.extend([entry.card] * count)
        validate_deck(cards)
        return cards

def save_deck(path, name, counts, energy_types):
    if not name.strip():
        raise ValueError('Deck name required')
    if not energy_types or len(energy_types) > 3 or len(set(energy_types)) != len(energy_types):
        raise ValueError('Choose 1–3 unique energy types')
    payload = {'name': name, 'cards': dict(counts), 'energy_types': list(energy_types)}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload

def load_deck(path, catalog, require_verified=False):
    deck = json.loads(Path(path).read_text(encoding='utf-8'))
    catalog.resolve(deck, require_verified=require_verified)
    if not deck.get('energy_types') or len(set(deck['energy_types'])) != len(deck['energy_types']) or len(deck['energy_types']) > 3:
        raise ValueError('Invalid energy configuration')
    return deck

def make_experiment(player_deck_path, opponents, games_per_matchup=100000, seed=20261116):
    if games_per_matchup < 1 or not opponents:
        raise ValueError('Invalid experiment')
    return {'player_deck_path': str(player_deck_path), 'opponents': list(opponents),
            'target_games_per_matchup': games_per_matchup, 'seed': seed,
            'execution_enabled': False,
            'blockers': ['verified full card effects', 'complete legal turn engine',
                         'verified opponent decklists', 'end-to-end match tests']}
