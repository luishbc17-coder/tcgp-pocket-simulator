# TCG Pocket Lab v0.9.12 — planejamento integrado com feixe limitado

**17/11/2026.** A política experimental `planning` agora compara sequências legais de energia, recuo e ataque, considerando o custo de sobrevivência e a resposta adversária visível. As evoluções e habilidades já suportadas recebem ordenação de prioridade, sem mudar regras.

As políticas **v0.9.11, v0.9.10, v0.9.9 e v0.9.8** continuam disponíveis no Laboratório de decisões. O catálogo contém **46 decks**, incluindo cinco novos exemplos bloqueados até homologação dos efeitos; os exemplos têm amostras pequenas e não demonstram força competitiva.

Arquivos desta versão: [`CHANGELOG_V0912.md`](CHANGELOG_V0912.md), [`FONTES_DECKS_V0912.md`](FONTES_DECKS_V0912.md), [`PLANO_TESTES_V0912.md`](PLANO_TESTES_V0912.md) e [`INSTALAR_V0912.txt`](INSTALAR_V0912.txt).

**Validação local:** 298 testes e 9 subtestes aprovados em 17/11/2026.

**Limitação:** testes unitários e duelos sintéticos confirmam funcionamento, não superioridade da IA. Benchmark de partidas com os dois baralhos reais ainda precisa ser executado.

---

# TCG Pocket Lab v0.9.11 — proteção de desempenho e energia com valor futuro

**17/11/2026.** Nova política experimental `planning` com avaliação probabilística
limitada da possibilidade de comprar evoluções da **própria lista inicial**,
valor residual de energia e preservação da política v0.9.9 quando o deck não
possui Pokémon evolutivos. As políticas anteriores permanecem selecionáveis.

O catálogo agora contém **41 decks**, incluindo cinco novos arquétipos
**não liberados para simulação** até auditoria de seus efeitos. Nenhuma
habilidade ou mecânica nova foi incluída no motor. Veja
[`CHANGELOG_V0911.md`](CHANGELOG_V0911.md),
[`FONTES_DECKS_V0911.md`](FONTES_DECKS_V0911.md) e
[`INSTALAR_V0911.txt`](INSTALAR_V0911.txt).

**Validação:** 290 testes e 9 subtestes aprovados localmente. Resultados dos
confrontos reais development/holdout ainda são necessários para determinar
se há melhoria; duelos sintéticos não demonstram força competitiva.

---

# TCG Pocket Lab v0.9.10 — preparação, evolução e auditoria inequívoca

**17/11/2026.** Planejadora experimental `planning` atualizada para `PlanningAgentV0910`,
com suporte na projeção a *Rare Candy já na mão*, evolução futura legal conhecida,
valor estratégico conservador das habilidades já implementadas (Water Shuriken,
Volt Charge, Ice Maker e Roar in Unison), progresso de energia rumo a ataques
alcançáveis e **identificador único para cada escolha de energia ou recuo**.

As políticas `planning_v099` e `planning_v098` continuam disponíveis para
confronto espelhado com as mesmas sementes. O motor de regras e o catálogo de
efeitos **não foram ampliados**. O projeto agora contém **36 decks** no catálogo:
os cinco novos estão **bloqueados para simulações**, com fontes e 20 cartas
individualmente especificadas. Ver `CHANGELOG_V0910.md`, `FONTES_DECKS_V0910.md`
e `INSTALAR_V0910.txt`.

**Limitação importante:** o planejamento é heurístico, não roda uma árvore
completa de estados e não usa a mão/deck ocultos do adversário. Os testes de
regressão automatizados não demonstram ganho de taxa de vitórias no meta real.

---

# TCG Pocket Lab v0.9.9 — planejamento, auditoria e Glaceon ex

**17/11/2026.** Nova IA `planning` com projeção mais consistente de ataques, anexos, evoluções e custo de recuo, comparações heurísticas de alternativas e benchmarking A/B com `planning_v098` disponível como referência. **31 decks** no catálogo, dos quais os cinco novos — incluindo **Glaceon ex / Vaporeon** — estão marcados para consulta/importação, mas **bloqueados para partidas** enquanto os respectivos efeitos não forem auditados. Nenhum novo handler de carta foi incluído.

Consulte [`CHANGELOG_V099.md`](CHANGELOG_V099.md), [`FONTES_DECKS_V099.md`](FONTES_DECKS_V099.md) e [`INSTALAR_V099.txt`](INSTALAR_V099.txt). Verificação local: **273 testes e 9 subtestes aprovados**. A força competitiva da nova IA **ainda não foi demonstrada**; a próxima etapa é repetir os testes reais development/holdout da v0.9.8.

