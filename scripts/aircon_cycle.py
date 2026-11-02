# Run scripts/main.py, or open in 自动化脚本 -> Python 脚本 using 打开 .py 文件.
# First learn the device's lowest temperature and highest fan speed in the app.
# Standalone: runs until stopped. In the app: obeys its selected run duration.
from studio.storage import Store

learned = Store().config().get("learned", {})
temperatures = [str(v) for v in learned.get("setpoint", [])]
# Low -> medium-low -> medium -> medium-high -> high. A is automatic.
fan_order = {"L": 0, "LM": 1, "M": 2, "MH": 3, "H": 4}
fan_speeds = [str(v) for v in learned.get("fanstep", []) if str(v) in fan_order]

if not temperatures or not fan_speeds:
    raise RuntimeError(
        "First learn the minimum temperature and a manual fan speed (L, LM, M, MH or H) "
        "using the official app recording feature."
    )

temperature = min(temperatures, key=float)
fan_speed = max(fan_speeds, key=fan_order.get)

ctx.log(f"Cycling at {temperature} C, fan {fan_speed}: 5 minutes on, 25 minutes off.")

while True:
    ctx.control("power", "1")
    ctx.control("setpoint", temperature)
    ctx.control("fanstep", fan_speed)
    ctx.wait(10 * 60)
    ctx.control("power", "0")
    ctx.wait(20 * 60)
