"""Streamlit UI for the universal TCG Pocket deck builder (no match simulation yet)."""
import json
from collections import Counter
from pathlib import Path
import streamlit as st
from deckbuilder import Catalog, make_experiment

ROOT = Path(__file__).resolve().parent
CATALOG = Catalog.from_json(ROOT / 'catalog.json')
META = ['Mega Altaria / Greninja', 'Mega Charizard Y / Entei',
        'Suicune / Baxcalibur', 'Magnezone / Miraidon', 'Hoopa / Mega Absol']
ENERGIES = ['water', 'fire', 'grass', 'lightning', 'psychic', 'fighting', 'darkness', 'metal', 'dragon', 'colorless']

st.set_page_config(page_title='TCG Pocket Lab', page_icon='🃏', layout='wide')
st.title('🃏 TCG Pocket Lab')
st.caption('Construtor universal de decks • protótipo v0.3 • partidas completas ainda não implementadas')
st.warning('O catálogo incluído é demonstrativo e NÃO foi verificado contra as cartas oficiais. Nenhuma taxa de vitória será gerada antes da validação do motor.')

if 'counts' not in st.session_state:
    st.session_state.counts = {}
if 'deck_name' not in st.session_state:
    st.session_state.deck_name = 'Meu deck'
if 'energy' not in st.session_state:
    st.session_state.energy = ['water']

builder, lab, about = st.tabs(['🧩 Montar deck', '⚔️ Confrontos', 'ℹ️ Sobre'])
with builder:
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader('Catálogo de cartas')
        query = st.text_input('Pesquisar por nome', placeholder='Ex.: Mudkip')
        kinds = ['Todos', 'pokemon', 'item', 'supporter', 'tool', 'stadium']
        kind = st.selectbox('Categoria', kinds)
        verified_only = st.checkbox('Somente cartas verificadas')
        matches = CATALOG.search(query, None if kind == 'Todos' else kind)
        if verified_only:
            matches = [e for e in matches if e.verified]
        st.caption(f'{len(matches)} carta(s) encontrada(s)')
        for entry in matches:
            card = entry.card
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(f'**{card.name}** · {card.kind} · ID `{card.id}`')
                    st.caption(('Verificada' if entry.verified else 'Não verificada') + (f' · {entry.source}' if entry.source else ''))
                with b:
                    count = st.session_state.counts.get(card.id, 0)
                    if st.button(f'➕ {count}/2', key=f'add-{card.id}', disabled=count >= 2 or sum(st.session_state.counts.values()) >= 20):
                        st.session_state.counts[card.id] = count + 1
                        st.rerun()
    with right:
        st.subheader('Seu deck')
        st.text_input('Nome do deck', key='deck_name')
        st.multiselect('Tipos de energia (1 a 3)', ENERGIES, key='energy', max_selections=3)
        total = sum(st.session_state.counts.values())
        st.progress(min(total / 20, 1), text=f'{total}/20 cartas')
        for card_id, count in list(st.session_state.counts.items()):
            if count < 1:
                continue
            entry = CATALOG.entries.get(card_id)
            name = entry.card.name if entry else f'ID desconhecido: {card_id}'
            a, b, c = st.columns([5, 1, 1])
            a.write(f'{count}× {name}')
            if b.button('−', key=f'minus-{card_id}'):
                if count == 1:
                    del st.session_state.counts[card_id]
                else:
                    st.session_state.counts[card_id] -= 1
                st.rerun()
            if c.button('+', key=f'plus-{card_id}', disabled=count >= 2 or total >= 20):
                st.session_state.counts[card_id] += 1
                st.rerun()
        payload = {'name': st.session_state.deck_name, 'energy_types': st.session_state.energy,
                   'cards': {k: v for k, v in st.session_state.counts.items() if v > 0}}
        errors = []
        if not st.session_state.deck_name.strip():
            errors.append('Informe o nome do deck.')
        if not 1 <= len(st.session_state.energy) <= 3:
            errors.append('Escolha de 1 a 3 tipos de energia.')
        try:
            CATALOG.resolve(payload)
        except ValueError as exc:
            errors.append(str(exc))
        if errors:
            for error in errors:
                st.error(error)
        else:
            st.success('Deck válido pelas regras estruturais implementadas (não significa legalidade competitiva confirmada).')
        st.download_button('⬇️ Exportar deck JSON', json.dumps(payload, ensure_ascii=False, indent=2),
                           file_name='meu_deck.json', mime='application/json')
        uploaded = st.file_uploader('Importar deck JSON', type=['json'])
        if uploaded is not None and st.button('Carregar arquivo'):
            try:
                imported = json.load(uploaded)
                if not isinstance(imported.get('cards'), dict):
                    raise ValueError('Campo cards inválido')
                counts = imported['cards']
                if any(k not in CATALOG.entries or type(v) is not int or v < 1 or v > 2 for k, v in counts.items()):
                    raise ValueError('IDs ou quantidades inválidos')
                if sum(counts.values()) > 20:
                    raise ValueError('Mais de 20 cartas')
                energy = imported.get('energy_types', [])
                if not isinstance(energy, list) or not 1 <= len(energy) <= 3 or len(set(energy)) != len(energy) or any(e not in ENERGIES for e in energy):
                    raise ValueError('Energia inválida')
                st.session_state.counts = counts.copy()
                st.session_state.deck_name = str(imported.get('name', 'Meu deck'))
                st.session_state.energy = energy
                st.rerun()
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                st.error(f'Não foi possível importar: {exc}')

with lab:
    st.subheader('Planejar confrontos')
    st.info('Esta etapa gera somente um plano reproduzível. O motor ainda não executa partidas completas.')
    opponents = st.multiselect('Decks adversários', META, default=META)
    games = st.number_input('Partidas por confronto', min_value=1, max_value=1_000_000, value=100_000, step=10_000)
    seed = st.number_input('Semente aleatória', min_value=0, value=20261116, step=1)
    st.metric('Partidas planejadas', f'{int(games) * len(opponents):,}'.replace(',', '.'))
    if opponents:
        plan = make_experiment('meu_deck.json', opponents, int(games), int(seed))
        plan['player_deck'] = {'name': st.session_state.deck_name, 'energy_types': st.session_state.energy,
                               'cards': dict(st.session_state.counts)}
        st.download_button('⬇️ Exportar plano de experimento', json.dumps(plan, ensure_ascii=False, indent=2),
                           file_name='experimento.json', mime='application/json')
    else:
        st.warning('Selecione ao menos um adversário.')
    st.button('▶️ Executar partidas', disabled=True, help='Disponível após validação dos efeitos e das regras completas.')

with about:
    st.markdown('''### Estado do projeto
- **Disponível:** busca, filtros, montagem, validação estrutural, importação/exportação JSON e planejamento de confrontos.
- **Pendente:** catálogo completo com fontes oficiais, efeitos executáveis, baralho do meta validado, IA de jogo completo e simulação de partidas.
- **Transparência:** IDs `demo-*` são exemplos, não cartas oficiais verificadas. Não são calculadas taxas de vitória fictícias.

Para ampliar o catálogo, edite `catalog.json` preservando os campos `card`, `verified` e `source`. Consulte o `README.md` para iniciar a aplicação.''')
