"""TCG Pocket Lab v0.9.13: bounded sequence planning, preserved baselines, 51 sourced presets."""
import json
from collections import defaultdict
import streamlit as st
import requests
from catalog_online import fetch_catalog, validate_selection, URL
from deckbuilder import make_experiment
from layout_helpers import paginate, PAGE_SIZE
from gameplay_catalog import GAMEPLAY_URL, audit_core_cards, audit_gameplay_records, compile_deck, evolution_line_map
from engine_diagnostics import run_smoke_checks
from matchup_compatibility import parse_payload, inspect_matchup, inspect_deck, load_compiled_deck
from battle_engine import play_fixture_match, RuleError, UnsupportedEffect
from meta_decks import DECKS, get_preset, verify_presets
from offmeta_builder import generate_favorite_candidates
from offmeta_benchmark import evaluate_candidate_field
from limitless_meta import default_snapshot, validate_snapshot, evaluate_reference_coverage, REFERENCE_URL
from card_support import build_support_index, coverage_summary
from meta_gauntlet import build_gauntlet_plan, run_meta_gauntlet, MAX_GAMES_PER_OPPONENT
from meta_matrix import build_matrix_plan, run_meta_matrix, MAX_GAMES_PER_PAIR, MAX_TOTAL_MATRIX_GAMES
from matrix_insights import score_interval, compare_matrix_policies, interesting_rounds
from matrix_replay import replay_matrix_round
from deck_transfer import stage_transfer, apply_pending_transfer
from batch_runner import run_technical_batch, compare_policies, MAX_BATCH_GAMES, verify_engine_compatibility
from tactical_agent import TacticalAgent
from strategic_agent import StrategicAgentV097
from planning_agent import PlanningAgentV098, PlanningAgentV099, PlanningAgentV0910, PlanningAgentV0911, PlanningAgentV0913
from policy_duel import duel_policies
from deck_identity import describe_selection, compare_decks
from visual_theme import (CSS, VERSION, hero, section, is_pokemon, card_caption,
                          deck_overview, matchup_preview, result_bars, status_pill, library_summary,
                          matrix_rank_cards, matrix_pair_cards, matrix_heatmap)

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
NAV_ITEMS = ('🔎 Cartas', '🧩 Meu deck', '⚔️ Meta', '🧪 Off-meta', '🏆 Matriz', '⚙️ Motor', 'ℹ️ Sobre')
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


