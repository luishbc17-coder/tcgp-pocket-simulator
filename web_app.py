"""Mobile-first catalog and deck builder. No simulated wins until game engine validated."""
import json
from collections import Counter
import streamlit as st
from catalog_online import fetch_catalog, validate_selection, URL
from deckbuilder import make_experiment

META = ['Mega Altaria / Greninja', 'Mega Charizard Y / Entei', 'Suicune / Baxcalibur',
        'Magnezone / Miraidon', 'Hoopa / Mega Absol']
ENERGIES = ['water', 'fire', 'grass', 'lightning', 'psychic', 'fighting', 'darkness', 'metal', 'dragon', 'colorless']
st.set_page_config(page_title='TCG Pocket Lab', page_icon='🃏', layout='wide')
st.title('🃏 TCG Pocket Lab')
st.caption('v0.4 • Catálogo comunitário • Montador de decks • Simulação ainda indisponível')
if 'counts' not in st.session_state: st.session_state.counts = {}
if 'deck_name' not in st.session_state: st.session_state.deck_name = 'Meu deck'
if 'energy' not in st.session_state: st.session_state.energy = ['water']

try:
    with st.spinner('Carregando catálogo de cartas...'):
        cards = fetch_catalog()
except Exception as exc:
    st.error('Não foi possível carregar o catálogo online. Confira a conexão ou tente novamente mais tarde.')
    st.caption(f'Detalhe técnico: {exc}')
    st.stop()

