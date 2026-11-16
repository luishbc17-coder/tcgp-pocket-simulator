"""TCG Pocket Lab v0.5.1: responsive grid, compact filters and deck editor."""
import json
from collections import defaultdict
import streamlit as st
from catalog_online import fetch_catalog, validate_selection, URL
from deckbuilder import make_experiment
from layout_helpers import paginate, PAGE_SIZE

META = ['Mega Altaria / Greninja', 'Mega Charizard Y / Entei', 'Suicune / Baxcalibur', 'Magnezone / Miraidon', 'Hoopa / Mega Absol']
ENERGIES = ['water', 'fire', 'grass', 'lightning', 'psychic', 'fighting', 'darkness', 'metal', 'dragon', 'colorless']
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
    return {'format':'tcgp-lab-v0.5.1','name':st.session_state.deck_name,'energy_types':list(st.session_state.energy),'cards':dict(st.session_state.counts)}

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
st.caption(f'v0.5.1 · {len(cards):,} registros · catálogo comunitário · simulações indisponíveis'.replace(',', '.'))
st.progress(min(total()/20,1),text=f'🧩 Meu deck: {total()}/20 cartas')
catalog_tab, deck_tab, lab_tab, info_tab = st.tabs(['🔎 Cartas','🧩 Meu deck','⚔️ Meta','ℹ️ Sobre'])

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
    uploaded=st.file_uploader('Importar deck JSON (v0.4, v0.5 ou v0.5.1)',type=['json'])
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
    st.subheader('Laboratório de confrontos')
    st.info('O motor de partidas completas ainda não está validado. Nenhuma taxa de vitória será calculada nesta versão.')
    opponents=st.multiselect('Adversários',META,default=META)
    games=st.number_input('Partidas por confronto',min_value=1,max_value=1_000_000,value=100_000,step=10_000)
    seed=st.number_input('Semente',min_value=0,value=20261116)
    st.metric('Partidas planejadas',f'{len(opponents)*int(games):,}'.replace(',','.'))
    if opponents:
        plan=make_experiment('meu_deck.json',opponents,int(games),int(seed))
        plan['player_deck']=payload()
        st.download_button('⬇️ Exportar plano',json.dumps(plan,ensure_ascii=False,indent=2),file_name='experimento.json')
    st.button('▶️ Simular partidas',disabled=True)
with info_tab:
    st.markdown('**Catálogo:** [PocketDecks](https://github.com/PocketDecks/pokemon-tcg-pocket-cards) (comunitário; não oficial).')
    st.markdown('**Limitações:** metadados e imagens podem estar incompletos; efeitos não são executáveis; decks de sessão não persistem após reinício; nenhuma partida completa foi simulada.')
    st.code(URL)
