# TCG Pocket Lab v0.9.12 — busca de sequências de ações

Data: 17/11/2026. **Release experimental, sem alegação de vantagem competitiva.**

## 1. Planejamento integrado

- Adicionada `PlanningAgentV0912`, disponível na interface como `planning`.
- Busca limitada por feixe (*beam search*) com até **10 alternativas intermediárias**; considera energia manual opcional, recuo legal opcional e ataques pagáveis no turno atual.
- A avaliação final incorpora ataque/dano e nocaute imediato, resposta adversária baseada nos Pokémon revelados e ataques visivelmente pagáveis (com uma resposta hipotética descontada), risco de perder atacante e um turno próprio futuro.
- Projeta descarte de energia por ataques e recuo, além de recuo/autodano em ataques já modelados; não executa transições fictícias.
- Reconsidera o plano após anexos e Supporters reais: não usa uma decisão antiga se o estado mudou.

## 2. Evoluções e habilidades já implementadas

- `TacticalAgent` oferece **hooks opcionais** exclusivos para a nova planejadora: ordem de evoluções legais conhecidas na mão e escolha de alvos da habilidade Water Shuriken. Políticas históricas seguem o mesmo fluxo e a mesma ordem anterior.
- Rare Candy não é inventado: somente é usado quando a carta e sua evolução estão na própria mão e quando a regra permite.
- A preparação do banco combina valor residual limitado de ataques/evoluções da v0.9.11 com o risco de ataques conhecidos que atingem o Banco.
- Os efeitos de ataques/habilidades que o motor não suporta **não foram implementados**.

## 3. Auditoria

- As decisões `sequence` incluem caminhos comparados, pontuação heurística, resposta visível, ataque futuro e indicador de sobrevivência ao pior cenário projetado (não é probabilidade).
- Eventos `sequence_preparation` detalham evoluções e habilidades executadas.
- `decision_audit.sequence_summary` consolida frequências registradas dentro do limite de 50 notas por agente por partida; não substitui a telemetria de ações reais.
- Continua proibido consultar mão/deck ocultos do oponente; a única leitura do próprio deck pelo avaliador probabilístico é seu comprimento, além da receita inicial conhecida.

## 4. Referências preservadas

`planning_v0911`, `planning_v0910`, `planning_v099`, `planning_v098` e políticas estratégica/tática/clássica permanecem disponíveis. O guardrail para baralhos **apenas com Básicos** continua delegando à v0.9.9, não específico de Hoopa.

## 5. Catálogo

Mais cinco decks **somente cadastrais**, totalizando **46**. Veja `FONTES_DECKS_V0912.md`. Por terem apenas 2–3 amostras públicas e cartas pendentes de homologação, os cinco continuam bloqueados para simulações.

## 6. Validação e limitações

- Rodar `PYTHONPATH=. python -m pytest -q --disable-warnings`.
- O planejador não executa um segundo turno completo do motor, não projeta todas as mecânicas de efeito nem aprende com dados históricos. Os valores são **heurísticos**, não probabilidades calibradas de vitória.
- Comparações com seus próprios decks aprovados ainda são necessárias. Os antigos conjuntos chamados holdout foram consultados no processo de desenvolvimento e não devem continuar sendo tratados como amostra inédita de validação.
- Nenhuma publicação no GitHub/Streamlit é realizada pelo ZIP.
