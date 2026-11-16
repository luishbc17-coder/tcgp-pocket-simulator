"""TCG Pocket Lab v0.9.3.4: Wally Colorless Energy and Turo Future support."""
import json
from collections import defaultdict
import streamlit as st
import requests
from catalog_online import fetch_catalog, validate_selection, URL
from deckbuilder import make_experiment
from layout_helpers import paginate, PAGE_SIZE
from gameplay_catalog import GAMEPLAY_URL, audit_core_cards, audit_gameplay_records, compile_deck, evolution_line_map
from engine_diagnostics import run_smoke_checks
from matchup_compatibility import parse_payload, inspect_matchup, load_compiled_deck
from battle_engine import play_fixture_match, RuleError, UnsupportedEffect
from meta_decks import DECKS, get_preset, verify_presets
from card_support import build_support_index, coverage_summary
from meta_gauntlet import build_gauntlet_plan, run_meta_gauntlet, MAX_GAMES_PER_OPPONENT
from deck_transfer import stage_transfer, apply_pending_transfer
from batch_runner import run_technical_batch, compare_policies, MAX_BATCH_GAMES, verify_engine_compatibility
from tactical_agent import TacticalAgent
from deck_identity import describe_selection, compare_decks
from visual_theme import (CSS, VERSION, hero, section, is_pokemon, card_caption,
                          deck_overview, matchup_preview, result_bars, status_pill, library_summary)

META = [entry['name'] for entry in DECKS.values()]
ENERGIES = ['water', 'fire', 'grass', 'lightning', 'psychic', 'fighting', 'darkness', 'metal']
st.set_page_config(page_title='TCG Pocket Lab', page_icon='🃏', layout='wide')
st.markdown(CSS, unsafe_allow_html=True)

for key, default in {'counts':{},'deck_name':'Meu deck','energy':['water'],'saved_decks':{},'page':1}.items():
    if key not in st.session_state: st.session_state[key] = default
if 'preset_opponent' not in st.session_state:
    # Altaria is typically the left deck; default to the intended opposing archetype.
    st.session_state.preset_opponent = 'hoopa_mega_absol'
# Migrate energy selections saved by older versions of the UI.
if any(e not in ENERGIES for e in st.session_state.energy):
    st.session_state.energy = [e for e in st.session_state.energy if e in ENERGIES] or ['water']

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_gameplay_catalog():
    """Fetch gameplay data independently of the optional catalog adapter.

    Compatibility with earlier catalog_online.py versions prevents a startup
    ImportError if Streamlit Cloud refreshes files in different deployments.
    """
    response = requests.get(GAMEPLAY_URL, timeout=30,
                            headers={'User-Agent': 'TCGPocketLab/0.7'})
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data = data.get('cards', [])
    if not isinstance(data, list) or len(data) < 100:
        raise ValueError('Catálogo gameplay incompleto ou esquema alterado')
    return data


@st.cache_data(ttl=3600, show_spinner=False)
def get_cards():
    return fetch_catalog()


@st.cache_data(ttl=3600, show_spinner=False)
def get_card_support_index():
    """Compile the optional catalog badge index only once per cache window."""
    return build_support_index(get_cards(), fetch_gameplay_catalog())

try:
    cards = get_cards()
except Exception as exc:
    st.error('Não foi possível carregar o catálogo. Tente novamente mais tarde.')
    st.caption(str(exc))
    st.stop()
by_id = {c['id']:c for c in cards}

def total(): return sum(st.session_state.counts.values())
def name_count(name):
    return sum(n for cid,n in st.session_state.counts.items() if cid in by_id and by_id[cid]['name'].casefold()==name.casefold())
def can_add(card):
    return total()<20 and st.session_state.counts.get(card['id'],0)<2 and name_count(card['name'])<2
def add(cid):
    card=by_id[cid]
    if can_add(card): st.session_state.counts[cid]=st.session_state.counts.get(cid,0)+1
def remove(cid):
    n=st.session_state.counts.get(cid,0)
    if n==1: del st.session_state.counts[cid]
    elif n>1: st.session_state.counts[cid]=n-1

def payload():
    return {'format':'tcgp-lab-v0.9.3','name':st.session_state.deck_name,'energy_types':list(st.session_state.energy),'cards':dict(st.session_state.counts)}

def load_payload(data):
    """Validate and stage import; apply it on the next Streamlit script run.

    It is unsafe to edit session_state.energy after the energy multiselect has
    been instantiated in this run (the old Copy button did exactly that).
    """
    stage_transfer(st.session_state, data, by_id, ENERGIES)


# This executes BEFORE st.text_input(deck_name) and st.multiselect(energy).
# It works for Copy preset, Import JSON, and Open saved deck alike.
_imported_deck = apply_pending_transfer(st.session_state)
if _imported_deck is not None:
    # The editor keys are widget-owned; staged imports take priority on next render.
    st.session_state.pop('deck_name_editor_v0933', None)
    st.session_state.pop('energy_editor_v0933', None)

st.markdown(hero(len(cards), total()), unsafe_allow_html=True)
_notice = st.session_state.pop('_deck_transfer_notice', None)
if _notice:
    st.success(f'Deck «{_notice}» carregado com sucesso. Continue na Arena ou abra Meu deck para editar.')
# Real, stateful navigation: unlike st.tabs, it does not rely on the frontend
# keeping an active tab after a rerun or a staged deck import.
NAV_ITEMS = ('🔎 Cartas', '🧩 Meu deck', '⚔️ Meta', '⚙️ Motor', 'ℹ️ Sobre')
with st.container(key='lab_navigation_v0933'):
    current_view = st.radio('Navegação principal', NAV_ITEMS, horizontal=True,
                            label_visibility='collapsed', key='main_view_v0933')


def save_deck_name():
    st.session_state.deck_name = st.session_state.deck_name_editor_v0933


def save_deck_energy():
    st.session_state.energy = list(st.session_state.energy_editor_v0933)

def reset_page():
    st.session_state.page = 1


def previous_page():
    st.session_state.page = max(1, st.session_state.page - 1)


def next_page():
    st.session_state.page += 1


def card_tile(card, location, support=None):
    """Create one compact card inside a Streamlit grid cell."""
    if card['image']:
        st.image(card['image'], use_container_width=True)
    else:
        st.caption('🃏 Imagem indisponível')
    n = st.session_state.counts.get(card['id'], 0)
    st.markdown(card_caption(card, n), unsafe_allow_html=True)
    if support:
        st.markdown(status_pill(support['status']), unsafe_allow_html=True)
    # This inner row must also stay horizontal on mobile.
    minus, plus = st.columns(2, gap='xsmall', wrap=False)
    minus.button('−', key=f'{location}_minus_{card["id"]}',
                 disabled=n == 0, on_click=remove, args=(card['id'],),
                 use_container_width=True)
    plus.button(f'+ {n}', key=f'{location}_plus_{card["id"]}',
                disabled=not can_add(card), on_click=add, args=(card['id'],),
                use_container_width=True)


