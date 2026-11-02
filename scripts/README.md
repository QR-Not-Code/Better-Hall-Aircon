# Standalone aircon scripts and the `ctx` interface

## Run the cycle without the desktop application

From the project folder, run:

```powershell
python scripts/main.py
```

If using this project's Python environment:

```powershell
.\.venv\Scripts\python.exe scripts/main.py
```

You can also open a terminal in `scripts` and run `python main.py`. The launcher
finds `aircon_cycle.py` beside itself regardless of the terminal's current folder.
Keep the project folders together: it imports the device code from `../studio`.
The project's root `main.py` starts the desktop app; `scripts/main.py` is the
standalone launcher.

Use Python 3.12 or newer on Windows, under the same Windows user that connected
the desktop application. The launcher reuses the account, room and learned values
already saved in `%LOCALAPPDATA%\HallAirconStudio`. The encrypted account file
belongs to that Windows user; no token needs to be copied into either script.
The current aircon cycle uses only the Python standard library and project code.
It does not need PySide6, the desktop app, the emulator or WireGuard to be running.

The launcher first queries the saved account to verify the room. It then executes
`aircon_cycle.py`, which chooses the lowest numeric learned temperature and the
highest learned manual fan speed. The manual order is `L`, `LM`, `M`, `MH`, `H`;
`A` is automatic and is excluded. With the currently learned values this selects
22 degrees and `H`. It repeats five minutes on and twenty-five minutes off.

Standalone execution has **no overall time or step limit**. Keep the terminal,
computer and internet connection available. Press **Ctrl+C** to stop, including
during a wait. Stopping does not issue an extra power command: the aircon stays
in its last state. Connection or script errors end the launcher with exit code 1;
Ctrl+C returns 130, and normal completion returns 0. A rejected or expired token
must be renewed using the application's connection setup before running again.

## What `ctx` is

`Context` is the class defined in `scripts/main.py`. The launcher creates one
instance named `ctx` and supplies it to `aircon_cycle.py` automatically. You do
not need to instantiate it inside that script. Its methods call the same
`Device`, `Integrations` and `Observer` implementations used by the desktop app.

The script also receives `inputs = None`, `variables = {}` and `result = None`,
matching the desktop code interface. These values exist only in this process;
the standalone launcher does not save script variables or use `result`.
`print()` writes directly to the terminal, while `ctx.log()` adds a timestamp.

For another Python program inside this project, the class can be used directly:

```python
from scripts.main import Context

ctx = Context()
state = ctx.refresh()
ctx.log(f"Power: {state['power']}, setpoint: {state.get('setpoint')}")
```

## Available functions

| Function | Behavior and return value |
| --- | --- |
| `ctx.control(field, value)` | Verify the room, apply an allowed control value and query for confirmation. Returns a device-state dictionary. Values are converted to strings by the device code. |
| `ctx.refresh()` | Query and verify the saved room. Returns its latest device-state dictionary and records observed changes. |
| `ctx.wait(seconds)` | Interruptible wait from 0 to 86400 seconds per call; accepts finite integers or decimals. Returns `None`. There is no overall standalone duration limit. |
| `ctx.log(value)` | Print a value to the terminal with the computer's local timestamp. Returns `None`. |
| `ctx.http(name, path='')` | Perform a JSON GET through a saved HTTP connection; return the whole JSON response or a selected field. |
| `ctx.request(name, method='GET', body=None, path='')` | Call a saved HTTP connection using GET, POST, PUT, PATCH, DELETE or HEAD. `body` is a JSON-compatible Python value; GET/HEAD ignore it. Returns selected JSON, or `None` for an empty response. |
| `ctx.mqtt(name, path='')` | Wait up to 20 seconds for the next or retained JSON message on a saved MQTT connection. Returns the whole message or a selected field. |
| `ctx.calendar(name, hours=24, keyword='')` | Read a saved ICS calendar, including recurring events. Returns up to 1000 dictionaries with `title` and ISO `start`. Hours are bounded to 1-720; keyword matching is case-insensitive. |
| `ctx.now()` | Return an ISO date/time string in the saved timezone, normally `Asia/Singapore`. |
| `ctx.events(cursor=0, field='*', source='*')` | Return observed changes with a sequence number greater than `cursor`, optionally filtered by field and source. This does not query the server itself. |

