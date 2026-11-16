"""TCG Pocket Lab v0.7: two-deck compatibility and technical match replay."""
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

META = ['Mega Altaria / Greninja', 'Mega Charizard Y / Entei', 'Suicune / Baxcalibur', 'Magnezone / Miraidon', 'Hoopa / Mega Absol']
ENERGIES = ['water', 'fire', 'grass', 'lightning', 'psychic', 'fighting', 'darkness', 'metal']
st.set_page_config(page_title='TCG Pocket Lab', page_icon='🃏', layout='wide')
st.markdown("""<style>
/* Only small visual refinements; the responsive grid is native Streamlit. */
.block-container {max-width: 1050px; padding-top: 1rem; padding-bottom: 3rem}
@media (max-width: 700px) {
    .block-container {padding-left: .6rem; padding-right: .6rem}
    h1 {font-size: 1.6rem !important}
    [data-testid="stGrid"] [data-testid="stButton"] button {min-height: 2.5rem; padding: .15rem .25rem}
    [data-testid="stGrid"] [data-testid="stImage"] img {border-radius: 5px}
}
</style>""", unsafe_allow_html=True)

for key, default in {'counts':{},'deck_name':'Meu deck','energy':['water'],'saved_decks':{},'page':1}.items():
    if key not in st.session_state: st.session_state[key] = default
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
    return {'format':'tcgp-lab-v0.7','name':st.session_state.deck_name,'energy_types':list(st.session_state.energy),'cards':dict(st.session_state.counts)}

def load_payload(data):
    counts=data['cards']
    if not isinstance(counts,dict) or any(cid not in by_id or type(n) is not int or not 1<=n<=2 for cid,n in counts.items()):
        raise ValueError('IDs ou quantidades inválidos no catálogo atual')
    if sum(counts.values())>20: raise ValueError('Mais de 20 cartas')
    grouped=defaultdict(int)
    for cid,n in counts.items(): grouped[by_id[cid]['name'].casefold()]+=n
    if any(n>2 for n in grouped.values()): raise ValueError('Mais de duas cópias do mesmo nome')
    energies=data.get('energy_types',[])
    if not isinstance(energies,list) or not 1<=len(energies)<=3 or len(energies)!=len(set(energies)) or any(e not in ENERGIES for e in energies):
        raise ValueError('Tipos de energia inválidos')
    st.session_state.counts=dict(counts)
    st.session_state.energy=list(energies)
    st.session_state.deck_name=str(data.get('name','Meu deck'))[:100]

st.title('🃏 TCG Pocket Lab')
st.caption(f'v0.7 · {len(cards):,} cartas jogáveis · catálogo comunitário · simulações competitivas não validadas'.replace(',', '.'))
st.progress(min(total()/20,1),text=f'🧩 Meu deck: {total()}/20 cartas')
catalog_tab, deck_tab, lab_tab, motor_tab, info_tab = st.tabs(['🔎 Cartas','🧩 Meu deck','⚔️ Meta','⚙️ Motor','ℹ️ Sobre'])

def reset_page():
    st.session_state.page = 1


def previous_page():
    st.session_state.page = max(1, st.session_state.page - 1)


def next_page():
    st.session_state.page += 1


def card_tile(card, location):
    """Create one compact card inside a Streamlit grid cell."""
    if card['image']:
        st.image(card['image'], use_container_width=True)
    else:
        st.caption('🃏 Imagem indisponível')
    st.markdown(f"**{card['name']}**")
    st.caption(f"{card['set']} · #{card['number']}")
    n = st.session_state.counts.get(card['id'], 0)
    # This inner row must also stay horizontal on mobile.
    minus, plus = st.columns(2, gap='xsmall', wrap=False)
    minus.button('−', key=f'{location}_minus_{card["id"]}',
                 disabled=n == 0, on_click=remove, args=(card['id'],),
                 use_container_width=True)
    plus.button(f'+ {n}', key=f'{location}_plus_{card["id"]}',
                disabled=not can_add(card), on_click=add, args=(card['id'],),
                use_container_width=True)


