"""TCG Pocket Lab v0.5: mobile card grid, deck workspace, local session deck slots."""
import json
from collections import defaultdict
import streamlit as st
from catalog_online import fetch_catalog, validate_selection, URL
from deckbuilder import make_experiment

META = ['Mega Altaria / Greninja', 'Mega Charizard Y / Entei', 'Suicune / Baxcalibur', 'Magnezone / Miraidon', 'Hoopa / Mega Absol']
ENERGIES = ['water', 'fire', 'grass', 'lightning', 'psychic', 'fighting', 'darkness', 'metal', 'dragon', 'colorless']
st.set_page_config(page_title='TCG Pocket Lab', page_icon='🃏', layout='wide')
st.markdown('''<style>
.block-container {padding-top: 1rem; padding-bottom: 3rem; max-width: 1050px}
[data-testid="stImage"] img {border-radius: 9px}
@media(max-width: 700px) {
 .block-container {padding-left: .65rem; padding-right: .65rem}
 h1 {font-size: 1.65rem !important}
 [data-testid="stVerticalBlockBorderWrapper"] {padding: 0 !important}
 div[data-testid="stButton"] button {min-height: 2.25rem; padding: .2rem .35rem}
}
</style>''', unsafe_allow_html=True)
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
    return {'format':'tcgp-lab-v0.5','name':st.session_state.deck_name,'energy_types':list(st.session_state.energy),'cards':dict(st.session_state.counts)}

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
st.caption(f'v0.5 · {len(cards):,} registros · catálogo comunitário · simulações indisponíveis'.replace(',', '.'))
st.progress(min(total()/20,1),text=f'🧩 Meu deck: {total()}/20 cartas')
catalog_tab, deck_tab, lab_tab, info_tab = st.tabs(['🔎 Cartas','🧩 Meu deck','⚔️ Meta','ℹ️ Sobre'])

with catalog_tab:
    query=st.text_input('Buscar carta',placeholder='Nome do Pokémon ou treinador')
    c1,c2=st.columns(2)
    sets=sorted({c['set'] for c in cards if c['set']})
    types=sorted({c['type'] for c in cards if c['type']})
    chosen_set=c1.selectbox('Expansão',['Todas']+sets)
    chosen_type=c2.selectbox('Categoria',['Todas']+types)
    filtered=[c for c in cards if query.casefold() in c['name'].casefold() and (chosen_set=='Todas' or c['set']==chosen_set) and (chosen_type=='Todas' or c['type']==chosen_type)]
    per_page=24
    pages=max(1,(len(filtered)+per_page-1)//per_page)
    # Clamp when a previous search had more pages.
    page=st.number_input('Página',min_value=1,max_value=pages,value=min(st.session_state.page,pages),key='page_input')
    st.session_state.page=page
    st.caption(f'{len(filtered)} resultados · página {page} de {pages}')
    visible=filtered[(page-1)*per_page:page*per_page]
    for i in range(0,len(visible),2):
        columns=st.columns(2,gap='small')
        for col,card in zip(columns,visible[i:i+2]):
            with col:
                with st.container(border=True):
                    if card['image']: st.image(card['image'],use_container_width=True)
                    else: st.caption('🃏 Imagem indisponível')
                    st.markdown(f"**{card['name']}**")
                    st.caption(f"{card['set']} · #{card['number']} · {card['type']}")
                    current=st.session_state.counts.get(card['id'],0)
                    minus,plus=st.columns(2,gap='small')
                    minus.button('−',key=f"card_minus_{card['id']}",disabled=current==0,on_click=remove,args=(card['id'],),use_container_width=True)
                    plus.button(f'+ ({current})',key=f"card_plus_{card['id']}",disabled=not can_add(card),on_click=add,args=(card['id'],),use_container_width=True)

with deck_tab:
    st.text_input('Nome do deck',key='deck_name')
    st.multiselect('Energias (até 3)',ENERGIES,key='energy',max_selections=3)
    selected=list(st.session_state.counts.items())
    if not selected: st.info('Seu deck está vazio. Vá à aba Cartas para adicionar Pokémon e treinadores.')
    for i in range(0,len(selected),2):
        cols=st.columns(2,gap='small')
        for col,(cid,n) in zip(cols,selected[i:i+2]):
            c=by_id.get(cid)
            with col:
                with st.container(border=True):
                    if c and c['image']: st.image(c['image'],use_container_width=True)
                    st.markdown(f"**{n}× {c['name'] if c else cid}**")
                    if c: st.caption(f"{c['set']} · #{c['number']}")
                    minus,plus=st.columns(2)
                    minus.button('−',key='deck_minus_'+cid,on_click=remove,args=(cid,),use_container_width=True)
                    plus.button('+',key='deck_plus_'+cid,disabled=not c or not can_add(c),on_click=add,args=(cid,),use_container_width=True)
    issues=validate_selection(st.session_state.counts,cards)
    if not st.session_state.energy: issues.append('Selecione ao menos um tipo de energia.')
    if issues: st.warning(' | '.join(issues))
    else: st.success('Passou nas verificações estruturais disponíveis; legalidade completa ainda não confirmada.')
    st.download_button('⬇️ Exportar deck JSON',json.dumps(payload(),ensure_ascii=False,indent=2),file_name='meu_deck.json',mime='application/json',use_container_width=True)
    uploaded=st.file_uploader('Importar deck JSON (v0.4 ou v0.5)',type=['json'])
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