---

# TCG Pocket Lab v0.9.4 — matriz de confrontos

Nova aba **🏆 Matriz** com 21 pares dos sete decks cadastrados, ranking técnico, análise de jogador inicial, cartões responsivos e relatório JSON/CSV. A interface permite 20, 40 ou 100 partidas por par com equilíbrio exato de primeiro jogador e posição. Os resultados são **experimentais** e não representam probabilidades do metagame real.

Consulte [`CHANGELOG_V094.md`](CHANGELOG_V094.md) e [`INSTALAR_V094.txt`](INSTALAR_V094.txt). Os modos existentes de catálogo, Meu deck, Arena, replay e comparador A/B foram preservados. Testes: **240 aprovados + 9 subtestes**, além de **2.625 partidas sintéticas** em duas políticas sem falhas internas. A renderização real do Streamlit Cloud ainda deve ser conferida após a publicação.

---

# TCG Pocket Lab v0.9.3.4

Correção da navegação móvel e da Arena; ver `INSTALAR_V0933.txt` e `CHANGELOG_V0933.md`.

# TCG Pocket Lab v0.9.3.2 — correção de efeitos (19/21 do diagnóstico)

Veja `CHANGELOG_V0932.md` e `INSTALAR_V0932.txt`. Os efeitos pendentes de Wally e Professor Turo seguem bloqueados; o motor continua experimental.

# TCG Pocket Lab v0.9.3 — série técnica contra o meta

Novidade: **Meu deck × Todo o meta** na Arena. O programa diagnostica cada um dos 7 arquétipos cadastrados e executa duelos **somente** com listas totalmente reconhecidas; adversários bloqueados aparecem com motivo e **sem taxa de vitória inventada**. Há relatório JSON por confronto, sementes reproduzíveis e duas políticas de IA.

Novos efeitos/handlers: Legendary Pulse, Ice Maker, Volt Charge, Ignition, Crystal Waltz, Blazing Beatdown, Crimson Dive, Diving Icicles, Serena's Choice, Eviolite, Giant Cape e Inflatable Boat. O motor ainda é parcial: nem todo deck da biblioteca está simulável.

Para atualizar: `INSTALAR_V093.txt`. Para histórico detalhado: `CHANGELOG_V093.md`. Testes locais: **194 testes + 9 subtestes aprovados**; dois lotes com 1.000 partidas técnicas cada, sem erro interno. **Não são probabilidades competitivas validadas.**

---

# TCG Pocket Lab v0.9.2 — laboratório beta

Sete listas de 20 cartas disponíveis na biblioteca, com cinco arquétipos novos;
compatibilidade de cartas sob demanda no catálogo, Arena com preview e cabeçalho
mobile mais compacto. Duas IAs e motor de jogo técnico mantidos **sem alteração**.

Veja `CHANGELOG_V092.md` e `INSTALAR_V092.txt` para novidades e atualização.

---

# TCG Pocket Lab — v0.9.0

**Versão experimental.** Construtor de decks Pokémon TCG Pocket com catálogo comunitário, inspeção conservadora de efeitos e um motor parcial de partidas auditadas.

A v0.9 inicia a transição para a v1.0: políticas de decisão comparáveis, telemetria de partidas e uma identidade visual mais consistente. **Não apresenta probabilidades competitivas confiáveis.**

## Novidades v0.9

- **IA clássica / IA tática:** selecione a heurística antiga da v0.8.4 ou a nova política v0.9 nos testes.
- A IA tática considera **ataques de evoluções futuras compatíveis com a Energy Zone**, protege recursos e tenta escolher melhor alvos, recuos e apoiadores.
- **A/B diagnóstico:** um botão executa 100 partidas sob cada política, com decks/seed iguais, e compara contagens. Isso **não é um teste causal de força da IA**, porque as ações mudam a trajetória aleatória dos duelos.
- **Telemetria:** ataques por nome, habilidades (Water Shuriken, Nightmare Aura), ferramentas, energia anexada, evolução, Doce Raro, recuo, nocautes, turnos sem ataques e distribuição de duração.
- **Interface:** novo cabeçalho, organização da Arena e painéis de resultados mais claros para celular e desktop.

## Como publicar

