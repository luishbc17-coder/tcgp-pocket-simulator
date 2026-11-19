# Protocolo de avaliação A/B — v0.9.12

**Objetivo:** comprovar ou refutar desempenho competitivo da nova política dentro do motor parcial, sem confundir progresso técnico com taxa de vitórias.

1. Para cada baralho `Mega Altaria ex / Greninja` e `Hoopa ex / Mega Absol ex`, comparar `planning` (v0.9.12) com `planning_v0911` e com `planning_v099`.
2. Development: **100 partidas** por confronto, semente **20261116** (pode ser reutilizada somente para diagnóstico, pois é conhecida).
3. Holdout *novo*: **100 partidas** por confronto, semente **77531041**, usando `benchmark_split='holdout'`. **Não usar essas partidas para ajustar parâmetros** da própria v0.9.12; caso ajustes sejam feitos, reservar um conjunto diferente para avaliação final.
4. Completar os oito blocos (2 decks × 2 referências × 2 splits = 800 partidas). Mais tarde adicionar novos decks **já simuláveis** com perfis de energia, controle e evolução distintos.
5. Critérios: jogos concluídos sem falhas; comparação de taxa de vitória, intervalos de 95%, uso de Mega Altaria/Darkrai, ataques, energias, recuos, Rare Candy, evolução, Water Shuriken, produtividade por ataque e detalhes de `decision_audit.sequence_summary`.
6. Os conjuntos antigos de `holdout` com semente 20261116 **já foram consultados e comparados em versões anteriores** e não são mais avaliação inteiramente independente.

**Aviso:** os resultados são confrontos espelhados de políticas heurísticas dentro do motor parcial. Não estimam taxa de vitória contra humanos nem no meta oficial.
