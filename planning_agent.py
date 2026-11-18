"""v0.9.8 baseline plus v0.9.9 public-information planning improvements.

This is deliberately not a search through a deep-copied Battle: that would
expose hidden opponent cards/shuffle state. We project only our visible board,
our known hand and opponent's face-up board, with an adversarial known-attack
response. No new card effects or move legality is implemented here.
"""
from __future__ import annotations
from collections import Counter
from copy import copy
from battle_engine import Attack, Battle, InPlay, Player, Card
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


class PlanningAgentV099(PlanningAgentV098):
    """v0.9.9: resource-aware two-own-turn public-state projection.

    This remains a heuristic *projection*, not a hidden-card or deterministic
    game-tree solver. It never mutates Battle or reads opponent hand/deck.
    """
    policy_name = 'planning_v099'
    FUTURE_DISCOUNT = 0.61
    RETREAT_PENALTY = 30.0

    @staticmethod
    def _retreat_cost(mon: InPlay, discount: int = 0) -> int:
        boat = bool(mon.tool and mon.tool.effect == 'inflatable_boat' and mon.card.element == 'water')
        balloon = bool(mon.tool and mon.tool.effect == 'small_balloon' and mon.card.stage == 0)
        return max(0, mon.card.retreat - discount - int(boat) - int(balloon))

    def _note(self, decision, chosen, alternatives, reason):
        """Counterfactual *scores*, not claims about observed alternate games."""
        enriched = [dict(item) for item in alternatives]
        ranked = sorted(enriched, key=lambda x:-x.get('score',-1e6))
        chosen_row = next((x for x in enriched if x.get('name') == chosen), None)
        if chosen_row is None and chosen == 'não anexar':
            chosen_score = getattr(self,'_energy_baseline_score',None)
        else:
            chosen_score = chosen_row.get('score') if chosen_row else None
        if chosen_score is not None:
            for row in enriched:
                row['delta_vs_chosen'] = round(row['score'] - chosen_score, 3)
                row['counterfactual_kind'] = 'estimativa_no_mesmo_estado'
        super()._note(decision, chosen, enriched, reason)
        if self.decision_records and self.decision_records[-1]['decision'] == decision:
            note=self.decision_records[-1]
            best_alternative=max((r['score'] for r in enriched if r.get('name')!=chosen), default=None)
            note['chosen_projected_score']=chosen_score
            note['best_rejected_projected_score']=best_alternative
            note['projected_margin']=(round(chosen_score-best_alternative,3)
                   if chosen_score is not None and best_alternative is not None else None)
            note['audit_limitations']='Comparação heurística entre ações; não é resultado causal de partidas contrafactuais.'

    def _future_best(self, own, active_idx, enemy, player, zone,
                     enemy_reply_damage, enemy_ko):
        """One attachment next turn; apply legal retreat payment and real evolution card.

        An attached Energy may only benefit the Pokémon that receives it. One
        evolution already in own hand can be used; unknown draws are excluded.
        """
        if enemy.max_hp <= enemy.damage:
            return {'score':0.0,'attack':'alvo nocauteado','pokemon':'—',
                    'attacher':None,'bench_access_discount':0,'evolution_in_hand':False}
        candidates=[]
        for idx,original in enumerate(own[:self.MAX_OWN_BRANCHES]):
            if idx == active_idx and enemy_ko:
                continue
            retreat_cost=0
            if idx != active_idx and not enemy_ko:
                retreat_cost=self._retreat_cost(own[active_idx])
                if len(own[active_idx].energy)<retreat_cost:
                    continue
            base=self._clone(original)
            if base.max_hp<=base.damage:
                continue
            evolutions=[(base.card,False)]
            if player.turns_taken + 1 >= 2:
                for card in player.hand:
                    if (card.kind=='pokemon' and card.stage==base.card.stage+1 and
                        card.evolves_from.casefold()==base.card.name.casefold()):
                        evolutions.append((card,True))
            for evo,is_evolution in evolutions:
                for add_energy in (False,True):
                    mon=self._clone(base)
                    if is_evolution:
                        mon.card=evo  # Real evolution's HP, weakness, and attacks
                    if mon.max_hp <= mon.damage:
                        continue
                    if add_energy:
                        mon.energy.append(zone)
                    payable=[a for a in mon.card.attacks if self._payable(mon,a)]
                    if not payable:
                        continue
                    for attack in payable:
                        _,raw,ko=self._attack_effect_value(mon,enemy,attack,len(own)-1)
                        value=raw - (17*retreat_cost + self.RETREAT_PENALTY if idx!=active_idx and not enemy_ko else 0)
                        # Future attachment is an opportunity cost, not free
                        value -= (3 if add_energy else 0)
                        if is_evolution:
                            value -= 8  # known but contingent on future timing
                        if enemy_ko:
                            value -= 6  # forced promotion, potential new risk
                        candidates.append({'score':round(value,3),'attack':attack.name,
                            'pokemon':mon.card.name,'attacher':original.card.name if add_energy else None,
                            'bench_access_discount':1.0,'evolution_in_hand':is_evolution,
                            'requires_switch':idx!=active_idx and not enemy_ko,
                            'retreat_energy_paid':retreat_cost,'future_attachment':add_energy,
                            'projected_ko':ko})
        return max(candidates,key=lambda x:x['score']) if candidates else {
            'score':0.0,'attack':'nenhum ataque legal alcançável','pokemon':'—',
            'attacher':None,'bench_access_discount':0,'evolution_in_hand':False}

    def _opponent_threat(self, attacker, foe, own_bench, foe_bench):
        """Known paid attacks plus *marked uncertain* one-energy reply.

        Opponent Energy Zone is not read. An extra card's own element is only
        a plausible, explicitly discounted worst-case reply.
        """
        options=super()._opponent_threat(attacker,foe,own_bench,foe_bench)
        current_names={x[3] for x in options}
        for attack in foe.card.attacks:
            if attack.name in current_names or self._payable(foe,attack):
                continue
            hypothetical=self._clone(foe)
            hypothetical.energy.append(foe.card.element)
            if not self._payable(hypothetical,attack):
                continue
            dmg=self.predicted_damage(hypothetical,attacker,attack,foe_bench)
            if attack.effect=='water_snipe_130_discard':
                dmg=0.0
            remaining=attacker.max_hp-attacker.damage
            ko=bool(dmg>=remaining and remaining>0 and dmg>0)
            harm=(min(max(0.0,dmg),remaining)*0.75 +
                  (165+55*max(0,attacker.card.points-1) if ko else 0)) * 0.52
            options.append((harm,dmg,ko,attack.name+' [possível +1 Energia]'))
        return sorted(options,reverse=True)[:self.MAX_REPLY_BRANCHES]

    def _path(self,p,foe,target_idx=None,fixed_attack=None,fixed_active_idx=None):
        if not p.active or not foe.active:
            return {'score':-1e6,'current':'sem ativo','next':'—','risk':0,'response':'—'}
        own=[self._clone(m) for m in p.all_in_play()]
        enemy=self._clone(foe.active)
        zone=p.energy_types[0]
        if target_idx is not None:
            if not 0<=target_idx<len(own):
                raise ValueError('Índice de anexo inválido')
            own[target_idx].energy.append(zone)
        active_idx=0 if fixed_active_idx is None else fixed_active_idx
        if not 0<=active_idx<len(own):
            return {'score':-1e6,'current':'recuo inválido','next':'—','risk':0,'response':'—'}
        active=own[active_idx]
        retreat_cost=0
        if active_idx:
            if p.retreated or p.active.status=='asleep':
                return {'score':-1e6,'current':'recuo ilegal','next':'—','risk':0,'response':'—'}
            retreat_cost=self._retreat_cost(own[0],p.retreat_discount)
            if len(own[0].energy)<retreat_cost:
                return {'score':-1e6,'current':'recuo sem energia','next':'—','risk':0,'response':'—'}
            own[0].energy=own[0].energy[retreat_cost:]
        attacks=[fixed_attack] if fixed_attack else list(active.card.attacks)
        attacks=[a for a in attacks if self._payable(active,a) and active.status!='asleep']
        if not attacks:
            attacks=[None]
        outcomes=[]
        for attack in attacks:
            now_damage,now_value,now_ko=(self._attack_effect_value(active,enemy,attack,len(own)-1)
                                         if attack else (0,0,False))
            if now_ko and (p.points+enemy.card.points>=3 or not foe.bench):
                outcomes.append({'score':850+40*enemy.card.points,'current':attack.name,
                   'next':'vitória imediata','risk':0,'response':'partida encerrada','now_ko':True})
                continue
            rivals=([self._clone(x) for x in foe.bench[:self.MAX_REPLY_BRANCHES]]
                    if now_ko else [self._clone(enemy)])
            if not now_ko:
                rivals[0].damage+=int(now_damage)
            future_own=[self._clone(mon) for mon in own]
            if attack and attack.effect=='discard_all_self_energy':
                future_own[active_idx].energy=[]
            elif attack and attack.effect=='water_snipe_130_discard':
                future_own[active_idx].energy=[x for x in future_own[active_idx].energy if x!='water']
            risk_paths=[]
            for rival in rivals:
                replies=self._opponent_threat(active,rival,len(own)-1,len(foe.bench))
                for harm,damage,ko,reply in replies:
                    survivors=[self._clone(m) for m in future_own]
                    # Mark a KO on the active before evaluating replacement.
                    survivors[active_idx].damage+=int(damage)
                    if ko and (foe.points+active.card.points>=3 or len(own)==1):
                        future={'score':0,'attack':'derrota projetada'}
                        total=now_value - 850 - harm
                    else:
                        future=self._future_best(survivors,active_idx,rival,p,zone,damage,ko)
                        total=now_value - 0.90*harm + self.FUTURE_DISCOUNT*future['score']
                    total-= (self.RETREAT_PENALTY+17*retreat_cost) if active_idx else 0
                    if attack is None:
                        total-=12
                    # Preserve resources: do not reward merely attaching to bench.
                    risk_paths.append((total,harm,reply,future))
            if risk_paths:
                total,harm,reply,future=min(risk_paths,key=lambda x:x[0])
                outcomes.append({'score':round(total,3),'current':attack.name if attack else 'passar sem ataque',
                   'next':future['attack'],'risk':round(harm,2),
                   'future_attack':future,'response':reply,'now_ko':now_ko})
        return max(outcomes,key=lambda x:x['score'])

    def select_energy_target(self,player):
        battle=self._context_battle
        if battle is None or len(player.energy_types)!=1:
            return super().select_energy_target(player)
        foe=battle.players[1-battle.current]
        if not player.active or not foe.active:
            return super().select_energy_target(player)
        baseline=self._path(player,foe)
        self._energy_baseline_score=baseline['score']
        options=[{'name':'não anexar','score':baseline['score'],
                  'current_attack':baseline['current'],'next_attack':baseline['next'],
                  'incoming_risk':baseline['risk']}]
        for idx,mon in enumerate(player.all_in_play()[:self.MAX_OWN_BRANCHES]):
            if mon.max_hp<=mon.damage:
                continue
            path=self._path(player,foe,target_idx=idx)
            delta=path['score']-baseline['score']
            # Reward finishing the Active's attack, not overloading an already
            # paid one. Encourage bench only for a real legal future path.
            enabled=any(not self._payable(mon,a) and self._can_reach(mon,a,player.energy_types[0],1)
                        for a in mon.card.attacks)
            bonus=7 if (idx==0 and enabled) else 0
            # Future turns are limited, so avoid many surplus attachments.
            if not enabled and len(mon.energy)>=2:
                bonus-=8
            score=round(path['score']+bonus,3)
            options.append({'name':mon.card.name,'index':idx,'score':score,
               'current_attack':path['current'],'next_attack':path['next'],
               'incoming_risk':path['risk'],'enemy_response':path['response'],
               'improvement_vs_no_attachment':round(delta,3),
               'enables_attack_immediately':enabled})
        best=max(options,key=lambda x:(x['score'], -x.get('index',9)))
        for row in options:
            if row is not best:
                row['rejected_because']='menor projeção considerando turno seguinte e custo de oportunidade'
        self._note('energy',best['name'],options,
                   'Compara não anexar e cada destino; energias só alimentam ataques legalmente alcançáveis')
        return player.all_in_play()[best['index']] if 'index' in best else None

    def _retreat_option(self,battle):
        p=battle.players[battle.current];foe=battle.players[1-battle.current]
        if not p.active or not foe.active or not p.bench or p.retreated:
            return None
        stay=self._path(p,foe,fixed_active_idx=0)
        options=[{'name':'manter ativo','score':stay['score'],'feasible':True}]
        for idx,mon in enumerate(p.all_in_play()[1:self.MAX_OWN_BRANCHES],start=1):
            result=self._path(p,foe,fixed_active_idx=idx)
            options.append({'name':mon.card.name,'index':idx,'score':result['score'],
                 'feasible':result['score']>-1e5,
                 'reason':result['current'] if result['score']>-1e5 else 'recuo inviável'})
        candidates=[r for r in options[1:] if r['feasible'] and r['score']>stay['score']+20]
        best=max(candidates,key=lambda x:x['score']) if candidates else options[0]
        self._note('retreat',best['name'],options,
                   'Preserva atacante; o custo do recuo já foi descontado e exige margem adicional de 20')
        return p.all_in_play()[best['index']] if 'index' in best else None


