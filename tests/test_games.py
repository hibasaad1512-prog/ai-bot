from app.database.db import Database
from app.games.engine import GameEngine
from app.games.points import Points

def test_game_awards_points(tmp_path):
    db=Database('sqlite:///'+str(tmp_path/'x.db')); e=GameEngine(Points(db)); g=e.start(1,'guess',1); assert e.join(1,9); winner=e.finish(1); assert winner==9