with catalog_tab:
    st.text_input('Buscar carta', placeholder='Nome do Pokémon ou treinador',
                  key='catalog_query', on_change=reset_page)
    with st.expander('⚙️ Filtrar por expansão e categoria', expanded=False):
        sets = sorted({c['set'] for c in cards if c['set']})
        types = sorted({c['type'] for c in cards if c['type']})
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox('Expansão', ['Todas'] + sets, key='chosen_set',
                         on_change=reset_page)
        with c2:
            st.selectbox('Categoria', ['Todas'] + types, key='chosen_type',
                         on_change=reset_page)

    query = st.session_state.get('catalog_query', '').strip().casefold()
    chosen_set = st.session_state.get('chosen_set', 'Todas')
    chosen_type = st.session_state.get('chosen_type', 'Todas')
    filtered = [c for c in cards
                if query in c['name'].casefold()
                and (chosen_set == 'Todas' or c['set'] == chosen_set)
                and (chosen_type == 'Todas' or c['type'] == chosen_type)]
    visible, page, pages = paginate(filtered, st.session_state.page, PAGE_SIZE)
    st.session_state.page = page
    st.caption(f'{len(filtered)} resultados · {PAGE_SIZE} por página')
    back, current, forward = st.columns([1, 1.3, 1], gap='xsmall', wrap=False)
    back.button('◀ Anterior', on_click=previous_page, disabled=page <= 1,
                use_container_width=True)
    current.markdown(f'<div style="text-align:center;padding:.45rem 0">{page} / {pages}</div>',
                     unsafe_allow_html=True)
    forward.button('Próxima ▶', on_click=next_page, disabled=page >= pages,
                   use_container_width=True)

    if not visible:
        st.info('Nenhuma carta encontrada para esses filtros.')
    else:
        # Streamlit >=1.67: up to 4 columns on desktop; 2 on typical phones.
        # The native grid reflows, unlike st.columns() with its default wrap.
        gallery = st.grid(4, min_column_width=150, gap='xsmall',
                          border=True, key='catalog_gallery')
        for card in visible:
            with gallery.cell():
                card_tile(card, 'catalog')

with deck_tab:
    st.text_input('Nome do deck', key='deck_name')
    st.multiselect('Energias (até 3)', ENERGIES, key='energy', max_selections=3)
    selected = list(st.session_state.counts.items())
    if not selected:
        st.info('Seu deck está vazio. Vá à aba Cartas para adicionar Pokémon e treinadores.')
    else:
        gallery = st.grid(4, min_column_width=150, gap='xsmall',
                          border=True, key='my_deck_gallery')
        for cid, n in selected:
            c = by_id.get(cid)
            with gallery.cell():
                if c:
                    card_tile(c, 'deck')
                else:
                    st.warning(f'Carta ausente: {cid}')
    issues=validate_selection(st.session_state.counts,cards)
    if not st.session_state.energy: issues.append('Selecione ao menos um tipo de energia.')
    if issues: st.warning(' | '.join(issues))
    else: st.success('Passou nas verificações estruturais disponíveis; legalidade completa ainda não confirmada.')
    st.download_button('⬇️ Exportar deck JSON',json.dumps(payload(),ensure_ascii=False,indent=2),file_name='meu_deck.json',mime='application/json',use_container_width=True)
    uploaded=st.file_uploader('Importar deck JSON (v0.4–v0.7)',type=['json'])
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