Consulte [`INSTALAR_V09.txt`](INSTALAR_V09.txt). A atualização a partir da v0.8.4 altera **5 arquivos**: `battle_metrics.py` (novo), `tactical_agent.py` (novo), `battle_engine.py`, `batch_runner.py`, `web_app.py`.

O Streamlit Cloud executa `web_app.py`. Mantenha `requirements.txt` com Streamlit >= 1.67. Se houver um erro de import após o commit, confira se os dois arquivos novos foram adicionados e depois reinicie o app.

## Validação local

```bash
python -m pytest -q
```

Antes desta entrega: **162 testes aprovados + 9 subtestes**, e 4 lotes técnicos de 1.000 partidas sem falhas nas verificações internas, usando **registros transcritos** de dois decks (não o catálogo online ao vivo). O arquivo `RELATORIO_REFERENCIA_V09.json` acompanha o pacote completo como prova inspecionável de uma execução local com dados de teste.

## O que segue fora do escopo

Regras universais de todas as cartas, Energy Zone multicolorida, estados especiais além do Sono, efeitos não auditados, estratégia ótima/treinada e validação externa com replays reais. O mecanismo de segurança recusa cartas que não tenham efeito reconhecido.

Veja [`ROADMAP_V10.md`](ROADMAP_V10.md) para os critérios planejados da versão 1.0.


## v0.9.3.4 — Wally e Professor Turo

A v0.9.3.4 reconhece Wally (anexação adicional de Energia Incolor a Estágio 2) e Professor Turo (embaralhamento de um Pokémon Futuro em jogo no deck; marcador `special_tags` fornecido pelo catálogo gameplay).

No laboratório, o motor continua **experimental**, e as listas dependem dos registros de cartas carregados do PocketDecks. Consulte `CHANGELOG_V0934.md` e `INSTALAR_V0934.txt` para detalhes e instalação.

## v0.9.5 — Replay, incerteza e mais arquétipos

A Matriz permite reproduzir uma rodada pela semente, revisar log e estados do
campo, comparar IA clássica/tática sobre a mesma seleção e ver intervalos de
confiança **aproximados**. Quatro decks representativos foram adicionados à
biblioteca (total de 11). **A compatibilidade ainda depende do catálogo e
regras suportadas**; os novos não entram em rankings se estiverem pendentes.

Consulte `CHANGELOG_V095.md` e `INSTALAR_V095.txt`.

## v0.9.6 — IA experimental e biblioteca de 16 decks

Terceira política de IA (`StrategicAgent`), benchmark direto usando um baralho
espelhado para as duas políticas (`policy_duel.py`) e 5 novas listas de 20
cartas **somente no catálogo**, ainda bloqueadas para simulação. Ver
`CHANGELOG_V096.md` e `INSTALAR_V096.txt`.

## v0.9.7 — IA auditável e biblioteca de 21 decks

Cinco decks novos para importar/editar (não simuláveis até auditoria),
IA Estratégica experimental v0.9.7 com escolha de ataque por nocaute,
planejamento de energia tipada e auditoria de alternativas. Laboratório de
IA compara v0.9.7 com a Estratégica v0.9.6, a Tática e a Clássica,
separando sementes de desenvolvimento e de validação reservada.
Veja `CHANGELOG_V097.md`, `FONTES_DECKS_V097.md` e `INSTALAR_V097.txt`.

## v0.9.8 — IA Planejadora e biblioteca de 26 decks

A política `planning` (`planning_agent.py`) projeta as consequências de anexos de energia, ataques e recuos até o próximo turno próprio, com uma resposta adversária baseada em ataques já visíveis e pagáveis. Não consulta a mão ou a ordem do deck ocultos do adversário. Usa busca limitada e estimativas; **não é um mecanismo completo de busca em árvore de partidas reais**, não implementa regras novas e continua experimental.

A aba **🏆 Matriz → Laboratório de decisões** permite comparar `planning` com `strategic` (v0.9.7), `strategic_v096`, `tactical` e `baseline`, nos conjuntos **Desenvolvimento** e **Validação reservada**. O relatório v0.9.8 inclui auditoria de alternativas, replay, eficiência normalizada por política e ataques/dano nominal por Pokémon. Isso **não** mede dano efetivo atribuído a cada Pokémon nem prova força contra humanos.

O catálogo soma 26 decks: 7 previamente testados e 19 ainda pendentes de auditoria. Cinco novos decks são registrados por versão, sem adicionar ataques ou habilidades ao motor nesse ciclo. Consulte `CHANGELOG_V098.md`, `FONTES_DECKS_V098.md` e `INSTALAR_V098.txt`.
