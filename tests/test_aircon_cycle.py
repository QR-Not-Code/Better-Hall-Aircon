from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / 'scripts' / 'aircon_cycle.py').read_text(encoding='utf-8')


class EndSimulation(Exception):
    pass


@pytest.mark.parametrize('temperatures, fans, expected_temperature, expected_fan', [
    (['26', '23', '22', '25', '24'], ['A', 'H', 'L', 'LM', 'M', 'MH'], '22', 'H'),
    (['22.5', '18', '9'], ['A', 'L', 'MH', 'M', 'LM'], '9', 'MH'),
    ([24, 22], ['A', 'L'], '22', 'L'),
])
def test_cycle_uses_numeric_minimum_and_highest_manual_fan(temperatures, fans, expected_temperature, expected_fan):
    ctx = Mock()
    waits = []

    def wait(seconds):
        waits.append(seconds)
        if len(waits) == 4:
            raise EndSimulation()

    ctx.wait.side_effect = wait
    with patch('studio.storage.Store') as store:
        store.return_value.config.return_value = {'learned': {'setpoint': temperatures, 'fanstep': fans}}
        with pytest.raises(EndSimulation):
            exec(compile(SOURCE, '<user-script>', 'exec'), {'ctx': ctx})

    assert waits == [300, 1500, 300, 1500]
    assert ctx.control.call_args_list == [
        call('power', '1'), call('setpoint', expected_temperature),
        call('fanstep', expected_fan), call('power', '0'),
    ] * 2


@pytest.mark.parametrize('learned', [{}, {'setpoint': ['22']}, {'setpoint': ['22'], 'fanstep': ['A', 'UNKNOWN']}])
def test_cycle_requires_learned_temperature_and_manual_fan_before_switching_on(learned):
    ctx = Mock()
    with patch('studio.storage.Store') as store:
        store.return_value.config.return_value = {'learned': learned}
        with pytest.raises(RuntimeError, match='First learn'):
            exec(compile(SOURCE, '<user-script>', 'exec'), {'ctx': ctx})
    ctx.control.assert_not_called()
