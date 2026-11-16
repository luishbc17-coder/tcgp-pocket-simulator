"""Audit and conservative adapter for PocketDecks v5 gameplay payload.

The provider documents this as a community data source, NOT an official game
rules engine. We only compile explicitly supported text into executable cards.
"""
from __future__ import annotations
from collections import Counter
import re
import unicodedata
from typing import Iterable
from battle_engine import Attack, Card, UnsupportedEffect, parse_cost, RuleError

GAMEPLAY_URL = (
    'https://raw.githubusercontent.com/PocketDecks/pokemon-tcg-pocket-cards/'
    'refs/heads/main/data/v5/cards.gameplay.min.json'
)


def audit_core_cards(cards: list[dict]) -> dict:
    ids = [str(c.get('id', '')) for c in cards]
    stages = Counter(c.get('stage') or 'N/A' for c in cards)
    sets = Counter(c.get('set') for c in cards if c.get('set'))
    issues = []
    duplicate_count = len(ids) - len(set(ids))
    if duplicate_count:
        issues.append(f'{duplicate_count} IDs repetidos')
    if any(not c.get('name') or not c.get('id') for c in cards):
        issues.append('Cartas sem nome ou ID')
    if not sets:
        issues.append('Nenhuma expansão identificada (set_code ausente?)')
    return {
        'records': len(cards),
        'unique_ids': len(set(ids)),
        'duplicates': duplicate_count,
        'expansions': len(sets),
        'by_stage': dict(stages),
        'missing_images': sum(not c.get('image') for c in cards),
        'issues': issues,
    }


def audit_gameplay_records(gameplay: list[dict], core: list[dict] | None = None) -> dict:
    if not isinstance(gameplay, list):
        raise ValueError('O gameplay precisa ser uma lista JSON')
    ids = [r.get('id') for r in gameplay]
    duplicates = len(ids) - len(set(ids))
    pokemon = [r for r in gameplay if r.get('type') == 'Pokémon']
    trainers = [r for r in gameplay if r.get('type') == 'Trainer']
    issues = []
    if duplicates:
        issues.append(f'{duplicates} IDs repetidos no gameplay')
    if len(gameplay) < 100:
        issues.append('Gameplay com menos de 100 registros; provável falha de carga')
    if any('set_code' not in r for r in gameplay):
        issues.append('Há cartas sem set_code')
    if any(not isinstance(r.get('health'), int) or not isinstance(r.get('attacks'), dict)
           for r in pokemon):
        issues.append('Pokémon com atributos de batalha incompletos')
    if any(not isinstance(r.get('card_text'), str) for r in trainers
           if not r.get('stage')):
        issues.append('Treinador sem texto mecânico')
    core_ids = set(x['id'] for x in (core or []) if x.get('id'))
    game_ids = set(ids)
    if core is not None and core_ids != game_ids:
        issues.append(f'IDs divergentes: {len(core_ids - game_ids)} só no core, '
                      f'{len(game_ids - core_ids)} só no gameplay')
    return {'records': len(gameplay), 'pokemon': len(pokemon),
            'trainers': len(trainers), 'unique_ids': len(game_ids),
            'duplicates': duplicates,
            'missing_from_gameplay': len(core_ids - game_ids),
            'extra_gameplay_ids': len(game_ids - core_ids) if core is not None else None,
            'issues': issues}


def _text(s):
    """Canonical English card text: ignore typography, not the mechanical words.

    OCR, JSON newlines and typographic apostrophes can vary between source
    versions. Entire texts are still compared with known reference sentences;
    unexpected mechanics never match merely because a familiar name is present.
    """
    text = unicodedata.normalize('NFKC', str(s or '')).casefold()
    text = (text.replace('’', "'").replace('‘', "'")
                .replace('—', '-').replace('–', '-').replace('−', '-')
                .replace('pokémon', 'pokemon'))
    text = re.sub(r'\s+', ' ', text).strip()
    return text.rstrip(' .')


