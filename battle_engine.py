"""TCG Pocket rules kernel, v0.8.2.

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
    if value is None or value == '' or value == '0' or (type(value) is int and value == 0):
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
    effect: str = ''  # exact recognized trainer effect
    ability: str = '' # exact recognized ability handler


@dataclass
class InPlay:
    card: Card
    damage: int = 0
    energy: list[str] = field(default_factory=list)
    entered_at: int = -1
    evolved_at: int = -1
    ability_used_turn: int = -1
    tool: Card | None = None
    status: str = ''  # only Asleep currently implemented


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
    item_locked: bool = False  # a pending Jingly Noise lock, expires after this player takes a turn
    retreat_discount: int = 0

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
            # Opening Bench is placed before either player takes a turn.
            # Baseline strategy: put up to three remaining Basics on Bench.
            for card in list(player.hand):
                if card.kind == 'pokemon' and card.stage == 0 and len(player.bench) < 3:
                    player.hand.remove(card)
                    player.bench.append(InPlay(card, entered_at=-1))
                    self.log.append(f'Setup P{i} bench {card.name}')

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
        p.retreat_discount = 0
        self._in_turn = True
        # In Pocket the first player does not draw on the opening turn.
        if not (self.turn == 0 and self.current == self.first):
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
        target.status = ''  # Evolving removes Special Conditions.
        target.evolved_at = self.turn
        self.log.append(f'P{i} evolves to {evolution.name}')

    def rare_candy(self, candy: Card, target: InPlay, evolution: Card, line_map: dict[str, str]):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (candy not in p.hand or candy.effect != 'rare_candy' or p.item_locked or p.turns_taken == 1 or
            target not in p.all_in_play() or target.card.stage != 0 or
            target.entered_at == self.turn or target.evolved_at == self.turn or
            evolution not in p.hand or evolution.stage != 2 or
            line_map.get(evolution.evolves_from.casefold(), '').casefold() != target.card.name.casefold()):
            raise RuleError('Illegal Rare Candy')
        p.hand.remove(candy)
        p.hand.remove(evolution)
        target.card = evolution
        target.status = ''  # Evolving removes Special Conditions.
        target.evolved_at = self.turn
        self.log.append(f'P{i} Rare Candy to {evolution.name}')

    def attach(self, target: InPlay):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (target not in p.all_in_play() or p.energy_used or
            (self.turn == 0 and i == self.first)):
            raise RuleError('Energy attachment unavailable')
        energy = p.energy_types[0]
        target.energy.append(energy)
        p.energy_used = True
        self.log.append(f'P{i} attaches {energy} to {target.card.name}')
        if target.card.ability == 'nightmare_aura' and energy == 'darkness':
            self._damage_target(1-i, self.players[1-i].active, 20, i, source='Darkrai ex — Nightmare Aura')

    def _damage_target(self, victim: int, pokemon: InPlay | None, amount: int,
                       scorer: int, source: str, attack_damage=False):
        """Apply direct/bench damage (without weakness), then resolve KO.

        Does not model simultaneous KO arbitration or prevention effects yet.
        """
        if pokemon is None or self.finished or amount < 0:
            return
        pokemon.damage += amount
        self.log.append(f'{source}: {amount} damage to P{victim} {pokemon.card.name}')
        if pokemon.damage >= pokemon.card.hp:
            if self.players[victim].active is pokemon:
                self._knockout(victim, scorer, from_attack=attack_damage)
            elif pokemon in self.players[victim].bench:
                if (attack_damage and victim != scorer and pokemon.tool is not None and
                        pokemon.tool.effect == 'lucky_egg'):
                    self.draw(victim, max(0, 5-len(self.players[victim].hand)))
                    self.log.append(f'P{victim} Lucky Egg draws to {len(self.players[victim].hand)} cards')
                self.players[victim].bench.remove(pokemon)
                self.players[scorer].points += pokemon.card.points
                self.log.append(f'P{victim} bench KO {pokemon.card.name}; P{scorer} score {self.players[scorer].points}')
                if self.players[scorer].points >= 3:
                    self.finished = True
                    self.winner = scorer

    def use_ability(self, pokemon: InPlay, target: InPlay | None = None):
        """Explicit activation of Greninja's once-per-turn Water Shuriken."""
        i = self.current
        self._require_action(i)
        own, other = self.players[i], self.players[1-i]
        if pokemon not in own.all_in_play() or pokemon.card.ability != 'water_shuriken':
            raise RuleError('Water Shuriken is unavailable')
        if pokemon.ability_used_turn == self.turn:
            raise RuleError('Water Shuriken already used this turn')
        if target is None:
            target = other.active
        if target not in other.all_in_play():
            raise RuleError('Water Shuriken target not in play')
        pokemon.ability_used_turn = self.turn
        self._damage_target(1-i, target, 20, i, source='Greninja — Water Shuriken')

    def equip_tool(self, tool: Card, target: InPlay):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (tool not in p.hand or tool.kind != 'tool' or
                target not in p.all_in_play() or target.tool is not None):
            raise RuleError('Illegal Pokémon Tool attachment')
        if tool.effect not in ('lucky_egg', 'deceptive_needle'):
            raise UnsupportedEffect('Pokémon Tool effect has no handler')
        p.hand.remove(tool)
        target.tool = tool
        self.log.append(f'P{i} attaches {tool.name} to {target.card.name}')

    def play_trainer(self, card: Card, target: InPlay | None = None):
        i = self.current
        self._require_action(i)
        p, opp = self.players[i], self.players[1-i]
        if card not in p.hand or card.kind not in ('supporter', 'item'):
            raise RuleError('Illegal trainer')
        if p.item_locked and card.kind == 'item':
            raise RuleError('Item cards locked by Jingly Noise')
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
        elif card.effect == 'copycat':
            p.hand.remove(card)
            p.deck.extend(p.hand)
            p.hand.clear()
            self.rng.shuffle(p.deck)
            self.draw(i, len(opp.hand))
        elif card.effect == 'center_lady':
            candidates = p.all_in_play()
            if target is None:
                target = max(candidates, key=lambda x:(x.damage, x.status == 'asleep')) if candidates else None
            if target is None or target not in candidates:
                raise RuleError('Pokémon Center Lady target must be your Pokémon')
            if target.damage == 0 and not target.status:
                raise RuleError('Pokémon Center Lady has nothing to heal')
            target.damage = max(0,target.damage-30)
            target.status = ''
            p.hand.remove(card)
        elif card.effect == 'repel':
            if not opp.active or opp.active.card.stage != 0 or not opp.bench:
                raise RuleError('Repel requires opposing Basic Active and Bench')
            # The affected opponent chooses which Pokémon becomes Active.
            if target is None:
                target = max(opp.bench, key=lambda x:(len(x.energy), x.card.hp-x.damage))
            if target not in opp.bench:
                raise RuleError('Repel replacement must come from opponent Bench')
            p.hand.remove(card)
            old=opp.active
            old.status=''
            opp.bench.remove(target)
            opp.active=target
            opp.bench.append(old)
        elif card.effect == 'mars':
            p.hand.remove(card)
            opp.deck.extend(opp.hand)
            opp.hand.clear()
            self.rng.shuffle(opp.deck)
            self.draw(1-i, max(0, 3 - opp.points))
        elif card.effect == 'cyrus':
            candidates = [x for x in opp.bench if x.damage > 0]
            if not candidates:
                raise RuleError('No damaged benched Pokémon for Cyrus')
            if target is None:
                target = max(candidates, key=lambda x:(x.damage, -(x.card.hp-x.damage)))
            if target not in candidates:
                raise RuleError('Cyrus target must be damaged and benched')
            p.hand.remove(card)
            old = opp.active
            opp.bench.remove(target)
            opp.active = target
            if old:
                old.status = ''
                opp.bench.append(old)
        elif card.effect == 'lucky_ice_pop':
            if not p.active or p.active.damage == 0:
                raise RuleError('Lucky Ice Pop needs a damaged Active Pokémon')
            p.hand.remove(card)
            p.active.damage = max(0, p.active.damage - 20)
            if self.rng.choice((True, False)):
                p.hand.append(card)
                self.log.append('Lucky Ice Pop coin: heads, returned to hand')
            else:
                self.log.append('Lucky Ice Pop coin: tails, discarded')
        elif card.effect == 'x_speed':
            p.hand.remove(card)
            p.retreat_discount += 1
        elif card.effect == 'field_blower':
            found = [x for x in opp.all_in_play() if x.tool is not None] or [
                x for x in p.all_in_play() if x.tool is not None]
            if not found:
                raise RuleError('Field Blower has no Pokémon Tool to discard')
            if target is None:
                target = found[0]
            if target not in found:
                raise RuleError('Field Blower target must have a Tool')
            target.tool = None
            p.hand.remove(card)
        else:
            raise UnsupportedEffect('Trainer effect requires handler')
        if card.kind == 'supporter':
            p.supporter_used = True
        self.log.append(f'P{i} plays {card.name}')

    def retreat(self, incoming: InPlay):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if p.retreated or not p.active or incoming not in p.bench or p.active.status == 'asleep':
            raise RuleError('Illegal retreat')
        need = max(0, p.active.card.retreat - p.retreat_discount)
        if len(p.active.energy) < need:
            raise RuleError('Not enough energy to retreat')
        del p.active.energy[:need]
        current = p.active
        current.status = ''  # Moving to Bench removes Special Conditions.
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
        me, them = self.players[i], self.players[1-i]
        if not me.active or not them.active or selected not in me.active.card.attacks:
            raise RuleError('Illegal attack')
        if me.active.status == 'asleep':
            raise RuleError('An Asleep Pokémon cannot attack')
        if not self.can_pay_energy(me.active, selected):
            raise RuleError('Attack energy cost unpaid')
        valid = ('', 'discard_2_global_random', 'heal_self_30', 'coin_bonus_30',
                 'bench_plus_30', 'snipe_20_bench', 'recoil_20',
                 'discard_opponent_supporter', 'item_lock_next_turn', 'sleep_active')
        if selected.effect not in valid:
            raise UnsupportedEffect('Attack effect requires handler')
        damage = selected.damage
        if selected.effect == 'coin_bonus_30':
            heads = self.rng.choice((True, False))
            self.log.append(f'P{i} coin flip: {"heads" if heads else "tails"}')
            if heads:
                damage += 30
        if selected.effect == 'bench_plus_30':
            damage += 30 * len(me.bench)
        if damage > 0 and them.active.card.weakness == me.active.card.element:
            damage += 20
        them.active.damage += damage
        self.log.append(f'P{i} {selected.name}, {damage} damage')
        if selected.effect == 'item_lock_next_turn':
            them.item_locked = True
        if selected.effect == 'sleep_active':
            them.active.status = 'asleep'
        if selected.effect == 'discard_opponent_supporter':
            supporters = [c for c in them.hand if c.kind == 'supporter']
            if supporters:
                chosen = supporters[0]  # deterministic baseline choice, not optimal
                them.hand.remove(chosen)
                self.log.append(f'Mega Absol ex discards opposing Supporter: {chosen.name}')
        if selected.effect == 'heal_self_30':
            old = me.active.damage
            me.active.damage = max(0, me.active.damage - 30)
            self.log.append(f'P{i} heals {old-me.active.damage}')
        if selected.effect == 'discard_2_global_random':
            for _ in range(2):
                pool = [pokemon for owner in self.players
                        for pokemon in owner.all_in_play()
                        for _ in pokemon.energy]
                if not pool:
                    break
                pokemon = self.rng.choice(pool)
                pokemon.energy.pop(self.rng.randrange(len(pokemon.energy)))
                self.log.append(f'{pokemon.card.name} discards 1 random Energy')
        # Hoopa side effects resolve before the KO checks; neither bonus applies
        # type weakness to Bench damage or self-damage.
        if not self.finished and selected.effect == 'snipe_20_bench' and them.bench:
            target = min(them.bench, key=lambda x:(x.card.hp-x.damage, x.card.hp))
            self._damage_target(1-i, target, 20, i, source='Hoopa ex — Shadow Bullet', attack_damage=True)
        if selected.effect == 'recoil_20':
            me.active.damage += 20
            self.log.append(f'P{i} Hoopa ex recoil: 20 damage')
        if not self.finished and them.active and them.active.damage >= them.active.card.hp:
            self._knockout(1-i, i, from_attack=True)
        if not self.finished and me.active and me.active.damage >= me.active.card.hp:
            self._knockout(i, 1-i)
        self.end_turn()

    def _knockout(self, victim: int, scorer: int, from_attack=False):
        p = self.players[victim]
        if not p.active:
            raise RuleError('No active Pokémon to KO')
        knocked = p.active
        p.active = None
        if (from_attack and victim != scorer and knocked.tool is not None and
                knocked.tool.effect == 'lucky_egg'):
            self.draw(victim, max(0, 5 - len(p.hand)))
            self.log.append(f'P{victim} Lucky Egg draws to {len(p.hand)} cards')
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
        # A Deceptive Needle attached to the current Darkness Active Pokémon
        # triggers at end of its owner's turn, even if it did not attack.
        p = self.players[self.current]
        if (not self.finished and p.active and p.active.card.element == 'darkness'
                and p.active.tool and p.active.tool.effect == 'deceptive_needle'):
            self._damage_target(1-self.current, self.players[1-self.current].active,
                                10, self.current, source='Deceptive Needle')
        # Special Conditions check between turns. Asleep gets one coin flip per
        # active affected Pokémon, even on the turn it became Asleep.
        if not self.finished:
            for player_idx, owner in enumerate(self.players):
                if owner.active and owner.active.status == 'asleep':
                    if self.rng.choice((True, False)):
                        owner.active.status = ''
                        self.log.append(f'P{player_idx} wakes from Asleep')
                    else:
                        self.log.append(f'P{player_idx} remains Asleep')
        # A Chingling lock lasts through this player's turn only.
        self.players[self.current].item_locked = False
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

    @staticmethod
    def select_energy_target(player: Player) -> InPlay | None:
        """Avoid charging a dead-end attack for a single-type Energy Zone.

        This is a lightweight heuristic, not optimal play. If every Pokémon
        currently in play lacks a usable attack we fall back to Active because
        it may evolve in a later turn.
        """
        if not player.active:
            return player.bench[0] if player.bench else None
        element = player.energy_types[0]
        preferred = []
        for pokemon in player.all_in_play():
            attacks = [a for a in pokemon.card.attacks
                       if a.cost and all(t in (element, 'colorless') for t in a.cost)]
            pending = [a for a in attacks if len(pokemon.energy) < len(a.cost)]
            if not pending:
                continue
            # Damage comes first; Active wins a tie to reduce unnecessary stall.
            strongest = max(a.damage + 30 * (a.effect == 'bench_plus_30') for a in pending)
            score = (strongest, pokemon is player.active, pokemon.card.stage,
                     -len(pokemon.energy))
            preferred.append((score, pokemon))
        return max(preferred, key=lambda x:x[0])[1] if preferred else player.active

    def play_turn(self, battle: Battle):
        i = battle.current
        p = battle.players[i]
        battle.begin_turn()
        # Items before evolution, prioritizing search for a basic.
        for c in list(p.hand):
            if c.effect == 'pokeball' and not p.item_locked and len(p.bench) < 3 and any(x.kind=='pokemon' and x.stage==0 for x in p.deck):
                battle.play_trainer(c)
        for c in list(p.hand):
            if c.kind == 'pokemon' and c.stage == 0 and len(p.bench) < 3:
                battle.bench_basic(c)
        # Apply field-blower only if the opponent has a useful Tool to remove.
        for c in list(p.hand):
            if c.effect == 'field_blower' and not p.item_locked and any(x.tool for x in battle.players[1-i].all_in_play()):
                battle.play_trainer(c)
        for tool in [c for c in list(p.hand) if c.kind=='tool']:
            target = p.active if p.active and p.active.tool is None else next(
                (x for x in p.bench if x.tool is None), None)
            if target:
                battle.equip_tool(tool,target)
        # Candy first, if the corresponding Stage 1 -> Basic lineage is known.
        for candy in [c for c in p.hand if c.effect == 'rare_candy' and not p.item_locked]:
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
        # Use Water Shuriken from either Active or Bench; prefer a knockout.
        for pokemon in list(p.all_in_play()):
            if pokemon.card.ability == 'water_shuriken' and pokemon.ability_used_turn != battle.turn:
                enemy = battle.players[1-i]
                targets = enemy.all_in_play()
                if targets:
                    victim = min(targets, key=lambda x: x.card.hp - x.damage)
                    battle.use_ability(pokemon, victim)
                    if battle.finished:
                        battle.end_turn()
                        return
        for c in list(p.hand):
            if c.effect == 'research' and len(p.hand) <= 8 and p.deck:
                battle.play_trainer(c)
                break
        # A conservative baseline for other supported Supporters and healing items.
        for c in list(p.hand):
            if c.effect == 'cyrus' and not p.supporter_used and any(x.damage for x in battle.players[1-i].bench):
                battle.play_trainer(c)
                break
        for c in list(p.hand):
            if c.effect == 'copycat' and not p.supporter_used and len(p.hand) <= 3 and len(battle.players[1-i].hand) > len(p.hand):
                battle.play_trainer(c)
                break
        for c in list(p.hand):
            if c.effect == 'center_lady' and not p.supporter_used and any(x.damage >= 30 or x.status for x in p.all_in_play()):
                battle.play_trainer(c)
                break
        for c in list(p.hand):
            if c.effect == 'lucky_ice_pop' and not p.item_locked and p.active and p.active.damage >= 20:
                battle.play_trainer(c)
                break
        # New basics obtained after draw.
        for c in list(p.hand):
            if c.kind == 'pokemon' and c.stage == 0 and len(p.bench) < 3:
                battle.bench_basic(c)
        if not p.energy_used and not (battle.turn == 0 and battle.first == i):
            # Single-type energy policy: favor a Pokémon with a payable attack.
            target = self.select_energy_target(p)
            if target:
                battle.attach(target)
                if battle.finished:
                    battle.end_turn()
                    return
        if p.active:
            options = [a for a in p.active.card.attacks if battle.can_pay_energy(p.active,a)]
            if options and p.active.status != 'asleep':
                battle.attack(max(options,key=lambda a:a.damage + (15 if a.effect=='coin_bonus_30' else 0)))
                return
        battle.end_turn()


def play_fixture_match(left, right, seed=0, energy_left=('water',), energy_right=('water',), line_map=None):
    battle = Battle(left, right, energy_left, energy_right, seed)
    agent = RuleAgent(line_map)
    while not battle.finished:
        agent.play_turn(battle)
    return battle
