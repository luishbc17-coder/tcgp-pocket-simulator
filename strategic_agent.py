"""TCG Pocket Lab v0.9.6: resource-aware heuristic policy.

No changes to game rules; estimates only from own legal deck/hand and public
board state. This agent does *not* search opponent's hidden cards or deck order.
It is an experimental deterministic policy, not trained or optimal AI.
"""
from __future__ import annotations
from collections import Counter
from battle_engine import Attack, Battle, InPlay, Player, RuleAgent
from tactical_agent import TacticalAgent


class StrategicAgent(TacticalAgent):
    policy_name = 'strategic_v096'

    def select_energy_target(self, player: Player) -> InPlay | None:
        """Prioritize attacks close to being usable; value evolution in hand.

        Current attacks receive an immediacy bonus. Evolution targets are
        discounted if the needed card is merely somewhere in the deck. An
        unplayable typed attack never receives energy from the Energy Zone.
        """
        if len(player.energy_types) != 1:
            return None
        best = None
        for mon in player.all_in_play():
            if mon.damage >= mon.max_hp:
                continue
            for attack, steps in self._prospective_attacks(mon, player):
                if not attack.cost or len(mon.energy) >= len(attack.cost):
                    continue
                cost = len(attack.cost)
                deficit = cost - len(mon.energy)
                available = Counter(mon.energy)
                required = Counter(t for t in attack.cost if t != 'colorless')
                missing_typed = sum(max(0, n - available[t]) for t, n in required.items())
                # One attached Energy per turn from the zone; all deficits need
                # to be reachable with the configured Energy type.
                if any(t not in (player.energy_types[0], 'colorless') for t in attack.cost):
                    continue
                # Non-static attacks are not assigned invented numerical damage.
                damage = max(0, attack.damage)
                if attack.effect == 'bench_plus_30':
                    damage += 30 * len(player.bench)
                elif attack.effect == 'coin_bonus_30':
                    damage += 15
                elif attack.effect == 'water_snipe_130_discard':
                    damage = max(damage, 85)
                elif attack.effect == 'snipe_20_bench':
                    damage += 15
                live_hp = mon.max_hp - mon.damage
                # A current attack gets a strong scheduling advantage, but do
                # not overcharge a finished attack instead of developing Bench.
                utility = (45 + 0.7 * damage - 27 * max(0, deficit - 1)
                           - 17 * steps + (16 if mon is player.active else 0)
                           + (25 if deficit == 1 and steps == 0 else 0)
                           + (13 if len(mon.energy) else 0)
                           - (25 if live_hp <= 30 else 0))
                if attack.effect == 'recoil_50' and live_hp <= 50:
                    utility -= 28
                if steps > 0:
                    # The deck's known composition is public to its owner;
                    # only the own hand makes an evolution immediately ready.
                    next_stage_in_hand = any(
                        c.kind == 'pokemon' and c.stage == mon.card.stage + 1
                        and c.evolves_from.casefold() == mon.card.name.casefold()
                        for c in player.hand)
                    utility += (20 if next_stage_in_hand else -12)
                # Improve colorless-cost shortfall decisions: typed energy now
                # counts towards Colorless, but not an unpayable typed attack.
                utility += 5 if missing_typed == 1 else 0
                key = (utility, mon is player.active, -deficit, mon.card.hp)
                if best is None or key > best[0]:
                    best = (key, mon)
        return best[1] if best else None

    @staticmethod
    def attack_utility(attacker: InPlay, opponent: InPlay, bench: list[InPlay],
                       attack: Attack) -> float:
        """Scoring extends the original heuristic without changing effects."""
        score = TacticalAgent.attack_utility(attacker, opponent, bench, attack)
        # The original heuristic already rewards KO/points. Resource discard
        # prevents an otherwise cheap overpowered attack preference.
        if attack.effect == 'discard_all_self_energy':
            score -= 12 * len(attacker.energy)
        if attack.effect == 'water_snipe_130_discard':
            score -= 14 * attacker.energy.count('water')
        if attack.effect == 'heal_self_30':
            score += 0.4 * min(attacker.damage,30)
        if attack.effect == 'item_lock_next_turn':
            score += 12
        if attack.effect == 'sleep_active':
            score += 10
        return score

    def _retreat_option(self, battle: Battle):
        """Avoid retreating to a clearly worse attack merely for preservation.

        TacticalAgent already evaluates attack improvements. In addition,
        preserve a damaged high-points Active when a Bench attacker can still
        act, and a known charged foe could knock out the Active next turn.
        """
        choice = super()._retreat_option(battle)
        if choice is not None:
            return choice
        p = battle.players[battle.current]
        foe = battle.players[1-battle.current]
        if (not p.active or not foe.active or not p.bench or p.retreated
                or p.active.status == 'asleep'):
            return None
        active = p.active
        boat = int(bool(active.tool and active.tool.effect == 'inflatable_boat'
                        and active.card.element == 'water'))
        boat += int(bool(active.tool and active.tool.effect == 'small_balloon'
                         and active.card.stage == 0))
        if len(active.energy) + p.retreat_discount + boat < active.card.retreat:
            return None
        # Use public attached energy and attacks; never assume a future hidden
        # attachment. Only current known incoming lethality is used.
        opp_utility = max((a.damage + (20 if active.card.weakness == foe.active.card.element else 0)
                           for a in foe.active.card.attacks
                           if a.damage > 0 and battle.can_pay_energy(foe.active, a)), default=0)
        if opp_utility < active.max_hp - active.damage or active.card.points < 2:
            return None
        active_attack = max((self.attack_utility(active, foe.active, p.bench, a)
                             for a in active.card.attacks if battle.can_pay_energy(active,a)),default=0)
        # Never sacrifice an immediate KO to escape a hypothetical reprisal.
        if active_attack >= 190:
            return None
        options=[]
        for mon in p.bench:
            replacement_attack = max((self.attack_utility(mon,foe.active,
                        [x for x in p.bench if x is not mon]+[active],a)
                        for a in mon.card.attacks if battle.can_pay_energy(mon,a)),default=0)
            if replacement_attack >= max(10,active_attack - 22) and mon.max_hp-mon.damage >= 35:
                options.append((replacement_attack,mon))
        return max(options,key=lambda x:x[0])[1] if options else None