def _same_text(source, reference):
    """Strict equality after removing nonsemantic formatting variations."""
    def canon(x):
        x = _text(x)
        # Some data revisions differ in comma spacing, full stops and bracket spacing.
        x = re.sub(r'\s*([,.!?()[\]])\s*', r'\1', x)
        x = re.sub(r'\[\s*([a-z])\s*\]', r'[\1]', x)
        return x
    return canon(source) == canon(reference)


def _is_one_of(source, *references):
    return any(_same_text(source, reference) for reference in references)


# Explicit reference transcriptions of the PocketDecks v5 English game text.
# Multiple entries are accepted only where the wording is mechanically identical.
TRAINER_EFFECTS = {
    "Serena's Choice": ('serenas_choice', (
        'Look at the top 3 cards of your deck and put 1 of them into your hand. Shuffle back into your deck.',
    )),
    "Professor's Research": ('research', (
        'Draw 2 cards.',
    )),
    'Poké Ball': ('pokeball', (
        'Put 1 random Basic Pokémon from your deck into your hand.',
    )),
    'Rare Candy': ('rare_candy', (
        "Choose 1 of your Basic Pokémon in play. If you have a Stage 2 card in your hand that evolves from that Pokémon, put that card on the Basic Pokémon to evolve it, skipping the Stage 1. You can't use this card during your first turn or on a Basic Pokémon that was put into play this turn.",
    )),
    'Copycat': ('copycat', (
        "Shuffle your hand into your deck. Draw a card for each card in your opponent's hand.",
    )),
    'Pokémon Center Lady': ('center_lady', (
        'Heal 30 damage from 1 of your Pokémon, and it recovers from all Special Conditions.',
    )),
    'Repel': ('repel', (
        "Switch out your opponent's Active Basic Pokémon to the Bench. (Your opponent chooses the new Active Pokémon.)",
    )),
    'Cyrus': ('cyrus', (
        "Switch in 1 of your opponent's Benched Pokémon that has damage on it to the Active Spot.",
    )),
    'Mars': ('mars', (
        "Your opponent shuffles their hand into their deck and draws a card for each of their remaining points needed to win.",
    )),
    'X Speed': ('x_speed', (
        'During this turn, the Retreat Cost of your Active Pokémon is 1 less.',
    )),
    'Field Blower': ('field_blower', (
        "Discard a Pokémon Tool card from a Pokémon (yours or your opponent's) , or discard a Stadium card in play.",
    )),
    'Lucky Ice Pop': ('lucky_ice_pop', (
        'Heal 20 damage from your Active Pokémon. If you healed any damage in this way, flip a coin. If heads, put this Lucky Ice Pop into your hand instead of discarding it.',
        'Heal 20 damage from your Active Pokémon. If you healed any damage in this way, flip a coin. If heads, put this Lucky Ice Pop into your hand instead of the discard pile.',
    )),
}


def _recognize_trainer(r: dict):
    name = r['name']
    text = r.get('card_text')
    if name == 'Rare Candy':
        # PocketDecks' Rare Candy has two known generations of the same English
        # effect. Both must contain all three restrictions and the Stage 2 jump.
        t = _text(text)
        if (t.startswith('choose 1 of your basic pokemon in play')
            and ('stage 2' in t and 'skipping the stage 1' in t)
            and ("can't use this card during your first turn" in t)
            and ('put into play this turn' in t or 'on the same turn it came into play' in t)
            and not ('except ' in t or 'unless ' in t)):
            return 'rare_candy'
        raise UnsupportedEffect(f'{name}: texto do Doce Raro divergente')
    entry = TRAINER_EFFECTS.get(name)
    if entry is not None and _is_one_of(text, *entry[1]):
        return entry[0]
    raise UnsupportedEffect(f'{name}: texto de treinador não reconhecido; conferir versão do catálogo')