with lab_tab:
    st.subheader('Comparar dois decks')
    st.caption('Monte seu deck na aba Meu deck. Depois carregue o adversário para diagnosticar cartas e efeitos necessários.')
    opponent_mode = st.radio('Deck adversário',
        ['Importar JSON','Deck salvo na sessão','Espelhar meu deck (depuração)'],
        horizontal=False, key='opponent_mode')
    opponent_payload = None
    if opponent_mode == 'Importar JSON':
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
                    else:
                        st.info('Adicione cartas na aba Meu deck.')
            st.download_button('⬇️ Exportar relatório de compatibilidade',
                               data=json.dumps(match_report,ensure_ascii=False,indent=2),
                               file_name='compatibilidade_decks_v07.json',
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
                            line_map=evolution_line_map(game_cards))
                        st.session_state['debug_trace']={
                            'seed':int(technical_seed), 'turns':demo.turn,
                            'winner':demo.winner,
                            'events':demo.log,
                            'left':payload(),'right':opponent_payload}
                    except (RuleError, UnsupportedEffect, ValueError, IndexError) as exc:
                        st.error(f'Partida técnica interrompida: {exc}')
                trace=st.session_state.get('debug_trace')
                if trace and trace['left']==payload() and trace['right']==opponent_payload:
                    st.info(f'Depuração concluída: {trace["turns"]} meios-turnos; '
                            'veja o histórico abaixo. O resultado não estima competitividade.')
                    with st.expander('Histórico da partida',expanded=True):
                        st.code('\n'.join(trace['events'][-250:]),language=None)
                    st.download_button('⬇️ Baixar replay JSON',
                                       json.dumps(trace,ensure_ascii=False,indent=2),
                                       file_name='duelo_debug.json',mime='application/json')
            else:
                st.warning('Duelo técnico bloqueado: corrija os problemas listados nos dois decks.')
    else:
        st.info('Importe ou selecione um deck adversário para iniciar o diagnóstico.')

    st.divider()
    st.subheader('Planejamento contra o meta')
    st.caption('Os arquétipos abaixo ainda não têm listas de 20 cartas verificadas '
               'nesta versão. Selecioná-los prepara um plano, não partidas.')
    opponents=st.multiselect('Adversários do meta',META,default=META)
    games=st.number_input('Partidas planejadas por confronto',min_value=1,
                           max_value=1_000_000,value=100_000,step=10_000)
    seed=st.number_input('Semente do planejamento',min_value=0,value=20261116)
    st.metric('Partidas planejadas (não executadas)',
              f'{len(opponents)*int(games):,}'.replace(',','.'))
    if opponents:
        plan=make_experiment('meu_deck.json',opponents,int(games),int(seed))
        plan['player_deck']=payload()
        st.download_button('⬇️ Exportar plano',
                           json.dumps(plan,ensure_ascii=False,indent=2),
                           file_name='experimento.json')
    st.button('▶️ Simular 100 mil partidas competitivas',disabled=True)
with motor_tab:
    st.subheader('Motor de regras v0.7')
    st.caption('Motor executável em testes técnicos; não é um simulador competitivo validado.')
    st.markdown('**Implementado:** mão inicial com Pokémon Básico, 20 cartas, banco de 3, compra, energia de tipo único, evolução, Doce Raro, recuo, ataques de dano fixo, fraqueza, nocaute, pontuação, IA básica e replay por semente.')
    st.markdown('**Efeitos adicionais codificados:** Pesquisa de Professores, Poké Bola, descarte aleatório do Mega Swampert ex, cura própria de 30 pontos e bônus de 30 por moeda, reconhecidos apenas pelo texto exato.')
    st.warning('Ainda não modelados: habilidades, condições especiais, ferramentas, estádios, zona de energia multicolorida, modificadores complexos, decisões ótimas e resoluções simultâneas. A partida de depuração não reproduz necessariamente todas as regras oficiais.')
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

with info_tab:
    st.markdown('**Fonte:** [PocketDecks v5](https://github.com/PocketDecks/pokemon-tcg-pocket-cards) — comunitária, não oficial; baseada em dados do Limitless.')
    st.markdown('**Versões da base:** `core` contém cartas distintas jogáveis (sem todas as variantes de arte); `gameplay` acrescenta dados de ataques, habilidades e treinadores. [Documentação de esquema](https://github.com/PocketDecks/pokemon-tcg-pocket-cards/blob/main/docs/payloads.md).')
    st.markdown('**Limitação central:** a leitura de texto de carta não executa automaticamente sua habilidade. Apenas handlers explicitamente auditados entram na simulação.')
    st.markdown('**Licença da base:** AGPL-3.0-or-later. Consulte a licença e os avisos de terceiros no repositório do PocketDecks antes de redistribuir os dados.')
    st.caption('URL do catálogo core:')
    st.code(URL)
    st.caption('URL do catálogo de batalha:')
    st.code(GAMEPLAY_URL)