if current_view == '🏆 Matriz':
    st.markdown(section('Matriz completa do meta',
        'Compare cada deck com todos os outros e identifique tendências do simulador.',
        'ARENA · ROUND ROBIN'), unsafe_allow_html=True)
    st.caption('Resultados técnicos com IA heurística, não probabilidades reais do meta. '
               'O ranking atribui 1 ponto por vitória e meio ponto por empate, '
               'com o mesmo número de partidas por adversário.')
    st.caption(f'🆕 Biblioteca ampliada: {len(DECKS)} decks. Os sete anteriores seguem selecionados por padrão; '
               'escolha os novos quando quiser testá-los. Listas novas aguardam auditoria individual.')
    selected_matrix = st.multiselect('Decks participantes', options=list(DECKS),
        default=list(DECKS)[:7], format_func=lambda slug: DECKS[slug]['name'],
        key='matrix_selected_v094')
    matrix_games = st.select_slider('Partidas por confronto',
        options=[20,40,100], value=20, key='matrix_games_v094')
    matrix_policy = st.selectbox('Política usada pelos dois jogadores',
        ['strategic','planning','tactical','baseline'],
        format_func=lambda mode: {'planning':'Planejadora v0.9.13 (experimental)', 'strategic':'Estratégica v0.9.7', 'tactical':'Tática v0.9', 'baseline':'Clássica v0.8.4'}[mode],
        key='matrix_policy_v094')
    matrix_seed = st.number_input('Semente da matriz', min_value=0, max_value=2_000_000_000,
        step=1, value=20261116, key='matrix_seed_v094')
    matrix_request = {'decks':list(selected_matrix), 'games_per_pair':int(matrix_games),
                      'agent_mode':matrix_policy, 'seed':int(matrix_seed)}
    matrix_data = None
    matrix_field = None
    matrix_plan = None
    if len(selected_matrix) >= 2:
        try:
            matrix_data = fetch_gameplay_catalog()
            matrix_field = {slug:get_preset(slug) for slug in DECKS if slug in selected_matrix}
            matrix_plan = build_matrix_plan(matrix_field, cards, matrix_data)
            st.markdown('<div class="lab-matrix-lead">'
                f'<span class="lab-matrix-hint">🃏 {len(selected_matrix)} decks</span>'
                f'<span class="lab-matrix-hint">⚔️ {matrix_plan["total_pairs"]} pares diferentes</span>'
                f'<span class="lab-matrix-hint">✅ {matrix_plan["ready_pairs"]} simuláveis</span>'
                f'<span class="lab-matrix-hint">🎲 {matrix_plan["ready_pairs"]*int(matrix_games)} partidas previstas</span>'
                '</div>', unsafe_allow_html=True)
            if matrix_plan['blocked_pairs']:
                st.warning(f'{matrix_plan["blocked_pairs"]} par(es) pendente(s). '
                           'Eles aparecerão sem pontuação e não entrarão no ranking.')
                with st.expander('Ver os efeitos e os confrontos pendentes'):
                    for pair in matrix_plan['pairs']:
                        if pair['status']=='blocked':
                            st.markdown(f'**{pair["left_name"]} × {pair["right_name"]}**')
                            for reason in pair['reasons'][:4]:
                                st.caption(reason)
        except (requests.RequestException, ValueError, KeyError,
                TypeError, RuleError, UnsupportedEffect) as exc:
            st.error(f'Não foi possível verificar os decks: {type(exc).__name__}: {exc}')
    else:
        st.info('Selecione pelo menos dois decks para montar a matriz.')
    matrix_requested_games = (matrix_plan['ready_pairs'] * int(matrix_games)
                              if matrix_plan else 0)
    if matrix_requested_games > MAX_TOTAL_MATRIX_GAMES:
        st.warning(f'Esta seleção exigiria {matrix_requested_games} partidas. '
                   f'O limite por execução é {MAX_TOTAL_MATRIX_GAMES}. '
                   'Reduza o número de decks ou de partidas por confronto.')
    can_run_matrix = bool(matrix_plan and matrix_plan['ready_pairs'] > 0
                          and matrix_requested_games <= MAX_TOTAL_MATRIX_GAMES)
    if st.button('▶ Executar matriz de confrontos', key='run_matrix_v094',
                 use_container_width=True, disabled=not can_run_matrix):
        bar = st.progress(0, text='Preparando matriz auditada…')
        try:
            def update_matrix(done, expected):
                if expected:
                    bar.progress(min(1.0,done/expected),
                                 text=f'{done}/{expected} partidas técnicas')
            matrix_result = run_meta_matrix(matrix_field, cards, matrix_data,
                games_per_pair=int(matrix_games),seed=int(matrix_seed),
                agent_mode=matrix_policy,progress=update_matrix)
            st.session_state['matrix_report_v094'] = {
                'request':matrix_request,'report':matrix_result}
            bar.progress(1.0,text=f'{matrix_result["completed"]} partidas concluídas')
            st.session_state.pop('matrix_error_v094',None)
        except (RuleError, UnsupportedEffect, ValueError, IndexError,
                TypeError, KeyError, AttributeError, RuntimeError) as exc:
            st.session_state.pop('matrix_report_v094',None)
            st.error(f'A matriz não pôde ser concluída: {type(exc).__name__}: {exc}')
            st.session_state['matrix_error_v094'] = {
                'kind':'technical_meta_matrix_failure', 'version':VERSION,
                'request':matrix_request, 'type':type(exc).__name__,
                'message':str(exc)[:500]}
    last_matrix_error = st.session_state.get('matrix_error_v094')
    if last_matrix_error and last_matrix_error['request']==matrix_request:
        st.download_button('⬇️ Diagnóstico da falha (JSON)',
            data=json.dumps(last_matrix_error,ensure_ascii=False,indent=2),
            file_name='erro_matriz_v094.json',mime='application/json',
            key='matrix_error_download_v094',use_container_width=True)
    saved_matrix = st.session_state.get('matrix_report_v094')
    if saved_matrix and saved_matrix['request']==matrix_request:
        matrix_report = saved_matrix['report']
        summary = matrix_report['summary']
        m1,m2,m3 = st.columns(3)
        m1.metric('Pares concluídos',f'{summary["completed_pairs"]}/{summary["total_pairs"]}')
        m2.metric('Partidas auditadas',matrix_report['completed'])
        m3.metric('Falhas',matrix_report['failed'])
        if not summary['ranking_complete']:
            st.warning('Matriz incompleta: não há ranking geral comparável. '
                       'A pontuação disponível é parcial e pares pendentes não contam como derrota.')
        st.markdown('### 🏆 Ranking experimental')
        st.caption('Pontuação = (vitórias + 0,5 × empates) ÷ partidas. '
                   'A posição só é atribuída quando todos os pares terminam sem falhas.')
        enriched_rank = []
        for rank_row in summary['ranking']:
            interval = score_interval(rank_row['wins'],rank_row['losses'],rank_row['draws'])
            enriched_rank.append({**rank_row,
                'ci_lower':interval['lower_pct'],'ci_upper':interval['upper_pct']})
        st.markdown(matrix_rank_cards(enriched_rank), unsafe_allow_html=True)
        st.caption('IC de 95% aproximado pelo método de Wilson (empate vale meia vitória). '
                   'Reflete apenas variação amostral do simulador, não erros da IA ou do motor.')
        st.markdown('### 🔄 Quem começa leva vantagem?')
        first = summary['first_player']
        if first['games']:
            c1,c2,c3=st.columns(3)
            c1.metric('Vitórias de quem começou',first['first_wins'])
            c2.metric('Vitórias do segundo',first['second_wins'])
            c3.metric('Empates',first['draws'])
            st.caption(f'De {first["games"]} partidas nos pares completos: '
                       f'quem começou venceu {first["first_win_pct"]:.1f}%. '
                       'Isso não isola o efeito causal de jogar primeiro.')
        st.markdown('### 🧩 Matriz de resultados')
        st.caption('Em cada célula: pontuação percentual do deck da linha contra '
                   'o deck da coluna; empate vale meio ponto. Deslize lateralmente no celular.')
        st.markdown(matrix_heatmap(matrix_report),unsafe_allow_html=True)
        completed_with_ci=[]
        for pair in matrix_report['pairs']:
            if pair['status']=='completed':
                o=pair['outcomes']
                ci=score_interval(o['left'],o['right'],o['draw'])
                completed_with_ci.append((ci['half_width_pct'],pair,ci))
        if completed_with_ci:
            widest=max(completed_with_ci,key=lambda item:item[0])
            st.caption(f'Maior incerteza amostral: {widest[1]["left_name"]} × '
                       f'{widest[1]["right_name"]} — '
                       f'{widest[2]["lower_pct"]:.1f}% a {widest[2]["upper_pct"]:.1f}% '
                       'para o primeiro deck.')
        with st.expander('⚔️ Ver os confrontos individualmente',expanded=False):
            focus=st.selectbox('Filtrar confrontos por deck',
                options=['Todos']+list(selected_matrix),
                format_func=lambda slug: DECKS[slug]['name'] if slug in DECKS else slug,
                key='matrix_pair_filter_v095')
            visible_pairs=[p for p in matrix_report['pairs'] if focus=='Todos' or
                           focus in (p['left_slug'],p['right_slug'])]
            st.caption(f'{len(visible_pairs)} confronto(s) nesta seleção.')
            st.markdown(matrix_pair_cards(visible_pairs),unsafe_allow_html=True)
        st.markdown('### 🔍 Reproduzir uma partida por semente')
        st.caption('Escolha uma rodada do relatório para reconstruir as jogadas e os estados do campo. '
                   'O replay é comparado com o resultado original; divergências ficam explícitas.')
        shortest=interesting_rounds(matrix_report,5)
        if shortest:
            st.caption('Rodadas mais rápidas: '+ ' · '.join(
                f'{x["left_name"]} × {x["right_name"]}: '
                f'rodada {x["round"]} ({x["half_turns"]} meios-turnos)'
                for x in shortest[:3]))
        completed_pairs=[p for p in matrix_report['pairs'] if p['status']=='completed']
        if completed_pairs:
            pair_idx=st.selectbox('Confronto para investigar',
                options=list(range(len(completed_pairs))),
                format_func=lambda idx:(f'{completed_pairs[idx]["left_name"]} × '
                                        f'{completed_pairs[idx]["right_name"]}'),
                key='matrix_replay_pair_v095')
            replay_pair=completed_pairs[pair_idx]
            if st.session_state.get('matrix_replay_round_v095',1) > replay_pair['completed']:
                st.session_state['matrix_replay_round_v095']=1
            replay_round=st.number_input('Rodada do confronto',min_value=1,
                max_value=int(replay_pair['completed']),step=1,value=1,
                key='matrix_replay_round_v095')
            if st.button('🔁 Reproduzir rodada auditada',key='run_matrix_replay_v095',
                         use_container_width=True):
                try:
                    replay=replay_matrix_round(matrix_report,matrix_field,matrix_data,
                        replay_pair['left_slug'],replay_pair['right_slug'],int(replay_round))
                    st.session_state['matrix_replay_result_v095']={
                        'request':matrix_request,'pair':(replay_pair['left_slug'],
                          replay_pair['right_slug']),'round':int(replay_round),
                        'data':replay}
                except (RuleError,UnsupportedEffect,ValueError,IndexError,
                        TypeError,KeyError,RuntimeError,AssertionError) as exc:
                    st.error(f'Replay não disponível: {type(exc).__name__}: {exc}')
            replay_saved=st.session_state.get('matrix_replay_result_v095')
            if replay_saved and replay_saved['request']==matrix_request and \
               replay_saved['pair']==(replay_pair['left_slug'],replay_pair['right_slug']) and \
               replay_saved['round']==int(replay_round):
                replay=replay_saved['data']
                if replay['matches_record']:
                    st.success(f'✅ Replay confirmado: mesma vitória, duração e semente {replay["seed"]}.')
                else:
                    st.error('⚠️ A execução não coincide com o resultado original. '
                             'Não considere esta rodada validada.')
                with st.expander('📜 Jogadas registradas',expanded=False):
                    st.code('\n'.join(replay['events']),language='text')
                with st.expander('🩺 Estado do campo após cada ação',expanded=False):
                    st.json(replay['snapshots'],expanded=False)
                st.download_button('⬇️ Baixar replay completo',
                    data=json.dumps(replay,ensure_ascii=False,indent=2),
                    file_name='replay_matriz_v095.json',mime='application/json',
                    key='download_matrix_replay_v095',use_container_width=True)
        st.markdown('### 🧠 Comparar IA clássica × tática')
        st.caption('Mantém as listas e sementes iniciais. Diferenças são descritivas: '
                   'as decisões podem alterar eventos aleatórios posteriores.')
        if summary['ranking_complete'] and matrix_policy in ('baseline','tactical'):
            if st.button('⚖️ Executar política alternativa para comparar',
                         key='run_matrix_ab_v095',use_container_width=True):
                other_mode='baseline' if matrix_policy=='tactical' else 'tactical'
                bar_ab=st.progress(0,text='Simulando política alternativa…')
                try:
                    other_report=run_meta_matrix(matrix_field,cards,matrix_data,
                        games_per_pair=int(matrix_games),seed=int(matrix_seed),
                        agent_mode=other_mode,
                        progress=lambda done,expected:bar_ab.progress(
                            min(1.,done/expected),text=f'{done}/{expected} partidas')
                            if expected else None)
                    baseline=other_report if other_mode=='baseline' else matrix_report
                    tactical=other_report if other_mode=='tactical' else matrix_report
                    comparison=compare_matrix_policies(baseline,tactical)
                    st.session_state['matrix_ab_report_v095']={
                        'request':matrix_request,'data':comparison}
                    bar_ab.progress(1.0,text='Comparação concluída')
                except (RuleError,UnsupportedEffect,ValueError,IndexError,TypeError,
                        KeyError,RuntimeError,AssertionError) as exc:
                    st.error(f'Comparação não concluída: {type(exc).__name__}: {exc}')
            ab_saved=st.session_state.get('matrix_ab_report_v095')
            if ab_saved and ab_saved['request']==matrix_request:
                comp=ab_saved['data']
                st.dataframe([{'Deck':r['name'],
                    'Clássica (%)':r['classic_score_pct'],
                    'Tática (%)':r['tactical_score_pct'],
                    'Diferença (p.p.)':r['delta_pp']} for r in comp['rows']],
                    hide_index=True,use_container_width=True)
                st.caption(comp['warning'])
                st.download_button('⬇️ Comparação entre IAs (JSON)',
                    data=json.dumps(comp,ensure_ascii=False,indent=2),
                    file_name='comparacao_matriz_v095.json',mime='application/json',
                    key='download_matrix_ab_v095',use_container_width=True)
        else:
            st.info('Comparação A/B clássica × tática disponível após matriz completa com uma dessas duas políticas. Para avaliar a estratégica, use Duelo entre IAs abaixo.')
        st.download_button('⬇️ Baixar matriz completa em JSON',
            data=json.dumps(matrix_report,ensure_ascii=False,indent=2),
            file_name='matriz_meta_v099.json',mime='application/json',
            key='download_matrix_json_v094',use_container_width=True)
        # A compact export is easier to inspect in a spreadsheet on a phone.
        import csv
        import io
        buffer=io.StringIO()
        writer=csv.writer(buffer)
        writer.writerow(['Deck A','Deck B','Estado','Partidas','Vitorias A',
                         'Vitorias B','Empates','Pontuacao A (%)','Pontuacao B (%)'])
        for item in matrix_report['pairs']:
            outcome=item.get('outcomes') or {}
            writer.writerow([item['left_name'],item['right_name'],item['status'],
                item.get('completed',0),outcome.get('left',''),outcome.get('right',''),
                outcome.get('draw',''),item.get('score_left_pct',''),
                item.get('score_right_pct','')])
        st.download_button('⬇️ Baixar confrontos em CSV',
            data='\ufeff'+buffer.getvalue(),file_name='matriz_meta_v099.csv',
            mime='text/csv',key='download_matrix_csv_v094',use_container_width=True)
    elif saved_matrix:
        st.info('A configuração da matriz mudou. Execute novamente para atualizar os resultados.')



    # Direct, mirror-deck policy duel isolates AI choices from deck strength.
    with st.expander('🧠 Laboratório de decisões · IA contra IA · v0.9.13', expanded=False):
        st.caption('🆕 IA Planejadora v0.9.13: self-play e proteção de recuos; busca limitada de sequências (energia, recuo e ataque), evolução/habilidades ordenadas e custo de sobrevivência. Compare com as referências históricas; experimental.')
        st.caption('Duas IAs jogam entre si usando a MESMA lista, com posições e ordem '
                   'de início equilibradas. Isso é mais útil para comparar políticas '
                   'do que modificar a IA dos dois lados simultaneamente.')
        duel_slug = st.selectbox('Deck de referência para ambas as IAs',
            list(DECKS), format_func=lambda slug: DECKS[slug]['name'],
            key='direct_duel_deck_v098')
        duel_col1, duel_col2 = st.columns(2)
        with duel_col1:
            ai_a = st.selectbox('IA A', ['planning','planning_v09121','planning_v0912','planning_v0911','planning_v099','planning_v0910','strategic','planning_v098','strategic_v096','tactical','baseline'],
                 format_func=lambda m:{'planning':'Planejadora 0.9.13','planning_v09121':'Planejadora 0.9.12.1','planning_v0912':'Planejadora anterior 0.9.12','planning_v0911':'Planejadora anterior 0.9.11','planning_v099':'Planejadora anterior 0.9.9','planning_v0910':'Planejadora anterior 0.9.10','planning_v098':'Planejadora anterior 0.9.8','strategic':'Estratégica 0.9.7','strategic_v096':'Estratégica 0.9.6','tactical':'Tática','baseline':'Clássica'}[m],
                 key='direct_duel_a_v098')
        with duel_col2:
            ai_b = st.selectbox('IA B', ['planning_v09121','planning_v0911','planning_v0912','planning_v099','planning_v0910','strategic','planning_v098','strategic_v096','tactical','baseline','planning'],
                 format_func=lambda m:{'planning':'Planejadora 0.9.13','planning_v09121':'Planejadora 0.9.12.1','planning_v0912':'Planejadora anterior 0.9.12','planning_v0911':'Planejadora anterior 0.9.11','planning_v099':'Planejadora anterior 0.9.9','planning_v0910':'Planejadora anterior 0.9.10','planning_v098':'Planejadora anterior 0.9.8','strategic':'Estratégica 0.9.7','strategic_v096':'Estratégica 0.9.6','tactical':'Tática','baseline':'Clássica'}[m],
                 key='direct_duel_b_v098')
        duel_games = st.select_slider('Partidas do confronto entre IAs',
            options=[20,100,200,400],value=100,key='direct_duel_n_v098')
        duel_seed = st.number_input('Semente para comparação direta', min_value=0,
            max_value=2_000_000_000, value=77531041, step=1,
            key='direct_duel_seed_v098')
        benchmark_split = st.radio('Conjunto de sementes', ['development', 'holdout'],
            format_func=lambda v:'Desenvolvimento (ajuste)' if v=='development' else
                'Validação reservada (teste independente)',
            horizontal=True, key='direct_duel_split_v098')
        st.caption('Na validação reservada, as sementes são deslocadas em +10 milhões. '
                   'Não use o resultado de validação para ajustar pesos e depois '
                   'afirmar que essa mesma amostra é independente.')
        duel_preset = get_preset(duel_slug)
        duel_block = duel_preset.get('simulation_blocked_reason','')
        if ai_a == ai_b:
            st.info('🪞 Self-play ativado: uma IA enfrenta uma cópia idêntica. A taxa de vitória entre clones NÃO indica força; avalie equilíbrio entre primeiro/segundo, recuos, evolução e ataques.')
        if duel_block:
            st.warning(f'Deck ainda não auditado: {duel_block}')
        can_duel = not duel_block
        if st.button('🪞 Executar self-play' if ai_a==ai_b else '⚔️ Comparar políticas',
                     key='run_direct_duel_v098',use_container_width=True,
                     disabled=not can_duel):
            progress_duel = st.progress(0,text='Preparando confronto entre IAs…')
            try:
                game_cards_duel = matrix_data if matrix_data is not None else fetch_gameplay_catalog()
                diagnosis_duel=inspect_deck(duel_preset,cards,game_cards_duel)
                if not diagnosis_duel['technical_demo_ready']:
                    raise ValueError('Deck incompatível. Revise as cartas pendentes no catálogo antes de jogar.')
                duel_report=duel_policies(
                    load_compiled_deck(duel_preset,game_cards_duel),
                    tuple(duel_preset['energy_types']),
                    evolution_line_map(game_cards_duel),
                    policy_a=ai_a,policy_b=ai_b,games=int(duel_games),
                    seed=int(duel_seed), benchmark_split=benchmark_split,
                    keep_replay=True,deck_name=duel_preset['name'],
                    progress=lambda done,target:progress_duel.progress(
                        min(1.,done/target),text=f'{done}/{target} partidas')
                        if target else None)
                st.session_state['direct_duel_report_v098']={
                    'config':(duel_slug,ai_a,ai_b,int(duel_games),int(duel_seed),benchmark_split),
                    'report':duel_report}
                progress_duel.progress(1.,text='Comparação concluída')
            except (RuleError,UnsupportedEffect,ValueError,TypeError,IndexError,
                    KeyError,AssertionError,AttributeError,RuntimeError) as exc:
                st.error(f'Confronto das IAs não pôde ser executado: {type(exc).__name__}: {exc}')
        saved_duel=st.session_state.get('direct_duel_report_v098')
        if saved_duel and saved_duel['config']==(duel_slug,ai_a,ai_b,int(duel_games),int(duel_seed),benchmark_split):
            report=saved_duel['report']
            st.metric('Partidas auditadas',report['completed'])
            st.caption('Deck: '+str(report.get('deck_name',duel_preset['name'])))
            st.caption('Conjunto: '+str(report.get('benchmark_split','development'))+
                ' · primeira semente: '+str(report.get('effective_seed',report['seed'])))
            o=report['outcomes'];ci=report['a_score_interval']
            st.markdown(f'**{ai_a}**: {o["a"]} vitórias · '
                        f'**{ai_b}**: {o["b"]} vitórias · {o["draw"]} empates')
            if report.get('self_play_diagnostics'):
                sp=report['self_play_diagnostics']
                st.markdown('**Diagnóstico de self-play (clones idênticos)**')
                st.caption(f'Quem começou venceu {sp["first_player_wins"]} partidas; quem começou em segundo, {sp["second_player_wins"]}. '
                           'Compare ritmo e ações; a vitória de A ou B não representa melhoria da política.')
                if sp['first_player_score_interval']:
                    sc=sp['first_player_score_interval']
                    st.caption(f'Pontuação de quem começou: {sc["score_pct"]:.1f}% (IC 95%: '
                               f'{sc["lower_pct"]:.1f}–{sc["upper_pct"]:.1f}%).')
                if sp.get('starting_position_signal')=='second_player_advantage_in_this_sample':
                    st.warning('Neste conjunto houve vantagem para quem começou em segundo. Investigue o efeito das regras, da política e das sementes antes de generalizar.')
                elif sp.get('starting_position_signal')=='first_player_advantage_in_this_sample':
                    st.warning('Neste conjunto houve vantagem para quem começou primeiro. Investigue com novos decks e sementes antes de generalizar.')
            if ci and not report.get('self_play_diagnostics'):
                st.caption(f'Pontuação da IA A: {ci["score_pct"]:.1f}% '
                           f'(IC aproximado de 95%: {ci["lower_pct"]:.1f}–{ci["upper_pct"]:.1f}%). '
                           'Não é uma taxa de vitória contra jogadores humanos.')
            st.caption('Indicadores observados no histórico, não uma avaliação perfeita das jogadas. Os totais devem ser lidos junto com o número de turnos de cada IA.')
            if report.get('scenario_intervals'):
                by_start = report['scenario_intervals']
                a_first = by_start['a_first']['score_pct']
                b_first = by_start['b_first']['score_pct']
                st.caption(f'Pontuação da IA A: {a_first:.1f}% começando primeiro; '
                           f'{b_first:.1f}% começando em segundo. Consulte os '
                           'intervalos completos no JSON; subgrupos têm menor amostra.')
            st.dataframe([{'IA': 'A · '+ai_a,'Energia anexada':report['telemetry']['left']['counts'].get('energy_attached',0),
                 'Turnos sem ataque':report['telemetry']['left']['counts'].get('turns_without_attack',0),
                 'Nocautes':report['telemetry']['left']['counts'].get('knockouts',0),
                 'Pontos marcados':report['telemetry']['left']['counts'].get('points_scored',0),
                 'Evoluções':report['telemetry']['left']['counts'].get('evolutions',0),
                 'Recuos':report['telemetry']['left']['counts'].get('retreats',0)},
                 {'IA':'B · '+ai_b,'Energia anexada':report['telemetry']['right']['counts'].get('energy_attached',0),
                 'Turnos sem ataque':report['telemetry']['right']['counts'].get('turns_without_attack',0),
                 'Nocautes':report['telemetry']['right']['counts'].get('knockouts',0),
                 'Pontos marcados':report['telemetry']['right']['counts'].get('points_scored',0),
                 'Evoluções':report['telemetry']['right']['counts'].get('evolutions',0),
                 'Recuos':report['telemetry']['right']['counts'].get('retreats',0)}],
                 hide_index=True,use_container_width=True)
            for side,label in [('left','IA A'),('right','IA B')]:
                counts=report['telemetry'][side]['counts']
                turns=counts.get('turns',0)
                if turns:
                    st.caption(f'{label}: {counts.get("turns_without_attack",0)/turns:.1%} '
                               f'dos turnos sem ataque · {counts.get("energy_attached",0)/turns:.2f} '
                               'energias anexadas por turno (média).')
            if report.get('efficiency'):
                rows_eff=[]
                for key,name in [('a',ai_a),('b',ai_b)]:
                    data=report['efficiency'][key]
                    rows_eff.append({'IA':name,'Turnos sem ataque (%)':data['turns_without_attack_pct'],
                                     'Nocautes / 100 ataques':data['knockouts_per_100_attacks'],
                                     'Pontos / 100 ataques':data['points_per_100_attacks'],
                                     'Anexos / 100 turnos':data['energy_per_100_turns'],
                                     'Dano nominal / ataque':data['gross_damage_per_attack']})
                st.markdown('**Eficiência normalizada por IA**')
                st.dataframe(rows_eff,hide_index=True,use_container_width=True)
                st.caption('Métricas descritivas do histórico: não atribuem causa às decisões nem comprovam superioridade.')
            with st.expander('🎯 Eficiência por atacante · métricas observadas', expanded=False):
                st.caption('Dano = valor numérico registrado no evento de ataque; pode incluir excesso sobre o HP restante e não incorpora todos os efeitos. Nocautes e pontos permanecem totais por IA, sem atribuição especulativa ao Pokémon.')
                attackers=[]
                for side,label in [('left','IA A · '+ai_a),('right','IA B · '+ai_b)]:
                    data=report['telemetry'][side]
                    for mon,n in sorted(data.get('attacks_by_pokemon',{}).items()):
                        dmg=data.get('reported_damage_by_pokemon',{}).get(mon,0)
                        attackers.append({'Política':label,'Atacante':mon,
                                          'Ataques':n,'Dano reportado':dmg,
                                          'Dano reportado/ataque':round(dmg/n,1) if n else None})
                if attackers:
                    st.dataframe(attackers,hide_index=True,use_container_width=True)
                else:
                    st.info('Nenhum ataque registrado neste relatório.')
            if report.get('decision_audit'):
                st.caption('Cobertura da auditoria: '+', '.join(
                    f'{k.upper()}={v}' for k,v in report['decision_audit'].get('coverage',{}).items())+
                    '. Políticas anteriores podem oferecer somente ações observadas, sem escores internos.')
                with st.expander('🔍 Auditoria — alternativas avaliadas pela IA', expanded=False):
                    st.caption('Registra as alternativas consideradas nos turnos amostrados, '
                               'pontuação heurística e motivo. Não é prova de jogada ótima.')
                    sample_rows = []
                    for entry in report['decision_audit'].get('examples', []):
                        if entry.get('projected_margin') is None:
                            continue
                        sample_rows.append({
                            'Partida': entry.get('round'),
                            'IA': entry.get('policy'),
                            'Decisão': entry.get('decision'),
                            'Escolha': entry.get('chosen'),
                            'Pontuação escolhida': entry.get('chosen_projected_score'),
                            'Melhor alternativa': entry.get('best_rejected_projected_score'),
                            'Margem projetada': entry.get('projected_margin'),
                        })
                    if sample_rows:
                        st.markdown('**Comparação contrafactual estimada (amostra)**')
                        st.dataframe(sample_rows, hide_index=True, use_container_width=True)
                        st.caption('Margens são diferenças de pontuação heurística no mesmo estado, '
                                   'não resultados de partidas alternativas. A auditoria registra '
                                   'somente uma amostra limitada de decisões.')
                    st.json(report['decision_audit'], expanded=False)
            if report.get('sample_replay'):
                with st.expander('🎞️ Replay auditado da primeira partida', expanded=False):
                    st.code('\n'.join(report['sample_replay'].get('events',[])),language='text')
                    st.json(report['sample_replay'].get('snapshots',[]),expanded=False)
            st.caption('As energias anexadas são contadas no formato real do log e '
                       'separadas em anexação manual ou por efeito. Isso não mede '
                       'automaticamente a qualidade de cada anexação.')
            if report['errors']:
                st.error('Algumas partidas falharam; não interprete as vitórias como resultado completo.')
            st.download_button('⬇️ Baixar benchmark de IA',
                data=json.dumps(report,ensure_ascii=False,indent=2),
                file_name='duelo_ias_v0913.json',mime='application/json',
                key='download_direct_duel_v098',use_container_width=True)



