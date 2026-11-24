from nanjung.handlers import common


class Conn:
    def __init__(self, alive=True):
        self.alive, self.closed = alive, False

    def run(self, sql):
        if not self.alive:
            raise OSError("broken pipe")

    def close(self):
        self.closed = True


def test_shared_conn_reuses_live_and_replaces_dead(monkeypatch):
    made = []
    monkeypatch.setattr(common.db, "connect", lambda: made.append(Conn()) or made[-1])
    monkeypatch.setattr(common, "_conn", None)
    a = common.shared_conn()
    assert common.shared_conn() is a and len(made) == 1
    a.alive = False
    b = common.shared_conn()
    assert b is not a and a.closed and len(made) == 2