if current_view == '🔎 Cartas':
    st.markdown(section('Explore as cartas',
        'Busque por nome, filtre por expansão e adicione cartas ao seu deck.',
        'COLEÇÃO'), unsafe_allow_html=True)
    st.text_input('Buscar carta', placeholder='Pesquise um Pokémon ou treinador…',
                  key='catalog_query', on_change=reset_page)
    st.radio('Tipo de carta', ['Todas', 'Pokémon', 'Treinadores'],
             horizontal=True, key='catalog_group_v091', on_change=reset_page)
    st.checkbox('🔬 Mostrar quais cartas já são simuláveis',
                key='show_support_v092', on_change=reset_page,
                help='Consulta a base de jogabilidade somente quando ativado. '
                     'Não garante fidelidade ao jogo oficial.')
    support_index = None
    if st.session_state.get('show_support_v092'):
        try:
            with st.spinner('Analisando compatibilidade das cartas...'):
                support_index = get_card_support_index()
            stats = coverage_summary({c['id']: 1 for c in cards}, support_index)
            st.caption((f'Compatíveis com o motor: {stats["supported"]:,} de {stats["total"]:,} cartas. '
                        'As demais permanecem no catálogo para montagem.').replace(',', '.'))
            st.selectbox('Filtrar pelo suporte do motor',
                         ['Todas', 'Com efeitos reconhecidos', 'Aguardando implementação'],
                         key='catalog_support_filter_v092', on_change=reset_page)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            st.warning(f'Não foi possível verificar os efeitos agora: {exc}')
    with st.expander('⚙️ Filtros avançados', expanded=False):
        sets = sorted({c['set'] for c in cards if c['set']})
        types = sorted({c['type'] for c in cards if c['type']})
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox('Expansão', ['Todas'] + sets, key='chosen_set',
                         on_change=reset_page)
        with c2:
            st.selectbox('Categoria', ['Todas'] + types, key='chosen_type',
                         on_change=reset_page)
        st.selectbox('Ordenação', ['Nome (A–Z)', 'Expansão', 'No meu deck primeiro'],
                     key='catalog_sort_v091', on_change=reset_page)
        st.checkbox('Mostrar somente cartas do meu deck',
                    key='only_my_cards_v091', on_change=reset_page)

    query = st.session_state.get('catalog_query', '').strip().casefold()
    chosen_set = st.session_state.get('chosen_set', 'Todas')
    chosen_type = st.session_state.get('chosen_type', 'Todas')
    card_group = st.session_state.get('catalog_group_v091', 'Todas')
    selected_ids = st.session_state.counts
    support_filter = st.session_state.get('catalog_support_filter_v092', 'Todas')
    filtered = [c for c in cards
                if query in c['name'].casefold()
                and (support_index is None or support_filter == 'Todas'
                     or (support_filter == 'Com efeitos reconhecidos' and support_index[c['id']]['status'] == 'supported')
                     or (support_filter == 'Aguardando implementação' and support_index[c['id']]['status'] != 'supported'))
                and (chosen_set == 'Todas' or c['set'] == chosen_set)
                and (chosen_type == 'Todas' or c['type'] == chosen_type)
                and (card_group == 'Todas'
                     or (card_group == 'Pokémon' and is_pokemon(c))
                     or (card_group == 'Treinadores' and not is_pokemon(c)))
                and (not st.session_state.get('only_my_cards_v091', False)
                     or selected_ids.get(c['id'], 0) > 0)]
    ordering = st.session_state.get('catalog_sort_v091', 'Nome (A–Z)')
    if ordering == 'No meu deck primeiro':
        filtered.sort(key=lambda c: (-selected_ids.get(c['id'], 0), c['name'].casefold(), c['id']))
    elif ordering == 'Expansão':
        filtered.sort(key=lambda c: (c['set'].casefold(), c['number'], c['name'].casefold()))
    else:
        filtered.sort(key=lambda c: (c['name'].casefold(), c['set'], c['id']))
    visible, page, pages = paginate(filtered, st.session_state.page, PAGE_SIZE)
    st.session_state.page = page
    st.caption(f'{len(filtered):,} cartas encontradas · página {page} de {pages}'.replace(',', '.'))
    back, current, forward = st.columns([1, 1.15, 1], gap='xsmall', wrap=False)
    back.button('◀ Voltar', key='catalog_prev_top', on_click=previous_page,
                disabled=page <= 1, use_container_width=True)
    current.markdown(f'<div style="text-align:center;padding:.55rem 0;font-size:.80rem">'
                     f'{page} / {pages}</div>', unsafe_allow_html=True)
    forward.button('Próxima ▶', key='catalog_next_top', on_click=next_page,
                   disabled=page >= pages, use_container_width=True)
    if not visible:
        st.info('Nenhuma carta encontrada. Experimente alterar os filtros.')
    else:
        # Native wrapping: typically two cards per row on Android, four on desktop.
        gallery = st.grid(4, min_column_width=146, gap='small',
                          border=True, key='catalog_gallery')
        for card in visible:
            with gallery.cell():
                card_tile(card, 'catalog', support_index[card['id']] if support_index else None)
        st.caption('Use os botões + e − em cada carta para ajustar as cópias do deck.')
        prev_bottom, page_bottom, next_bottom = st.columns([1, 1.15, 1],gap='xsmall',wrap=False)
        prev_bottom.button('◀ Voltar', key='catalog_prev_bottom',
                           on_click=previous_page, disabled=page <= 1,
                           use_container_width=True)
        page_bottom.markdown(f'<div style="text-align:center;padding:.55rem 0;font-size:.80rem">'
                             f'{page} / {pages}</div>', unsafe_allow_html=True)
        next_bottom.button('Próxima ▶', key='catalog_next_bottom',
                           on_click=next_page, disabled=page >= pages,
                           use_container_width=True)