if current_view == '🧪 Off-meta':
    st.markdown(section('Laboratório off-meta',
        'Escolha sua carta favorita, crie hipóteses de decks e teste somente as listas compatíveis.',
        'PESQUISA · V0.9.13'), unsafe_allow_html=True)
    st.info('A IA ainda NÃO aprende nem inventa regras: esta etapa gera hipóteses a partir de '
            'listas existentes. Só recomenda desempenho após partidas realmente executadas.')

    # External data is a dated snapshot, not inferred from current local games.
    if 'limitless_snapshot_v0913' not in st.session_state:
        st.session_state['limitless_snapshot_v0913'] = default_snapshot()
    with st.expander('📊 Referência externa — Play Limitless', expanded=True):
        st.caption('Fonte: Play Limitless, Pokémon TCG Pocket. Retrato consultado em 19/11/2026; '
                   'não é atualização automática. A participação e o win rate da tabela pertencem '
                   'aos torneios, NÃO são resultados do nosso simulador.')
        st.link_button('Abrir dados do Limitless', REFERENCE_URL)
        snapshot_file = st.file_uploader('Importar snapshot JSON validado (opcional)',type=['json'],
                                         key='limitless_import_v0913')
        if snapshot_file is not None and st.button('Validar e aplicar snapshot',key='limitless_apply_v0913'):
            try:
                incoming=json.loads(snapshot_file.getvalue().decode('utf-8'))
                st.session_state['limitless_snapshot_v0913']=validate_snapshot(incoming)
                st.success('Snapshot validado; participações externas atualizadas nesta sessão.')
            except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
                st.error(f'Não foi possível importar o snapshot: {exc}')
        snapshot=st.session_state['limitless_snapshot_v0913']
        st.caption(f"Último retrato: {snapshot.get('observed_on','sem data')} · "
                   f"{len(snapshot['archetypes'])} arquétipos nesta amostra. "
                   'O restante do meta permanece fora da amostra.')
        st.dataframe([{'Arquétipo':a['name'], 'Participação (%)':a['share_pct'],
                       'Win rate externo (%)':a.get('observed_win_pct'),
                       'Decks registrados':a.get('count')}
                      for a in snapshot['archetypes']],
                     use_container_width=True,hide_index=True)
        st.download_button('Baixar snapshot versionado (JSON)',
                           data=json.dumps(snapshot,ensure_ascii=False,indent=2),
                           file_name='limitless_pocket_snapshot_v0913.json',mime='application/json',
                           key='limitless_download_v0913')

    st.markdown('### Começar por uma carta favorita')
    query_fav=st.text_input('Busque pelo nome do Pokémon ou da carta',
        placeholder='Ex.: Dragonite, Greninja, Gengar…',key='favorite_query_v0913')
    matches=([c for c in cards if query_fav.strip().casefold() in c['name'].casefold()]
             if query_fav.strip() else [])
    matches=sorted(matches,key=lambda c:(c['name'].casefold(),c['id']))[:100]
    if query_fav.strip() and not matches:
        st.warning('Nenhuma carta com esse nome no catálogo carregado.')
    if matches:
        candidate_favorite=st.selectbox('Carta / edição específica',
            [c['id'] for c in matches],
            format_func=lambda cid:f"{by_id[cid]['name']} · {cid}",
            key='favorite_card_v0913')
        st.caption('Geração determinística: variações de listas conhecidas mantendo a carta escolhida. '
                   'Uma evolução sem linha prévia cadastrada não é completada por suposição.')
        if st.button('✨ Gerar hipóteses de deck',key='generate_offmeta_v0913',use_container_width=True):
            st.session_state['offmeta_request_v0913'] = candidate_favorite
        chosen=st.session_state.get('offmeta_request_v0913')
        if chosen==candidate_favorite:
            options=generate_favorite_candidates(chosen,cards,DECKS,
                        current=payload() if total()==20 else None,max_candidates=5)
            if not options:
                st.warning('Não há uma construção segura a partir das listas atuais para esta evolução. '
                           'É necessário cadastrar/validar sua linha evolutiva antes de propor uma lista completa.')
            else:
                st.markdown(f'**{len(options)} hipóteses para {by_id[chosen]["name"]}**')
                st.caption('A ordem das opções NÃO representa um ranking de força. '
                           'Listas catalogadas/bloqueadas não recebem percentuais de vitória.')
                try:
                    game_catalog=fetch_gameplay_catalog()
                except (requests.RequestException,ValueError,TypeError) as exc:
                    game_catalog=None
                    st.warning(f'Compatibilidade temporariamente indisponível: {exc}')
                opponent_options=[r['slug'] for r in snapshot['archetypes'] if r['slug'] in DECKS]
                chosen_rivals=st.multiselect('Adversários do Limitless para testar',
                    opponent_options, default=[slug for slug in ('hoopa_mega_absol','mega_altaria_greninja')
                                              if slug in opponent_options],
                    format_func=lambda slug: DECKS[slug]['name'],key='offmeta_rivals_v0913')
                games_off=st.select_slider('Partidas por adversário compatível',
                    options=[20,40,100],value=40,key='offmeta_games_v0913')
                seed_off=st.number_input('Semente experimental',min_value=0,
                    max_value=2_000_000_000,value=77531041,step=1,key='offmeta_seed_v0913')
                if 'offmeta_results_v0913' not in st.session_state:
                    st.session_state['offmeta_results_v0913']={}
                if st.button('🧪 Simular todas as hipóteses elegíveis e comparar',
                             key='offmeta_all_v0913',disabled=not game_catalog or not chosen_rivals,
                             use_container_width=True):
                    try:
                        rivals={slug:get_preset(slug) for slug in chosen_rivals}
                        comparison=evaluate_candidate_field(options,rivals,cards,game_catalog,
                            games_per_opponent=int(games_off),seed=int(seed_off),snapshot=snapshot)
                        st.session_state['offmeta_all_results_v0913']={
                            'request':[chosen,chosen_rivals,int(games_off),int(seed_off)],
                            'result':comparison}
                    except (RuleError,UnsupportedEffect,ValueError,TypeError,KeyError,RuntimeError) as exc:
                        st.error(f'Não foi possível comparar as hipóteses: {exc}')
                combined=st.session_state.get('offmeta_all_results_v0913')
                if combined and combined['request']==[chosen,chosen_rivals,int(games_off),int(seed_off)]:
                    report_all=combined['result']
                    st.markdown('**Avaliação conjunta das candidatas**')
                    st.dataframe([{'Construção':r['name'], 'Ranking técnico':r['rank'],
                                   'Status':r['status'], 'Partidas':r['completed'],
                                   'Cobertura do meta (%)':r['covered_meta_share_pct'],
                                   'Score ponderado (%)':r['technical_weighted_score_pct']}
                                   for r in report_all['candidates']],
                                 use_container_width=True,hide_index=True)
                    st.caption(report_all['warnings'])
                    if not report_all['ranked']:
                        st.info('Sem ranking comparável: faltam duas candidatas simuláveis '
                                'com exatamente os mesmos adversários e número de partidas.')
                    st.download_button('Baixar comparação completa JSON',
                        data=json.dumps(report_all,ensure_ascii=False,indent=2),
                        file_name='offmeta_comparacao_v0913.json',mime='application/json',
                        key='offmeta_all_download_v0913')

                for candidate in options:
                    deck=candidate['deck']
                    with st.expander(candidate['label'],expanded=False):
                        st.caption(f"Fonte de construção: {candidate['source_name']} · "
                                   f"{candidate['favorite_copies']} cópia(s) da carta escolhida · "
                                   f"{candidate['changes_from_source']} substituição(ões) · "
                                   f"energia: {', '.join(deck['energy_types'])}")
                        inspection=inspect_deck(deck,cards,game_catalog) if game_catalog else None
                        blocked=deck.get('simulation_blocked_reason','')
                        ready=bool(inspection and inspection['technical_demo_ready'] and not blocked)
                        if ready:
                            st.success('20/20 cartas reconhecidas. Elegível para duelo técnico (não homologação competitiva).')
                        else:
                            reasons=([blocked] if blocked else []) + (
                                inspection['issues'] if inspection else ['Catálogo de jogabilidade indisponível'])
                            st.warning('Não simulável nesta versão: '+'; '.join(reasons[:3]))
                            if inspection:
                                missing=[f"{c['name']}: {c['reason']}" for c in inspection['cards']
                                         if c['status']=='bloqueada']
                                if missing: st.caption('; '.join(missing[:4]))
                        with st.container():
                            st.download_button('Baixar deck JSON',
                                data=json.dumps(deck,ensure_ascii=False,indent=2),
                                file_name=f"offmeta_{candidate['id']}_v0913.json",mime='application/json',
                                key=f"offmeta_download_{candidate['id']}")
                            if st.button('🧩 Carregar para editar',key=f"offmeta_load_{candidate['id']}"):
                                try:
                                    load_payload(deck)
                                    st.success('Deck enviado ao editor. Abra a aba Meu deck para editar.')
                                    st.rerun()
                                except (ValueError,KeyError,TypeError) as exc:
                                    st.error(str(exc))
                            if st.button('⚔️ Simular esta hipótese',key=f"offmeta_sim_{candidate['id']}",
                                         disabled=not ready or not chosen_rivals):
                                rival_field={slug:get_preset(slug) for slug in chosen_rivals}
                                try:
                                    report=run_meta_gauntlet(deck,rival_field,cards,game_catalog,
                                      games_per_opponent=int(games_off),seed=int(seed_off),
                                      agent_mode='planning')
                                    report['limitless_reference']=evaluate_reference_coverage(
                                        report['results'],snapshot)
                                    st.session_state['offmeta_results_v0913'][candidate['id']]=(
                                        {'request':[chosen,chosen_rivals,int(games_off),int(seed_off),
                                                    deck['cards']], 'report':report})
                                except (RuleError,UnsupportedEffect,ValueError,IndexError,
                                        KeyError,TypeError,RuntimeError) as exc:
                                    st.error(f'Erro de simulação: {exc}')
                            saved=st.session_state['offmeta_results_v0913'].get(candidate['id'])
                            request=[chosen,chosen_rivals,int(games_off),int(seed_off),deck['cards']]
                            if saved and saved['request']==request:
                                report=saved['report']
                                weighted=report['limitless_reference']
                                st.metric('Partidas concluídas',report['completed'])
                                st.metric('Participação do meta coberta por simulações',
                                          f"{weighted['completed_share_pct']:.2f}%")
                                if weighted['conditional_score_pct'] is None:
                                    st.info('Nenhum adversário escolhido possui mecânicas plenamente suportadas. '
                                            'Não há taxa de vitória a informar.')
                                else:
                                    st.metric('Resultado técnico ponderado, SOMENTE cobertura',
                                              f"{weighted['conditional_score_pct']:.1f}%")
                                st.caption(weighted['warning'])
                                st.dataframe([{'Adversário':r['name'],'Status':r['status'],
                                               'Jogos':r.get('completed',0),'Win rate técnico (%)':r.get('win_rate')}
                                              for r in report['results']],use_container_width=True,
                                             hide_index=True)
                                st.download_button('Baixar relatório de simulações JSON',
                                    data=json.dumps(report,ensure_ascii=False,indent=2),
                                    file_name=f"offmeta_resultado_{candidate['id']}_v0913.json",
                                    mime='application/json',key=f"offmeta_report_{candidate['id']}")