class PlanningAgentV0910(PlanningAgentV099):
    """v0.9.10: public, bounded 2-turn projection with known Rare Candy,
    supported-ability option value, useful energy preparation and unique audit IDs.

    This is a *heuristic*, not a full rollout of the opponent turn; hidden
    decks/hands or hypothetical future draws are never accessed or invented.
    """
    policy_name = 'planning_v0910'
    MAX_PROJECTED_ABILITY_BONUS = 55.0
    MAX_PREPARATION_BONUS = 25.0

    def _known_evolutions(self, mon: InPlay, player: Player):
        """(card, method) legal on next own turn from the current hand only.

        The previous card must survive and still be present. Item lock is not
        assumed to persist across turns, but Candy remains discounted for that
        uncertainty. Stage 2 cannot be reached through two ordinary evolutions
        in a single future turn.
        """
        options = [(mon.card, 'none')]
        if player.turns_taken + 1 < 2:
            return options
        own_candy = any(c.effect == 'rare_candy' for c in player.hand)
        for card in player.hand:
            if card.kind != 'pokemon':
                continue
            if (card.stage == mon.card.stage + 1 and
                card.evolves_from.casefold() == mon.card.name.casefold()):
                options.append((card, 'regular'))
            elif (mon.card.stage == 0 and card.stage == 2 and own_candy
                  and self.line_map.get(card.evolves_from.casefold(), '').casefold()
                  == mon.card.name.casefold()):
                options.append((card, 'rare_candy'))
        return options

    @staticmethod
    def _energy_shortfall(mon: InPlay, attack: Attack, zone: str) -> int:
        """Smallest number of *zone-type* attachments to pay the attack."""
        required = Counter(t for t in attack.cost if t != 'colorless')
        present = Counter(mon.energy)
        if any(present[t] < n for t,n in required.items() if t != zone):
            return 99
        colored = max(0, required.get(zone,0)-present[zone])
        total = max(0, len(attack.cost)-len(mon.energy))
        return max(total,colored)

    def _future_support_bonus(self, own: list[InPlay], enemy: InPlay, player: Player, zone: str):
        """Value *existing implemented* support abilities after opponent reply.

        Avoids pretending an ability happened or drawing from hidden zones;
        capability is an option value, discounted because actual use/survival
        next turn is uncertain. Bonus is counted once for the whole board.
        """
        if enemy.damage >= enemy.max_hp:
            return 0.0, []
        bonuses=[]
        rare_candy_left=sum(c.effect=='rare_candy' for c in player.hand)
        for mon in own:
            if mon.damage>=mon.max_hp:
                continue
            options=self._known_evolutions(mon, player)
            highest=(0.0,None)
            for evolution,method in options:
                ability=evolution.ability
                if ability=='water_shuriken':
                    dmg=min(20,max(0,enemy.max_hp-enemy.damage))
                    val=0.75*dmg + (55 if dmg>0 and enemy.max_hp-enemy.damage<=20 else 0)
                elif ability=='volt_charge' and zone=='lightning':
                    val=16
                elif ability=='ice_maker' and zone=='water' and any(m.card.element=='water' for m in own):
                    val=18
                elif ability=='roar_in_unison' and zone=='darkness' and mon.max_hp-mon.damage>30:
                    val=16
                else:
                    val=0.0
                if method=='rare_candy' and not rare_candy_left:
                    val=0
                if method!='none':
                    val*=0.77 if method=='regular' else 0.63
                # A vulnerable support Pokemon may not survive; bench cards
                # are less exposed than a face-up active attacker.
                if mon is own[0] and mon.max_hp-mon.damage<=50:
                    val*=0.55
                if val>highest[0]:
                    highest=(val, (evolution.name,ability,method))
            if highest[0] > 0:
                bonuses.append(highest)
        # One ability per unique Pokemon remains possible; cap to prevent
        # utility inflation from repeated identical Support cards.
        bonuses.sort(reverse=True,key=lambda x:x[0])
        selected=bonuses[:2]
        return min(self.MAX_PROJECTED_ABILITY_BONUS,sum(x[0] for x in selected)), [x[1] for x in selected]

    def _future_best(self, own, active_idx, enemy, player, zone,
                     enemy_reply_damage, enemy_ko):
        if enemy.max_hp <= enemy.damage:
            return {'score':0.0,'attack':'alvo nocauteado','pokemon':'—',
                    'ability_options':[], 'evolution_in_hand':False}
        candidates=[]
        for idx,original in enumerate(own[:self.MAX_OWN_BRANCHES]):
            if idx==active_idx and enemy_ko:
                continue
            if original.damage>=original.max_hp:
                continue
            retreat_cost=0
            if idx!=active_idx and not enemy_ko:
                retreat_cost=self._retreat_cost(own[active_idx])
                if len(own[active_idx].energy)<retreat_cost:
                    # Cannot claim a bench attack if retreat cannot be paid.
                    continue
            for evo,method in self._known_evolutions(original, player):
                for attach in (False,True):
                    mon=self._clone(original)
                    mon.card=evo
                    if mon.max_hp <= mon.damage:
                        continue
                    if attach:
                        mon.energy.append(zone)
                    for attack in mon.card.attacks:
                        if not self._payable(mon,attack):
                            continue
                        _,raw,ko=self._attack_effect_value(mon,enemy,attack,len(own)-1)
                        cost=(self.RETREAT_PENALTY+17*retreat_cost) if idx!=active_idx and not enemy_ko else 0
                        value=raw-cost-(3 if attach else 0)
                        if method=='regular': value-=8
                        elif method=='rare_candy': value-=15 # requires both cards in hand and an unlocked item
                        if enemy_ko: value-=6
                        candidates.append({'score':round(value,3),'attack':attack.name,
                            'pokemon':evo.name,'attacher':original.card.name if attach else None,
                            'evolution_in_hand':method!='none','evolution_method':method,
                            'requires_switch':idx!=active_idx and not enemy_ko,
                            'retreat_energy_paid':retreat_cost,'future_attachment':attach,
                            'projected_ko':ko})
        support,sources=self._future_support_bonus(own,enemy,player,zone)
        if not candidates:
            # Even without a payable attack, next-turn abilities can still
            # matter. Do not invent an attack in these states.
            return {'score':round(support,3),'attack':'nenhum ataque legal alcançável',
                    'pokemon':'—','evolution_in_hand':False,
                    'ability_options':sources,'projected_ability_value':round(support,3)}
        best=max(candidates,key=lambda row:row['score'])
        return {**best,'score':round(best['score']+support,3),
                'ability_options':sources,'projected_ability_value':round(support,3)}

    def _preparation_value(self, player:Player, target_idx:int|None)->tuple[float,str]:
        """Only reward energy that reduces shortfall on a *known* reachable line.

        This small residual protects setup from looking identical to doing
        nothing when the 2-turn horizon ends before an evolution can attack.
        """
        if target_idx is None:
            return 0.0,'sem anexo'
        mons=player.all_in_play()
        if not 0<=target_idx<len(mons) or len(player.energy_types)!=1:
            return 0.0,'fora do campo'
        mon=mons[target_idx]
        if mon.damage>=mon.max_hp:
            return 0.0,'nocauteado'
        zone=player.energy_types[0]
        baseline=self._clone(mon)
        additional=self._clone(mon);additional.energy.append(zone)
        best=0.0; best_reason='nenhum ataque novo aproximado'
        for evo,method in self._known_evolutions(mon,player):
            if not evo.attacks:
                continue
            before=self._clone(baseline);before.card=evo
            after=self._clone(additional);after.card=evo
            for attack in evo.attacks:
                old=self._energy_shortfall(before,attack,zone)
                new=self._energy_shortfall(after,attack,zone)
                if old==99 or new>=old or old>3:
                    continue
                # Near a real payable attack, the attachment has more value.
                score={0:22,1:17,2:10,3:3}.get(new,0)
                if method=='rare_candy':score*=0.82
                if method=='regular':score*=0.9
                if target_idx==0 and mon.max_hp-mon.damage<=60:
                    score*=0.62
                if score>best:
                    best=score;best_reason=f'{evo.name}: {attack.name} ({old}→{new} energias)'
        return round(min(self.MAX_PREPARATION_BONUS,best),3),best_reason

    def _note(self,decision,chosen,alternatives,reason):
        """Match by stable action ID/board slot, NEVER Pokémon display name."""
        if len(self.decision_records)>=50:
            return
        normalized=[]
        for i,row in enumerate(alternatives):
            item=dict(row)
            item.setdefault('choice_id',f'{decision}:action:{i}')
            item.setdefault('label',item.get('name','ação'))
            normalized.append(item)
        if isinstance(chosen,dict):
            selected_id=chosen['choice_id']
            selected_label=chosen.get('label',chosen.get('name','ação'))
        else:
            selected_label=chosen
            match=next((r for r in normalized if r['name']==chosen),None)
            selected_id=match['choice_id'] if match else None
        chosen_row=next((r for r in normalized if r['choice_id']==selected_id),None)
        chosen_score=chosen_row['score'] if chosen_row else None
        for row in normalized:
            row['delta_vs_chosen']=(round(row['score']-chosen_score,3)
                if chosen_score is not None else None)
            row['counterfactual_kind']='estimativa_no_mesmo_estado'
        rejected=[row for row in normalized if row['choice_id']!=selected_id]
        runner=max((r['score'] for r in rejected),default=None)
        self.decision_records.append({'turn':self._context_battle.turn if self._context_battle is not None else None,
            'player':self._context_battle.current if self._context_battle is not None else None,
            'decision':decision,'chosen':selected_label,'chosen_id':selected_id,
            'alternatives':sorted(normalized,key=lambda row:(-row['score'],row['choice_id']))[:6],
            'reason':reason,'chosen_projected_score':chosen_score,
            'best_rejected_projected_score':runner,
            'projected_margin':round(chosen_score-runner,3) if chosen_score is not None and runner is not None else None,
            'audit_limitations':'Comparação heurística entre ações; não é resultado causal de partidas contrafactuais.'})

    def select_energy_target(self,player):
        battle=self._context_battle
        if battle is None or len(player.energy_types)!=1:
            return super().select_energy_target(player)
        foe=battle.players[1-battle.current]
        if not player.active or not foe.active:
            return super().select_energy_target(player)
        baseline=self._path(player,foe)
        options=[{'name':'não anexar','label':'não anexar','choice_id':'energy:none',
                  'score':baseline['score'],'current_attack':baseline['current'],
                  'next_attack':baseline['next'],'incoming_risk':baseline['risk']}]
        for idx,mon in enumerate(player.all_in_play()[:self.MAX_OWN_BRANCHES]):
            if mon.max_hp<=mon.damage:continue
            path=self._path(player,foe,target_idx=idx)
            progress,reason=self._preparation_value(player,idx)
            # A useful attachment deserves credit; unneeded excess energy not.
            immediate=any(not self._payable(mon,a) and self._can_reach(mon,a,player.energy_types[0],1)
                          for a in mon.card.attacks)
            surplus=not immediate and progress==0 and len(mon.energy)>=2
            score=round(path['score']+progress*0.8+(6 if immediate and idx==0 else 0)
                        -(11 if surplus else 0),3)
            slot='Ativo' if idx==0 else f'Banco {idx}'
            options.append({'name':mon.card.name,'label':f'{mon.card.name} [{slot}]',
                'choice_id':f'energy:slot:{idx}','index':idx,'score':score,
                'current_attack':path['current'],'next_attack':path['next'],
                'incoming_risk':path['risk'],'enemy_response':path['response'],
                'preparation_bonus':round(progress*0.8,3),'preparation_reason':reason,
                'improvement_vs_no_attachment':round(path['score']-baseline['score'],3),
                'enables_attack_immediately':immediate})
        chosen=max(options,key=lambda x:(x['score'],-x.get('index',99)))
        if chosen['choice_id']!='energy:none' and chosen['score']<=baseline['score']+1.5:
            chosen=options[0]
        self._note('energy',chosen,options,
          'Dois turnos, evolução conhecida/Rare Candy, habilidade suportada, preparo de energia e custo de oportunidade')
        return player.all_in_play()[chosen['index']] if 'index' in chosen else None

    def _retreat_option(self,battle):
        p=battle.players[battle.current];foe=battle.players[1-battle.current]
        if not p.active or not foe.active or not p.bench or p.retreated:return None
        stay=self._path(p,foe,fixed_active_idx=0)
        options=[{'name':'manter ativo','label':'manter '+p.active.card.name,
                  'choice_id':'retreat:stay','score':stay['score'],'feasible':True}]
        for idx,mon in enumerate(p.all_in_play()[1:self.MAX_OWN_BRANCHES],start=1):
            result=self._path(p,foe,fixed_active_idx=idx)
            options.append({'name':mon.card.name,'label':f'{mon.card.name} [Banco {idx}]',
                   'choice_id':f'retreat:slot:{idx}','index':idx,'score':result['score'],
                   'feasible':result['score']>-1e5,
                   'reason':result['current'] if result['score']>-1e5 else 'recuo inviável'})
        viable=[row for row in options[1:] if row['feasible'] and row['score']>stay['score']+24]
        chosen=max(viable,key=lambda x:x['score']) if viable else options[0]
        self._note('retreat',chosen,options,'Recuo legal, identificador de slot e margem mínima de 24 pontos')
        return p.all_in_play()[chosen['index']] if 'index' in chosen else None