def _recognize_attack(r: dict, raw_attack: dict):
    name = raw_attack.get('name')
    damage = raw_attack.get('damage')
    effect = raw_attack.get('effect')
    if name is None:
        return None
    cost = parse_cost(raw_attack.get('cost'))
    if (r['name'] == 'Swablu' and name == 'Sing' and cost == ('colorless',)
            and damage in (None, 0) and _same_text(effect, "Your opponent's Active Pokémon is now Asleep.")):
        return Attack(name, cost, 0, 'sleep_active')
    if (r['name'] == 'Chien-Pao ex' and name == 'Diving Icicles'
        and damage is None and cost == ('water', 'water', 'water')
        and _same_text(effect, "Discard all [W] Energy from this Pokémon. This attack does 130 damage to 1 of your opponent's Pokémon.")):
        return Attack(name, cost, 0, 'water_snipe_130_discard')
    if type(damage) is not int or damage < 0:
        raise UnsupportedEffect(f'{r["name"]} / {name}: dano dinâmico ou desconhecido')
    if not effect:
        return Attack(name, cost, damage)
    if _same_text(effect, 'Heal 30 damage from this Pokémon.'):
        return Attack(name, cost, damage, 'heal_self_30')
    if _same_text(effect, 'Flip a coin. If heads, this attack does 30 more damage.'):
        return Attack(name, cost, damage, 'coin_bonus_30')
    if (r['name'] == 'Suicune ex' and name == 'Crystal Waltz'
        and damage == 20 and cost == ('water','water')
        and _same_text(effect, "This attack does 20 damage for each Benched Pokémon (both yours and your opponent's).")):
        return Attack(name, cost, damage, 'both_benches_plus_20')
    if (r['name'] == 'Entei ex' and name == 'Blazing Beatdown'
        and damage == 60 and cost == ('fire','fire')
        and _is_one_of(effect,
            'If this Pokémon has at least 2 extra [R] Energy attached, this attack does 60 more damage.',
            'If this Pokémon has at least 2 extra Fire Energy attached, this attack does 60 more damage.')):
        return Attack(name, cost, damage, 'fire_extra_2_plus_60')
    if (r['name'] == 'Mega Charizard Y ex' and name == 'Crimson Dive'
        and damage == 250 and cost == ('fire','fire','fire','colorless')
        and _same_text(effect, 'This Pokémon also does 50 damage to itself.')):
        return Attack(name, cost, damage, 'recoil_50')
    if (r['name'] == 'Mega Altaria ex' and name == 'Mega Harmony'
        and damage == 40 and cost == ('psychic','psychic')
        and _same_text(effect, 'This attack does 30 more damage for each of your Benched Pokémon.')):
        return Attack(name, cost, damage, 'bench_plus_30')
    if r['name'] == 'Hoopa ex':
        if (name == 'Shadow Bullet' and damage == 30 and cost == ('darkness',)
            and _same_text(effect, "This attack also does 20 damage to 1 of your opponent's Benched Pokémon.")):
            return Attack(name, cost, damage, 'snipe_20_bench')
        if (name == 'Dynamite Punch' and damage == 100 and cost == ('darkness','darkness','colorless')
            and _same_text(effect, 'This Pokémon also does 20 damage to itself.')):
            return Attack(name, cost, damage, 'recoil_20')
    if (r['name'] == 'Mega Absol ex' and name == 'Darkness Claw'
        and damage == 80 and cost == ('darkness','darkness')
        and _same_text(effect, 'Your opponent reveals their hand. Choose a Supporter card you find there and discard it.')):
        return Attack(name, cost, damage, 'discard_opponent_supporter')
    if (r['name'] == 'Chingling' and name == 'Jingly Noise'
        and damage == 10 and cost == ()
        and _same_text(effect, "During your opponent's next turn, they can't play any Item cards from their hand.")):
        return Attack(name, cost, damage, 'item_lock_next_turn')
    if (r['name'] == 'Mega Swampert ex' and name == 'Strong-Armed Destroyer'
        and damage == 150 and cost == ('water','water','water')
        and _same_text(effect, "Discard 2 random Energy from among the Energy attached to all Pokémon (both yours and your opponent's).")):
        return Attack(name, cost, damage, 'discard_2_global_random')
    raise UnsupportedEffect(f'{r["name"]} / {name}: efeito de ataque não reconhecido; conferir texto')


