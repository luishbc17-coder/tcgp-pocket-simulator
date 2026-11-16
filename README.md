# Pokémon TCG Pocket — auditable simulator prototype

This is **not** a complete game simulator. It intentionally does **not** execute 100,000 matches or report win rates until all card effects and game rules have been validated.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Implemented
- 20-card deck size, max two copies by name, Basic Pokémon requirement
- evolution chain, evolution timing, preservation of damage and energy
- one energy attachment per turn, damage, knockout and 3-point win
- first baseline agent decisions: choose evolution, choose energy recipient
- configuration for 5 × 100,000 matches, disabled until validated

## Missing
- authoritative card catalog and expansion-specific printings
- setup/guaranteed Basic opening hand and mulligan handling
- actual energy zone, first-player restrictions, attack costs and turn-ending attack
- Trainer/item/supporter effects and Rare Candy
- active/bench promotion, retreat, statuses, weakness, abilities, attack side effects
- legal action enumeration and full agent turn loop
- five fully validated opponent decklists and strategic agents
- seeded match replay, test fixtures, and simulation output

Card statistics in the engine tests are fixtures, **not** an authoritative source of card text.

## Universal deck builder (v0.2)

The simulator is **not locked to Swampert**. `catalog.json` defines card IDs and metadata, while each custom deck is a separate JSON file containing card counts and energy types. These demonstration records are deliberately marked `verified=false`; they are NOT a verified full card database.

From the project directory:

```bash
python cli.py search swampert
python cli.py validate decks/example_swampert.json
python cli.py experiment decks/example_swampert.json --opponents "Mega Altaria / Greninja" "Suicune / Baxcalibur" --games 100000
python -m unittest discover -s tests -v
```

To make your own deck, copy `decks/example_swampert.json`, replace the card IDs and quantities, and validate it with the CLI. The builder checks 20 cards, maximum two copies of a name, and at least one Basic Pokémon. **It cannot yet execute games**. Full card effects, energy rules, current legality, setup, and complete turn sequencing still require sourced implementation and tests. The `experiment` command only writes a disabled experiment plan.

## Interface web local (v0.3)

Requer Python 3.10+ e acesso à internet **somente para instalar** o Streamlit.

```bash
pip install -r requirements.txt
streamlit run web_app.py
```

Abra a URL local exibida no terminal (normalmente `http://localhost:8501`).
A interface permite pesquisar o catálogo demonstrativo, montar um deck de 20 cartas,
importar/exportar JSON e gerar um plano de 100.000 confrontos por adversário.
O botão **Executar partidas** está intencionalmente desabilitado: o motor ainda não
implementa partidas completas, e o catálogo atual não é oficial/verificado.
