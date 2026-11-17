"""v0.9.8: bounded, public-information, two-own-turn *projection*.

This is deliberately not a search through a deep-copied Battle: that would
expose hidden opponent cards/shuffle state. We project only our visible board,
our known hand and opponent's face-up board, with an adversarial known-attack
response. No new card effects or move legality is implemented here.
"""
from __future__ import annotations
from collections import Counter
from copy import copy
from battle_engine import Attack, Battle, InPlay, Player
from strategic_agent import StrategicAgentV097


class PlanningAgentV098(StrategicAgentV097):
    policy_name = 'planning_v098'
    MAX_OWN_BRANCHES = 5
    MAX_REPLY_BRANCHES = 3
    HORIZON_OWN_TURNS = 2

    @staticmethod
    def _clone(mon: InPlay) -> InPlay:
        new = copy(mon)
        new.energy = list(mon.energy)
        return new

    @staticmethod
    def _payable(mon: InPlay, attack: Attack) -> bool:
        return Battle.can_pay_energy(mon, attack)

    @staticmethod
    def _can_reach(mon: InPlay, attack: Attack, zone: str, extra: int = 0) -> bool:
        energy = Counter(mon.energy)
        energy[zone] += extra
        required = Counter(t for t in attack.cost if t != 'colorless')
        return sum(energy.values()) >= len(attack.cost) and all(
            energy[t] >= count for t, count in required.items())

    def _known_evolution_attacks(self, mon: InPlay, player: Player):
        """Only evolution cards *already in own hand* can be future options."""
        moves = [(a, 0, mon.card.name) for a in mon.card.attacks]
        for card in player.hand:
            if (card.kind == 'pokemon' and card.stage == mon.card.stage + 1
                    and card.evolves_from.casefold() == mon.card.name.casefold()):
                moves.extend((a, 1, card.name) for a in card.attacks)
        return moves

    def _attack_effect_value(self, attacker: InPlay, foe: InPlay,
                             attack: Attack, bench_count: int) -> tuple[float, float, bool]:
        """Expected (not sampled) direct active damage, utility and KO flag."""
        dmg = self.predicted_damage(attacker, foe, attack, bench_count)
        # Unknown/targeted effects are not assumed to damage the face-up Active.
        if attack.effect == 'water_snipe_130_discard':
            dmg = 0.0  # conservative: snipe might pick an opponent on the Bench
        remaining = max(0, foe.max_hp - foe.damage)
        effective = min(max(0.0, dmg), remaining)
        ko = bool(dmg >= remaining and remaining > 0 and dmg > 0)
        utility = 0.9 * effective + (150 + 55 * max(0, foe.card.points - 1) if ko else 0)
        utility += (12 if attack.effect in ('item_lock_next_turn','sleep_active') else 0)
        utility += (15 if attack.effect == 'snipe_20_bench' else 0)
        utility += (4 if attack.effect == 'heal_self_30' else 0)
        if attack.effect == 'water_snipe_130_discard':
            utility += 28 - 8 * attacker.energy.count('water')
        if attack.effect == 'discard_all_self_energy':
            utility -= 15 * len(attacker.energy)
        if attack.effect in ('recoil_20', 'recoil_50'):
            recoil = 50 if attack.effect == 'recoil_50' else 20
            utility -= recoil * 0.7
            if attacker.max_hp - attacker.damage <= recoil:
                utility -= 170 + 35 * attacker.card.points
        return dmg, utility, ko

    def _opponent_threat(self, attacker: InPlay, foe: InPlay,
                         own_bench: int, foe_bench: int):
        """Pessimistic reply from *currently payable, face-up* foe attacks.

        This is not clairvoyance: unknown draws/attachments are represented by
        uncertainty in the displayed audit, never by reading hidden cards.
        """
        options = []
        for attack in foe.card.attacks:
            if not self._payable(foe, attack):
                continue
            dmg = self.predicted_damage(foe, attacker, attack, foe_bench)
            if attack.effect == 'water_snipe_130_discard':
                # Target selection cannot be known to threaten the Active.
                dmg = 0.0
            damage = min(max(0.0, dmg), attacker.max_hp-attacker.damage)
            ko = bool(dmg > 0 and dmg >= attacker.max_hp-attacker.damage)
            harm = damage * 0.75 + (165 + 55 * max(0, attacker.card.points-1) if ko else 0)
            options.append((harm, dmg, ko, attack.name))
        options.sort(reverse=True)
        return options[:self.MAX_REPLY_BRANCHES] or [(0.0, 0.0, False, 'sem ataque pago visível')]

    def _future_best(self, own: list[InPlay], active_idx: int,
                     enemy: InPlay, player: Player, zone: str,
                     enemy_reply_damage: float, enemy_ko: bool) -> dict:
        """Best reachable attack after the opponent's projected reply and
        ONE next own zone attachment; no unknown cards are invented.
        """
        candidates = []
        for idx, original in enumerate(own):
            # Active KO is reflected in the projection; a bench attacker can
            # then be promoted. The full KO/replacement rule is not replayed.
            if idx == active_idx and enemy_ko:
                continue
            mon = self._clone(original)
            # Only consider a Bench attacker next turn if the current Active
            # could pay for a retreat from public attachments, or if the Active
            # is KOd and a replacement is mandatory. Unknown X Speed draws
            # must not be assumed available.
            if idx != active_idx and not enemy_ko:
                prior_active=own[active_idx]
                discount=int(bool(prior_active.tool and
                    prior_active.tool.effect=='inflatable_boat' and
                    prior_active.card.element=='water'))
                discount += int(bool(prior_active.tool and
                    prior_active.tool.effect=='small_balloon' and
                    prior_active.card.stage==0))
                cost=max(0,prior_active.card.retreat-discount)
                if len(prior_active.energy)<cost:
                    continue
            access = 1.0 if idx == active_idx else (0.78 if enemy_ko else 0.53)
            for attach in (0,1):
                if attach:
                    mon.energy.append(zone)
                for attack, steps, evolved_to in self._known_evolution_attacks(mon,player):
                    if steps > 1 or not self._payable(mon, attack):
                        continue
                    dmg, value, ko = self._attack_effect_value(mon, enemy, attack, len(own)-1)
                    if enemy.max_hp-enemy.damage <= 0:
                        # Already KOd on previous own turn; hypothetical new
                        # enemy Pokémon is unobserved and must not be guessed.
                        continue
                    if steps:
                        # A known evolution card can be played on the next
                        # turn if timing permits, but the actual evolution's
                        # effects are not simulated by this abstraction.
                        value *= 0.73
                    value *= access
                    value -= (5 if attach else 0)
                    candidates.append({'score':round(value,3),'attack':attack.name,
                        'pokemon':evolved_to,'attacher':mon.card.name if attach else None,
                        'bench_access_discount':round(access,2),'evolution_in_hand':bool(steps)})
                if attach:
                    mon.energy.pop()
        return max(candidates, key=lambda x:x['score']) if candidates else {
            'score':0.0,'attack':'nenhum ataque disponível','pokemon':'—',
            'attacher':None,'bench_access_discount':0,'evolution_in_hand':False}

    def _path(self, p: Player, foe: Player, target_idx: int | None = None,
              fixed_attack: Attack | None = None, fixed_active_idx: int | None = None):
        if not p.active or not foe.active:
            return {'score':-1e6,'current':'sem ativo','next':'—', 'risk':0}
        own = [self._clone(m) for m in p.all_in_play()]
        enemy = self._clone(foe.active)
        zone = p.energy_types[0]
        if target_idx is not None:
            if not 0 <= target_idx < len(own):
                raise ValueError('Índice de energia inválido')
            own[target_idx].energy.append(zone)
        active_idx = 0 if fixed_active_idx is None else fixed_active_idx
        active = own[active_idx]
        retreat_resource_cost = 0
        if active_idx:
            if p.retreated or p.active.status == 'asleep':
                return {'score':-1e6,'current':'recuo ilegal','next':'—','risk':0}
            discount = int(bool(p.active.tool and p.active.tool.effect == 'inflatable_boat' and p.active.card.element=='water'))
            discount += int(bool(p.active.tool and p.active.tool.effect == 'small_balloon' and p.active.card.stage==0))
            cost=max(0,p.active.card.retreat-p.retreat_discount-discount)
            if len(own[0].energy)<cost:
                return {'score':-1e6,'current':'recuo sem energia','next':'—','risk':0}
            own[0].energy=own[0].energy[cost:]
            retreat_resource_cost = cost
        attack_options = ([fixed_attack] if fixed_attack else active.card.attacks)
        attack_options = [a for a in attack_options if self._payable(active,a)]
        if active.status == 'asleep':
            attack_options = []
        if not attack_options:
            attack_options = [None]
        outcomes = []
        for attack in attack_options:
            now_damage, now_value, now_ko = (self._attack_effect_value(active,enemy,attack,len(own)-1)
                if attack is not None else (0.0,0.0,False))
            # An already won game is decisive. Enemy reply doesn't happen.
            if now_ko and (p.points + enemy.card.points >= 3 or not foe.bench):
                value = 800.0 + 40 * enemy.card.points
                outcomes.append({'score':value,'current':attack.name,'next':'vitória imediata','risk':0,
                    'future_attack':None,'response':'partida encerrada','now_ko':True})
                continue
            # A KO does not cancel the opponent's turn if there are visible
            # Bench Pokémon to promote. Consider each face-up replacement; the
            # adversary gets to choose the most inconvenient one.
            replacements = ([self._clone(x) for x in foe.bench[:self.MAX_REPLY_BRANCHES]]
                            if now_ko else [self._clone(enemy)])
            if not now_ko:
                replacements[0].damage += int(now_damage)
            reply_paths=[]
            for proj_enemy in replacements:
                responses=self._opponent_threat(active,proj_enemy,len(own)-1,len(foe.bench))
                future_own=[self._clone(mon) for mon in own]
                # Reflect the attack's resource expenditure before considering
                # the next own attachment; otherwise repeat attacks look free.
                if attack and attack.effect == 'discard_all_self_energy':
                    future_own[active_idx].energy=[]
                elif attack and attack.effect == 'water_snipe_130_discard':
                    future_own[active_idx].energy=[x for x in future_own[active_idx].energy
                                                     if x != 'water']
                for harm,damage,ko,reply in responses:
                    after_reply=[self._clone(mon) for mon in future_own]
                    after_reply[active_idx].damage += int(damage)
                    fut=self._future_best(after_reply,active_idx,proj_enemy,p,zone,damage,ko)
                    value = now_value - 0.82*harm + 0.68*fut['score']
                    value -= 13 * retreat_resource_cost
                    if ko and (foe.points + active.card.points >= 3 or len(own)==1):
                        value -= 800  # projected terminal loss
                    if attack is None:
                        value -= 10
                    if target_idx is not None and target_idx != active_idx:
                        value += 4
                    reply_paths.append((value,harm,reply,fut))
            worst=min(reply_paths,key=lambda x:x[0])
            val,harm,reply,fut=worst
            outcomes.append({'score':round(val,3),
                'current':attack.name if attack else 'passar sem ataque',
                'next':fut['attack'],'risk':round(harm,2),
                'future_attack':fut,'response':reply,'now_ko':now_ko})
        return max(outcomes,key=lambda x:x['score'])

    def select_energy_target(self, player: Player) -> InPlay | None:
        battle=self._context_battle
        if battle is None or len(player.energy_types)!=1:
            return super().select_energy_target(player)
        foe=battle.players[1-battle.current]
        if not player.active or not foe.active:
            return super().select_energy_target(player)
        # No new attachment should be made to a card whose *only* current
        # attacks are already covered unless it also enables a different move.
        baseline=self._path(player,foe)
        options=[]
        for idx,mon in enumerate(player.all_in_play()[:self.MAX_OWN_BRANCHES]):
            if mon.damage>=mon.max_hp:
                continue
            path=self._path(player,foe,target_idx=idx)
            # Compare against not attaching; preserve moderate future option
            # value but avoid dumping energy into a dead strategic line.
            path_score=path['score']+ (2 if len(mon.energy)==0 else 0)
            options.append({'name':mon.card.name,'index':idx,'score':round(path_score,3),
                'current_attack':path['current'],'next_attack':path['next'],
                'incoming_risk':path['risk'],'enemy_response':path['response']})
        if not options:
            return None
        best=max(options,key=lambda x:(x['score'],-x['index']))
        if best['score'] <= baseline['score'] + 1.5:
            self._note('energy','não anexar',options,
                'Nenhum anexo supera claramente manter o estado atual na projeção de 2 turnos')
            return None
        for item in options:
            if item is not best:
                item['rejected_because']='menor valor esperado nos cenários públicos considerados'
        self._note('energy',best['name'],options,
            'Projeção de 2 turnos próprios: ação atual, pior resposta conhecida e próximo ataque; sem acessar cartas ocultas')
        return player.all_in_play()[best['index']]

    def _choose_attack(self, battle: Battle, viable: list[Attack]) -> Attack:
        p=battle.players[battle.current];foe=battle.players[1-battle.current]
        if not p.active or not foe.active:
            return super()._choose_attack(battle,viable)
        options=[]
        for attack in viable:
            outcome=self._path(p,foe,fixed_attack=attack)
            options.append({'name':attack.name,'score':outcome['score'],
                'enemy_response':outcome['response'],
                'incoming_risk':outcome['risk'],'next_attack':outcome['next']})
        best=max(options,key=lambda x:x['score'])
        for option in options:
            if option is not best:
                option['rejected_because']='menor valor projetado após a resposta adversária'
        self._note('attack',best['name'],options,
            'Dano/pontos agora + ataque futuro − pior resposta com ataques públicos já pagos')
        return next(a for a in viable if a.name == best['name'])

    def _retreat_option(self, battle: Battle):
        p=battle.players[battle.current];foe=battle.players[1-battle.current]
        if not p.active or not foe.active or not p.bench or p.retreated:
            return None
        stay=self._path(p,foe,fixed_active_idx=0)
        options=[{'name':'manter '+p.active.card.name,'score':stay['score'],
                  'feasible':True,'reason':'permanecer ativo'}]
        for idx,mon in enumerate(p.all_in_play()[1:self.MAX_OWN_BRANCHES],start=1):
            result=self._path(p,foe,fixed_active_idx=idx)
            options.append({'name':mon.card.name,'index':idx,'score':result['score'],
                 'feasible':result['score']>-1e5,
                 'reason':result['current'] if result['score']>-1e5 else 'sem recuo legal ou energia'})
        candidates=[x for x in options[1:] if x['feasible'] and x['score']>stay['score']+24]
        best=max(candidates,key=lambda x:x['score']) if candidates else None
        self._note('retreat',best['name'] if best else 'manter ativo',options,
            'Trocar somente se a melhora projetada superar 24 pontos e o recuo for legal')
        return p.all_in_play()[best['index']] if best else None
