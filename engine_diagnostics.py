"""Clearly synthetic smoke tests: proves the loop executes, not card accuracy."""
from battle_engine import Attack, Card, play_fixture_match


def _fixture_deck(prefix):
    basic = Card(prefix+'basic',prefix+' Basic (fixture)','pokemon',
                 hp=70,points=1,element='water',retreat=1,
                 attacks=(Attack('Fixture water attack',('water',),40),))
    deck=[basic,basic]
    for i in range(9):
        item=Card(prefix+str(i),f'{prefix} placeholder {i}', 'item')
        deck += [item,item]
    return deck


def run_smoke_checks(n=100,seed=20261116):
    if not 1 <= n <= 5000:
        raise ValueError('Run 1–5000 synthetic smoke matches')
    a,b=_fixture_deck('A'),_fixture_deck('B')
    errors=[]
    played=0
    for i in range(n):
        try:
            g=play_fixture_match(a,b,seed=seed+i)
            if not g.finished or g.turn>30 or g.winner not in (None,0,1):
                raise AssertionError('Invalid final game state')
            played+=1
        except (AssertionError,ValueError,IndexError) as exc:
            errors.append(f'Partida fictícia #{i}: {exc}')
    return {'attempted':n,'completed':played,'errors':errors[:10],
            'disclaimer':'Cartas fictícias. Não são resultados competitivos.'}