if current_view == '⚔️ Meta':
    st.markdown(section('Arena de confrontos',
        'Escolha seu oponente, confira os efeitos e investigue o comportamento da IA.',
        'BATTLE LAB'), unsafe_allow_html=True)
    st.caption('Os resultados são experimentais: a IA e o motor ainda não reproduzem todas as regras do jogo.')
    st.button('🏆 Abrir matriz de confrontos', key='open_matrix_v094',
        use_container_width=True,
        on_click=lambda: st.session_state.__setitem__('main_view_v0933','🏆 Matriz'))
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
        ['Estratégica v0.9.7 — prioriza recursos e sobrevivência',
         'Planejadora v0.9.13 — self-play e controle de recuo (experimental)',
         'Tática v0.9 — considera evoluções e melhores trocas',
         'Clássica v0.8.4 — referência anterior'],
        key='policy_choice_v09',
        help='A mesma política controla os dois jogadores. Não é treinamento de modelo de IA.')
    agent_mode = ('planning' if policy_label.startswith('Planejadora') else
                  'strategic' if policy_label.startswith('Estratégica') else
                  'tactical' if policy_label.startswith('Tática') else 'baseline')
    st.caption('Planejadora v0.9.13 combina caminhos de energia, recuo e ataque com evolução/abilities legais; nenhum acesso a informação oculta e nenhuma nova regra implementada.')

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
            player_id=describe_selection(payload(),'Meu deck').get('recognized_preset')
            player_pending=DECKS.get(player_id,{}).get('simulation_blocked_reason','')
            opponent_id=describe_selection(opponent_payload,'Adversário').get('recognized_preset')
            opponent_pending=(opponent_payload.get('simulation_blocked_reason') or
                              DECKS.get(opponent_id,{}).get('simulation_blocked_reason',''))
            if match_report['technical_demo_ready'] and not (player_pending or opponent_pending):
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
                            agent_cls={'baseline':None,'tactical':TacticalAgent,'strategic':StrategicAgentV097,'planning':PlanningAgentV0911}[agent_mode])
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
                st.warning('Duelo técnico bloqueado: ainda há cartas ou efeitos aguardando auditoria.')
                if player_pending:
                    st.info('Seu deck: '+player_pending)
                if opponent_pending:
                    st.info('Adversário: '+opponent_pending)
    else:
        st.info('Importe ou selecione um deck adversário para iniciar o diagnóstico.')


if current_view == '⚙️ Motor':
    st.subheader('Motor de regras — base v0.9.3.4, políticas de IA até v0.9.13')
    st.caption('Motor executável em testes técnicos; não é um simulador competitivo validado. A v1.0 ficará reservada para fidelidade e interface aprimoradas.')
    st.markdown('**Implementado:** mão inicial com Pokémon Básico, 20 cartas, banco de 3, compra, energia de tipo único, evolução, Doce Raro, recuo, ataques de dano fixo, fraqueza, nocaute, pontuação, IA clássica, tática e estratégica selecionáveis, lote auditado até 1.000 partidas, alternância de jogador inicial e replay por semente.')
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

