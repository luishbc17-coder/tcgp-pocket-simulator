"""Auditable Pocket simulation kernel. No unverified card effects are implemented."""
from dataclasses import dataclass, field
from collections import Counter
import random

@dataclass(frozen=True)
class Card:
    id: str
    name: str
    kind: str  # pokemon, item, supporter, tool, stadium
    stage: int = 0
    evolves_from: str | None = None
    hp: int = 0
    points: int = 1

@dataclass
class Pokemon:
    card: Card
    damage: int = 0
    energy: Counter = field(default_factory=Counter)
    evolved_turn: int = -1
    played_turn: int = 0

@dataclass
class Player:
    deck: list[Card]
    hand: list[Card] = field(default_factory=list)
    active: Pokemon | None = None
    bench: list[Pokemon] = field(default_factory=list)
    points: int = 0
    supporter_used: bool = False
    energy_attached: bool = False

@dataclass
class Game:
    players: tuple[Player, Player]
    turn: int = 0
    current: int = 0
    winner: int | None = None
    rng: random.Random = field(default_factory=random.Random)

    def draw(self, player: int, n: int = 1) -> None:
        p = self.players[player]
        for _ in range(n):
            if p.deck:
                p.hand.append(p.deck.pop())

    def begin_turn(self) -> None:
        p = self.players[self.current]
        p.supporter_used = False
        p.energy_attached = False
        self.draw(self.current)

    def end_turn(self) -> None:
        self.current = 1 - self.current
        self.turn += 1

    def attach(self, target: Pokemon, energy_type: str) -> None:
        p = self.players[self.current]
        if p.energy_attached or target not in ([p.active] + p.bench):
            raise ValueError('Illegal energy attachment')
        target.energy[energy_type] += 1
        p.energy_attached = True

    def evolve(self, target: Pokemon, evolution: Card) -> None:
        p = self.players[self.current]
        if target not in ([p.active] + p.bench):
            raise ValueError('Not your Pokemon')
        if evolution not in p.hand or evolution.kind != 'pokemon':
            raise ValueError('Evolution not in hand')
        if evolution.stage != target.card.stage + 1 or evolution.evolves_from != target.card.name:
            raise ValueError('Wrong evolution chain')
        if target.played_turn == self.turn or target.evolved_turn == self.turn:
            raise ValueError('Cannot evolve this turn')
        p.hand.remove(evolution)
        target.card = evolution
        target.evolved_turn = self.turn

    def knockout(self, attacker: int, target: Pokemon) -> None:
        defender = self.players[1 - attacker]
        if target not in ([defender.active] + defender.bench):
            raise ValueError('Invalid target')
        defender.points += 0  # explicit: defender never scores for losing a Pokemon
        self.players[attacker].points += target.card.points
        if defender.active is target:
            defender.active = None
        else:
            defender.bench.remove(target)
        if self.players[attacker].points >= 3:
            self.winner = attacker

    def deal_damage(self, attacker: int, target: Pokemon, amount: int) -> None:
        if amount < 0:
            raise ValueError('Negative damage')
        target.damage += amount
        if target.damage >= target.card.hp:
            self.knockout(attacker, target)

def validate_deck(cards: list[Card]) -> None:
    if len(cards) != 20:
        raise ValueError('Deck must contain exactly 20 cards')
    counts = Counter(c.name for c in cards)
    if max(counts.values()) > 2:
        raise ValueError('More than 2 copies of a card name')
    if not any(c.kind == 'pokemon' and c.stage == 0 for c in cards):
        raise ValueError('Deck needs a Basic Pokemon')

class RuleBasedAgent:
    """Deterministic baseline; no claim of optimal play."""
    def choose_energy_target(self, player: Player) -> Pokemon:
        candidates = [p for p in [player.active, *player.bench] if p]
        if not candidates:
            raise ValueError('No Pokemon in play')
        return max(candidates, key=lambda p: (p.card.stage, p.card.hp - p.damage))

    def choose_evolution(self, player: Player, turn: int):
        for target in [player.active, *player.bench]:
            if target is None or target.played_turn == turn or target.evolved_turn == turn:
                continue
            for card in player.hand:
                if card.kind == 'pokemon' and card.evolves_from == target.card.name and card.stage == target.card.stage + 1:
                    return target, card
        return None