by_id = {c['id']: c for c in cards}
# Keep legacy imports visible without pretending demo IDs belong to this catalog.
st.caption(f'{len(cards):,} registros disponíveis • Fonte comunitária PocketDecks'.replace(',', '.'))
st.info('Os dados são de uma comunidade independente e podem conter lacunas. Imagens dependem dos endereços disponibilizados pela fonte. Nenhum efeito de carta foi validado como regra executável.')
builder, lab, about = st.tabs(['🧩 Montar deck', '⚔️ Confrontos', 'ℹ️ Sobre'])
with builder:
    st.subheader('Encontrar cartas')
    query = st.text_input('Nome da carta', placeholder='Ex.: Swampert, Charizard...')
    a,b = st.columns(2)
    sets = sorted({c['set'] for c in cards if c['set']})
    types = sorted({c['type'] for c in cards if c['type']})
    chosen_set = a.selectbox('Expansão', ['Todas'] + sets)
    chosen_type = b.selectbox('Categoria', ['Todas'] + types)
    filtered = [c for c in cards if query.casefold() in c['name'].casefold()
                and (chosen_set == 'Todas' or c['set'] == chosen_set)
                and (chosen_type == 'Todas' or c['type'] == chosen_type)]
    st.caption(f'{len(filtered)} resultados. Mostrando até 60 por página.')
    page_count = max(1, (len(filtered)+59)//60)
    page = st.number_input('Página', 1, page_count, 1)
    page_cards = filtered[(page-1)*60:page*60]
    for c in page_cards:
        with st.container(border=True):
            img, detail, action = st.columns([1, 3, 1])
            if c['image']:
                img.image(c['image'], use_container_width=True)
            else:
                img.caption('Sem imagem')
            detail.markdown(f"**{c['name']}**")
            detail.caption(f"{c['set']} · #{c['number']} · {c['type']}" + (f" · {c['hp']} HP" if c['hp'] else ''))
            count = st.session_state.counts.get(c['id'], 0)
            name_count = sum(n for cid,n in st.session_state.counts.items() if by_id.get(cid,{}).get('name','').casefold() == c['name'].casefold())
            if action.button(f'＋ {count}', key='add-'+c['id'], disabled=sum(st.session_state.counts.values())>=20 or count>=2 or name_count>=2):
                st.session_state.counts[c['id']] = count+1
                st.rerun()
    st.divider()
    st.subheader('Meu deck')
    st.text_input('Nome do deck', key='deck_name')
    st.multiselect('Energias (até 3)', ENERGIES, key='energy', max_selections=3)
    total = sum(st.session_state.counts.values())
    st.progress(min(total/20,1), text=f'{total}/20 cartas')
    for cid,n in list(st.session_state.counts.items()):
        c = by_id.get(cid)
        left,minus,plus = st.columns([5,1,1])
        left.write(f"{n}× {c['name'] if c else cid} · {c['set'] if c else 'desconhecida'}")
        if minus.button('−',key='minus-'+cid):
            if n==1: del st.session_state.counts[cid]
            else: st.session_state.counts[cid]-=1
            st.rerun()
        name_count = sum(q for k,q in st.session_state.counts.items() if by_id.get(k,{}).get('name','').casefold()==(c['name'].casefold() if c else ''))
        if plus.button('+',key='plus-'+cid,disabled=n>=2 or name_count>=2 or total>=20):
            st.session_state.counts[cid]+=1
            st.rerun()
    issues = validate_selection(st.session_state.counts, cards)
    if not st.session_state.energy: issues.append('Escolha ao menos um tipo de energia.')
    if issues:
        st.warning(' | '.join(issues))
    else:
        st.success('Deck estruturalmente válido pelas verificações disponíveis. Legalidade completa ainda não confirmada.')
    payload = {'format':'tcgp-lab-v0.4','name':st.session_state.deck_name,'energy_types':st.session_state.energy,
               'cards':dict(st.session_state.counts)}
    st.download_button('⬇️ Exportar deck JSON',json.dumps(payload,ensure_ascii=False,indent=2),
                       file_name='meu_deck.json',mime='application/json')
    uploaded = st.file_uploader('Importar deck JSON',type=['json'])
    if uploaded is not None and st.button('Carregar deck'):
        try:
            data = json.load(uploaded)
            counts = data['cards']
            if not isinstance(counts,dict) or any(cid not in by_id or type(n) is not int or not 1<=n<=2 for cid,n in counts.items()):
                raise ValueError('Cartas não reconhecidas neste catálogo ou quantidades inválidas')
            if sum(counts.values())>20: raise ValueError('Deck com mais de 20 cartas')
            energies=data.get('energy_types',[])
            if not isinstance(energies,list) or not 1<=len(energies)<=3 or len(set(energies))!=len(energies) or any(x not in ENERGIES for x in energies):
                raise ValueError('Energias inválidas')
            st.session_state.counts=counts.copy()
            st.session_state.energy=energies
            st.session_state.deck_name=str(data.get('name','Meu deck'))
            st.rerun()
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            st.error(f'Erro ao importar: {exc}')
with lab:
    st.subheader('Laboratório de confrontos')
    st.info('Ainda não há partidas completas: esta seção exporta apenas a configuração do experimento.')
    opponents=st.multiselect('Adversários',META,default=META)
    games=st.number_input('Partidas por confronto',min_value=1,max_value=1_000_000,value=100_000,step=10_000)
    seed=st.number_input('Semente',min_value=0,value=20261116)
    st.metric('Partidas planejadas',f'{len(opponents)*int(games):,}'.replace(',','.'))
    if opponents:
        plan=make_experiment('meu_deck.json',opponents,int(games),int(seed))
        plan['player_deck']={'name':st.session_state.deck_name,'cards':dict(st.session_state.counts),'energy_types':st.session_state.energy}
        st.download_button('⬇️ Exportar experimento',json.dumps(plan,ensure_ascii=False,indent=2),file_name='experimento.json')
    st.button('▶️ Executar partidas',disabled=True,help='Aguardando motor de regras completo e validado')
with about:
    st.markdown('**Fonte do catálogo:** [PocketDecks](https://github.com/PocketDecks/pokemon-tcg-pocket-cards). Atualização em cache por uma hora. Não é fonte oficial da Pokémon Company.')
    st.markdown('**Limitações:** dados comunitários sujeitos a mudanças de esquema; tradução e imagens podem não estar disponíveis; nenhum ataque ou habilidade é executado; ainda não há simulação de partidas.')
    st.code(URL)
