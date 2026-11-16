"""Validate a deck transfer *without* mutating Streamlit widget state.

The web layer stages this result, calls st.rerun(), and only applies the staged
values on the NEXT run, before any widgets have been instantiated.
"""
from collections import Counter


def prepare_transfer(data, by_id, allowed_energies):
    if not isinstance(data, dict):
        raise ValueError('O deck precisa ser um objeto JSON.')
    counts = data.get('cards')
    if not isinstance(counts, dict):
        raise ValueError('O campo cards precisa ser um objeto.')
    if len(counts) > 20:
        raise ValueError('O deck não pode ter mais de 20 IDs.')
    total = 0
    names = Counter()
    for cid, quantity in counts.items():
        if cid not in by_id:
            raise ValueError(f'Carta não encontrada no catálogo: {cid}')
        if type(quantity) is not int or quantity < 1 or quantity > 2:
            raise ValueError(f'Quantidade inválida para {cid}.')
        total += quantity
        names[by_id[cid]['name'].casefold()] += quantity
    if total > 20:
        raise ValueError('O deck tem mais de 20 cartas.')
    if any(n > 2 for n in names.values()):
        raise ValueError('Mais de duas cópias com o mesmo nome, incluindo artes diferentes.')
    energies = data.get('energy_types')
    if (not isinstance(energies, list) or not 1 <= len(energies) <= 3
            or len(set(energies)) != len(energies)
            or any(not isinstance(e, str) or e not in allowed_energies for e in energies)):
        raise ValueError('Tipos de energia inválidos.')
    return {
        'counts': dict(counts),
        'energy': list(energies),
        'deck_name': str(data.get('name') or 'Meu deck')[:100],
    }


def stage_transfer(state, data, by_id, allowed_energies):
    """Stage a validated deck; existing widget-bound values remain unchanged."""
    staged = prepare_transfer(data, by_id, allowed_energies)
    state['_pending_deck_transfer'] = staged
    return staged


def apply_pending_transfer(state):
    """Must be called at script startup BEFORE widgets are registered."""
    pending = state.pop('_pending_deck_transfer', None)
    if pending is None:
        return None
    for key in ('counts', 'energy', 'deck_name'):
        state[key] = pending[key]
    state['_deck_transfer_notice'] = pending['deck_name']
    return pending['deck_name']