if current_view == '🧩 Meu deck':
    st.markdown(section('Construa seu deck',
        'Monte uma lista de 20 cartas e escolha a energia para testar na arena.',
        'DECK BUILDER'), unsafe_allow_html=True)
    st.session_state.setdefault('deck_name_editor_v0933', st.session_state.deck_name)
    st.session_state.setdefault('energy_editor_v0933', list(st.session_state.energy))
    st.text_input('Nome do deck', key='deck_name_editor_v0933', on_change=save_deck_name)
    st.multiselect('Energias (até 3)', ENERGIES, key='energy_editor_v0933',
                   max_selections=3, on_change=save_deck_energy)
    st.markdown(deck_overview(st.session_state.counts, by_id, st.session_state.energy),
                unsafe_allow_html=True)
    selected = list(st.session_state.counts.items())
    if not selected:
        st.info('Seu deck está vazio. Comece na aba Cartas: escolha um Pokémon e toque em +.')
    else:
        selected_cards = [(cid, n, by_id.get(cid)) for cid,n in selected]
        for title, group in [('Pokémon', [(cid,n,c) for cid,n,c in selected_cards if c and is_pokemon(c)]),
                             ('Treinadores', [(cid,n,c) for cid,n,c in selected_cards if c and not is_pokemon(c)])]:
            if group:
                st.markdown(section(title, f'{sum(n for _, n, _ in group)} cartas selecionadas',
                                    'COMPOSIÇÃO'), unsafe_allow_html=True)
                gallery = st.grid(4, min_column_width=146, gap='small',
                                  border=True, key=f'my_deck_{title.lower()}_gallery_v091')
                for cid,n,c in group:
                    with gallery.cell():
                        card_tile(c, 'deck')
        missing = [cid for cid,n,c in selected_cards if c is None]
        for cid in missing:
            st.warning(f'Carta ausente no catálogo: {cid}')
    issues=validate_selection(st.session_state.counts,cards)
    if not st.session_state.energy: issues.append('Selecione ao menos um tipo de energia.')
    if issues: st.warning(' | '.join(issues))
    else: st.success('Passou nas verificações estruturais disponíveis; legalidade completa ainda não confirmada.')
    st.download_button('⬇️ Exportar deck JSON',json.dumps(payload(),ensure_ascii=False,indent=2),file_name='meu_deck.json',mime='application/json',use_container_width=True)
    uploaded=st.file_uploader('Importar deck JSON (v0.4–v0.9.3)',type=['json'])
    if uploaded and st.button('Importar arquivo'):
        try:
            load_payload(json.load(uploaded)); st.rerun()
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc: st.error(f'Importação recusada: {exc}')
    st.divider()
    st.subheader('Decks salvos nesta sessão')
    st.caption('Estes slots são temporários: para guardar permanentemente, exporte o JSON. Não há armazenamento em nuvem.')
    if st.button('💾 Salvar deck neste navegador'):
        st.session_state.saved_decks[st.session_state.deck_name]=payload()
        st.success('Salvo na sessão atual.')
    for name,data in list(st.session_state.saved_decks.items()):
        col1,col2,col3=st.columns([3,1,1])
        col1.write(name)
        if col2.button('Abrir',key='open_'+name):
            try: load_payload(data); st.rerun()
            except ValueError as exc: st.error(str(exc))
        if col3.button('Excluir',key='delete_'+name):
            del st.session_state.saved_decks[name]; st.rerun()

