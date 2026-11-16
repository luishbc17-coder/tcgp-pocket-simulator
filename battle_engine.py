"""TCG Pocket rules kernel, v0.8.4.

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
ENGINE_API_VERSION = 2  # v0.8.3.1 batch/audit protocol: supports forced first player

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
    tags: tuple[str, ...] = ()  # source special_tags, including 'future'


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
    mirror_shot_pending: bool = False  # next turn: coin on attack attempt
    pre_evolutions: list[Card] = field(default_factory=list)  # card stack for Turo

    @property
    def max_hp(self) -> int:
        """Giant Cape increases maximum HP; its removal can cause a KO."""
        return self.card.hp + (20 if self.tool and self.tool.effect == 'giant_cape' else 0)


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
    stadium_used: bool = False
    stadium_action_used: bool = False
    energy_discard: Counter = field(default_factory=Counter)

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
                 energy_left=('water',), energy_right=('water',), seed=0,
                 force_first: int | None = None):
        validate_deck(left, tuple(energy_left))
        validate_deck(right, tuple(energy_right))
        if len(energy_left) != 1 or len(energy_right) != 1:
            raise UnsupportedEffect('Mixed-type Energy Zone not implemented')
        self.rng = random.Random(seed)
        self.players = [Player(list(left), tuple(energy_left)),
                        Player(list(right), tuple(energy_right))]
        self.turn = 0
        if force_first is not None and force_first not in (0, 1):
            raise RuleError('force_first must be P0, P1 or None')
        self.current = self.rng.randrange(2) if force_first is None else force_first
        self.first = self.current
        self.winner: int | None = None
        self.finished = False
        self.log: list[str] = []
        self._in_turn = False
        self.stadium: Card | None = None
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
        p.stadium_used = False
        p.stadium_action_used = False
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

    def bench_basic(self, card: Card, trigger_bench_ability: bool = False):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if card not in p.hand or card.kind != 'pokemon' or card.stage != 0 or len(p.bench) >= 3:
            raise RuleError('Cannot bench Pokémon')
        p.hand.remove(card)
        incoming = InPlay(card, entered_at=self.turn)
        p.bench.append(incoming)
        self.log.append(f'P{i} benches {card.name}')
        if trigger_bench_ability and card.ability == 'legendary_drive' and p.active:
            all_energy = [e for mon in p.all_in_play() if mon is not incoming for e in mon.energy]
            for mon in p.all_in_play():
                if mon is not incoming:
                    mon.energy.clear()
            incoming.energy.extend(all_energy)
            old = p.active
            p.bench.remove(incoming)
            p.active = incoming
            old.status = ''
            p.bench.append(old)
            self.log.append(f'P{i} Miraidon ex — Legendary Drive: switches with {old.card.name}; transfers {len(all_energy)} Energy')
        elif trigger_bench_ability and card.ability != 'legendary_drive':
            raise RuleError('No triggered bench ability on this Pokémon')

    def evolve(self, target: InPlay, evolution: Card):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        boosted = target is p.active and target.card.ability == 'boosted_evolution'
        if (p.turns_taken == 1 and not boosted) or target not in p.all_in_play():
            raise RuleError('Evolution not allowed now')
        if ((target.entered_at == self.turn and not boosted) or target.evolved_at == self.turn or
            evolution not in p.hand or evolution.kind != 'pokemon' or
            evolution.stage != target.card.stage + 1 or
            evolution.evolves_from.casefold() != target.card.name.casefold()):
            raise RuleError('Illegal evolution')
        old_name = target.card.name
        old_spot = 'Ativo' if target is p.active else 'Banco'
        p.hand.remove(evolution)
        target.pre_evolutions.append(target.card)
        target.card = evolution
        target.status = ''  # Evolving removes Special Conditions.
        target.mirror_shot_pending = False
        target.evolved_at = self.turn
        self.log.append(f'P{i} evolves {old_name} -> {evolution.name} ({old_spot})')
        if target.damage >= target.max_hp:
            self._damage_target(i, target, 0, 1-i, source=f'Evolution HP change: {evolution.name}')
            return
        # Ignition triggers only when Charmeleon is played from hand to evolve.
        # It is separate from the regular once-per-turn Energy attachment.
        if (evolution.ability == 'ignition' and p.energy_types == ('fire',)
                and p.active and p.active.card.element == 'fire'):
            self._zone_attach(i, p.active, 'fire', 'Charmeleon — Ignition')

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
        old_name = target.card.name
        old_spot = 'Ativo' if target is p.active else 'Banco'
        p.hand.remove(candy)
        p.hand.remove(evolution)
        target.pre_evolutions.append(target.card)
        target.card = evolution
        target.status = ''  # Evolving removes Special Conditions.
        target.mirror_shot_pending = False
        target.evolved_at = self.turn
        self.log.append(f'P{i} Rare Candy: {old_name} -> {evolution.name} ({old_spot})')
        if target.damage >= target.max_hp:
            self._damage_target(i, target, 0, 1-i, source=f'Rare Candy HP change: {evolution.name}')
            return

    def _zone_attach(self, i: int, target: InPlay, energy: str, source: str):
        target.energy.append(energy)
        self.log.append(f'P{i} {source}: +1 {energy} to {target.card.name}')
        amount = {'nightmare_aura': 20, 'flame_aura': 30}.get(target.card.ability, 0)
        expected = {'nightmare_aura': 'darkness', 'flame_aura': 'fire'}
        if amount and energy == expected[target.card.ability]:
            self._damage_target(1-i, self.players[1-i].active, amount, i,
                                source=f'{target.card.name} — {target.card.ability}')

    def attach(self, target: InPlay):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (target not in p.all_in_play() or p.energy_used or
            (self.turn == 0 and i == self.first)):
            raise RuleError('Energy attachment unavailable')
        energy = p.energy_types[0]
        p.energy_used = True
        self._zone_attach(i, target, energy, 'manual energy')

    @staticmethod
    def attack_damage_after_tool(pokemon: InPlay, amount: int, attacker_card: Card | None = None) -> int:
        """Only attacks (not abilities or self damage) are reduced by Eviolite."""
        if (attacker_card is not None and attacker_card.name.casefold().endswith(' ex')
                and pokemon.card.ability == 'safeguard_ex'):
            return 0
        if (pokemon.tool and pokemon.tool.effect == 'eviolite'
                and pokemon.card.stage == 0):
            return max(0, amount - 20)
        return amount

    def _damage_target(self, victim: int, pokemon: InPlay | None, amount: int,
                       scorer: int, source: str, attack_damage=False):
        """Apply direct/bench damage (without weakness), then resolve KO.

        Does not model simultaneous KO arbitration or prevention effects yet.
        """
        if pokemon is None or self.finished or amount < 0:
            return
        if attack_damage and victim != scorer:
            amount = self.attack_damage_after_tool(pokemon, amount, self.players[scorer].active.card if self.players[scorer].active else None)
        pokemon.damage += amount
        self.log.append(f'{source}: {amount} damage to P{victim} {pokemon.card.name}')
        if pokemon.damage >= pokemon.max_hp:
            if self.players[victim].active is pokemon:
                self._knockout(victim, scorer, from_attack=attack_damage)
            elif pokemon in self.players[victim].bench:
                self.players[victim].energy_discard.update(pokemon.energy)
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
        """Execute only explicit, compiled once-per-turn abilities.

        Volt Charge/Ice Maker attach one extra typed Energy from a *single-type*
        Energy Zone and do not consume the regular manual attachment.
        """
        i = self.current
        self._require_action(i)
        own, other = self.players[i], self.players[1-i]
        if pokemon not in own.all_in_play() or pokemon.ability_used_turn == self.turn:
            raise RuleError('Ability is unavailable or already used this turn')
        effect = pokemon.card.ability
        if effect == 'water_shuriken':
            if target is None:
                target = other.active
            if target not in other.all_in_play():
                raise RuleError('Water Shuriken target not in play')
            pokemon.ability_used_turn = self.turn
            self._damage_target(1-i, target, 20, i, source='Greninja — Water Shuriken')
        elif effect == 'volt_charge':
            if own.energy_types != ('lightning',):
                raise RuleError('Volt Charge requires Lightning Energy Zone')
            pokemon.ability_used_turn = self.turn
            self._zone_attach(i, pokemon, 'lightning', 'Magneton — Volt Charge')
        elif effect == 'ice_maker':
            if (own.energy_types != ('water',) or not own.active
                    or own.active.card.element != 'water'):
                raise RuleError('Ice Maker requires Active Water Pokémon and Water Energy Zone')
            pokemon.ability_used_turn = self.turn
            self._zone_attach(i, own.active, 'water', 'Baxcalibur — Ice Maker')
        elif effect == 'roar_in_unison':
            if own.energy_types != ('darkness',):
                raise RuleError('Roar in Unison requires Darkness Energy Zone')
            pokemon.ability_used_turn = self.turn
            self._zone_attach(i, pokemon, 'darkness', 'Hydreigon — Roar in Unison')
            self._zone_attach(i, pokemon, 'darkness', 'Hydreigon — Roar in Unison')
            self._damage_target(i, pokemon, 30, 1-i, source='Hydreigon — Roar in Unison recoil')
        else:
            raise RuleError('No activatable ability handler for this Pokémon')

    def equip_tool(self, tool: Card, target: InPlay):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (tool not in p.hand or tool.kind != 'tool' or
                target not in p.all_in_play() or target.tool is not None):
            raise RuleError('Illegal Pokémon Tool attachment')
        if tool.effect not in ('lucky_egg', 'deceptive_needle',
                               'giant_cape', 'eviolite', 'inflatable_boat', 'small_balloon'):
            raise UnsupportedEffect('Pokémon Tool effect has no handler')
        p.hand.remove(tool)
        target.tool = tool
        self.log.append(f'P{i} attaches {tool.name} to {target.card.name}')

    def play_stadium(self, card: Card):
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if (card.kind != 'stadium' or card not in p.hand or p.stadium_used
                or (self.stadium and self.stadium.name == card.name)
                or card.effect not in ('training_area','rainbow_cave')):
            raise RuleError('Illegal Stadium card play')
        previous = self.stadium
        p.hand.remove(card)
        p.stadium_used = True
        self.stadium = card
        self.log.append(f'P{i} stadium: {card.name}' + (f' (replaces {previous.name})' if previous else ''))

    def use_stadium(self):
        """Rainbow Cave advances the Energy Zone; with a single-type Zone, the
        generated type is necessarily unchanged. This does NOT enable mixed Zones.
        """
        i = self.current
        self._require_action(i)
        p = self.players[i]
        if not self.stadium or self.stadium.effect != 'rainbow_cave' or p.stadium_action_used:
            raise RuleError('Rainbow Cave unavailable or already used this turn')
        p.stadium_action_used = True
        self.log.append(f'P{i} Rainbow Cave re-generates {p.energy_types[0]} (mono-type Energy Zone)')

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
        elif card.effect == 'serenas_choice':
            if not p.deck:
                raise RuleError("Serena's Choice requires cards in deck")
            p.hand.remove(card)
            viewed = [p.deck.pop() for _ in range(min(3, len(p.deck)))]
            # Choose from viewed cards only, without knowing future deck order.
            priority = {'pokemon': 4, 'item': 3, 'supporter': 2, 'tool': 1}
            chosen = max(viewed, key=lambda c: (priority.get(c.kind, 0), c.stage, c.hp))
            viewed.remove(chosen)
            p.hand.append(chosen)
            p.deck.extend(viewed)
            self.rng.shuffle(p.deck)
            self.log.append(f"P{i} Serena's Choice: selects {chosen.name} from {len(viewed)+1} cards")
        elif card.effect in ('lisia','clemont'):
            if card.effect == 'lisia':
                matching = [x for x in p.deck if x.kind == 'pokemon' and x.stage == 0 and x.hp <= 50]
            else:
                matching = [x for x in p.deck if x.name in ('Magneton', 'Heliolisk', "Clemont's Backpack")]
            if not matching:
                raise RuleError(f'{card.name}: no eligible cards/space')
            p.hand.remove(card)
            for _ in range(min(2,len(matching),10-len(p.hand))):
                chosen = self.rng.choice(matching)
                matching.remove(chosen)
                p.deck.remove(chosen)
                p.hand.append(chosen)
                self.log.append(f'P{i} {card.name}: searches {chosen.name}')
        elif card.effect == 'may':
            matching = [x for x in p.deck if x.kind == 'pokemon']
            if not matching:
                raise RuleError('May needs Pokémon in deck and hand space')
            p.hand.remove(card)
            drawn = []
            for _ in range(min(2,len(matching),10-len(p.hand))):
                chosen = self.rng.choice(matching)
                matching.remove(chosen)
                p.deck.remove(chosen)
                p.hand.append(chosen)
                drawn.append(chosen)
            # Shuffle as many Pokémon back as were actually found.
            for _ in drawn:
                returns = [x for x in p.hand if x.kind == 'pokemon']
                if not returns:
                    raise RuleError('May cannot return searched Pokémon')
                chosen = min(returns, key=lambda x:(x.stage, x.hp))
                p.hand.remove(chosen)
                p.deck.append(chosen)
            self.rng.shuffle(p.deck)
            self.log.append(f'P{i} May searches {len(drawn)} Pokémon and returns {len(drawn)}')
        elif card.effect == 'wally_colorless':
            # Wally explicitly takes a *Colorless* Energy from the Zone.
            # This is an additional Supporter attachment, independent of the
            # mono-type Energy Zone configuration and manual attachment.
            candidates = [mon for mon in p.all_in_play() if mon.card.stage == 2]
            if target is None:
                target = max(candidates, key=lambda mon: (
                    mon is p.active, -len(mon.energy))) if candidates else None
            if target is None or target not in candidates:
                raise RuleError('Wally needs a Stage 2 Pokémon in play')
            p.hand.remove(card)
            self._zone_attach(i, target, 'colorless', 'Wally')
        elif card.effect == 'professor_turo':
            # special_tags['future'] comes from the battle catalogue. A
            # Future-looking name alone never qualifies for Turo.
            candidates = [mon for mon in p.all_in_play() if 'future' in mon.card.tags]
            if target is None:
                bench_candidates = [mon for mon in p.bench if mon in candidates]
                target = max(bench_candidates, key=lambda mon: (
                    mon.damage, -len(mon.energy))) if bench_candidates else (
                    p.active if p.active in candidates and p.bench else None)
            if target is None or target not in candidates:
                raise RuleError('Professor Turo needs a Future Pokémon in play')
            if target is p.active and not p.bench:
                # Avoid leaving no Active Pokémon in a game that continues.
                raise RuleError('Professor Turo cannot remove the only Active Pokémon')
            p.hand.remove(card)
            if target is p.active:
                replacement = max(p.bench, key=lambda mon:(len(mon.energy),mon.max_hp-mon.damage))
                p.bench.remove(replacement)
                p.active = replacement
                self.log.append(f'P{i} Professor Turo promotes {replacement.card.name}')
            else:
                p.bench.remove(target)
            p.energy_discard.update(target.energy)
            returned = target.pre_evolutions + [target.card]
            p.deck.extend(returned)
            self.rng.shuffle(p.deck)
            self.log.append(f'P{i} Professor Turo shuffles {target.card.name} '
                            f'({len(returned)} Pokémon card(s)) into deck; '
                            f'discards {len(target.energy)} Energy')
        elif card.effect == 'flame_patch':
            if (not p.active or p.active.card.element != 'fire'
                    or p.energy_discard['fire'] <= 0):
                raise RuleError('Flame Patch requires Active Fire Pokémon and discarded Fire Energy')
            p.hand.remove(card)
            p.energy_discard['fire'] -= 1
            p.active.energy.append('fire')  # discard pile != Energy Zone; no Flame Aura trigger
            self.log.append(f'P{i} Flame Patch: +1 discarded Fire to {p.active.card.name}')
        elif card.effect == 'copycat':
            p.hand.remove(card)
            shuffled_count = len(p.hand)
            opponent_hand = len(opp.hand)
            p.deck.extend(p.hand)
            p.hand.clear()
            self.rng.shuffle(p.deck)
            self.draw(i, opponent_hand)
            self.log.append(f'P{i} Copycat: shuffles {shuffled_count} hand cards, draws {len(p.hand)} (opponent had {opponent_hand})')
        elif card.effect == 'center_lady':
            candidates = p.all_in_play()
            if target is None:
                target = max(candidates, key=lambda x:(x.damage, x.status == 'asleep')) if candidates else None
            if target is None or target not in candidates:
                raise RuleError('Pokémon Center Lady target must be your Pokémon')
            if target.damage == 0 and not target.status:
                raise RuleError('Pokémon Center Lady has nothing to heal')
            amount = min(30, target.damage)
            target.damage = max(0,target.damage-30)
            target.status = ''
            p.hand.remove(card)
            self.log.append(f'P{i} Pokémon Center Lady heals {amount} from {target.card.name}, clears status')
        elif card.effect in ('sabrina','blues_provocation'):
            if card.effect == 'blues_provocation' and not any(
                    m.card.name in ('Venusaur','Charizard','Blastoise','Pidgeot') for m in p.all_in_play()):
                raise RuleError("Blue's Provocation requires a named Pokémon in play")
            if not opp.active or not opp.bench:
                raise RuleError('Opponent has no Benched Pokémon for switching')
            if target is None:
                target = max(opp.bench,key=lambda x:(len(x.energy),x.max_hp-x.damage)) if card.effect == 'sabrina' else min(opp.bench,key=lambda x:(x.max_hp-x.damage,x.card.points))
            if target not in opp.bench:
                raise RuleError('Switch target must be opposing Benched Pokémon')
            p.hand.remove(card)
            old = opp.active
            old.status = ''
            old.mirror_shot_pending = False
            opp.bench.remove(target)
            opp.active = target
            opp.bench.append(old)
            self.log.append(f'P{i} {card.name}: switches opponent {old.card.name} -> {target.card.name}')
        elif card.effect == 'repel':
            if not opp.active or opp.active.card.stage != 0 or not opp.bench:
                raise RuleError('Repel requires opposing Basic Active and Bench')
            # The affected opponent chooses which Pokémon becomes Active.
            if target is None:
                target = max(opp.bench, key=lambda x:(len(x.energy), x.max_hp-x.damage))
            if target not in opp.bench:
                raise RuleError('Repel replacement must come from opponent Bench')
            p.hand.remove(card)
            old=opp.active
            old.status=''
            old.mirror_shot_pending = False
            opp.bench.remove(target)
            opp.active=target
            opp.bench.append(old)
            self.log.append(f'P{i} Repel switches P{1-i} Active {old.card.name} -> {target.card.name} (Basic; opposing Bench)')
        elif card.effect == 'mars':
            p.hand.remove(card)
            shuffled_count = len(opp.hand)
            draw_count = max(0, 3 - opp.points)
            opp.deck.extend(opp.hand)
            opp.hand.clear()
            self.rng.shuffle(opp.deck)
            self.draw(1-i, draw_count)
            self.log.append(f'P{i} Mars: P{1-i} shuffles {shuffled_count} hand cards and draws {len(opp.hand)} (remaining points {draw_count})')
        elif card.effect == 'cyrus':
            candidates = [x for x in opp.bench if x.damage > 0]
            if not candidates:
                raise RuleError('No damaged benched Pokémon for Cyrus')
            if target is None:
                target = max(candidates, key=lambda x:(x.damage, -(x.max_hp-x.damage)))
            if target not in candidates:
                raise RuleError('Cyrus target must be damaged and benched')
            p.hand.remove(card)
            old = opp.active
            opp.bench.remove(target)
            opp.active = target
            if old:
                old.status = ''
                old.mirror_shot_pending = False
                opp.bench.append(old)
            self.log.append(f'P{i} Cyrus switches P{1-i} Active {old.card.name if old else "none"} -> {target.card.name} ({target.damage} damage; opposing Bench)')
        elif card.effect == 'lucky_ice_pop':
            if not p.active or p.active.damage == 0:
                raise RuleError('Lucky Ice Pop needs a damaged Active Pokémon')
            p.hand.remove(card)
            healed = min(p.active.damage, 20)
            p.active.damage = max(0, p.active.damage - 20)
            self.log.append(f'P{i} Lucky Ice Pop heals {healed} from {p.active.card.name}')
            if self.rng.choice((True, False)):
                p.hand.append(card)
                self.log.append('Lucky Ice Pop coin: heads, returned to hand')
            else:
                self.log.append('Lucky Ice Pop coin: tails, discarded')
        elif card.effect == 'x_speed':
            p.hand.remove(card)
            p.retreat_discount += 1
            self.log.append(f'P{i} X Speed: retreat cost discounted by {p.retreat_discount} this turn')
        elif card.effect == 'field_blower':
            found = [x for x in opp.all_in_play() if x.tool is not None] or [
                x for x in p.all_in_play() if x.tool is not None]
            if not found and self.stadium is not None:
                old_stadium = self.stadium.name
                self.stadium = None
                p.hand.remove(card)
                self.log.append(f'P{i} Field Blower: discards stadium {old_stadium}')
                self.log.append(f'P{i} plays {card.name}')
                return
            if not found:
                raise RuleError('Field Blower has no Pokémon Tool or Stadium to discard')
            if target is None:
                target = found[0]
            if target not in found:
                raise RuleError('Field Blower target must have a Tool')
            removed = target.tool.name
            target.tool = None
            p.hand.remove(card)
            owner = i if target in p.all_in_play() else 1-i
            self.log.append(f'P{i} Field Blower: removes {removed} from P{owner} {target.card.name}')
            if target.damage >= target.max_hp:
                self._damage_target(owner, target, 0, 1-owner, source=f'{removed} removed')
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
        boat = bool(p.active.tool and p.active.tool.effect == 'inflatable_boat'
                    and p.active.card.element == 'water')
        balloon = bool(p.active.tool and p.active.tool.effect == 'small_balloon'
                       and p.active.card.stage == 0)
        need = max(0, p.active.card.retreat - p.retreat_discount - int(boat) - int(balloon))
        if len(p.active.energy) < need:
            raise RuleError('Not enough energy to retreat')
        p.energy_discard.update(p.active.energy[:need])
        del p.active.energy[:need]
        current = p.active
        current.status = ''  # Moving to Bench removes Special Conditions.
        current.mirror_shot_pending = False
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

    def attack(self, selected: Attack, target: InPlay | None = None):
        i = self.current
        self._require_action(i)
        me, them = self.players[i], self.players[1-i]
        if not me.active or not them.active or selected not in me.active.card.attacks:
            raise RuleError('Illegal attack')
        if me.active.status == 'asleep':
            raise RuleError('An Asleep Pokémon cannot attack')
        if not self.can_pay_energy(me.active, selected):
            raise RuleError('Attack energy cost unpaid')
        if me.active.mirror_shot_pending:
            me.active.mirror_shot_pending = False
            heads = self.rng.choice((True,False))
            self.log.append(f'P{i} Mirror Shot restriction: {"heads" if heads else "tails"}')
            if not heads:
                self.end_turn()
                return
        valid = ('', 'discard_2_global_random', 'heal_self_30', 'coin_bonus_30',
                 'bench_plus_30', 'snipe_20_bench', 'recoil_20',
                 'discard_opponent_supporter', 'item_lock_next_turn', 'sleep_active',
                 'both_benches_plus_20', 'fire_extra_2_plus_60', 'recoil_50',
                 'water_snipe_130_discard','mirror_shot',
                 'lightning_each_plus_20','basic_plus_50','discard_all_self_energy')
        if selected.effect not in valid:
            raise UnsupportedEffect('Attack effect requires handler')
        if selected.effect == 'water_snipe_130_discard':
            if target is None:
                target = min(them.all_in_play(), key=lambda x:(x.max_hp-x.damage, x.card.points))
            if target not in them.all_in_play():
                raise RuleError('Diving Icicles target must be an opposing Pokémon in play')
            count = me.active.energy.count('water')
            me.energy_discard.update(['water']*count)
            me.active.energy = [e for e in me.active.energy if e != 'water']
            self.log.append(f'P{i} {me.active.card.name} Diving Icicles: discards {count} Water Energy')
            amount = 130
            if target is them.active and target.card.weakness == me.active.card.element:
                amount += 20
            # Damage to an attacker-selected Pokémon; Bench does not take Weakness.
            self._damage_target(1-i, target, amount, i, source=f'P{i} Diving Icicles', attack_damage=True)
            self.end_turn()
            return
        if target is not None:
            raise RuleError('Explicit attack targets are only supported by Diving Icicles')
        damage = selected.damage
        if selected.effect == 'coin_bonus_30':
            heads = self.rng.choice((True, False))
            self.log.append(f'P{i} coin flip: {"heads" if heads else "tails"}')
            if heads:
                damage += 30
        if selected.effect == 'bench_plus_30':
            damage += 30 * len(me.bench)
        if selected.effect == 'both_benches_plus_20':
            damage += 20 * (len(me.bench) + len(them.bench))
        if selected.effect == 'lightning_each_plus_20':
            damage += 20 * me.active.energy.count('lightning')
        if selected.effect == 'basic_plus_50' and them.active.card.stage == 0:
            damage += 50
        if (self.stadium and self.stadium.effect == 'training_area'
                and me.active.card.stage == 1 and damage > 0):
            damage += 10
        if selected.effect == 'fire_extra_2_plus_60':
            # Blazing Beatdown needs two *additional* Fire on top of RR cost.
            if Counter(me.active.energy)['fire'] >= 4:
                damage += 60
        if damage > 0 and them.active.card.weakness == me.active.card.element:
            damage += 20
        damage = self.attack_damage_after_tool(them.active, damage, me.active.card)
        them.active.damage += damage
        self.log.append(f'P{i} {me.active.card.name} uses {selected.name}, {damage} damage to P{1-i} Active {them.active.card.name}')
        if selected.effect == 'item_lock_next_turn':
            them.item_locked = True
        if selected.effect == 'sleep_active':
            them.active.status = 'asleep'
        if selected.effect == 'mirror_shot':
            them.active.mirror_shot_pending = True
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
                discarded = pokemon.energy.pop(self.rng.randrange(len(pokemon.energy)))
                owner_idx = next(idx for idx,pl in enumerate(self.players) if pokemon in pl.all_in_play())
                self.players[owner_idx].energy_discard[discarded] += 1
                self.log.append(f'{pokemon.card.name} discards 1 random Energy')
        # Resolve *all* attack damage before checking KOs. Pocket treats KOs
        # from the same attack (including recoil and Bench damage) together;
        # stopping after a single first KO produced impossible survivors.
        if selected.effect == 'snipe_20_bench' and them.bench:
            target = min(them.bench, key=lambda x: (x.max_hp-x.damage, x.max_hp))
            bench_damage = self.attack_damage_after_tool(target, 20, me.active.card)
            target.damage += bench_damage
            self.log.append(f'Hoopa ex — Shadow Bullet: {bench_damage} damage to P{1-i} {target.card.name}')
        if selected.effect in ('recoil_20', 'recoil_50'):
            recoil = 20 if selected.effect == 'recoil_20' else 50
            me.active.damage += recoil
            self.log.append(f'P{i} {me.active.card.name} recoil: {recoil} damage')
        if selected.effect == 'discard_all_self_energy':
            me.energy_discard.update(me.active.energy)
            self.log.append(f'P{i} {me.active.card.name}: discards all {len(me.active.energy)} Energy')
            me.active.energy.clear()
        self._resolve_attack_knockouts()
        self.end_turn()

    def _resolve_attack_knockouts(self):
        """Score all KOs from the current attack as one resolution group.

        Winners are determined by *number of satisfied conditions* (3+ points,
        or all opposing Pokemon gone), not by arbitrary processing order.
        """
        # Collect before mutating the field so no KO is lost to early finish.
        knocked = {
            idx: ([p.active] if p.active and p.active.damage >= p.active.max_hp else []) +
                 [x for x in p.bench if x.damage >= x.max_hp]
            for idx, p in enumerate(self.players)
        }
        for victim, victims in knocked.items():
            scorer = 1-victim
            owner = self.players[victim]
            for pokemon in victims:
                if owner.active is pokemon:
                    owner.active = None
                    spot = 'Active'
                else:
                    owner.bench.remove(pokemon)
                    spot = 'Bench'
                owner.energy_discard.update(pokemon.energy)
                if pokemon.tool and pokemon.tool.effect == 'lucky_egg' and victim != self.current:
                    self.draw(victim, max(0, 5-len(owner.hand)))
                    self.log.append(f'P{victim} Lucky Egg draws to {len(owner.hand)} cards')
                self.players[scorer].points += pokemon.card.points
                self.log.append(f'P{victim} {spot} KO {pokemon.card.name}; '
                                f'P{scorer} score {self.players[scorer].points}')
        conditions = [
            (int(p.points >= 3) +
             int(self.players[1-i].active is None and not self.players[1-i].bench))
            for i, p in enumerate(self.players)
        ]
        if max(conditions) > 0:
            self.finished = True
            self.winner = 0 if conditions[0] > conditions[1] else 1 if conditions[1] > conditions[0] else None
            self.log.append(f'Attack end: conditions P0={conditions[0]}, P1={conditions[1]}; '
                            f'result={"tie" if self.winner is None else "P"+str(self.winner)}')
            return
        for idx, p in enumerate(self.players):
            if p.active is None and p.bench:
                replacement = max(p.bench, key=lambda x: (len(x.energy), x.max_hp-x.damage))
                p.bench.remove(replacement)
                p.active = replacement
                self.log.append(f'P{idx} promotes {replacement.card.name}')

    def _knockout(self, victim: int, scorer: int, from_attack=False):
        p = self.players[victim]
        if not p.active:
            raise RuleError('No active Pokémon to KO')
        knocked = p.active
        p.energy_discard.update(knocked.energy)
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
            replacement = max(p.bench, key=lambda x: (len(x.energy), x.max_hp-x.damage))
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
        # Legendary Pulse draws one card only while its owner remains Active
        # at the end of their turn. Respect the hand cap and game-over.
        if not self.finished and p.active and p.active.card.ability == 'legendary_pulse':
            before = len(p.hand)
            self.draw(self.current, 1)
            self.log.append(f'P{self.current} {p.active.card.name} — Legendary Pulse: '
                            f'draws {len(p.hand)-before} card(s)')
        # Bad Dreams fires at the end of either player's turn, before Asleep recovery.
        if not self.finished:
            for owner_idx, owner in enumerate(self.players):
                for mon in list(owner.all_in_play()):
                    foe_active = self.players[1-owner_idx].active
                    if (not self.finished and mon.card.ability == 'bad_dreams'
                            and foe_active and foe_active.status == 'asleep'):
                        self._damage_target(1-owner_idx, foe_active, 20, owner_idx,
                                            source='Darkrai — Bad Dreams')
        # Mirror Shot's restriction ends with the defending player's turn.
        for mon in self.players[self.current].all_in_play():
            mon.mirror_shot_pending = False
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
    def attack_utility(attacker: InPlay, opponent: InPlay, bench: list[InPlay],
                       attack: Attack) -> float:
        """Transparent heuristic: prioritize KOs, damage, and immediate tactical effects.

        Does not look into the other player's hand or future deck order. It is
        a baseline policy for debugging, not a strong/optimal player.
        """
        damage = attack.damage
        if attack.effect == 'lightning_each_plus_20':
            damage += 20 * attacker.energy.count('lightning')
        if attack.effect == 'basic_plus_50' and opponent.card.stage == 0:
            damage += 50
        if attack.effect == 'bench_plus_30':
            damage += 30 * len(bench)
        if attack.effect == 'both_benches_plus_20':
            # Opponent Bench size isn't exposed to this utility; score is a
            # conservative minimum, while actual damage is computed by Battle.
            damage += 20 * len(bench)
        if attack.effect == 'fire_extra_2_plus_60' and Counter(attacker.energy)['fire'] >= 4:
            damage += 60
        if attack.effect == 'coin_bonus_30':
            damage += 15  # expected value of one fair 30-damage coin flip
        if damage > 0 and opponent.card.weakness == attacker.card.element:
            damage += 20
        ko = damage >= opponent.max_hp - opponent.damage
        score = float(damage + (160 + 30 * opponent.card.points if ko else 0))
        if attack.effect == 'water_snipe_130_discard':
            score += 100  # 130 targeted damage minus all Water Energy discarded
        if attack.effect == 'snipe_20_bench':
            score += 15  # extra damage to Bench, no weakness
        if attack.effect == 'heal_self_30':
            score += 0.75 * min(attacker.damage, 30)
        if attack.effect == 'sleep_active':
            score += 12
        if attack.effect == 'item_lock_next_turn':
            score += 10
        if attack.effect == 'discard_opponent_supporter':
            score += 10
        if attack.effect == 'discard_2_global_random':
            score += 5  # may affect both sides; rough small value
        if attack.effect in ('recoil_20', 'recoil_50'):
            recoil = 20 if attack.effect == 'recoil_20' else 50
            score -= recoil
            if attacker.damage + recoil >= attacker.max_hp and not ko:
                score -= 250  # avoid self-KO unless it also secures a KO
        return score

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
            strongest = max(a.damage + 30 * (a.effect == 'bench_plus_30')
                            + 105 * (a.effect == 'water_snipe_130_discard') for a in pending)
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
                battle.bench_basic(c, trigger_bench_ability=(c.ability == 'legendary_drive' and sum(len(x.energy) for x in p.all_in_play()) >= 2))
        for card in list(p.hand):
            if card.kind == 'stadium' and not p.stadium_used and (not battle.stadium or battle.stadium.name != card.name):
                battle.play_stadium(card)
                break
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
                    ((p.turns_taken > 1 and target.entered_at != battle.turn) or (target is p.active and target.card.ability == 'boosted_evolution'))
                    and target.evolved_at != battle.turn):
                    battle.evolve(target,evo)
                    break
        if battle.finished:
            battle.end_turn()
            return
        # Use recovered Fire Energy on Active Fire attackers without treating it
        # as Energy-Zone attachment (Flame Aura must NOT activate).
        for c in list(p.hand):
            if (c.effect == 'flame_patch' and not p.item_locked and p.active
                    and p.active.card.element == 'fire' and p.energy_discard['fire'] > 0):
                battle.play_trainer(c)
        # Activated abilities: energy acceleration and Water Shuriken.
        for pokemon in list(p.all_in_play()):
            if pokemon.ability_used_turn == battle.turn:
                continue
            if pokemon.card.ability == 'water_shuriken':
                enemy = battle.players[1-i]
                targets = enemy.all_in_play()
                if targets:
                    victim = min(targets, key=lambda x: x.max_hp - x.damage)
                    battle.use_ability(pokemon, victim)
                    if battle.finished:
                        battle.end_turn()
                        return
            elif (pokemon.card.ability == 'volt_charge' and p.energy_types == ('lightning',)):
                battle.use_ability(pokemon)
            elif (pokemon.card.ability == 'ice_maker' and p.energy_types == ('water',)
                  and p.active and p.active.card.element == 'water'):
                battle.use_ability(pokemon)
            elif (pokemon.card.ability == 'roar_in_unison' and p.energy_types == ('darkness',)
                  and pokemon.damage + 30 < pokemon.max_hp):
                battle.use_ability(pokemon)
        # Supporters with specific eligibility: only spend them when useful.
        # Wally accelerates Stage 2 Pokémon with genuine Colorless Energy.
        if not p.supporter_used:
            wally = next((c for c in p.hand if c.effect == 'wally_colorless'), None)
            stage2 = [mon for mon in p.all_in_play() if mon.card.stage == 2]
            if wally and stage2:
                target = max(stage2, key=lambda mon:(mon is p.active, -len(mon.energy)))
                battle.play_trainer(wally, target=target)
        # Turo recycles a badly damaged Future Pokémon (no points awarded).
        if not p.supporter_used:
            turo = next((c for c in p.hand if c.effect == 'professor_turo'), None)
            candidates = [mon for mon in p.bench if 'future' in mon.card.tags
                          and mon.damage >= max(30, mon.max_hp // 2)]
            if turo and candidates:
                target = max(candidates,key=lambda mon:(mon.damage / mon.max_hp, -len(mon.energy)))
                battle.play_trainer(turo, target=target)
        for c in list(p.hand):
            if c.effect == 'research' and not p.supporter_used and len(p.hand) <= 8 and p.deck:
                battle.play_trainer(c)
                break
        for c in list(p.hand):
            if c.effect == 'serenas_choice' and not p.supporter_used and p.deck:
                battle.play_trainer(c)
                break
        for c in list(p.hand):
            if c.effect in ('lisia','clemont','may') and not p.supporter_used and p.deck:
                match = {'lisia': lambda x: x.kind=='pokemon' and x.stage==0 and x.hp<=50,
                         'clemont': lambda x: x.name in ('Magneton','Heliolisk',"Clemont's Backpack"),
                         'may': lambda x: x.kind=='pokemon'}[c.effect]
                if any(match(x) for x in p.deck):
                    battle.play_trainer(c)
                    break
        # A conservative baseline for other supported Supporters and healing items.
        for c in list(p.hand):
            if c.effect == 'cyrus' and not p.supporter_used and any(x.damage for x in battle.players[1-i].bench):
                battle.play_trainer(c)
                break
        for c in list(p.hand):
            if c.effect == 'blues_provocation' and not p.supporter_used and battle.players[1-i].bench \
                    and any(mon.card.name in ('Venusaur','Charizard','Blastoise','Pidgeot') for mon in p.all_in_play()):
                target = min(battle.players[1-i].bench, key=lambda x:x.max_hp-x.damage)
                if p.active and any(battle.can_pay_energy(p.active,a) and a.damage >= target.max_hp-target.damage for a in p.active.card.attacks):
                    battle.play_trainer(c,target=target)
                    break
        for c in list(p.hand):
            if c.effect == 'sabrina' and not p.supporter_used and battle.players[1-i].bench and battle.players[1-i].active:
                foe=battle.players[1-i]
                if len(foe.active.energy)>=2 and max(len(x.energy) for x in foe.bench)<len(foe.active.energy):
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
                battle.bench_basic(c, trigger_bench_ability=(c.ability == 'legendary_drive' and sum(len(x.energy) for x in p.all_in_play()) >= 2))
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
                battle.attack(max(options,key=lambda a:self.attack_utility(p.active,battle.players[1-i].active,p.bench,a)))
                return
        battle.end_turn()


def play_fixture_match(left, right, seed=0, energy_left=('water',), energy_right=('water',),
                       line_map=None, force_first=None, battle_cls=Battle, agent_cls=None):
    battle = battle_cls(left, right, energy_left, energy_right, seed, force_first=force_first)
    agent = (agent_cls or RuleAgent)(line_map)
    while not battle.finished:
        agent.play_turn(battle)
    return battle
