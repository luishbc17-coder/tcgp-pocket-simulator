# Cinco decks da v0.9.12 — evidência pública e limites

Dados verificados em **17/11/2026**, página de amostras de decks do Pokémon TCG Pocket. As páginas exibem listas de 20 cartas montadas por agregação estatística a partir dos decks publicados, **não correspondem necessariamente à lista de um jogador específico**.

| Chave | Arquétipo | Energia do exemplo | Amostra pública | Fonte |
|---|---|---|---:|---|
| `bellibolt_pawmot` | Bellibolt ex / Pawmot | Lightning | 2 | https://www.pokemontcgpocket.app/en/deck/bellibolt-ex-b2a-pawmot-c1 |
| `mega_dragonite_suicune` | Mega Dragonite ex / Suicune ex | Water | 2 | https://www.pokemontcgpocket.app/en/deck/mega-dragonite-ex-c1-suicune-ex-a4a |
| `mega_lopunny_lopunny` | Mega Lopunny ex / Lopunny | Fighting | 3 | https://www.pokemontcgpocket.app/en/deck/mega-lopunny-ex-b1a-lopunny-c1 |
| `mega_lucario_lycanroc` | Mega Lucario ex / Lycanroc ex | Fighting | 3 | https://www.pokemontcgpocket.app/en/deck/mega-lucario-ex-b3-lycanroc-ex-c1 |
| `solgaleo_melmetal` | Solgaleo ex / Melmetal | Metal | 2 | https://www.pokemontcgpocket.app/en/deck/solgaleo-ex-a3-melmetal-c1 |

**Atenção:** A dimensão amostral é muito pequena e não comprova que esses decks sejam competitivos. A descrição das cartas e sua implementação no simulador são separadas do cadastro da lista: todos os cinco têm `release_stage='catalog_only'` e `simulation_blocked_reason` preenchido.

IDs de carta apresentados apenas como `181`, `185` ou `225` na fonte foram normalizados segundo o conjunto correspondente (A1-181, A1-185, A1-225), mantendo essa resolução documentada. A amostra de Mega Dragonite/Suicune usa um único tipo de energia no **registro do exemplo**, mas isso não valida os custos reais dos ataques no motor.

Para ver as quantidades exatas, use `get_preset(slug)['cards']`. Nenhuma habilidade nova foi implementada nesta versão.
