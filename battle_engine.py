"""TCG Pocket rules kernel, v0.7.

Only effects explicitly identified in cards are executable. Unsupported text MUST
prevent a real matchup from being run; tests may use synthetic fixtures.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
import random

ENERGY_CODES = {'G': 'grass', 'R': 'fire', 'W': 'water', 'L': 'lightning',
                'P': 'psychic', 'F': 'fighting', 'D': 'darkness',
                'M': 'metal', 'C': 'colorless'}
MAX_TURNS = 30

class RuleError(ValueError):
    pass

class UnsupportedEffect(RuleError):
    pass


def parse_cost(value: str | None) -> tuple[str, ...]:
    """PocketDecks uses compact string costs, e.g. WWW or GCC."""
    if not value:
        return ()
    if not isinstance(value, str) or any(code not in ENERGY_CODES for code in value):
        raise UnsupportedEffect(f'Unrecognized energy cost: {value!r}')
    return tuple(ENERGY_CODES[x] for x in value)


@dataclass(frozen=True)
class Attack:
    name: str
    cost: tuple[str, ...]
    damage: int
    effect: str = ''  # '', 'discard_2_global_random'; never raw card text


@dataclass(frozen=True)
class Card:
    id: str
    name: str
    kind: str  # pokemon, item, supporter; no tools/stadia until supported
    stage: int = 0
    evolves_from: str = ''
    hp: int = 0
    points: int = 0
    element: str = ''
    weakness: str = ''
    retreat: int = 0
    attacks: tuple[Attack, ...] = ()
    effect: str = ''  # '', 'research', 'pokeball', 'rare_candy'


@dataclass
class InPlay:
    card: Card
    damage: int = 0
    energy: list[str] = field(default_factory=list)
    entered_at: int = -1
    evolved_at: int = -1


@dataclass
class Player:
    deck: list[Card]
    energy_types: tuple[str, ...]
    hand: list[Card] = field(default_factory=list)
    active: InPlay | None = None
    bench: list[InPlay] = field(default_factory=list)
    points: int = 0
    turns_taken: int = 0
    energy_used: bool = False
    supporter_used: bool = False
    retreated: bool = False

    def all_in_play(self) -> list[InPlay]:
        return ([self.active] if self.active else []) + self.bench


def validate_deck(cards: list[Card], energy_types: tuple[str, ...]) -> None:
    if len(cards) != 20:
        raise RuleError('Deck must have 20 cards')
    if not any(c.kind == 'pokemon' and c.stage == 0 for c in cards):
        raise RuleError('Deck has no Basic Pokémon')
    if any(n > 2 for n in Counter(c.name.casefold() for c in cards).values()):
        raise RuleError('More than 2 copies of a name')
    if not 1 <= len(energy_types) <= 3 or len(set(energy_types)) != len(energy_types):
        raise RuleError('Invalid Energy Zone types')
    if any(x not in (set(ENERGY_CODES.values()) - {'colorless'}) for x in energy_types):
        raise RuleError('Energy Zone contains invalid type')


class Battle:
    """Strict, no-effect guessing. All actions validated and replayable via event log.

    The Energy Zone is restricted to a single type in rated simulations because
    the exact mixed-type generation sequencing has not yet been implemented.
    """
    def __init__(self, left: list[Card], right: list[Card],
                 energy_left=('water',), energy_right=('water',), seed=0):
        validate_deck(left, tuple(energy_left))
        validate_deck(right, tuple(energy_right))
        if len(energy_left) != 1 or len(energy_right) != 1:
            raise UnsupportedEffect('Mixed-type Energy Zone not implemented')
        self.rng = random.Random(seed)
        self.players = [Player(list(left), tuple(energy_left)),
                        Player(list(right), tuple(energy_right))]
        self.turn = 0
        self.current = self.rng.randrange(2)
        self.first = self.current
        self.winner: int | None = None
        self.finished = False
        self.log: list[str] = []
        self._in_turn = False
        for i, player in enumerate(self.players):
            self._initial_hand(player)
            basics = [c for c in player.hand if c.kind == 'pokemon' and c.stage == 0]
            choice = max(basics, key=lambda c: (max((a.damage for a in c.attacks), default=0), c.hp))
            player.hand.remove(choice)
            player.active = InPlay(choice, entered_at=-1)
            self.log.append(f'Setup P{i} active {choice.name}')

    def _initial_hand(self, p: Player):
        # Draw 5 cards conditioned on a Basic; deck order remains randomized.
        # This is an explicit approximation of the game's guaranteed Basic draw.
        for _ in range(20000):
            self.rng.shuffle(p.deck)
            proposed = p.deck[-5:]
            if any(c.kind == 'pokemon' and c.stage == 0 for c in proposed):
                p.hand.extend(p.deck[-5:])
                del p.deck[-5:]
                return
        raise RuleError('Unable to form opening hand')

    def begin_turn(self):
        if self.finished or self._in_turn:
            raise RuleError('Cannot begin turn')
        p = self.players[self.current]
        p.turns_taken += 1
        p.energy_used = False
        p.supporter_used = False
        p.retreated = False
        self._in_turn = True
        self.draw(self.current, 1)
        self.log.append(f'Turn {self.turn + 1}, P{self.current}')

    def _require_action(self, player: int):
        if self.finished or not self._in_turn or self.current != player:
            raise RuleError('Action outside your turn')

    def draw(self, who, count=1):
        p = self.players[who]
        for _ in range(count):
            if p.deck and len(p.hand) < 10:
                p.hand.append(p.deck.pop())

    def bench_basic(self, card: Card):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if card not in p.hand or card.kind != 'pokemon' or card.stage != 0 or len(p.bench) >= 3:
            raise RuleError('Cannot bench Pokémon')
        p.hand.remove(card)
        p.bench.append(InPlay(card, entered_at=self.turn))
        self.log.append(f'P{i} benches {card.name}')

    def evolve(self, target: InPlay, evolution: Card):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if p.turns_taken == 1 or target not in p.all_in_play():
            raise RuleError('Evolution not allowed now')
        if (target.entered_at == self.turn or target.evolved_at == self.turn or
            evolution not in p.hand or evolution.kind != 'pokemon' or
            evolution.stage != target.card.stage + 1 or
            evolution.evolves_from.casefold() != target.card.name.casefold()):
            raise RuleError('Illegal evolution')
        p.hand.remove(evolution)
        target.card = evolution
        target.evolved_at = self.turn
        self.log.append(f'P{i} evolves to {evolution.name}')

    def rare_candy(self, candy: Card, target: InPlay, evolution: Card, line_map: dict[str, str]):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (candy not in p.hand or candy.effect != 'rare_candy' or p.turns_taken == 1 or
            target not in p.all_in_play() or target.card.stage != 0 or
            target.entered_at == self.turn or target.evolved_at == self.turn or
            evolution not in p.hand or evolution.stage != 2 or
            line_map.get(evolution.evolves_from.casefold(), '').casefold() != target.card.name.casefold()):
            raise RuleError('Illegal Rare Candy')
        p.hand.remove(candy)
        p.hand.remove(evolution)
        target.card = evolution
        target.evolved_at = self.turn
        self.log.append(f'P{i} Rare Candy to {evolution.name}')

    def attach(self, target: InPlay):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (target not in p.all_in_play() or p.energy_used or
            (self.turn == 0 and i == self.first)):
            raise RuleError('Energy attachment unavailable')
        target.energy.append(p.energy_types[0])
        p.energy_used = True
        self.log.append(f'P{i} attaches {p.energy_types[0]} to {target.card.name}')

    def play_trainer(self, card: Card):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if card not in p.hand or card.kind not in ('supporter', 'item'):
            raise RuleError('Illegal trainer')
        if p.supporter_used and card.kind == 'supporter':
            raise RuleError('Supporter already used')
        if card.effect == 'research':
            p.hand.remove(card)
            self.draw(i, 2)
        elif card.effect == 'pokeball':
            basics = [c for c in p.deck if c.kind == 'pokemon' and c.stage == 0]
            if not basics:
                raise RuleError('No Basic Pokémon to search')
            found = self.rng.choice(basics)
            p.deck.remove(found)
            p.hand.remove(card)
            if len(p.hand) < 10:
                p.hand.append(found)
            else:
                p.deck.append(found)
            # The card's text says random Basic, and does not shuffle the deck.
        else:
            raise UnsupportedEffect('Trainer effect requires handler')
        if card.kind == 'supporter':
            p.supporter_used = True
        self.log.append(f'P{i} plays {card.name}')

    def retreat(self, incoming: InPlay):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if p.retreated or not p.active or incoming not in p.bench:
            raise RuleError('Illegal retreat')
        need = p.active.card.retreat
        if len(p.active.energy) < need:
            raise RuleError('Not enough energy to retreat')
        del p.active.energy[:need]
        current = p.active
        p.bench.remove(incoming)
        p.active = incoming
        p.bench.append(current)
        p.retreated = True
        self.log.append(f'P{i} retreats into {incoming.card.name}')

    @staticmethod
    def can_pay_energy(attacker: InPlay, attack: Attack) -> bool:
        if len(attacker.energy) < len(attack.cost):
            return False
        owned = Counter(attacker.energy)
        required = Counter(x for x in attack.cost if x != 'colorless')
        return all(owned[t] >= n for t, n in required.items())

    def attack(self, selected: Attack):
        i = self.current
        self._require_action(i)
        me = self.players[i]
        them = self.players[1-i]
        if not me.active or not them.active or selected not in me.active.card.attacks:
            raise RuleError('Illegal attack')
        if not self.can_pay_energy(me.active, selected):
            raise RuleError('Attack energy cost unpaid')
        if selected.effect not in ('', 'discard_2_global_random', 'heal_self_30', 'coin_bonus_30'):
            raise UnsupportedEffect('Attack effect requires handler')
        damage = selected.damage
        if selected.effect == 'coin_bonus_30':
            heads = self.rng.choice((True, False))
            self.log.append(f'P{i} coin flip: {"heads" if heads else "tails"}')
            if heads:
                damage += 30
        if damage > 0 and them.active.card.weakness == me.active.card.element:
            damage += 20
        them.active.damage += damage
        self.log.append(f'P{i} {selected.name}, {damage} damage')
        if selected.effect == 'heal_self_30':
            old_damage = me.active.damage
            me.active.damage = max(0, me.active.damage - 30)
            self.log.append(f'P{i} {me.active.card.name} heals {old_damage - me.active.damage}')
        if selected.effect == 'discard_2_global_random':
            # Both sides' remaining Pokémon supply the shared random Energy pool.
            for _ in range(2):
                # Rebuild after each removal: every remaining Energy token has
                # equal weight, and zero-energy Pokemon can never be selected.
                pool = [pokemon for owner in self.players
                        for pokemon in owner.all_in_play()
                        for _ in pokemon.energy]
                if not pool:
                    break
                pokemon = self.rng.choice(pool)
                pokemon.energy.pop(self.rng.randrange(len(pokemon.energy)))
                self.log.append(f'{pokemon.card.name} discards 1 random Energy')
        if them.active and them.active.damage >= them.active.card.hp:
            self._knockout(1-i,  i)
        self.end_turn()

    def _knockout(self, victim: int, scorer: int):
        p = self.players[victim]
        if not p.active:
            raise RuleError('No active Pokémon to KO')
        knocked = p.active
        p.active = None
        self.players[scorer].points += knocked.card.points
        self.log.append(f'P{victim} KO {knocked.card.name}; P{scorer} score {self.players[scorer].points}')
        if self.players[scorer].points >= 3 or not p.bench:
            self.winner, self.finished = scorer, True
        else:
            # Promotion is chosen by the rule agent; this default is deterministic.
            replacement = max(p.bench, key=lambda x: (len(x.energy), x.card.hp-x.damage))
            p.bench.remove(replacement)
            p.active = replacement
            self.log.append(f'P{victim} promotes {replacement.card.name}')

    def end_turn(self):
        if not self._in_turn:
            raise RuleError('Turn not started')
        self._in_turn = False
        self.turn += 1
        if not self.finished and self.turn >= MAX_TURNS:
            self.finished = True
            self.winner = None
        elif not self.finished:
            self.current = 1-self.current


class RuleAgent:
    """A transparent baseline policy, not an optimal or learned player."""
    def __init__(self, line_map=None):
        self.line_map = line_map or {}

    def play_turn(self, battle: Battle):
        i = battle.current
        p = battle.players[i]
        battle.begin_turn()
        # Items before evolution, prioritizing search for a basic.
        for c in list(p.hand):
            if c.effect == 'pokeball' and len(p.bench) < 3 and any(x.kind=='pokemon' and x.stage==0 for x in p.deck):
                battle.play_trainer(c)
        for c in list(p.hand):
            if c.kind == 'pokemon' and c.stage == 0 and len(p.bench) < 3:
                battle.bench_basic(c)
        # Candy first, if the corresponding Stage 1 -> Basic lineage is known.
        for candy in [c for c in p.hand if c.effect == 'rare_candy']:
            matched = None
            for target in p.all_in_play():
                for evo in p.hand:
                    if (evo.stage == 2 and self.line_map.get(evo.evolves_from.casefold(), '').casefold() == target.card.name.casefold()
                        and p.turns_taken > 1 and target.entered_at != battle.turn and target.evolved_at != battle.turn):
                        matched = (target,evo)
                        break
                if matched:
                    break
            if matched:
                battle.rare_candy(candy,*matched,self.line_map)
        # Regular evolutions, highest stage first.
        for evo in sorted(list(p.hand),key=lambda x: x.stage,reverse=True):
            for target in p.all_in_play():
                if (evo.stage in (1,2) and evo.stage == target.card.stage+1 and
                    evo.evolves_from.casefold() == target.card.name.casefold() and
                    p.turns_taken > 1 and target.entered_at != battle.turn and target.evolved_at != battle.turn):
                    battle.evolve(target,evo)
                    break
        for c in list(p.hand):
            if c.effect == 'research' and len(p.hand) <= 8 and p.deck:
                battle.play_trainer(c)
                break
        # New basics obtained after draw.
        for c in list(p.hand):
            if c.kind == 'pokemon' and c.stage == 0 and len(p.bench) < 3:
                battle.bench_basic(c)
        if not p.energy_used and not (battle.turn == 0 and battle.first == i):
            # Charge active attacker preferentially.
            target = p.active if p.active else (p.bench[0] if p.bench else None)
            if target:
                battle.attach(target)
        if p.active:
            options = [a for a in p.active.card.attacks if battle.can_pay_energy(p.active,a)]
            if options:
                battle.attack(max(options,key=lambda a:a.damage + (15 if a.effect=='coin_bonus_30' else 0)))
                return
        battle.end_turn()


def play_fixture_match(left, right, seed=0, energy_left=('water',), energy_right=('water',), line_map=None):
    battle = Battle(left, right, energy_left, energy_right, seed)
    agent = RuleAgent(line_map)
    while not battle.finished:
        agent.play_turn(battle)
    return battle