### Device control and state

Allowed control fields are:

| Field | Values |
| --- | --- |
| `power` | `"1"` on; `"0"` off. |
| `flap` | `"S"` swing on; `"N"` swing off. |
| `setpoint` | A temperature previously learned from an official app operation. |
| `fanstep` | A fan code previously learned from an official app operation. |
| `mode` | A mode code previously learned from an official app operation. |

Unlearned temperature, fan and mode values are rejected before sending a command.
Read learned values with `ctx.store.config().get("learned", {})`. The cycle script
reads the same settings through `Store()` so it also works in the desktop editor.

State dictionaries can include `power`, `current_temperature`, `setpoint`,
`flap`, `fanstep`, `mode`, `status`, `comm_stat`, `maintenance_mode`, `aircon_type`,
`identity_verified`, `updated` and `demo`. Optional fields may be absent. Control
results additionally include `result`, such as `"already_set"` or `"confirmed"`.
The device code checks server status; it does not measure actual fan power.

```python
ctx.control("power", "1")
ctx.wait(5 * 60)
ctx.control("power", "0")
ctx.wait(25 * 60)
```

### HTTP, MQTT and calendars

`name` refers to an existing connection saved through the desktop application's
**外部连接器** section. A path such as `sensor.temperature` or `items.0.value`
selects nested JSON data. An empty path returns the entire response.

```python
temperature = ctx.http("room_sensor", "sensor.temperature")
ctx.log(temperature)

response = ctx.request("my_api", "POST", {"enabled": True}, "")
humidity = ctx.mqtt("room_mqtt", "humidity")
upcoming = ctx.calendar("my_calendar", 24, "class")
ctx.log(ctx.now())
```

These example connection names must be replaced by names you have configured.
Optional functions require these packages in the Python environment running
`scripts/main.py`:

```powershell
python -m pip install tzdata icalendar recurring-ical-events paho-mqtt
```

`ctx.now()` needs timezone data on Windows (`tzdata`). Calendar reading additionally
needs `icalendar` and `recurring-ical-events`; MQTT needs `paho-mqtt`. Ordinary
device control and HTTP calls do not require those optional packages.

### Observed changes

Changes are observed only when this process queries or controls the device;
there is no background polling. The initial query establishes a baseline.
Up to 500 changes are retained in memory. Each change has `seq`, `field`,
`before`, `after`, `source` and a Unix `timestamp`.

```python
cursor = 0
ctx.refresh()
ctx.wait(10)
ctx.refresh()
for event in ctx.events(cursor, "power", "*"):
    ctx.log(event)
    cursor = event["seq"]
```

Sources are `local_correlated`, `suspected_external` or `telemetry`. Correlation
is an inference about observed changes, not proof of who operated the aircon.
History and sequence numbers restart when the standalone launcher restarts.

## Errors and stopping

Device and connection failures normally raise `studio.storage.StudioError`.
The standalone class calls the backend directly, whereas desktop `ctx` calls
travel through a child-process interface and can surface as `RuntimeError`.
Ctrl+C raises `KeyboardInterrupt`; do not catch and ignore it in a repeating
script if you want Ctrl+C to stop the launcher.

For code using another thread, `ctx.cancel.set()` requests cancellation. Waiting
and subsequent `ctx` calls stop with `KeyboardInterrupt`; device confirmation
and MQTT also observe that event. An already-sent network command cannot be
retracted. The desktop application's run-duration and step limits apply only
when the script is run inside the application, not through this launcher.