class PlanningAgentV0911(PlanningAgentV0910):
    """v0.9.11: conservative public-deck setup valuation and energy tempo.

    No access to either shuffled deck's card identities, opponent hand or
    opponent Energy Zone. The optionally configured OWN deck roster is the
    pre-shuffle 20-card list, not the remaining draw pile. Probabilities are
    deliberately *discounted upper-bound estimates*, not simulated draws.
    """
    policy_name = 'planning_v0911'
    MAX_UNSEEN_EVOLUTION_BONUS = 12.0
    MAX_ENERGY_RESIDUAL_BONUS = 30.0

    def __init__(self, line_map=None):
        super().__init__(line_map)
        self._own_deck_roster: tuple[Card,...] = ()
        # Evidence-based guardrail: the 0.9.10 planner lost ground on the
        # all-basic Hoopa roster. Retain the *exact* 0.9.9 policy for all-basic
        # lists, not a Pokemon-name-specific hardcode, until A/B validation.
        self._basic_only_reference = PlanningAgentV099(line_map)
        self._execution_route = 'planning_v0911'

    def play_turn(self, battle: Battle):
        has_evolution = any(c.kind=='pokemon' and c.stage>0
                            for c in self._own_deck_roster)
        has_pokemon = any(c.kind=='pokemon' for c in self._own_deck_roster)
        if has_pokemon and not has_evolution:
            self._execution_route='planning_v099_guardrail_all_basic'
            result=self._basic_only_reference.play_turn(battle)
            self.decision_records=self._basic_only_reference.decision_records
            for record in self.decision_records:
                record['policy_route']='planning_v099_guardrail_all_basic'
            return result
        self._execution_route='planning_v0911'
        return super().play_turn(battle)

    def configure_own_deck(self, cards):
        """Supply own PUBLIC starting recipe, never the shuffled deck order."""
        roster=tuple(cards)
        if len(roster)!=20 or not all(isinstance(x,Card) for x in roster):
            raise ValueError('Perfil próprio requer as 20 cartas originais')
        self._own_deck_roster=roster
        return self

    @staticmethod
    def _two_draw_upper_probability(population: int, hits: int) -> float:
        """P(at least one match in up to 2 draws), before safety discount."""
        n=max(0,int(population)); k=max(0,min(n,int(hits)))
        if not n or not k:return 0.0
        misses=1.0
        for draw in range(min(2,n)):
            misses*=max(0,n-k-draw)/max(1,n-draw)
        return max(0.0,min(1.0,1.0-misses))

    def _unseen_evolution_bonus(self, player:Player, target:InPlay, zone:str):
        """Probabilistic option for an evolution *in the known recipe*.

        Estimate which roster cards might still be drawable from known own
        hand/board. Never enumerate player.deck or look at opponent private
        data. Discarded/evolved cards can only reduce real probabilities, so
        the result is discounted and capped. No speculative card is actually
        placed in hand or used in the search tree.
        """
        if not self._own_deck_roster:
            return 0.0, 'perfil inicial não fornecido'
        current = target.card
        if current.stage >= 2:
            return 0.0, 'último estágio'
        visible=Counter(c.id for c in player.hand)
        visible.update(m.card.id for m in player.all_in_play())
        for mon in player.all_in_play():
            visible.update(c.id for c in mon.pre_evolutions)
        roster=Counter(c.id for c in self._own_deck_roster)
        # Only read the own remaining deck *length*, not its contents.
        n=len(player.deck)
        if n<=0:return 0.0,'sem compras restantes'
        best=0.0; name='sem evolução plausível'
        for evo in self._own_deck_roster:
            if evo.kind!='pokemon' or evo.stage<=current.stage:continue
            direct=(evo.stage==current.stage+1 and
                    evo.evolves_from.casefold()==current.name.casefold())
            candy_line=(current.stage==0 and evo.stage==2 and
                   self.line_map.get(evo.evolves_from.casefold(),'').casefold()==current.name.casefold())
            if not direct and not candy_line:continue
            remaining=max(0,roster[evo.id]-visible[evo.id])
            if not remaining:continue
            p_draw=self._two_draw_upper_probability(n,remaining)*0.65
            if candy_line:
                known_candy=any(c.effect=='rare_candy' for c in player.hand)
                if not known_candy:
                    # The card AND an Item would have to be acquired; keep the
                    # speculative route weak rather than inventing Rare Candy.
                    p_draw*=0.18 if any(c.effect=='rare_candy' for c in self._own_deck_roster) else 0
                else:
                    p_draw*=0.72
            base=self._clone(target); boosted=self._clone(target)
            base.card=evo;boosted.card=evo;boosted.energy.append(zone)
            for atk in evo.attacks:
                old=self._energy_shortfall(base,atk,zone)
                new=self._energy_shortfall(boosted,atk,zone)
                if old==99 or new>=old or old>4:continue
                # Attack's damage is an upper bound on payoff, but this is
                # resource *option* value, not free projected damage.
                impact=min(26,9+0.12*max(0,atk.damage))
                readiness={0:1.0,1:0.85,2:0.65,3:0.35,4:0.10}.get(new,0)
                value=p_draw*impact*readiness
                if value>best:best=value;name=f'{evo.name}: {atk.name}, P~{p_draw:.2f}'
        return round(min(self.MAX_UNSEEN_EVOLUTION_BONUS,best),3),name

    def _energy_residual(self, player:Player, index:int):
        mon=player.all_in_play()[index]
        if mon.damage>=mon.max_hp:return (0.,'nocauteado')
        zone=player.energy_types[0]
        known,known_reason=self._preparation_value(player,index)
        uncertain,uncertain_reason=self._unseen_evolution_bonus(player,mon,zone)
        # Future attack setup for any *currently visible* card, including
        # backups with 2-3 Energy moves. This restores the tempo incentive
        # weakened by the v0.9.10 no-attach threshold.
        baseline=self._clone(mon);added=self._clone(mon);added.energy.append(zone)
        best_existing=0.0
        for atk in mon.card.attacks:
            old=self._energy_shortfall(baseline,atk,zone)
            new=self._energy_shortfall(added,atk,zone)
            if old==99 or new>=old or old>4:continue
            score={0:23,1:17,2:12,3:5,4:1}.get(new,0)
            score+=min(7,max(0,atk.damage)*0.05)
            best_existing=max(best_existing,score)
        # Both known and probable evolutions compete for the same energy,
        # rather than being summed as multiple imaginary attackers.
        setup=max(known, best_existing) + uncertain
        if mon is player.active and mon.max_hp-mon.damage<=40:
            setup*=0.60
        if index and player.active and any(self._payable(player.active,a)
                                          for a in player.active.card.attacks):
            # A ready Active allows building a reserve; this does not imply
            # an invented future switch or an extra turn's attachment.
            setup+=3.5 if best_existing or known or uncertain else 0
        return round(min(self.MAX_ENERGY_RESIDUAL_BONUS,setup),3),(
            f'conhecido: {known_reason}; baralho: {uncertain_reason}')

    def select_energy_target(self,player):
        battle=self._context_battle
        if battle is None or len(player.energy_types)!=1:
            return super().select_energy_target(player)
        foe=battle.players[1-battle.current]
        if not player.active or not foe.active:
            return super().select_energy_target(player)
        baseline=self._path(player,foe)
        options=[{'name':'não anexar','label':'não anexar','choice_id':'energy:none',
                  'score':baseline['score'], 'current_attack':baseline['current'],
                  'next_attack':baseline['next'], 'incoming_risk':baseline['risk']}]
        for idx,mon in enumerate(player.all_in_play()[:self.MAX_OWN_BRANCHES]):
            if mon.max_hp<=mon.damage:continue
            path=self._path(player,foe,target_idx=idx)
            residual,why=self._energy_residual(player,idx)
            ready=any(self._payable(mon,a) for a in mon.card.attacks)
            immediate=any(not self._payable(mon,a) and
                self._can_reach(mon,a,player.energy_types[0],1) for a in mon.card.attacks)
            # No reward for overfilling a paid attack unless the energy is
            # needed by another visible/possible line.
            waste=(10 if ready and not immediate and residual==0 else 0)
            score=round(path['score']+residual*0.89+(4 if immediate and idx==0 else 0)-waste,3)
            label='Ativo' if idx==0 else f'Banco {idx}'
            options.append({'name':mon.card.name,'label':f'{mon.card.name} [{label}]',
                'choice_id':f'energy:slot:{idx}','index':idx,'score':score,
                'current_attack':path['current'],'next_attack':path['next'],
                'incoming_risk':path['risk'],'enemy_response':path['response'],
                'residual_bonus':round(residual*0.89,3),'residual_reason':why,
                'improvement_vs_no_attachment':round(path['score']-baseline['score'],3),
                'enables_attack_immediately':immediate})
        # Deterministic tie-breaks: stronger decision first, never a random
        # opponent-side hidden field. Keep the no-attach branch for wasted fuel.
        chosen=max(options,key=lambda x:(x['score'], -x.get('index',99)))
        if chosen['choice_id']!='energy:none' and chosen['score']<=baseline['score']+1.0:
            chosen=options[0]
        self._note('energy',chosen,options,
           'Projeção pública + valor residual de ataques e evoluções do deck conhecido; sem consultar cartas ocultas')
        return player.all_in_play()[chosen['index']] if 'index' in chosen else None
