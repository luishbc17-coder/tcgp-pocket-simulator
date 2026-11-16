"""PocketDecks v5 core and gameplay catalog adapters.

Community-maintained source. `core` is a playables catalogue, not all alternate
rarity prints. Runtime audit helps identify changed schemas or incomplete data.
"""
import re
import requests
try:
    import streamlit as st
except ImportError:  # pure functions remain unit-testable without web dependencies
    class _NoStreamlit:
        @staticmethod
        def cache_data(*args, **kwargs):
            return lambda fn: fn
    st = _NoStreamlit()
from gameplay_catalog import GAMEPLAY_URL

URL = 'https://raw.githubusercontent.com/PocketDecks/pokemon-tcg-pocket-cards/refs/heads/main/data/v5/cards.core.min.json'


def normalize(raw):
    if not isinstance(raw, dict):
        return None
    name = raw.get('name') or raw.get('cardName')
    set_code = raw.get('set_code') or raw.get('set') or raw.get('setCode') or raw.get('expansion') or ''
    if isinstance(set_code, dict):
        set_code = set_code.get('code') or set_code.get('id') or ''
    cid = raw.get('id')
    number = raw.get('number') or raw.get('cardNumber')
    if number is None and cid:
        number = str(cid).rsplit('-', 1)[-1]
    if not name or not cid or number is None:
        return None
    image = raw.get('image') or raw.get('imageUrl') or raw.get('image_url') or ''
    if isinstance(image, dict):
        image = image.get('url') or image.get('small') or ''
    if not isinstance(image, str) or not image.startswith('https://'):
        image = ''
    typ = raw.get('type') or raw.get('cardType') or raw.get('category') or ''
    if isinstance(typ, dict):
        typ = typ.get('name', '')
    return {'id': str(cid), 'name': str(name), 'set': str(set_code), 'number': str(number),
            'type': str(typ), 'subcategory': str(raw.get('subtype') or ''),
            'stage': raw.get('stage'), 'image': image,
            'hp': raw.get('health') or raw.get('hp'), 'raw': raw}


def _request_catalog(url, kind):
    response = requests.get(url,timeout=30,headers={'User-Agent': 'TCGPocketLab/0.6'})
    response.raise_for_status()
    data = response.json()
    if isinstance(data,dict):
        data = data.get('cards', [])
    if not isinstance(data,list) or len(data)<100:
        raise ValueError(f'Catálogo {kind} incompleto ou esquema alterado')
    return data


@st.cache_data(ttl=3600,show_spinner=False)
def fetch_catalog():
    data = _request_catalog(URL, 'core')
    cards = [c for raw in data if (c:=normalize(raw))]
    if len(cards) != len(data):
        raise ValueError('Nem todas as cartas foram normalizadas; catálogo não confiável')
    return cards


@st.cache_data(ttl=3600,show_spinner=False)
def fetch_gameplay_catalog():
    return _request_catalog(GAMEPLAY_URL, 'gameplay')


def validate_selection(counts, catalog):
    by_id = {c['id']: c for c in catalog}
    issues = []
    if sum(counts.values()) != 20:
        issues.append('O deck precisa ter exatamente 20 cartas.')
    by_name = {}
    basics = 0
    for cid, n in counts.items():
        if cid not in by_id:
            issues.append(f'Carta não encontrada no catálogo: {cid}')
            continue
        if type(n) is not int or not 1 <= n <= 2:
            issues.append(f'Quantidade inválida para {cid}')
            continue
        name = by_id[cid]['name'].casefold()
        by_name[name] = by_name.get(name, 0) + n
        if by_id[cid]['type']=='Pokémon' and by_id[cid].get('stage')=='Basic':
            basics += n
    if any(n > 2 for n in by_name.values()):
        issues.append('Há mais de duas cópias de um mesmo nome, incluindo artes diferentes.')
    if basics==0:
        issues.append('O deck precisa conter pelo menos um Pokémon Básico.')
    return issues