def _recognize_ability(r: dict) -> str:
    data = r.get('ability') or {}
    if not data.get('exists'):
        return ''
    name = data.get('name')
    effect = data.get('effect')
    if (name == 'Legendary Pulse' and r['name'] in ('Entei ex', 'Suicune ex', 'Raikou ex')
        and _same_text(effect, 'At the end of your turn, if this Pokémon is in the Active Spot, draw a card.')):
        return 'legendary_pulse'
    if (r['name'] == 'Baxcalibur' and name == 'Ice Maker'
        and _is_one_of(effect,
            'Once during your turn, you may take a [W] Energy from your Energy Zone and attach it to the [W] Pokémon in the Active Spot.',
            'Once during your turn, you may take a Water Energy from your Energy Zone and attach it to the Water Pokémon in the Active Spot.')):
        return 'ice_maker'
    if (r['name'] == 'Magneton' and name == 'Volt Charge'
        and _is_one_of(effect,
            'Once during your turn, you may take a [L] Energy from your Energy Zone and attach it to this Pokémon.',
            'Once during your turn, you may take a Lightning Energy from your Energy Zone and attach it to this Pokémon.')):
        return 'volt_charge'
    if (r['name'] == 'Charmeleon' and name == 'Ignition'
        and _is_one_of(effect,
            'Once during your turn, when you play this Pokémon from your hand to evolve 1 of your Pokémon, you may take a [R] Energy from your Energy Zone and attach it to your Active [R] Pokémon.',
            'Once during your turn, when you play this Pokémon from your hand to evolve 1 of your Pokémon, you may take a Fire Energy from your Energy Zone and attach it to your Active Fire Pokémon.')):
        return 'ignition'
    if (r['name'] == 'Greninja' and name == 'Water Shuriken'
        and _same_text(effect, "Once during your turn, you may do 20 damage to 1 of your opponent's Pokémon.")):
        return 'water_shuriken'
    if (r['name'] == 'Darkrai ex' and name == 'Nightmare Aura'
        and _same_text(effect, "Whenever you attach a [D] Energy from your Energy Zone to this Pokémon, do 20 damage to your opponent's Active Pokémon.")):
        return 'nightmare_aura'
    raise UnsupportedEffect(f'{r["name"]}: habilidade {name} não reconhecida; conferir texto')


