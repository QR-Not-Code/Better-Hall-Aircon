"""Run aircon_cycle.py without starting the desktop application."""
import datetime as dt
import math
from pathlib import Path
import runpy
import sys
import threading


# Resolve both project imports and the cycle script independently of the cwd.
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIRECTORY.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from studio.device import Device
from studio.integrations import Integrations
from studio.storage import Store, StudioError


class Context:
    """The standalone ctx interface, using the desktop app's saved settings."""

    def __init__(self, store=None):
        self.store = Store() if store is None else store
        self.device = Device(self.store)
        self.integrations = Integrations(self.store)
        self.cancel = threading.Event()

    def _check_running(self):
        if self.cancel.is_set():
            raise KeyboardInterrupt

    def control(self, field, value):
        """Apply a verified control value and return the confirmed state."""
        self._check_running()
        return self.device.control(field, value, cancel=self.cancel)

    def refresh(self):
        """Query and verify the configured room's current state."""
        self._check_running()
        return self.device.status()

    def wait(self, seconds):
        """Wait for 0-86400 seconds, interruptibly, without a script deadline."""
        self._check_running()
        seconds = float(seconds)
        if not math.isfinite(seconds) or not 0 <= seconds <= 86400:
            raise StudioError('Wait duration must be between 0 and 86400 seconds.')
        self.log(f'Waiting {seconds:g} seconds.')
        if self.cancel.wait(seconds):
            raise KeyboardInterrupt

    def log(self, value):
        """Print a timestamped message to the terminal."""
        self._check_running()
        timestamp = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        print(f'[{timestamp}] {value}', flush=True)

    def http(self, name, path=''):
        """Read JSON from a named HTTP connection."""
        self._check_running()
        return self.integrations.http(name, path)

    def request(self, name, method='GET', body=None, path=''):
        """Call a named HTTP connection with a method and optional JSON body."""
        self._check_running()
        return self.integrations.request(name, method, body, path)

    def mqtt(self, name, path=''):
        """Read the next/retained JSON MQTT message, waiting up to 20 seconds."""
        self._check_running()
        return self.integrations.mqtt(name, path, cancel=self.cancel)

    def calendar(self, name, hours=24, keyword=''):
        """Read upcoming events from a named ICS calendar connection."""
        self._check_running()
        return self.integrations.calendar(name, hours, keyword)

    def now(self):
        """Return an ISO timestamp in the app's configured timezone."""
        self._check_running()
        return self.integrations.now().isoformat()

    def events(self, cursor=0, field='*', source='*'):
        """Return changes observed by this process after a sequence number."""
        self._check_running()
        return self.device.observer.since(cursor, field, source)


def main():
    ctx = None
    try:
        ctx = Context()
        ctx.log('Checking the saved account and room...')
        ctx.refresh()
        ctx.log('Connected. Starting aircon_cycle.py. Press Ctrl+C to stop.')
        runpy.run_path(
            str(SCRIPT_DIRECTORY / 'aircon_cycle.py'),
            init_globals={'ctx': ctx, 'inputs': None, 'variables': {}, 'result': None},
            run_name='__user_script__',
        )
        return 0
    except KeyboardInterrupt:
        print('\nScript stopped. The aircon remains in its last state.', flush=True)
        return 130
    except (StudioError, RuntimeError, OSError, ValueError) as error:
        print(f'Script failed: {error}', file=sys.stderr, flush=True)
        return 1
    finally:
        if ctx is not None:
            ctx.cancel.set()


if __name__ == '__main__':
    raise SystemExit(main())
