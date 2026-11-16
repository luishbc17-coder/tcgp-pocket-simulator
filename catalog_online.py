"""Community catalog adapter; metadata is not executable gameplay rules."""
import requests
import streamlit as st

URL = 'https://raw.githubusercontent.com/PocketDecks/pokemon-tcg-pocket-cards/refs/heads/main/data/v5/cards.core.min.json'


def normalize(raw):
    if not isinstance(raw, dict):
        return None
    name = raw.get('name') or raw.get('cardName')
    set_code = raw.get('set') or raw.get('setCode') or raw.get('expansion') or ''
    if isinstance(set_code, dict):
        set_code = set_code.get('code') or set_code.get('id') or ''
    number = raw.get('number') or raw.get('cardNumber') or raw.get('deckBuilderNr') or raw.get('id')
    if not name or number is None:
        return None
    unique = str(raw.get('id') or f'{set_code}-{number}')
    image = raw.get('image') or raw.get('imageUrl') or raw.get('image_url') or ''
    if isinstance(image, dict):
        image = image.get('url') or image.get('small') or ''
    if not isinstance(image, str) or not image.startswith('https://'):
        image = ''
    typ = raw.get('type') or raw.get('cardType') or raw.get('category') or ''
    if isinstance(typ, dict):
        typ = typ.get('name', '')
    return {'id': unique, 'name': str(name), 'set': str(set_code), 'number': str(number),
            'type': str(typ), 'image': image, 'hp': raw.get('hp') or raw.get('health'),
            'raw': raw}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_catalog():
    response = requests.get(URL, timeout=25, headers={'User-Agent': 'TCGPocketLab/0.4'})
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data = data.get('cards', [])
    if not isinstance(data, list):
        raise ValueError('Formato inesperado do catálogo')
    cards = [x for raw in data if (x := normalize(raw))]
    if len(cards) < 100:
        raise ValueError('Catálogo incompleto ou esquema alterado')
    return cards


def validate_selection(counts, catalog):
    by_id = {c['id']: c for c in catalog}
    issues = []
    if sum(counts.values()) != 20:
        issues.append('O deck precisa ter exatamente 20 cartas.')
    by_name = {}
    for cid, n in counts.items():
        if cid not in by_id:
            issues.append(f'Carta não encontrada no catálogo: {cid}')
            continue
        if type(n) is not int or not 1 <= n <= 2:
            issues.append(f'Quantidade inválida para {cid}')
            continue
        name = by_id[cid]['name'].casefold()
        by_name[name] = by_name.get(name, 0) + n
    if any(n > 2 for n in by_name.values()):
        issues.append('Há mais de duas cópias de um mesmo nome, incluindo artes diferentes.')
    return issues
