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


class StrategicAgentV097(StrategicAgent):
    """v0.9.7 auditable, resource- and knockout-aware heuristic.

    Only reads own deck/hand and public attached energy/board.  It does not
    inspect the opponent's hidden cards or alter any game effect.
    """
    policy_name = 'strategic_v097'

    def __init__(self, line_map=None):
        super().__init__(line_map)
        self.decision_records: list[dict] = []
        self._context_battle = None

    def _note(self, decision: str, chosen: str, alternatives: list[dict], reason: str):
        if len(self.decision_records) >= 50:
            return
        b = self._context_battle
        self.decision_records.append({
            'turn': b.turn if b is not None else None,
            'player': b.current if b is not None else None,
            'decision': decision, 'chosen': chosen,
            'alternatives': sorted(alternatives, key=lambda row: -row['score'])[:6],
            'reason': reason,
        })

    def play_turn(self, battle: Battle):
        self._context_battle = battle
        try:
            return super().play_turn(battle)
        finally:
            self._context_battle = None

    @staticmethod
    def predicted_damage(attacker: InPlay, opponent: InPlay, attack: Attack,
                         bench_count: int) -> float:
        """Public-state attack estimate, not a simulated random outcome."""
        amount = float(attack.damage)
        if attack.effect == 'water_snipe_130_discard':
            amount = 130.0
        elif attack.effect == 'bench_plus_30':
            amount += 30 * bench_count
        elif attack.effect == 'both_benches_plus_20':
            amount += 20 * bench_count  # opponent bench unknown to this scorer
        elif attack.effect == 'coin_bonus_30':
            amount += 15  # fair coin expectation
        elif attack.effect == 'lightning_each_plus_20':
            amount += 20 * attacker.energy.count('lightning')
        elif attack.effect == 'basic_plus_50' and opponent.card.stage == 0:
            amount += 50
        elif attack.effect == 'fire_extra_2_plus_60' and attacker.energy.count('fire') >= 4:
            amount += 60
        if amount > 0 and attacker.card.element and opponent.card.weakness == attacker.card.element:
            amount += 20
        if (attacker.card.name.casefold().endswith(' ex') and
                opponent.card.ability == 'safeguard_ex'):
            return 0.0
        if opponent.card.ability == 'fur_coat':
            amount = max(0, amount - 20)
        if (opponent.tool is not None and opponent.tool.effect == 'eviolite'
                and opponent.card.stage == 0):
            amount = max(0, amount - 20)
        return amount

    @staticmethod
    def attack_utility(attacker: InPlay, opponent: InPlay, bench: list[InPlay],
                       attack: Attack) -> float:
        damage = StrategicAgentV097.predicted_damage(attacker, opponent, attack, len(bench))
        remaining = opponent.max_hp - opponent.damage
        ko = damage >= remaining and damage > 0
        # Score realized damage, with an explicit premium for taking prize points.
        value = 0.95 * min(damage, remaining) + (195 + 65 * max(0, opponent.card.points - 1) if ko else 0)
        if attack.effect == 'draw_1':
            value += 28
        if attack.effect == 'zone_water_to_two_bench':
            value += 32*min(2,len(bench))
        if attack.effect == 'snipe_20_bench' and bench:
            value += 12
        if attack.effect == 'water_snipe_130_discard':
            value += 12  # allows targeting bench, but KO not assumed there
            value -= 14 * attacker.energy.count('water')
        if attack.effect == 'discard_all_self_energy':
            value -= 17 * len(attacker.energy)
        if attack.effect == 'discard_2_global_random':
            value += 3
        if attack.effect == 'discard_opponent_supporter':
            value += 14
        if attack.effect == 'heal_self_30':
            value += 0.8 * min(30, attacker.damage)
        if attack.effect == 'sleep_active':
            value += 13
        if attack.effect == 'item_lock_next_turn':
            value += 12
        if attack.effect == 'mirror_shot':
            value += 10
        if attack.effect in ('recoil_20', 'recoil_50'):
            recoil = 20 if attack.effect == 'recoil_20' else 50
            value -= recoil * 0.6
            if attacker.damage + recoil >= attacker.max_hp:
                # One's own ex may hand out 2 or 3 points.  Avoid the recoil
                # unless it decides the battle; don't guess either score state.
                value -= (100 if ko else 330) + 45 * max(0, attacker.card.points - 1)
        return round(value, 3)

    def select_energy_target(self, player: Player) -> InPlay | None:
        if len(player.energy_types) != 1:
            return None
        zone = player.energy_types[0]
        battle = self._context_battle
        opposing = battle.players[1 - battle.current].active if battle else None
        options = []
        for index, mon in enumerate(player.all_in_play()):
            remaining_hp = mon.max_hp - mon.damage
            if remaining_hp <= 0:
                continue
            for attack, steps in self._prospective_attacks(mon, player):
                if not attack.cost:
                    continue
                # Pay typed costs from existing attachments plus future Zone
                # energy.  Colorless accepts any type.  Already attached
                # irrelevant energy does not make typed attacks impossible.
                required = Counter(t for t in attack.cost if t != 'colorless')
                owned = Counter(mon.energy)
                missing = {t: max(0, n-owned[t]) for t, n in required.items()}
                if any(n > 0 and t != zone for t, n in missing.items()):
                    continue
                deficit = max(max(0, len(attack.cost)-len(mon.energy)), sum(missing.values()))
                if deficit <= 0:
                    continue
                dmg = max(0, attack.damage)
                if attack.effect == 'bench_plus_30':
                    dmg += 30 * len(player.bench)
                elif attack.effect == 'lightning_each_plus_20':
                    dmg += 20 * (owned['lightning'] + int(zone == 'lightning')*deficit)
                elif attack.effect == 'water_snipe_130_discard':
                    dmg = 130
                elif attack.effect == 'coin_bonus_30':
                    dmg += 15
                if steps:
                    next_in_hand = any(c.kind=='pokemon' and c.stage == mon.card.stage+1
                          and c.evolves_from.casefold() == mon.card.name.casefold()
                          for c in player.hand)
                else:
                    next_in_hand = True
                imminent = bool(opposing and any(battle.can_pay_energy(opposing, a)
                    and self.predicted_damage(opposing, mon, a, len(battle.players[1-battle.current].bench)) >= remaining_hp
                    for a in opposing.card.attacks)) if battle else False
                if opposing is not None:
                    dmg += 20 * int(bool(mon.card.element) and
                                    opposing.card.weakness == mon.card.element)
                    if opposing.tool and opposing.tool.effect=='eviolite' and opposing.card.stage==0:
                        dmg=max(0,dmg-20)
                    if opposing.card.ability=='safeguard_ex' and mon.card.name.casefold().endswith(' ex'):
                        dmg=0
                can_ko = (opposing is not None and steps == 0 and deficit == 1 and
                           dmg > 0 and dmg >= opposing.max_hp-opposing.damage)
                score = (65 + .75*dmg - 42*(deficit-1) - 32*steps
                         + (25 if mon is player.active else 0)
                         + (30 if deficit==1 and steps==0 and mon is player.active else 0)
                         + (110 + 20 * max(0, opposing.card.points-1) if can_ko else 0)
                         + (22 if next_in_hand and steps else -23 if steps else 0)
                         + (8 if mon.energy else 0)
                         - (115 if imminent and not can_ko else 0)
                         - (16 if remaining_hp<=40 else 0))
                if attack.effect == 'discard_all_self_energy':
                    score -= 20
                options.append({'name':mon.card.name,'index':index,
                                'attack':attack.name,'steps':steps,
                                'deficit':deficit,'score':round(score,2),
                                'imminent_ko':imminent,'possible_ko_next':can_ko})
        if not options:
            self._note('energy','não anexar',[],
                'Nenhum ataque alcançável precisa de energia adicional')
            return None
        # Stable tie-breaks, so no RNG is consumed by the policy.
        best = max(options, key=lambda v:(v['score'],-v['steps'],-v['deficit'],-v['index']))
        chosen = player.all_in_play()[best['index']]
        self._note('energy',chosen.card.name,options,
            f'Planejamento de energia: {best["attack"]}, faltam {best["deficit"]} anexo(s)')
        return chosen

    def _choose_attack(self, battle: Battle, viable: list[Attack]) -> Attack:
        p = battle.players[battle.current]
        foe = battle.players[1-battle.current]
        evaluated = []
        for attack in viable:
            if attack.effect == 'water_snipe_130_discard':
                # The engine automatically selects the weakest-health target,
                # including Bench.  Bench damage does not apply Weakness.
                target = min(foe.all_in_play(), key=lambda x:(x.max_hp-x.damage,x.card.points))
                remain = target.max_hp-target.damage
                damage = 130
                if target is foe.active and p.active.card.element and target.card.weakness == p.active.card.element:
                    damage += 20
                damage = Battle.attack_damage_after_tool(target,damage,p.active.card)
                score = (0.95*min(damage,remain) + (195+65*max(0,target.card.points-1)
                         if damage > 0 and damage >= remain else 0)
                         + 12 - 14*p.active.energy.count('water'))
                evaluated.append({'name':attack.name,'score':round(score,2),
                                  'target':target.card.name,
                                  'target_slot':'active' if target is foe.active else 'bench'})
            else:
                evaluated.append({'name':attack.name,
                    'score':round(self.attack_utility(p.active,foe.active,p.bench,attack),2)})
        best_idx = max(range(len(viable)), key=lambda idx:evaluated[idx]['score'])
        chosen = viable[best_idx]
        self._note('attack',chosen.name,evaluated,
            'Dano útil + nocaute/pontos − custo de recursos e autolesão')
        return chosen

    def _retreat_option(self, battle: Battle):
        chosen = super()._retreat_option(battle)
        p = battle.players[battle.current]
        if p.active and p.bench:
            self._note('retreat',chosen.card.name if chosen else 'manter ativo',
                [{'name': 'manter '+p.active.card.name, 'score': 0.0}]+[
                 {'name':x.card.name,'score':round(float(max((self.attack_utility(
                     x,battle.players[1-battle.current].active,p.bench,a)
                     for a in x.card.attacks if battle.can_pay_energy(x,a)),default=0)),2)}
                 for x in p.bench],
                'Trocar apenas quando houver benefício ofensivo ou risco público de nocaute')
        return chosen
