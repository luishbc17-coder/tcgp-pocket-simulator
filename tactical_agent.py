"""TCG Pocket Lab 0.9 tactical policy.

Deterministic, explainable one-ply heuristics. No hidden hand/deck peeking in
turn decisions: future evolutions are considered from the player's own cards,
which a deck player is permitted to know (but not their shuffled order).

This is NOT an optimal/learned player. Outcomes are technical only.
"""
from __future__ import annotations
from collections import Counter
from battle_engine import Attack, Battle, InPlay, Player, RuleAgent


class TacticalAgent(RuleAgent):
    policy_name = 'tactical_v09'

    def _compatible(self, attack: Attack, energy: str) -> bool:
        return all(t in (energy, 'colorless') for t in attack.cost)

    def _prospective_attacks(self, target: InPlay, player: Player):
        """Return plausible future moves from own cards, not opponent state.

        Evolved moves are tagged as contingent; this is a prioritization hint,
        never permission to perform an unavailable attack.
        """
        energy = player.energy_types[0]
        candidates = [(attack, 0) for attack in target.card.attacks
                      if self._compatible(attack, energy)]
        name = target.card.name.casefold()
        for card in player.hand + player.deck:
            if card.kind != 'pokemon':
                continue
            stage = 0
            if card.stage == target.card.stage + 1 and card.evolves_from.casefold() == name:
                stage = 1
            elif (target.card.stage == 0 and card.stage == 2
                  and self.line_map.get(card.evolves_from.casefold(), '').casefold() == name):
                stage = 2
            if stage:
                for attack in card.attacks:
                    if self._compatible(attack, energy):
                        candidates.append((attack, stage))
        return candidates

    def select_energy_target(self, player: Player) -> InPlay | None:
        """Charge a reachable move, including an evolution we can eventually play.

        The 0.8.x baseline sometimes placed Psychic energy on Froakie despite
        Greninja's Water attack. 0.9 considers what Swablu can evolve into.
        """
        options = []
        for mon in player.all_in_play():
            if mon.damage >= mon.card.hp:
                continue
            moves = self._prospective_attacks(mon, player)
            for attack, evo_steps in moves:
                cost = len(attack.cost)
                if cost == 0:
                    continue  # free attacks need no charging
                # Don't load energy beyond what's required for this move.
                if len(mon.energy) >= cost:
                    continue
                deficit = cost - len(mon.energy)
                expected_damage = attack.damage
                if attack.effect == 'bench_plus_30':
                    expected_damage += 30 * min(3, len(player.bench))
                if attack.effect == 'coin_bonus_30':
                    expected_damage += 15
                if attack.effect == 'snipe_20_bench':
                    expected_damage += 18
                if attack.effect == 'recoil_20':
                    expected_damage -= 15
                # Value high-impact evolved attacks, but penalize distant goals.
                score = (expected_damage + 24 * (evo_steps > 0) - 11 * evo_steps
                         - 7 * max(0, deficit - 1)
                         + 8 * int(mon is player.active)
                         + 9 * int(len(mon.energy) > 0)
                         + 7 * int(attack.effect == 'discard_opponent_supporter')
                         + 8 * int(mon.card.ability == 'nightmare_aura'))
                # Do not invest heavily into a damaged fragile Pokemon.
                if mon.card.hp - mon.damage <= 30:
                    score -= 35
                options.append((score, mon, attack.name))
        if not options:
            # The only useful energy may be for retreat or future unseen draw.
            # A zero-cost attacker needs no energy, so do not automatically charge it.
            return None
        return max(options, key=lambda item: item[0])[1]

    @staticmethod
    def attack_utility(attacker: InPlay, opponent: InPlay, bench: list[InPlay],
                       attack: Attack) -> float:
        score = RuleAgent.attack_utility(attacker, opponent, bench, attack)
        remaining = opponent.card.hp - opponent.damage
        predicted = attack.damage + (30 * len(bench) if attack.effect == 'bench_plus_30' else 0)
        if predicted > 0 and opponent.card.weakness == attacker.card.element:
            predicted += 20
        if attack.effect == 'snipe_20_bench':
            score += 10  # single-turn pressure across two lanes
        if attack.effect == 'discard_opponent_supporter':
            score += 10
        # Avoid a needless self-KO: scoring may secure 3 points, but that is
        # treated as a special case (simultaneous KOs are handled by the engine).
        if attack.effect == 'recoil_20' and attacker.damage + 20 >= attacker.card.hp:
            score -= 150 if predicted >= remaining else 320
        return score

    def _choose_cyrus_target(self, battle: Battle) -> InPlay | None:
        i = battle.current
        owner, opp = battle.players[i], battle.players[1-i]
        if not owner.active or not opp.active:
            return None
        current = max((self.attack_utility(owner.active, opp.active, owner.bench, a)
                       for a in owner.active.card.attacks if battle.can_pay_energy(owner.active, a)),
                      default=0)
        viable = []
        for target in opp.bench:
            if target.damage <= 0:
                continue
            value = max((self.attack_utility(owner.active, target, owner.bench, a)
                         for a in owner.active.card.attacks if battle.can_pay_energy(owner.active, a)),
                        default=0)
            # A switch is useful if it exposes a KO or a significantly better target.
            if value > current + 25:
                viable.append((value, target))
        return max(viable, key=lambda x: x[0])[1] if viable else None

    def _retreat_option(self, battle: Battle):
        p = battle.players[battle.current]
        if not p.active or p.active.status == 'asleep' or p.retreated or not p.bench:
            return None
        if len(p.active.energy) + p.retreat_discount < p.active.card.retreat:
            return None
        foe = battle.players[1-battle.current].active
        if not foe:
            return None
        old = max((self.attack_utility(p.active, foe, p.bench, a)
                   for a in p.active.card.attacks if battle.can_pay_energy(p.active, a)), default=-30)
        targets = []
        for mon in p.bench:
            new = max((self.attack_utility(mon, foe, [x for x in p.bench if x is not mon] + [p.active], a)
                       for a in mon.card.attacks if battle.can_pay_energy(mon, a)), default=-30)
            # Don't retreat just for tiny benefits or lose huge invested energy.
            if new > old + 25 and (new > 20 or old < 0):
                targets.append((new - old, mon))
        return max(targets, key=lambda x: x[0])[1] if targets else None

    def play_turn(self, battle: Battle):
        i = battle.current
        p, foe = battle.players[i], battle.players[1-i]
        battle.begin_turn()

        # Search and set up only while a Bench slot exists.
        for card in list(p.hand):
            if (card.effect == 'pokeball' and not p.item_locked and len(p.bench) < 3
                    and any(c.kind == 'pokemon' and c.stage == 0 for c in p.deck)):
                battle.play_trainer(card)
        for card in list(p.hand):
            if card.kind == 'pokemon' and card.stage == 0 and len(p.bench) < 3:
                battle.bench_basic(card)
        for card in list(p.hand):
            if card.effect == 'field_blower' and not p.item_locked and any(x.tool for x in foe.all_in_play()):
                battle.play_trainer(card)

        # Tool attachment: Deceptive Needle has an effect only on a Darkness
        # Pokemon in the Active Spot; don't waste it on a non-Dark Pokemon.
        for card in [c for c in list(p.hand) if c.kind == 'tool']:
            target = None
            if card.effect == 'deceptive_needle':
                if p.active and p.active.card.element == 'darkness' and not p.active.tool:
                    target = p.active
                else:
                    target = next((x for x in p.bench if x.card.element == 'darkness' and not x.tool), None)
            elif card.effect == 'lucky_egg':
                if p.active and not p.active.tool:
                    target = p.active
                else:
                    target = next((x for x in p.bench if not x.tool), None)
            if target:
                battle.equip_tool(card, target)

        for candy in [c for c in list(p.hand) if c.effect == 'rare_candy' and not p.item_locked]:
            made = False
            for mon in p.all_in_play():
                for evo in list(p.hand):
                    if (evo.stage == 2 and p.turns_taken > 1
                        and self.line_map.get(evo.evolves_from.casefold(), '').casefold() == mon.card.name.casefold()
                        and mon.entered_at != battle.turn and mon.evolved_at != battle.turn):
                        battle.rare_candy(candy, mon, evo, self.line_map)
                        made = True
                        break
                if made:
                    break
        for evo in sorted(list(p.hand), key=lambda c: c.stage, reverse=True):
            for mon in p.all_in_play():
                if (evo.stage in (1, 2) and evo.stage == mon.card.stage + 1
                    and evo.evolves_from.casefold() == mon.card.name.casefold()
                    and p.turns_taken > 1 and mon.entered_at != battle.turn and mon.evolved_at != battle.turn):
                    battle.evolve(mon, evo)
                    break

        for mon in list(p.all_in_play()):
            if mon.card.ability == 'water_shuriken' and mon.ability_used_turn != battle.turn:
                choices = foe.all_in_play()
                if choices:
                    victim = min(choices, key=lambda x: (x.card.hp-x.damage, x.card.points))
                    battle.use_ability(mon, victim)
                    if battle.finished:
                        battle.end_turn()
                        return

        # Draw support first if the hand is shallow; a preserved Cyrus can turn
        # an otherwise weak attack into an immediate KO after energy attachment.
        for card in list(p.hand):
            if card.effect == 'research' and not p.supporter_used and len(p.hand) <= 5 and p.deck:
                battle.play_trainer(card)
                break
        for card in list(p.hand):
            if card.kind == 'pokemon' and card.stage == 0 and len(p.bench) < 3:
                battle.bench_basic(card)
        if not p.energy_used and not (battle.turn == 0 and battle.first == i):
            target = self.select_energy_target(p)
            if target is not None:
                battle.attach(target)
                if battle.finished:
                    battle.end_turn()
                    return

        # A damaged opponent on Bench can be pulled into the Active spot if it
        # improves attack utility. No switching solely because Cyrus is in hand.
        for card in list(p.hand):
            if card.effect == 'cyrus' and not p.supporter_used:
                target = self._choose_cyrus_target(battle)
                if target:
                    battle.play_trainer(card, target=target)
                    break
        for card in list(p.hand):
            if card.effect == 'copycat' and not p.supporter_used and p.deck:
                if len(foe.hand) >= len(p.hand) + 2:
                    battle.play_trainer(card)
                    break
        for card in list(p.hand):
            if card.effect == 'center_lady' and not p.supporter_used:
                targets = [x for x in p.all_in_play() if x.damage >= 30 or x.status]
                if targets:
                    target = max(targets, key=lambda x: (x.damage, x is p.active))
                    battle.play_trainer(card, target=target)
                    break
        for card in list(p.hand):
            if card.effect == 'mars' and not p.supporter_used and len(foe.hand) > max(0, 3 - foe.points):
                battle.play_trainer(card)
                break
        for card in list(p.hand):
            if card.effect == 'lucky_ice_pop' and not p.item_locked and p.active and p.active.damage >= 20:
                battle.play_trainer(card)
                break

        # Avoid retreating unless the new Active can do something stronger.
        destination = self._retreat_option(battle)
        if destination:
            battle.retreat(destination)
        elif any(c.effect == 'x_speed' for c in p.hand) and not p.item_locked and p.active and p.bench:
            # Use X Speed only when it enables a desirable retreat.
            old_discount = p.retreat_discount
            p.retreat_discount += 1
            candidate = self._retreat_option(battle)
            p.retreat_discount = old_discount
            if candidate:
                x_speed = next(c for c in p.hand if c.effect == 'x_speed')
                battle.play_trainer(x_speed)
                battle.retreat(candidate)

        if p.active and p.active.status != 'asleep':
            viable = [a for a in p.active.card.attacks if battle.can_pay_energy(p.active, a)]
            if viable:
                best = max(viable, key=lambda a: self.attack_utility(p.active, foe.active, p.bench, a))
                battle.attack(best)
                return
        battle.end_turn()
