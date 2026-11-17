"""Dated 20-card sample lists for THIRTY-ONE Pocket archetypes (2026-11-16).

IDs are the lowercase PocketDecks v5 IDs, NOT the display-style P-A-005.
These are community consensus samples; they are not a particular tournament winner.
Each list has 20 dated, source-checked cards. New listings are catalog-only until
all mechanics have been independently recognized by the battle engine.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy

DECKS = {
    'mega_altaria_greninja': {
        'name': 'Mega Altaria ex / Greninja',
        'energy_types': ['psychic'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/mega-altaria-ex-b1-greninja-a1',
        'source_checked': '2026-11-16',
        'sample_through': '2026-11-15',
        'description': 'Lista representativa; Greninja é usado pela habilidade Water Shuriken.',
        'release_stage': 'technical_tested',
        'cards': {
            'a1-089': 2,  # Greninja
            'b1-196': 2,  # Swablu
            'b1-109': 2,  # Chingling
            'a1-087': 2,  # Froakie
            'b1-102': 1,  # Mega Altaria ex
            'pa-005': 2,  # Poké Ball
            'pa-007': 2,  # Professor's Research
            'b1-225': 2, # Copycat
            'a3-144': 2, # Rare Candy
            'b3-148': 2, # Lucky Egg
            'a2-150': 1, # Cyrus
        },
    },
    'hoopa_mega_absol': {
        'name': 'Hoopa ex / Mega Absol ex',
        'energy_types': ['darkness'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/hoopa-ex-b4-mega-absol-ex-b1',
        'source_checked': '2026-11-16',
        'sample_through': '2026-11-14',
        'description': 'Lista representativa; Hoopa ex pressiona o banco e Mega Absol ex interrompe apoiadores.',
        'release_stage': 'technical_tested',
        'cards': {
            'b4-103': 2, # Hoopa ex
            'b1-151': 1, # Mega Absol ex
            'a2-110': 1, # Darkrai ex
            'pa-005': 2, # Poké Ball
            'a2-150': 2, # Cyrus
            'b2-145': 2, # Lucky Ice Pop
            'b4-148': 2, # Deceptive Needle
            'pa-007': 2, # Professor's Research
            'b3-147': 1, # Field Blower
            'pa-002': 1, # X Speed
            'a2b-070': 1, # Pokémon Center Lady
            'a3a-064': 1, # Repel
            'a2-155': 1, # Mars
            'b1-225': 1, # Copycat
        },
    },
    'charizard_entei': {
        'name': 'Mega Charizard Y ex / Entei ex',
        'energy_types': ['fire'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/mega-charizard-y-ex-b1a-entei-ex-a4a',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-15',
        'description': 'Lista consensual de torneios; Flame Patch e Estádio ainda requerem motor próprio.',
        'release_stage': 'catalog_only',
        'cards': {
            'a4a-010': 2, 'b2b-008': 2, 'b2b-007': 2,
            'b1a-014': 1, 'c1-018': 1, 'b1-217': 2,
            'pa-005': 2, 'pa-007': 2, 'b4-155': 1,
            'b4-153': 1, 'c1-126': 1, 'c1-127': 1,
            'a2b-070': 1, 'b1-223': 1,
        },
    },
    'suicune_baxcalibur': {
        'name': 'Suicune ex / Baxcalibur',
        'energy_types': ['water'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/suicune-ex-a4a-baxcalibur-b2a',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-11',
        'description': 'Lista consensual; aceleração de energia e ferramentas exigem suporte adicional.',
        'release_stage': 'catalog_only',
        'cards': {
            'a4a-020': 2, 'b2a-036': 2, 'b2a-034': 2, 'b2a-037': 1,
            'a3-144': 2, 'pa-005': 2, 'pa-007': 2,
            'a4a-067': 1, 'c1-127': 1, 'a2-155': 1,
            'c1-123': 1, 'b1-225': 1, 'a2b-070': 1, 'a2-147': 1,
        },
    },
    'magnezone_miraidon': {
        'name': 'Magnezone / Miraidon ex',
        'energy_types': ['lightning'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/magnezone-b1a-miraidon-ex-b3a',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-14',
        'description': 'Lista consensual; Magneton usa Volt Charge. Códigos 098/225 do site são A1-098/A1-225.',
        'release_stage': 'catalog_only',
        'cards': {
            'a1-098': 2, 'b1a-024': 2, 'b1a-026': 2,
            'a3-066': 2, 'b3a-019': 1, 'pa-005': 2, 'pa-007': 2,
            'b1-226': 1, 'a2-150': 1, 'b1a-068': 1,
            'b3a-073': 1, 'c1-127': 1, 'b1-225': 1, 'a2-147': 1,
        },
    },
    'altaria_espeon': {
        'name': 'Mega Altaria ex / Espeon',
        'energy_types': ['psychic'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/mega-altaria-ex-b1-espeon-b3a',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-14',
        'description': 'Construção alternativa de Altaria; contém Estádio, ferramenta e Sabrina.',
        'release_stage': 'catalog_only',
        'cards': {
            'b1-184': 2, 'b2b-040': 2, 'b3a-020': 2,
            'b1-196': 2, 'b1-102': 1, 'a4a-059': 1,
            'pa-007': 2, 'b1-225': 2, 'pa-005': 2,
            'a1-225': 1, 'b2-153': 1, 'b3b-064': 1, 'b3-147': 1,
        },
    },
    'umbreon_hydreigon': {
        'name': 'Umbreon / Hydreigon',
        'energy_types': ['darkness'],
        'source': 'https://www.pokemontcgpocket.app/en/deck/umbreon-c1-hydreigon-b1',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-15',
        'description': 'Lista consensual; habilidades e ataques de Hydreigon/Umbreon aguardam revisão.',
        'release_stage': 'catalog_only',
        'cards': {
            'b1-155': 2, 'b1-157': 2, 'c1-084': 2,
            'b1-184': 2, 'a3-144': 2, 'pa-007': 2,
            'b1-225': 2, 'b4-148': 2, 'a2-150': 1,
            'pa-005': 1, 'c1-127': 1, 'pa-002': 1,
        },
    },
    # Four representative 20-card lists from the Nov 8, 2026 tournament snapshot.
    # The references provide card numbers and quantities; the actual remote
    # gameplay catalog still decides whether a deck is eligible for simulation.
    'mega_manectric_heliolisk': {
        'name': 'Mega Manectric ex / Heliolisk',
        'energy_types': ['lightning'],
        'source': 'https://pocket.pokemongohub.net/en/decks/meta/mega-manectric-ex-heliolisk',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-08',
        'description': 'Lista representativa de torneio; Clemont e acessórios exigem auditoria antes do duelo.',
        'release_stage': 'catalog_only',
        'cards': {
            'b1a-028':2, 'b4-061':2, 'b2b-026':1, 'b2b-027':2,
            'b1a-068':2, 'pa-007':2, 'b1-225':1, 'a2-150':1,
            'a1-225':1, 'pa-005':2, 'b1a-066':2,
            'b3b-065':1, 'b2-153':1,
        },
    },
    'mega_lucario_lucario': {
        'name': 'Mega Lucario ex / Lucario',
        'energy_types': ['fighting'],
        'source': 'https://pocket.pokemongohub.net/en/decks/meta/mega-lucario-ex-lucario',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-08',
        'description': 'Lista representativa de torneio; efeitos de Korrina e do estádio exigem auditoria.',
        'release_stage': 'catalog_only',
        'cards': {
            'b3-079':2, 'b3-081':2, 'a2-092':1, 'a1-154':1,
            'b3-078':1, 'pa-007':2, 'b1-225':2, 'a2-150':1,
            'a2b-070':1, 'b3-149':1, 'pa-005':2, 'pa-002':1,
            'b3-147':1, 'b2-145':1, 'b3-154':1,
        },
    },
    'giratina_dragonair': {
        'name': 'Giratina ex / Dragonair',
        'energy_types': ['grass', 'psychic'],
        'source': 'https://pocket.pokemongohub.net/en/decks/meta/giratina-ex-dragonair',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-08',
        'description': 'Lista representativa; Energy Zone multicolorida não foi validada no motor.',
        'release_stage': 'catalog_only',
        'simulation_blocked_reason': 'A combinação de energias Planta/Psíquica requer validar a geração da Energy Zone.',
        'cards': {
            'c1-098':2, 'b4-117':2, 'c1-101':2, 'b4-124':1,
            'b1-225':2, 'pa-007':2, 'a1-225':1, 'a2b-070':1,
            'c1-127':1, 'pa-005':2, 'b3-147':1,
            'c1-123':1, 'b4-155':2,
        },
    },
    'vespiquen_shuckle': {
        'name': 'Vespiquen ex / Shuckle ex',
        'energy_types': ['grass'],
        'source': 'https://pocket.pokemongohub.net/en/decks/meta/vespiquen-ex-shuckle-ex',
        'source_checked': '2026-11-16', 'sample_through': '2026-11-08',
        'description': 'Lista representativa; Leaf Cape e Fragrant Forest precisam de compatibilidade confirmada.',
        'release_stage': 'catalog_only',
        'cards': {
            'b4-010':2, 'b4-011':2, 'a4-021':2, 'b2-017':1,
            'b1-225':2, 'pa-007':2, 'a2-150':1, 'a1-225':1,
            'pa-002':2, 'b3-147':1, 'a3-147':2, 'b3-153':2,
        },
    },

    # Additional verified 20-card tournament samples (Nov 8 snapshot).
    # Library-only until mechanics can be verified; no new effect handlers.
    'greninja_ex_mega_greninja': {
        'name': 'Mega Greninja ex / Greninja ex',
        'energy_types': ['water'],
        'source': 'https://pocket.pokemongohub.net/en/decks/meta/greninja-ex-mega-greninja-ex',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Lista completa de torneio; importação disponível, duelo depende de auditoria do motor.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista cadastrada; ataques e efeitos ainda aguardam auditoria de compatibilidade.',
        'cards':{'b1-071':2,'c1-041':2,'a1-089':2,'b1-073':1,
                 'c1-042':1,'a4a-020':2,'pa-007':2,'b1-225':2,
                 'a2-150':1,'pa-005':2,'a3-144':1,'b3-147':1,'a4a-067':1},
    },
    'mega_mewtwo_x_mew': {
        'name':'Mega Mewtwo X ex / Mew ex',
        'energy_types':['psychic'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/mega-mewtwo-x-ex-mew-ex',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Lista completa de torneio; mantém suporte técnico bloqueado até auditar os efeitos.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista cadastrada; ataques e efeitos ainda aguardam auditoria de compatibilidade.',
        'cards':{'c1-057':2,'c1-056':2,'b3b-035':1,
                 'pa-007':2,'b3-149':1,'b1-225':1,'a2-150':1,
                 'a1-225':1,'a2-155':1,'pa-005':2,'b3-147':1,
                 'c1-123':2,'b2-155':2,'b3-154':1},
    },
    'hydreigon_mega_absol': {
        'name':'Hydreigon / Mega Absol ex',
        'energy_types':['darkness'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/hydreigon-mega-absol-ex',
        'source_checked':'2026-11-16','sample_through':'2026-10-27',
        'description':'Lista de torneio da janela de outubro; ainda não auditada na Arena.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista cadastrada; ataques e efeitos ainda aguardam auditoria de compatibilidade.',
        'cards':{'b1-155':2,'b1-157':2,'b3-115':1,'b1-151':1,
                 'pa-007':2,'b1-225':2,'a2-150':1,'a1-225':1,
                 'pa-005':2,'a3-144':2,'b2-145':2,'b4-148':2},
    },
    'mega_greninja_suicune': {
        'name':'Mega Greninja ex / Suicune ex',
        'energy_types':['water'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/mega-greninja-ex-suicune-ex',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Lista completa de torneio; nova evolução e ferramentas aguardam auditoria.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista cadastrada; ataques e efeitos ainda aguardam auditoria de compatibilidade.',
        'cards':{'c1-040':2,'c1-041':2,'a1-089':2,'c1-042':1,
                 'a4a-020':2,'pa-007':2,'b1-223':1,'b1-225':1,
                 'a2-150':1,'pa-005':2,'a3-144':1,'a4a-067':1,
                 'a2-147':1,'b4-154':1},
    },
    'mega_sceptile_greninja': {
        'name':'Mega Sceptile ex / Greninja',
        'energy_types':['grass'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/mega-sceptile-ex-greninja',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Lista completa de torneio; Water Shuriken não requer Água, mas outras mecânicas aguardam auditoria.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista cadastrada; ataques e efeitos ainda aguardam auditoria de compatibilidade.',
        'cards':{'b3-005':2,'b3-006':1,'b3-008':2,
                 'a1-087':1,'a1-089':1,'a3a-007':1,'b3b-061':1,
                 'c1-127':2,'pa-007':2,'b1-225':1,'a2-150':1,
                 'pa-005':2,'a3-144':2,'b3b-064':1},
    },
    # v0.9.7: five sourced, exact 20-card sample lists, library-only.
    # IDs checked against PocketDecks v5 gameplay records on 2026-11-16.
    'dragonair_mega_rayquaza': {
        'name':'Dragonair / Mega Rayquaza ex',
        'energy_types':['fire','lightning'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/dragonair-mega-rayquaza-ex',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Dragão multicolorido; lista de torneio completa e identificada, sem efeitos novos.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Energy Zone multicolorida e novos efeitos ainda não foram auditados.',
        'cards':{'b2b-051':2,'b4-117':2,'b3a-054':2,'b4-120':1,
                 'pa-007':2,'b1-225':2,'a2b-070':1,'b3a-072':1,
                 'a1-225':1,'pa-005':2,'b3a-069':1,'b3b-064':1,'b4-155':2},
    },
    'dedenne_indeedee': {
        'name':'Dedenne ex / Indeedee ex',
        'energy_types':['lightning','psychic','grass'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/dedenne-ex-indeedee-ex',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Lista representativa com três tipos de energia; cadastrada apenas para edição.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Energy Zone multicolorida e novos efeitos ainda não foram auditados.',
        'cards':{'b3b-024':2,'b1-121':2,'a3-066':2,'b2-017':1,
                 'b1-225':2,'pa-007':2,'a2-150':1,'pa-005':2,
                 'a2-147':2,'b3b-064':2,'a3b-067':1,'b2-147':1},
    },
    'butterfree_mega_sceptile': {
        'name':'Butterfree / Mega Sceptile ex',
        'energy_types':['grass'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/butterfree-mega-sceptile-ex',
        'source_checked':'2026-11-16','sample_through':'2026-10-27',
        'description':'Lista representativa da janela de outubro; sem nova habilidade implementada.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista de 20 cartas registrada; efeitos e habilidades ainda exigem auditoria.',
        'cards':{'b3b-001':2,'b3b-002':2,'b3b-003':2,'b3-005':1,
                 'b3-006':1,'b3-008':1,'pa-007':2,'a1-219':1,
                 'b1-225':1,'a1-225':1,'a2-150':1,'b1a-067':2,
                 'a3-147':1,'b3-153':2},
    },
    'pikachu_pawmot': {
        'name':'Pikachu ex / Pawmot',
        'energy_types':['lightning'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/pikachu-ex-pawmot',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Lista representativa elétrica; importação disponível, jogo ainda bloqueado.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista de 20 cartas registrada; efeitos e habilidades ainda exigem auditoria.',
        'cards':{'c1-048':2,'c1-050':2,'c1-043':2,'c1-047':1,
                 'pa-007':2,'b1-225':2,'a2-150':1,'c1-127':1,
                 'pa-005':2,'a3-144':2,'a3a-064':1,'c1-124':2},
    },
    'umbreon_mega_absol': {
        'name':'Umbreon / Mega Absol ex',
        'energy_types':['darkness'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/mega-absol-ex-umbreon',
        'source_checked':'2026-11-16','sample_through':'2026-11-08',
        'description':'Nova variante Noturna com Umbreon, Absol e Mega Sableye.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Lista de 20 cartas registrada; efeitos e habilidades ainda exigem auditoria.',
        'cards':{'b1-184':2,'c1-084':2,'b1-151':2,'b3b-041':1,
                 'b1-225':2,'pa-007':2,'a2-154':1,'a1-225':1,
                 'a2-150':1,'pa-005':2,'pa-002':2,'b4-148':2},
    },
    # v0.9.8: five source-backed, 20-card lists; catalog-only, no engine effects.
    'umbreon_mega_sableye': {
        'name':'Umbreon / Mega Sableye ex', 'energy_types':['darkness'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/umbreon-mega-sableye-ex',
        'source_checked':'2026-11-17','sample_through':'2026-11-08',
        'description':'Lista completa de torneio com Umbreon, Mega Sableye e Mega Absol.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Pendências de ataques e efeitos ainda não auditadas.',
        'cards':{'b1-184':2,'c1-084':2,'b1-151':1,'b3b-041':1,'b3-115':1,
                 'pa-007':2,'b1-225':2,'a1-225':1,'a2b-070':1,'b1-223':1,
                 'pa-005':2,'b2-145':2,'b4-148':2},
    },
    'raikou_pawmot': {
        'name':'Raikou ex / Pawmot', 'energy_types':['lightning'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/raikou-ex-pawmot',
        'source_checked':'2026-11-17','sample_through':'2026-11-08',
        'description':'Lista completa de torneio de Raikou ex e Pawmot.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Pendências de ataques e efeitos ainda não auditadas.',
        'cards':{'c1-048':2,'c1-050':2,'a4a-025':2,'c1-043':1,'pa-007':2,
                 'a2-150':1,'c1-127':1,'b1-225':1,'a3-144':2,'pa-005':2,
                 'b3-147':1,'c1-123':2,'c1-124':1},
    },
    'mega_blaziken_greninja': {
        'name':'Mega Blaziken ex / Greninja', 'energy_types':['fire'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/mega-blaziken-ex-greninja',
        'source_checked':'2026-11-17','sample_through':'2026-10-27',
        'description':'Lista completa de torneio; Greninja auxilia com Water Shuriken.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Pendências de ataques e efeitos ainda não auditadas.',
        'cards':{'b1-033':2,'b1-034':1,'b1-036':2,'a1-087':1,'a1-089':1,
                 'b1-044':1,'b3-024':1,'pa-007':2,'b1-225':2,'a2-150':1,
                 'pa-005':2,'a3-144':2,'b1-217':1,'b2b-069':1},
    },
    'hydreigon_mega_sableye': {
        'name':'Hydreigon / Mega Sableye ex', 'energy_types':['darkness'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/hydreigon-mega-sableye-ex',
        'source_checked':'2026-11-17','sample_through':'2026-09-29',
        'description':'Lista completa histórica de torneio com dois atacantes de Trevas.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Pendências de ataques e efeitos ainda não auditadas.',
        'cards':{'b1-155':2,'b1-157':2,'b1-151':1,'b3b-041':1,'b3-115':1,
                 'pa-007':2,'b1-225':2,'a2-150':1,'pa-005':2,'a3-144':2,
                 'a3a-064':1,'b2-145':1,'b3-147':1,'b4-148':1},
    },
    'hoopa_greninja': {
        'name':'Hoopa ex / Greninja', 'energy_types':['darkness'],
        'source':'https://pocket.pokemongohub.net/en/decks/meta/hoopa-ex-greninja',
        'source_checked':'2026-11-17','sample_through':'2026-09-07',
        'description':'Lista histórica completa; Greninja oferece dano pelo banco.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Pendências de ataques e efeitos ainda não auditadas.',
        'cards':{'a1-087':2,'a1-089':2,'b4-103':2,'b3b-041':1,'pa-007':2,
                 'b1-225':2,'a2-150':1,'pa-005':2,'a3-144':2,
                 'pa-002':2,'b4-148':2},
    },


    # v0.9.9: five additional dated 20-card deck samples. Catalog-only until
    # mechanics can be audited; intentionally NO new attack/ability handlers.
    'glaceon_ex_vaporeon': {
        'name':'Glaceon ex / Vaporeon',
        'energy_types':['water'],
        'source':'https://pokebase.app/pokemon-tcg-pocket/archetype/glaceon-ex-vaporeon',
        'source_checked':'2026-11-17','sample_through':'histórico; data exata não publicada',
        'description':'Lista completa documentada de torneio (yisus777, 93º); Glaceon ex Snowy Terrain não implementada. Outra variante ficou em 4º, porém sem lista completa recuperável; não é tier competitivo atual.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Glaceon ex Snowy Terrain e demais efeitos da lista não passaram por auditoria do motor.',
        'cards':{'a3b-055':2,'a2a-022':2,'a1a-019':2,'a2-050':1,'b1a-065':1,
                 'a1-220':2,'pa-007':1,'a1-225':1,'a2-150':1,'b1-225':1,
                 'pa-005':2,'a3b-066':1,'pa-002':1,'a2-146':1,'a4a-067':1},
    },
    'mega_mewtwo_x_diancie': {
        'name':'Mega Mewtwo X ex / Mega Diancie ex',
        'energy_types':['psychic'],
        'source':'https://www.pokemontcgpocket.app/en/deck/mega-mewtwo-x-ex-c1-mega-diancie-ex-b3b',
        'source_checked':'2026-11-17','sample_through':'2026-11-12',
        'description':'Lista representativa agregada de 53 amostras de torneio; contém estádio e ferramenta não auditados.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Efeitos de ferramentas, estádio e Pokémon requerem auditoria.',
        'cards':{'b3b-031':2,'b3b-032':1,'c1-056':1,'b3b-035':1,
                 'b2-155':2,'pa-005':2,'pa-007':2,'c1-123':2,'c1-127':2,
                 'b1-225':1,'b2-145':1,'a2b-070':1,'a1-225':1,'a2-150':1},
    },
    'alolan_exeggutor_ribombee': {
        'name':'Alolan Exeggutor ex / Ribombee',
        'energy_types':['grass'],
        'source':'https://www.pokemontcgpocket.app/en/deck/alolan-exeggutor-ex-ribombee-c1',
        'source_checked':'2026-11-17','sample_through':'2026-11-06',
        'description':'Lista representativa agregada de 49 amostras de torneio; habilidades e estádio pendentes.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Ataques, Quick-Grow Extract e Fragrant Forest não auditados.',
        'cards':{'c1-015':2,'a1a-001':2,'c1-005':2,'c1-014':2,'b3-004':1,
                 'b1a-067':2,'pa-007':2,'b3-153':2,'a3-147':2,'b1-225':1,
                 'b2-145':1,'a2-150':1},
    },
    'chien_pao_baxcalibur': {
        'name':'Chien-Pao ex / Baxcalibur',
        'energy_types':['water'],
        'source':'https://www.pokemontcgpocket.app/en/deck/chien-pao-ex-baxcalibur-b2a',
        'source_checked':'2026-11-17','sample_through':'2026-11-13',
        'description':'Lista representativa agregada de 10 amostras de torneio; aceleração de energia exige validação.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Aceleração de energia e ferramentas ainda não auditadas.',
        'cards':{'b2a-036':2,'b2a-037':2,'pb-037':2,
                 'a3-144':2,'pa-005':2,'b1-225':2,'c1-127':2,
                 'c1-123':2,'b2b-069':1,'b3-147':1,'pa-007':1,'a1-220':1},
    },
    'mega_gardevoir_diancie': {
        'name':'Mega Gardevoir ex / Mega Diancie ex',
        'energy_types':['psychic'],
        'source':'https://www.pokemontcgpocket.app/en/deck/mega-gardevoir-ex-b2-mega-diancie-ex-b3b',
        'source_checked':'2026-11-17','sample_through':'2026-11-13',
        'description':'Lista representativa agregada de 10 amostras de torneio; habilidades ainda não auditadas.',
        'release_stage':'catalog_only',
        'simulation_blocked_reason':'Habilidades de Gardevoir/Diancie, estádio e apoiadores ainda não auditados.',
        'cards':{'b2-070':2,'b2-066':2,'b3b-032':1,'b2-063':1,'a3-080':1,'b2-064':1,
                 'pa-007':2,'a3-144':2,'b2-155':2,'b2-149':2,'pa-005':2,
                 'a2-150':1,'b1-225':1},
    },

}


def get_preset(slug: str) -> dict:
    if slug not in DECKS:
        raise KeyError(f'Preset não verificado: {slug}')
    d = deepcopy(DECKS[slug])
    if sum(d['cards'].values()) != 20:
        raise RuntimeError('Preset com quantidade de cartas incorreta')
    if not all(type(n) is int and 1 <= n <= 2 for n in d['cards'].values()):
        raise RuntimeError('Quantidade por carta inválida')
    return {'format': 'tcgp-lab-v0.8', **d}


def verify_presets(core_cards: list[dict]) -> dict[str, dict]:
    """Keep remote data mismatches visible; never replace a missing ID by name."""
    lookup = {card['id']:card for card in core_cards}
    out = {}
    for slug in DECKS:
        deck = get_preset(slug)
        missing = [cid for cid in deck['cards'] if cid not in lookup]
        repeated_names = Counter()
        for cid, count in deck['cards'].items():
            if cid in lookup:
                repeated_names[lookup[cid]['name'].casefold()] += count
        bad_names = {name:n for name,n in repeated_names.items() if n > 2}
        out[slug] = {
            'name': deck['name'], 'total': sum(deck['cards'].values()),
            'missing_ids': missing, 'duplicate_names': bad_names,
            'ready_to_inspect': not missing and not bad_names,
        }
    return out
