"""Observed transitions, not authoritative actor attribution."""
import threading
import time
from collections import deque


class Observer:
    fields = ('power', 'flap', 'setpoint', 'fanstep', 'mode', 'comm_stat', 'current_temperature')

    def __init__(self):
        self.lock = threading.RLock()
        self.last = {}
        self.changed_at = {}
        self.pending = {}
        self.events = deque(maxlen=500)
        self.serial = 0

    def expect(self, field, value):
        with self.lock:
            self.pending[field] = (str(value), time.monotonic() + 45)

    def sample(self, state):
        with self.lock:
            now = time.monotonic()
            for field in self.fields:
                if field not in state:
                    continue
                value = state[field]
                if field in self.last and str(value) != str(self.last[field]):
                    expected, until = self.pending.get(field, (None, 0))
                    source = ('telemetry' if field in ('current_temperature', 'comm_stat') else
                              'local_correlated' if str(value) == expected and now <= until else 'suspected_external')
                    self.serial += 1
                    self.events.append(dict(seq=self.serial, field=field, before=self.last[field], after=value,
                                            source=source, timestamp=time.time()))
                    self.changed_at[field] = now
                    if source == 'local_correlated':
                        self.pending.pop(field, None)
                self.changed_at.setdefault(field, now)
                self.last[field] = value
        return state

    def since(self, cursor=0, field='*', source='*'):
        with self.lock:
            return [dict(e) for e in self.events if e['seq'] > cursor and (field == '*' or e['field'] == field)
                    and (source == '*' or e['source'] == source)]

    def stable(self, field):
        with self.lock:
            return max(0, time.monotonic() - self.changed_at.get(field, time.monotonic()))