if current_view == '⚔️ Meta':
    st.markdown(section('Arena de confrontos',
        'Escolha seu oponente, confira os efeitos e investigue o comportamento da IA.',
        'BATTLE LAB'), unsafe_allow_html=True)
    st.caption('Os resultados são experimentais: a IA e o motor ainda não reproduzem todas as regras do jogo.')
    if st.session_state.get('_deck_transfer_notice_meta'):
        st.success(st.session_state.pop('_deck_transfer_notice_meta'))
    with st.expander(f'📚 Biblioteca de decks — {len(DECKS)} listas de 20 cartas', expanded=False):
        st.caption('Escolha uma lista pronta e importe para Meu deck. '
                   'Decks novos são liberados somente após a verificação completa de seus efeitos.')
        my_preset_slug = st.selectbox('Escolha o deck para importar', list(DECKS),
                                     format_func=lambda slug: DECKS[slug]['name'],
                                     key='preset_player_v092')
        my_preset = get_preset(my_preset_slug)
        st.markdown(library_summary(my_preset['name'], my_preset['energy_types'],
                                    my_preset.get('release_stage','catalog_only'),
                                    sum(my_preset['cards'].values())),
                    unsafe_allow_html=True)
        if st.button('🧩 Carregar lista no Meu deck', key='load_preset_v092',
                     use_container_width=True):
            try:
                load_payload(my_preset)
                st.session_state['_deck_transfer_notice_meta'] = 'Deck carregado. Continue na Arena ou abra Meu deck para editar.'
                st.rerun()
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f'Não foi possível carregar este deck: {exc}')
    policy_label = st.selectbox(
        'Política da IA para este experimento',
        ['Tática v0.9 — considera evoluções e melhores trocas',
         'Clássica v0.8.4 — referência anterior'],
        key='policy_choice_v09',
        help='A mesma política controla os dois jogadores. Não é treinamento de modelo de IA.')
    agent_mode = 'tactical' if policy_label.startswith('Tática') else 'baseline'
    st.caption('IA tática: evita energias sem ataque viável, considera evoluções, recua com critério e usa Cyrus de modo mais seletivo.')

    st.divider()
    st.markdown(section('Meu deck × Todo o meta',
        'Compare sua lista com todos os arquétipos cadastrados em uma única execução, '
        'sem simular cartas cujo efeito ainda esteja pendente.',
        'GAUNTLET · EXPERIMENTAL'), unsafe_allow_html=True)
    st.caption('As taxas exibidas refletem somente duelos técnicos executados com IA heurística. '
               'Adversários incompatíveis são identificados e excluídos dos percentuais.')
    st.markdown(f'**Seu deck atual:** {st.session_state.deck_name} · '
                f'{total()}/20 cartas · Energia: {", ".join(st.session_state.energy)}')
    if st.button('🧩 Usar Mega Altaria/Greninja para testar a Arena',
                 key='gauntlet_starter_deck_v0933', use_container_width=True):
        try:
            load_payload(get_preset('mega_altaria_greninja'))
            st.session_state['_deck_transfer_notice_meta'] = (
                'Mega Altaria/Greninja carregado. A Arena permanece selecionada.')
            st.rerun()
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f'Não foi possível carregar o deck de referência: {exc}')
    with st.expander('🔄 Catálogo de combate e diagnóstico', expanded=False):
        st.caption('O catálogo de combate pode permanecer em cache. Se habilidades novas ' 
                   'aparecerem como não reconhecidas, atualize a fonte antes de testar.')
        if st.button('Atualizar dados de cartas e rever compatibilidade',
                     key='refresh_gameplay_v0931', use_container_width=True):
            fetch_gameplay_catalog.clear()
            get_card_support_index.clear()
            st.rerun()
        st.caption('A exportação diagnóstica abaixo contém somente textos públicos ' 
                   'de cartas dos decks cadastrados; não inclui dados pessoais.')
    chosen_gauntlet = st.multiselect('Decks do meta a enfrentar', options=list(DECKS),
        default=list(DECKS), format_func=lambda slug: DECKS[slug]['name'],
        key='gauntlet_field_v093')
    include_mirror = st.checkbox('Incluir confronto espelhado (se houver)',
        value=False, key='gauntlet_mirror_v093')
    gauntlet_games = st.select_slider('Partidas por adversário compatível',
        options=[25,50,100,250], value=100, key='gauntlet_games_v093')
    gauntlet_seed = st.number_input('Semente da série', min_value=0, max_value=2_000_000_000,
        value=20261116, step=1, key='gauntlet_seed_v093')
    gauntlet_player = payload()
    gauntlet_request = {
        'player': gauntlet_player, 'field': list(chosen_gauntlet),
        'mirror': bool(include_mirror), 'games': int(gauntlet_games),
        'seed': int(gauntlet_seed), 'agent_mode': agent_mode,
    }
    gauntlet_data = None
    gauntlet_plan = None
    if chosen_gauntlet:
        try:
            gauntlet_data = fetch_gameplay_catalog()
            gauntlet_field = {slug:get_preset(slug) for slug in chosen_gauntlet}
            gauntlet_plan = build_gauntlet_plan(
                gauntlet_player, gauntlet_field, cards, gauntlet_data,
                include_mirror=include_mirror)
            from visual_theme import gauntlet_status_summary, gauntlet_cards
            if not gauntlet_plan['player']['technical_demo_ready']:
                st.error('Seu deck atual ainda não pode ser simulado. '
                         'Escolha uma lista compatível ou corrija as cartas abaixo.')
                for issue in gauntlet_plan['player']['issues'][:3]:
                    st.warning(issue)
                for blocked in [c for c in gauntlet_plan['player']['cards']
                                if c['status'] == 'bloqueada'][:5]:
                    st.caption(f'{blocked["name"]}: {blocked["reason"]}')
            st.markdown(gauntlet_status_summary(gauntlet_plan), unsafe_allow_html=True)
            with st.expander('📋 Ver compatibilidade por adversário', expanded=False):
                st.markdown(gauntlet_cards(gauntlet_plan['opponents']),
                            unsafe_allow_html=True)
            with st.expander('Detalhes das cartas e mecânicas pendentes'):
                for row in gauntlet_plan['opponents']:
                    if row['reasons']:
                        st.markdown(f"**{row['name']}**")
                        for reason in row['reasons'][:6]:
                            st.write('• ' + reason)
            from meta_diagnostics import blocked_catalog_diagnostics
            debug_export = blocked_catalog_diagnostics(gauntlet_plan,
                gauntlet_field, gauntlet_data)
            if debug_export['blocked_cards']:
                st.download_button('⬇ Baixar diagnóstico das cartas pendentes (JSON)',
                    data=json.dumps(debug_export, ensure_ascii=False, indent=2),
                    file_name='diagnostico_cartas_v0931.json', mime='application/json',
                    key='download_catalog_diag_v0931', use_container_width=True)
            if gauntlet_plan['ready'] == 0:
                st.warning('Nenhum dos adversários selecionados é simulável com seu deck. '
                           'Confira os motivos ou escolha outro confronto.')
            st.caption(f"Execução prevista: {gauntlet_plan['ready'] * int(gauntlet_games)} partidas "
                       f"auditadas em {gauntlet_plan['ready']} confronto(s).")
        except (requests.RequestException, ValueError, TypeError, KeyError, RuleError) as exc:
            st.error(f'Falha na verificação do meta: {exc}')
    else:
        st.info('Escolha pelo menos um deck adversário para montar a série.')
    can_run_gauntlet = bool(gauntlet_plan and gauntlet_plan['ready'] > 0)
    if can_run_gauntlet:
        st.info(f'{gauntlet_plan["ready"]} confronto(s) disponível(is). Os decks pendentes serão ignorados, não contam como derrota.')
    if st.button('▶ Simular apenas os confrontos compatíveis', use_container_width=True,
                 disabled=not can_run_gauntlet, key='run_gauntlet_v093'):
        bar = st.progress(0, text='Preparando confrontos auditados…')
        try:
            count = gauntlet_plan['ready'] * int(gauntlet_games)
            def update_gauntlet(done, expected):
                if expected:
                    bar.progress(min(1.0, done/expected),
                                 text=f'{done}/{expected} partidas técnicas')
            output = run_meta_gauntlet(
                gauntlet_player, gauntlet_field, cards, gauntlet_data,
                games_per_opponent=int(gauntlet_games), seed=int(gauntlet_seed),
                agent_mode=agent_mode, include_mirror=bool(include_mirror),
                progress=update_gauntlet)
            st.session_state['gauntlet_report_v093'] = {
                'request': gauntlet_request, 'report': output}
            bar.progress(1.0, text=f'{output["completed"]}/{count} concluídas')
        except (RuleError, UnsupportedEffect, ValueError, IndexError,
                TypeError, KeyError, AttributeError, RuntimeError) as exc:
            st.error(f'Não foi possível concluir a série: {type(exc).__name__}: {exc}')
            st.session_state['gauntlet_failure_v0933'] = {
                'kind': 'technical_gauntlet_failure',
                'version': VERSION,
                'agent_mode': agent_mode,
                'request': gauntlet_request,
                'error_type': type(exc).__name__,
                'error_message': str(exc)[:500],
            }
        else:
            st.session_state.pop('gauntlet_failure_v0933', None)
    last_failure = st.session_state.get('gauntlet_failure_v0933')
    if last_failure and last_failure['request'] == gauntlet_request:
        st.download_button('⬇️ Baixar diagnóstico de falha da simulação',
            data=json.dumps(last_failure, ensure_ascii=False, indent=2),
            file_name='diagnostico_erro_simulacao_v0933.json',
            mime='application/json', key='gauntlet_failure_download_v0933',
            use_container_width=True)
    saved_gauntlet = st.session_state.get('gauntlet_report_v093')
    if saved_gauntlet and saved_gauntlet['request'] == gauntlet_request:
        gauntlet_report = saved_gauntlet['report']
        st.markdown('#### Resultado por adversário')
        st.dataframe([{
            'Adversário': row['name'],
            'Estado': {'completed':'✅ Concluído','partial':'⚠️ Parcial',
                       'blocked':'🛠️ Bloqueado','mirror':'🔁 Espelhado',
                       'error':'❌ Erro'}.get(row['status'], row['status']),
            'Vitórias': row['outcomes']['left'] if row['outcomes'] else None,
            'Derrotas': row['outcomes']['right'] if row['outcomes'] else None,
            'Empates': row['outcomes']['draw'] if row['outcomes'] else None,
            'Vitórias (%)': row['win_rate'],
            'Partidas': row['completed'],
        } for row in gauntlet_report['results']], use_container_width=True, hide_index=True)
        g1,g2 = st.columns(2, gap='small')
        g1.metric('Partidas técnicas concluídas', gauntlet_report['completed'])
        g2.metric('Falhas', gauntlet_report['failed'])
        if gauntlet_report['overall_win_rate'] is not None:
            st.metric('Vitórias nos confrontos executados',
                      f'{gauntlet_report["overall_win_rate"]:.1f}%')
        st.caption(gauntlet_report['overall_rate_note'])
        st.download_button('⬇️ Baixar relatório completo da série (JSON)',
            data=json.dumps(gauntlet_report, ensure_ascii=False, indent=2),
            file_name='meu_deck_vs_meta_v093.json', mime='application/json',
            use_container_width=True, key='download_gauntlet_v093')
    elif saved_gauntlet:
        st.info('A configuração mudou desde o último teste. Execute novamente para atualizar os resultados.')


    st.divider()
    st.subheader('Duelo contra um adversário')
    opponent_mode = st.radio('Deck adversário',
        ['Deck do meta','Importar JSON','Deck salvo na sessão','Espelhar meu deck (depuração)'],
        horizontal=False, key='opponent_mode')
    opponent_payload = None
    if opponent_mode == 'Deck do meta':
        def choose_hoopa_opponent():
            st.session_state.preset_opponent = 'hoopa_mega_absol'
        st.button('⚔️ Selecionar Hoopa ex / Mega Absol ex como adversário',
                  on_click=choose_hoopa_opponent, key='select_hoopa_v084',
                  use_container_width=True)
        selected_slug = st.selectbox('Escolha o adversário', list(DECKS),
                                     format_func=lambda slug: DECKS[slug]['name'],
                                     key='preset_opponent')
        opponent_payload = get_preset(selected_slug)
        st.markdown(library_summary(opponent_payload['name'], opponent_payload['energy_types'],
                                    opponent_payload.get('release_stage','catalog_only'),
                                    sum(opponent_payload['cards'].values())),
                    unsafe_allow_html=True)
        # Use a real source card image without generating or fabricating artwork.
        featured_id = next((cid for cid in opponent_payload['cards']
                            if cid in by_id and by_id[cid].get('image')
                            and any(tag in by_id[cid]['name'].casefold()
                                    for tag in ('mega', 'hoopa', 'suicune', 'miraidon', 'umbreon'))), None)
        if featured_id:
            st.image(by_id[featured_id]['image'], width=118,
                     caption=by_id[featured_id]['name'])
        audit_preset = verify_presets(cards)[selected_slug]
        if audit_preset['ready_to_inspect']:
            st.caption('Lista de 20 cartas com IDs correspondentes ao catálogo carregado.')
        else:
            st.error('A fonte do catálogo mudou: ' + ', '.join(audit_preset['missing_ids']) +
                     ' · confira os IDs antes de executar qualquer teste.')
        st.caption(opponent_payload['description'])
        st.markdown(f'[Consultar lista de origem]({opponent_payload["source"]}) '
                    f'· cartas verificadas até {opponent_payload["sample_through"]}.')
        with st.expander('🃏 Ver as 20 cartas desta lista', expanded=False):
            st.dataframe([{'Qtd.': n, 'Carta': by_id[cid]['name'] if cid in by_id else cid,
                           'Expansão': cid.split('-')[0].upper(), 'ID': cid}
                          for cid,n in opponent_payload['cards'].items()],
                         use_container_width=True, hide_index=True)
        st.download_button('⬇️ Baixar lista do adversário',
                           json.dumps(opponent_payload,ensure_ascii=False,indent=2),
                           file_name=f'{selected_slug}.json',mime='application/json',
                           use_container_width=True)
        if st.button('🧩 Copiar este deck para Meu deck',use_container_width=True):
            try:
                load_payload(opponent_payload)
                st.session_state['_deck_transfer_notice_meta'] = 'Lista copiada. A aba Meta continuará aberta; selecione Meu deck quando quiser editar.'
                st.rerun()
            except ValueError as exc:
                st.error(f'Não foi possível copiar a lista: {exc}')
    elif opponent_mode == 'Importar JSON':
        opponent_file = st.file_uploader('Deck adversário exportado do TCG Pocket Lab (.json)',
                                         type=['json'], key='opponent_deck_json')
        if opponent_file is not None:
            if opponent_file.size > 100_000:
                st.error('Arquivo muito grande para ser um deck de 20 cartas.')
            else:
                try:
                    opponent_payload = parse_payload(json.loads(opponent_file.getvalue().decode('utf-8')))
                except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                    st.error(f'Deck adversário inválido: {exc}')
    elif opponent_mode == 'Deck salvo na sessão':
        names = list(st.session_state.saved_decks)
        if names:
            selected_name = st.selectbox('Escolher deck adversário',names)
            try:
                opponent_payload = parse_payload(st.session_state.saved_decks[selected_name])
            except ValueError as exc:
                st.error(f'Deck salvo inválido: {exc}')
        else:
            st.info('Nenhum deck foi salvo nesta sessão. Salve um na aba Meu deck ou importe JSON.')
    else:
        opponent_payload = parse_payload(payload())
        st.caption('Usa sua própria lista como adversária para depuração, não como previsão do metagame.')

    if opponent_payload is not None:
        try:
            with st.spinner('Verificando as cartas no catálogo de batalha...'):
                game_cards = fetch_gameplay_catalog()
            match_report = inspect_matchup(payload(),opponent_payload,cards,game_cards)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            st.error(f'Não foi possível conferir os dois decks: {exc}')
        else:
            left_r = match_report['player']
            right_r = match_report['opponent']
            preview_left = describe_selection(payload(), 'Meu deck')
            preview_right = describe_selection(opponent_payload, 'Adversário')
            preview_comparison = compare_decks(preview_left, preview_right)
            st.markdown(matchup_preview(preview_left, preview_right),
                        unsafe_allow_html=True)
            st.caption('Os identificadores resumidos distinguem as composições reais dos decks.')
            if preview_comparison['warning']:
                st.warning(preview_comparison['warning'])
            c1,c2 = st.columns(2, gap='small')
            c1.metric('Meu deck — efeitos suportados',f'{left_r["supported"]}/{left_r["total"]}')
            c2.metric('Adversário — efeitos suportados',f'{right_r["supported"]}/{right_r["total"]}')
            for label, report in [('Meu deck',left_r),('Adversário',right_r)]:
                with st.expander(f'🔎 {label} — {report["unsupported"]} carta(s) sem suporte',
                                 expanded=report['unsupported']>0 or bool(report['issues'])):
                    st.caption(f'Energia: {", ".join(report["energy_types"])}; '
                               f'{report["total"]} cartas na lista.')
                    for issue in report['issues']:
                        st.warning(issue)
                    if report['cards']:
                        st.dataframe([{'Qtd.':x['quantity'],'Carta':x['name'],
                                       'Situação':x['status'], 'Motivo':x['reason']}
                                      for x in report['cards']],
                                     use_container_width=True, hide_index=True)
                        details = [
                            {'ID':x['id'], 'Carta':x['name'],
                             'Dados originais':json.dumps(x.get('source_details'),ensure_ascii=False,indent=2)}
                            for x in report['cards'] if x['reason'] and x.get('source_details')
                        ]
                        if details:
                            with st.expander('🧾 Conferir textos originais das cartas bloqueadas'):
                                st.caption('Registro do catálogo recebido pelo aplicativo; '
                                           'permite identificar diferenças de texto e versão.')
                                st.dataframe(details,use_container_width=True,hide_index=True)
                        for note in report.get('notes', []):
                            if note.startswith('A energia escolhida'):
                                st.warning(note)
                    else:
                        st.info('Adicione cartas na aba Meu deck.')
            st.download_button('⬇️ Exportar relatório de compatibilidade',
                               data=json.dumps(match_report,ensure_ascii=False,indent=2),
                               file_name='compatibilidade_decks_v08.json',
                               mime='application/json', use_container_width=True)
            st.divider()
            st.subheader('Duelo técnico — 1 partida')
            st.caption('Execução apenas para depuração. A IA é básica, certas regras ainda '
                       'não estão modeladas e resultados não representam win rates reais.')
            if match_report['technical_demo_ready']:
                technical_seed = st.number_input('Semente do duelo',min_value=0,
                                                  value=20261116,key='technical_seed')
                if st.button('▶ Executar uma partida de depuração',use_container_width=True):
                    try:
                        demo=play_fixture_match(
                            load_compiled_deck(payload(),game_cards),
                            load_compiled_deck(opponent_payload,game_cards),
                            seed=int(technical_seed),
                            energy_left=tuple(payload()['energy_types']),
                            energy_right=tuple(opponent_payload['energy_types']),
                            line_map=evolution_line_map(game_cards),
                            agent_cls=TacticalAgent if agent_mode == 'tactical' else None)
                        st.session_state['debug_trace']={
                            'agent_mode': agent_mode,
                            'seed':int(technical_seed), 'turns':demo.turn,
                            'winner':demo.winner,
                            'first_player':demo.first,
                            'energy_left':list(payload()['energy_types']),
                            'energy_right':list(opponent_payload['energy_types']),
                            'events':demo.log,
                            'left':payload(),'right':opponent_payload}
                    except (RuleError, UnsupportedEffect, ValueError, IndexError) as exc:
                        st.error(f'Partida técnica interrompida: {exc}')
                trace=st.session_state.get('debug_trace')
                if trace and trace['left']==payload() and trace['right']==opponent_payload and trace.get('agent_mode')==agent_mode:
                    st.info(f'Depuração concluída: {trace["turns"]} meios-turnos; '
                            'veja o histórico abaixo. O resultado não estima competitividade.')
                    with st.expander('Histórico da partida',expanded=True):
                        st.caption(f'P0 (Meu deck): {", ".join(trace.get("energy_left", []))} · '
                                   f'P1 (Adversário): {", ".join(trace.get("energy_right", []))} · '
                                   f'Começou: P{trace.get("first_player", "?")}')
                        st.code('\n'.join(trace['events'][-250:]),language=None)
                    st.download_button('⬇️ Baixar replay JSON',
                                       json.dumps(trace,ensure_ascii=False,indent=2),
                                       file_name='duelo_debug.json',mime='application/json')
                st.divider()
                st.subheader('🧪 Lotes auditados · v0.9')
                st.warning('Estes resultados medem o comportamento de uma IA experimental num '
                           'motor ainda incompleto. NÃO são probabilidades confiáveis de vitória no meta.')
                st.caption('A cada quatro partidas o teste alterna a posição dos decks e quem começa. '
                           'Cada ação é verificada; falhas são contabilizadas separadamente.')
                try:
                    verify_engine_compatibility()
                except RuleError as incompatibility:
                    st.error(str(incompatibility))
                    st.info('O lote fica bloqueado até os módulos do motor serem sincronizados.')
                batch_n = st.select_slider('Quantidade de partidas técnicas',
                      options=[25, 100, 250, 500, 1000], value=1000, key='batch_n_v09')
                batch_seed = st.number_input('Semente inicial do lote', min_value=0,
                      value=20261116, key='batch_seed_v09')
                if st.button('▶ Executar lote técnico com auditoria', key='run_batch_v09',
                             use_container_width=True):
                    bar = st.progress(0, text='Verificando as partidas...')
                    def update_batch_progress(done, expected):
                        bar.progress(min(done / expected, 1.0),
                                     text=f'{done}/{expected} partidas processadas')
                    try:
                        selected_left = payload()
                        selected_right = opponent_payload
                        report_batch = run_technical_batch(
                            load_compiled_deck(selected_left, game_cards),
                            load_compiled_deck(selected_right, game_cards),
                            energy_left=tuple(selected_left['energy_types']),
                            energy_right=tuple(selected_right['energy_types']),
                            left_payload=selected_left, right_payload=selected_right,
                            line_map=evolution_line_map(game_cards),
                            games=int(batch_n), seed=int(batch_seed),
                            agent_mode=agent_mode,
                            progress=update_batch_progress)
                        st.session_state['technical_batch_v09'] = {
                            'left': selected_left, 'right': selected_right,
                            'agent_mode': agent_mode, 'report': report_batch}
                    except (RuleError, UnsupportedEffect, ValueError, IndexError, TypeError) as exc:
                        st.error(f'O lote foi interrompido (verifique a versão do motor): {exc}')
                    finally:
                        bar.empty()
                stored = st.session_state.get('technical_batch_v09')
                if stored and stored['left'] == payload() and stored['right'] == opponent_payload and stored.get('agent_mode')==agent_mode:
                    result = stored['report']
                    report_left, report_right = result['decks']['left'], result['decks']['right']
                    st.markdown('**Decks confirmados no lote**')
                    st.caption(f'Política usada nos dois lados: {result["agent_mode"]}')
                    st.caption(f'Esquerdo: {report_left["recognized_name"] or report_left["name"]} '
                               f'· {report_left["card_count"]} cartas · '
                               f'{", ".join(report_left["energy_types"])} · '
                               f'ID {report_left["signature"][:12]}')
                    st.caption(f'Direito: {report_right["recognized_name"] or report_right["name"]} '
                               f'· {report_right["card_count"]} cartas · '
                               f'{", ".join(report_right["energy_types"])} · '
                               f'ID {report_right["signature"][:12]}')
                    if result['matchup']['warning']:
                        st.warning(result['matchup']['warning'])
                    r1,r2,r3 = st.columns(3)
                    r1.metric('Partidas processadas',result['attempted'])
                    r2.metric('Sem falhas de estado',result['completed'])
                    r3.metric('Falhas detectadas',result['failed'])
                    if result['failed']:
                        st.error('Foram detectadas inconsistências. Não use os resultados até corrigi-las.')
                        with st.expander('Falhas e sementes para reprodução',expanded=True):
                            st.json(result['errors'])
                    elif result['completed'] == result['configured']:
                        st.success('As partidas completaram as verificações internas do motor. '
                                   'Ainda não foi validada a fidelidade às regras nem a força da IA.')
                    st.caption(f'Ações verificadas: {result["checked_actions"]:,} · '
                               f'Média: {result["average_half_turns"]} meios-turnos · '
                               f'Primeira semente: {result["seed"]}'.replace(',', '.'))
                    if result['completed']:
                        st.markdown(result_bars(
                            report_left['recognized_name'] or report_left['name'],
                            report_right['recognized_name'] or report_right['name'],
                            result['outcomes'], result['completed']),
                            unsafe_allow_html=True)
                    telemetry = result.get('telemetry', {})
                    if telemetry:
                        with st.expander('📊 Decisões e uso de cartas por deck', expanded=True):
                            indicators = [('turns','Turnos jogados'),('turns_without_attack','Turnos sem ataque'),
                                          ('attacks','Ataques executados'),('energy_attached','Energias anexadas'),
                                          ('evolutions','Evoluções'),('rare_candy','Doce Raro'),
                                          ('water_shuriken','Water Shuriken'),('nightmare_aura','Nightmare Aura'),
                                          ('deceptive_needle','Deceptive Needle'),('retreats','Recuos'),
                                          ('knockouts','Nocautes'),('switch_effects','Trocas por efeito')]
                            st.dataframe([{'Indicador':label,
                                           'Meu deck':telemetry['left']['counts'].get(metric,0),
                                           'Adversário':telemetry['right']['counts'].get(metric,0)}
                                          for metric,label in indicators],
                                         use_container_width=True,hide_index=True)
                            for side,label in [('left','Meu deck'),('right','Adversário')]:
                                attacks = telemetry[side].get('attacks_by_name',{})
                                st.caption(label + ' · ataques mais usados')
                                st.dataframe([{'Ataque':move,'Usos':n}
                                              for move,n in sorted(attacks.items(),key=lambda kv:(-kv[1],kv[0]))[:8]],
                                             use_container_width=True,hide_index=True)
                    if result.get('duration_distribution'):
                        with st.expander('⏱️ Duração das partidas'):
                            st.dataframe([{'Meios-turnos':intervalo,'Partidas':qtde}
                                          for intervalo,qtde in result['duration_distribution'].items()],
                                         use_container_width=True,hide_index=True)
                    with st.expander('Contagem técnica de saídas da IA (não é win rate)',expanded=False):
                        st.dataframe([
                            {'Saída técnica':report_left['recognized_name'] or report_left['name'], 'Partidas':result['outcomes']['left']},
                            {'Saída técnica':report_right['recognized_name'] or report_right['name'], 'Partidas':result['outcomes']['right']},
                            {'Saída técnica':'Empate', 'Partidas':result['outcomes']['draw']}
                        ],use_container_width=True,hide_index=True)
                        st.write('Distribuição por quem começou:')
                        st.json(result['first_player_splits'])
                        st.write('Distribuição por posição P0/P1:')
                        st.json(result['seating_splits'])
                        st.caption('Não interprete essas contagens como chances de ganhar partidas reais.')
                    with st.expander('Identidade verificada em cada partida'):
                        st.caption('P0/P1 são posições; os IDs identificam a composição das cartas e os tipos de energia.')
                        st.dataframe([{
                            'Partida':r['round'], 'Semente':r['seed'],
                            'P0': ('Esquerdo' if r['p0_deck']==report_left['signature'] else 'Direito') if not result['matchup']['is_mirror'] else 'Espelhado',
                            'P1': ('Esquerdo' if r['p1_deck']==report_left['signature'] else 'Direito') if not result['matchup']['is_mirror'] else 'Espelhado',
                            'Começou':f'P{r["first_player"]}',
                            'Resultado':r['outcome'],
                            'Meios-turnos':r['half_turns'],
                        } for r in result['rounds']], use_container_width=True, hide_index=True)
                    if result.get('sample_replay'):
                        with st.expander('Replay auditado — primeira partida'):
                            st.caption('Contém estados após cada ação: HP, dano, energias, Banco e pontos.')
                            sample = result['sample_replay']
                            st.caption(f'P0: {sample["p0_deck"]["recognized_name"] or sample["p0_deck"]["name"]} · '
                                       f'P1: {sample["p1_deck"]["recognized_name"] or sample["p1_deck"]["name"]}')
                            st.code('\n'.join(sample['events'][-250:]), language=None)
                            st.download_button('⬇ Baixar replay e estados (JSON)',
                                json.dumps(sample, ensure_ascii=False, indent=2),
                                file_name='replay_auditado_v09.json', mime='application/json',
                                use_container_width=True)
                    st.download_button('⬇ Baixar relatório do lote (JSON)',
                        json.dumps(result,ensure_ascii=False,indent=2),
                        file_name='lote_tecnico_v09.json', mime='application/json',
                        use_container_width=True)
                with st.expander('🔁 Comparar IA clássica × tática (A/B experimental)'):
                    st.caption('São 100 partidas por política, com os mesmos decks e sementes. '
                               'Como ambos os jogadores usam a mesma política em cada lote e '
                               'a sequência de eventos muda, o teste compara comportamento — '
                               'não determina qual IA é mais forte.')
                    if st.button('▶ Comparar 100 partidas por política', key='compare_policy_v09',
                                 use_container_width=True):
                        try:
                            test_left, test_right = payload(), opponent_payload
                            comparison = compare_policies(
                                load_compiled_deck(test_left,game_cards),
                                load_compiled_deck(test_right,game_cards),
                                energy_left=tuple(test_left['energy_types']),
                                energy_right=tuple(test_right['energy_types']),
                                left_payload=test_left,right_payload=test_right,
                                line_map=evolution_line_map(game_cards),
                                games=100,seed=int(batch_seed))
                            st.session_state['policy_compare_v09']={
                                'left':test_left,'right':test_right,'report':comparison}
                        except (RuleError,UnsupportedEffect,ValueError,IndexError,TypeError) as exc:
                            st.error(f'Comparação interrompida: {exc}')
                    pair=st.session_state.get('policy_compare_v09')
                    if pair and pair['left']==payload() and pair['right']==opponent_payload:
                        comparison=pair['report']
                        st.dataframe([{'Política': 'Clássica' if key=='baseline' else 'Tática',
                                       'Completas': item['completed'],
                                       'Falhas': item['failed'],
                                       'Média (meios-turnos)': item['average_half_turns'],
                                       'Ataques (ambos os lados)': sum(item['telemetry'][z]['counts'].get('attacks',0) for z in ('left','right')),
                                       'Evoluções': sum(item['telemetry'][z]['counts'].get('evolutions',0) for z in ('left','right')),
                                       'Recuos': sum(item['telemetry'][z]['counts'].get('retreats',0) for z in ('left','right'))}
                                      for key,item in comparison['policies'].items()],
                                     use_container_width=True,hide_index=True)
                        for policy_code, policy_data in comparison['policies'].items():
                            st.markdown(result_bars(
                                ('Clássica' if policy_code == 'baseline' else 'Tática') + ' · Meu deck',
                                ('Clássica' if policy_code == 'baseline' else 'Tática') + ' · Adversário',
                                policy_data['outcomes'], policy_data['completed']),
                                unsafe_allow_html=True)
                        st.download_button('⬇ Exportar comparação A/B (JSON)',
                            json.dumps(comparison,ensure_ascii=False,indent=2),
                            file_name='comparacao_politicas_v09.json',mime='application/json',
                            use_container_width=True)

            else:
                st.warning('Duelo técnico bloqueado: corrija os problemas listados nos dois decks.')
    else:
        st.info('Importe ou selecione um deck adversário para iniciar o diagnóstico.')