def compile_card(raw: dict) -> Card:
    """Fail closed: no silent approximation of abilities, tools or card text."""
    if not isinstance(raw, dict) or not raw.get('id') or not raw.get('name'):
        raise UnsupportedEffect('Incomplete card identity')
    if raw.get('stage') and raw.get('type') == 'Trainer':
        raise UnsupportedEffect(f'{raw["name"]}: fóssil/jogabilidade especial pendente')
    if raw.get('type') == 'Trainer':
        subtype = str(raw.get('subtype', '')).lower()
        if subtype == 'supporter':
            kind = 'supporter'
        elif subtype == 'item':
            kind = 'item'
        elif subtype == 'tool':
            kind = 'tool'
        else:
            raise UnsupportedEffect(f'{raw["name"]}: tipo {subtype} não implementado')
        if kind == 'tool':
            detail = raw.get('card_text')
            if (raw['name'] == 'Lucky Egg' and _same_text(detail,
                "if the pokémon this card is attached to is knocked out by damage from an attack from your opponent's pokémon, draw cards until you have 5 cards in your hand")):
                return Card(raw['id'],raw['name'],kind,effect='lucky_egg')
            if (raw['name'] == 'Deceptive Needle' and _same_text(detail,
                "at the end of your turn, if the [ d ] pokémon this card is attached to is in the active spot, do 10 damage to your opponent's active pokémon")):
                return Card(raw['id'],raw['name'],kind,effect='deceptive_needle')
            if (raw['name'] == 'Giant Cape' and _same_text(detail,
                    'The Pokémon this card is attached to gets +20 HP.')):
                return Card(raw['id'],raw['name'],kind,effect='giant_cape')
            if (raw['name'] == 'Eviolite' and _same_text(detail,
                    "The Basic Pokémon this card is attached to takes −20 damage from attacks from your opponent's Pokémon.")):
                return Card(raw['id'],raw['name'],kind,effect='eviolite')
            if (raw['name'] == 'Inflatable Boat' and _is_one_of(detail,
                    'The Retreat Cost of the [ W ] Pokémon this card is attached to is 1 less.',
                    'The Retreat Cost of the {W} Pokémon this card is attached to is 1 less.')):
                return Card(raw['id'],raw['name'],kind,effect='inflatable_boat')
            raise UnsupportedEffect(f'{raw["name"]}: efeito de ferramenta ainda não implementado')
        return Card(raw['id'], raw['name'], kind, effect=_recognize_trainer(raw))
    if raw.get('type') != 'Pokémon':
        raise UnsupportedEffect(f'{raw["name"]}: categoria desconhecida')
    ability_handler = _recognize_ability(raw)
    stage_map = {'Basic': 0, 'Stage 1': 1, 'Stage 2': 2}
    if raw.get('stage') not in stage_map:
        raise UnsupportedEffect(f'{raw["name"]}: estágio desconhecido')
    element = str(raw.get('subtype', '')).casefold()
    if element not in ('grass','fire','water','lightning','psychic','fighting',
                       'darkness','metal','dragon','colorless'):
        raise UnsupportedEffect(f'{raw["name"]}: tipo desconhecido {element}')
    attacks = raw.get('attacks') or {}
    if not isinstance(attacks, dict):
        raise UnsupportedEffect(f'{raw["name"]}: formato de ataques inválido')
    out = []
    for slot in ('1', '2'):
        candidate = attacks.get(slot)
        if not candidate:
            continue
        attack = _recognize_attack(raw,candidate)
        if attack:
            out.append(attack)
    if not out:
        # Some playable Pokémon don't attack (e.g. Fossils), not yet supported.
        raise UnsupportedEffect(f'{raw["name"]}: sem ataques suportados')
    hp = raw.get('health')
    if type(hp) is not int or hp <= 0:
        raise UnsupportedEffect(f'{raw["name"]}: HP inválido')
    points = raw.get('points')
    if points not in (1,2,3):
        raise UnsupportedEffect(f'{raw["name"]}: pontuação inválida')
    retreat = raw.get('retreat')
    if type(retreat) is not int or retreat < 0:
        raise UnsupportedEffect(f'{raw["name"]}: recuo inválido')
    return Card(raw['id'],raw['name'],'pokemon',stage_map[raw['stage']],
                raw.get('evolves_from') or '',hp,points,
                element,str(raw.get('weakness') or '').casefold(),retreat,
                tuple(out), ability=ability_handler)


def compile_deck(counts: dict[str,int], gameplay: list[dict]) -> tuple[list[Card], list[str]]:
    lookup = {r['id']: r for r in gameplay}
    output, errors = [], []
    for card_id, n in counts.items():
        if type(n) is not int or n not in (1,2):
            errors.append(f'{card_id}: quantidade inválida')
            continue
        if card_id not in lookup:
            errors.append(f'{card_id}: não encontrado no catálogo gameplay')
            continue
        try:
            card = compile_card(lookup[card_id])
            output.extend([card] * n)
        except UnsupportedEffect as ex:
            errors.append(str(ex))
    if sum(counts.values()) != 20:
        errors.append('O deck precisa ter exatamente 20 cartas')
    return output, errors


def evolution_line_map(gameplay: list[dict]) -> dict[str,str]:
    return {str(r.get('name','')).casefold(): str(r['evolves_from'])
            for r in gameplay if r.get('stage') == 'Stage 1' and r.get('evolves_from')}