if current_view == '⚙️ Motor':
    st.subheader('Motor de regras v0.9.3.4 — expansão incremental')
    st.caption('Motor executável em testes técnicos; não é um simulador competitivo validado. A v1.0 ficará reservada para fidelidade e interface aprimoradas.')
    st.markdown('**Implementado:** mão inicial com Pokémon Básico, 20 cartas, banco de 3, compra, energia de tipo único, evolução, Doce Raro, recuo, ataques de dano fixo, fraqueza, nocaute, pontuação, IA clássica e IA tática selecionáveis, lote auditado até 1.000 partidas, alternância de jogador inicial e replay por semente.')
    st.markdown('**Efeitos técnicos implementados:** Mega Altaria, Greninja, Hoopa ex, Mega Absol ex, Entei/Suicune (Legendary Pulse), Baxcalibur (Ice Maker), Magneton (Volt Charge), Charmeleon (Ignition), ataques Crystal Waltz, Blazing Beatdown, Crimson Dive e Diving Icicles (Chien-Pao ex), Serena’s Choice, Eviolite, Giant Cape, Inflatable Boat, Chingling, Darkrai ex, Swablu (Sono), Copycat, Cyrus, Mars, X Speed, Lucky Ice Pop, Lucky Egg, Deceptive Needle, Field Blower, Repel e Pokémon Center Lady. A correspondência é feita pelo texto registrado no catálogo.')
    st.warning('Ainda não são universais: condições especiais além de Sono, ferramentas/efeitos fora destes presets, estádios, zona multicolorida, estratégia avançada e validação independente de fidelidade. Nocautes simultâneos de ataques agora são resolvidos em grupo e testados. Não trate os lotes técnicos como win rates reais.')
    st.divider()
    st.subheader('Auditoria do catálogo')
    audit=audit_core_cards(cards)
    a,b,c=st.columns(3)
    a.metric('Registros core',audit['records'])
    b.metric('Expansões',audit['expansions'])
    c.metric('IDs duplicados',audit['duplicates'])
    if audit['issues']:
        st.error(' | '.join(audit['issues']))
    else:
        st.success('Catálogo core passou nas verificações estruturais implementadas.')
    st.caption(f'Imagens ausentes: {audit["missing_images"]}. Core não inclui todas as artes alternativas.')
    if st.button('🔍 Baixar e comparar dados gameplay',use_container_width=True):
        try:
            with st.spinner('Consultando a base de combate PocketDecks...'):
                st.session_state.gameplay_data=fetch_gameplay_catalog()
        except Exception as exc:
            st.error(f'Não foi possível carregar a base gameplay: {exc}')
    gp=st.session_state.get('gameplay_data')
    if gp is not None:
        report=audit_gameplay_records(gp,cards)
        st.caption(f'Gameplay: {report["records"]} registros; {report["pokemon"]} Pokémon; {report["trainers"]} treinadores; {report["missing_from_gameplay"]} IDs do core ausentes.')
        if report['issues']:
            st.warning(' | '.join(report['issues']))
        else:
            st.success('Gameplay passou nas verificações estruturais e de IDs implementadas.')
        st.subheader('Compatibilidade do seu deck')
        compiled, blocked=compile_deck(st.session_state.counts,gp)
        if len(st.session_state.energy) != 1:
            blocked.append('Zona de energia multicolorida ainda não suportada')
        if not blocked:
            st.success('Todas as cartas selecionadas têm handlers cadastrados. Isso ainda não valida uma partida contra o meta.')
        else:
            st.info(f'{len(blocked)} pendência(s) impedem a simulação competitiva.')
            with st.expander('Ver cartas e regras pendentes'):
                for reason in blocked[:40]:
                    st.write('• '+reason)
                if len(blocked)>40: st.caption('Outras pendências omitidas para economizar espaço.')
    else:
        st.caption('Use o botão acima para baixar o catálogo de combate e conferir seu deck. A análise não é feita automaticamente para não tornar a tela inicial lenta.')
    st.divider()
    st.subheader('Teste técnico de execução')
    st.caption('Usa cartas fictícias de teste, sem relação com probabilidades de decks reais.')
    if st.button('▶️ Executar 100 partidas técnicas',use_container_width=True):
        with st.spinner('Testando o motor...'):
            diagnostic=run_smoke_checks(100)
        if diagnostic['errors']:
            st.error(f'{diagnostic["completed"]}/{diagnostic["attempted"]} partidas técnicas concluídas; falhas: {diagnostic["errors"]}')
        else:
            st.success(f'{diagnostic["completed"]}/{diagnostic["attempted"]} partidas técnicas concluídas sem exceções. Não representa win rate contra o meta.')

if current_view == 'ℹ️ Sobre':
    st.markdown('**Fonte:** [PocketDecks v5](https://github.com/PocketDecks/pokemon-tcg-pocket-cards) — comunitária, não oficial; baseada em dados do Limitless.')
    st.markdown('**Versões da base:** `core` contém cartas distintas jogáveis (sem todas as variantes de arte); `gameplay` acrescenta dados de ataques, habilidades e treinadores. [Documentação de esquema](https://github.com/PocketDecks/pokemon-tcg-pocket-cards/blob/main/docs/payloads.md).')
    st.markdown('**Limitação central:** a leitura de texto de carta não executa automaticamente sua habilidade. Apenas handlers explicitamente auditados entram na simulação.')
    st.markdown('**Licença da base:** AGPL-3.0-or-later. Consulte a licença e os avisos de terceiros no repositório do PocketDecks antes de redistribuir os dados.')
    st.caption('URL do catálogo core:')
    st.code(URL)
    st.caption('URL do catálogo de batalha:')
    st.code(GAMEPLAY_URL)

