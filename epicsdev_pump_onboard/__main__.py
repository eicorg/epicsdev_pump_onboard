"""EPICS PVAccess server for On-Board cryopumps (CTI manual P/N 8040410)."""
# pylint: disable=invalid-name,broad-exception-caught
__version__ = 'v0.0.1 2026-11-19'# AI-generated

import argparse
from dataclasses import dataclass
from functools import partial
import math
import threading
import time

import pyvisa

from epicsdev import epicsdev as edev

DEVICE = 'pump_onboard:'
RESOURCE = 'TCPIP::ctrl-901mp7-mds01::2104::SOCKET'
SWITCHES = (
    ('Pump', 'Pump motor', 'A'),
    ('CryoTC', 'Cryopump thermocouple gauge', 'B'),
    ('AuxTC', 'Auxiliary thermocouple gauge', 'C'),
    ('RoughValve', 'Rough valve', 'D'),
    ('PurgeValve', 'Purge valve', 'E'),
    ('KeypadLock', 'Keypad access lockout', 'z'),
)
MEASUREMENTS = (
    ('Stage1Temperature', 'First stage temperature', 'J', 'K'),
    ('Stage2Temperature', 'Second stage temperature', 'K', 'K'),
    ('CryoPressure', 'Cryopump TC pressure', 'L', 'mTorr'),
    ('AuxPressure', 'Auxiliary TC pressure', 'M', 'mTorr'),
    ('ElapsedHours', 'Pump elapsed time', 'Y?', 'h'),
    ('RegenCount', 'Completed regeneration cycles', 'Z', ''),
    ('HoursSinceRegen', 'Time since last full regeneration', 'a', 'h'),
    ('RegenTimeRemaining', 'Current regeneration phase time remaining', 'k', 'min'),
    ('FailedPurgeCycles', 'Failed purge cycles', 'l', ''),
    ('FailedRORCycles', 'Failed or extended rate-of-rise cycles', 'm', ''),
    ('RateOfRise', 'Last measured rate of rise', 'n', 'mTorr/min'),
)
REGEN_PARAMETERS = (
    ('RestartDelay', 'Pump restart delay', '0', 59994, 'min'),
    ('ExtendedPurgeTime', 'Extended purge time', '1', 9999, 'min'),
    ('RepurgeCycles', 'Number of repurge cycles', '2', 20, ''),
    ('RoughPressure', 'Rough-to pressure', '3', 200, 'mTorr'),
    ('RateOfRiseLimit', 'Rate-of-rise limit', '4', 100, 'mTorr/min'),
    ('RORCycles', 'Rate-of-rise cycle limit', '5', 40, ''),
    ('RecoveryTemperature', 'Power failure restart temperature', '6', 80, 'K'),
    ('RepurgeTime', 'Repurge time', 'G', 9999, 'min'),
)

#````````````````````````````````````````````````````````````````````````````
# Definitions of PVs, their types, units, limits, and setter functions are
# defined in the myPVDefs() function below.
def myPVDefs():
    """Return list of PV definitions"""
    # abbreviations for PV definition dictionary keys
    F, T, U, LL, LH = 'features', 'type', 'units', 'limitLow', 'limitHigh'
    SET = 'setter'

    pv_defs = [
['dateTime', 'Server local date/time', 'N/A'],
['Resource', 'Requested VISA resource', C_.pargs.resource],
['Identification', 'Module type and software revision', ''],
['Connected', 'Last polling cycle succeeded', 0, {T: 'u8'}],
['LastError', 'Last communication or command error', ''],
['PowerFailureSeen', 'Power failure reported since server start', 0, {T: 'u8'}],
['RegenState', 'Raw regeneration step code (manual Appendix C)', ''],
['RegenFlags', 'Regen flags: 1 waiting, 2 purge failure, 4 heater failure',
    0, {T: 'u8'}],
['PowerRecoveryState', 'Power recovery state (manual command t?)', ''],
['Stage1Setpoint', 'First stage control temperature; 0 disables control', 0,
    {F: 'W', T: 'i32', U: 'K', LL: 0, LH: 320,
     SET: partial(_set_integer, command='H', low=0, high=320)}],
['Stage1SetpointRBV', 'First stage control temperature readback', 0,
    {T: 'i32', U: 'K'}],
['PowerRecovery', 'Power recovery mode: 0 off, 1 on, 2 below temperature limit',
    0, {F: 'W', T: 'i32', LL: 0, LH: 2,
        SET: partial(_set_integer, command='i', low=0, high=2)}],
['PowerRecoveryRBV', 'Power recovery mode readback', 0, {T: 'i32'}],
['StartRegen', 'Start regeneration (write 1)', 0,
    {F: 'W', T: 'u8', LL: 0, LH: 1,
     SET: partial(_set_action, command='N1')}],
['AbortRegen', 'Abort regeneration (write 1)', 0,
    {F: 'W', T: 'u8', LL: 0, LH: 1,
     SET: partial(_set_action, command='N0')}],
    ]
    for name, description, command in SWITCHES:
        pv_defs.extend([
            [name, description + ' command (0 off/closed, 1 on/open)', 0,
             {F: 'W', T: 'u8', LL: 0, LH: 1,
              SET: partial(_set_integer, command=command, low=0, high=1)}],
            [name + 'RBV', description + ' readback', 0, {T: 'u8'}],
        ])
    for name, description, _command, units in MEASUREMENTS:
        pv_defs.append([name, description, float('nan'), {T: 'f64', U: units}])
    for name, description, selector, high, units in REGEN_PARAMETERS:
        low = 25 if selector == '3' else 1 if selector == '4' else 0
        pv_defs.extend([
            ['Regen:' + name, description, low,
             {F: 'W', T: 'i32', U: units, LL: low, LH: high,
              SET: partial(_set_integer, command='P' + selector,
                           low=low, high=high, width=5)}],
            ['Regen:' + name + 'RBV', description + ' readback', low,
             {T: 'i32', U: units}],
        ])
    return pv_defs
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

@dataclass(slots=True)
class C_:
    """Container for module state variables."""
    pargs = None #
    manager = None
    instrument = None
    lock = threading.RLock()
    power_failure = False

def _checksum(data: str) -> str:
    """Appendix B: modulo-256 sum, fold the top two bits, bias by ASCII 0."""
    total = sum(data.encode('ascii')) & 0xff
    return chr(((total ^ (total >> 6)) & 0x3f) + 0x30)

def _packet(command: str) -> str:
    if not 1 <= len(command) <= 14:
        raise ValueError('Command data must contain 1 to 14 ASCII characters')
    if any(ord(char) < 32 or ord(char) > 126 or char == '$' for char in command):
        raise ValueError('Command data must be printable ASCII without $')
    return '$' + command + _checksum(command)

def _decode(reply: str) -> str:
    if not reply.startswith('$') or not 4 <= len(reply) <= 17:
        raise ValueError(f'Invalid On-Board packet: {reply!r}')
    if not reply.endswith('\r'):
        raise ValueError('Missing On-Board carriage-return terminator')
    data = reply[1:-2]
    if '$' in data or _checksum(data) != reply[-2]:
        raise ValueError(f'On-Board checksum mismatch: {reply!r}')
    status = data[0]
    if status in ('B', 'F', 'H'):
        C_.power_failure = True
    if status in ('E', 'F'):
        raise RuntimeError('On-Board rejected command or parameter')
    if status in ('G', 'H'):
        raise RuntimeError('On-Board interlock prevents command execution')
    if status not in ('A', 'B'):
        raise ValueError(f'Unknown On-Board response status: {status!r}')
    return data[1:].strip()

def _disconnect():
    with C_.lock:
        if C_.instrument is not None:
            try:
                C_.instrument.close()
            except (pyvisa.errors.VisaIOError, OSError):
                pass
            C_.instrument = None

def _connect():
    if C_.manager is None:
        C_.manager = pyvisa.ResourceManager(C_.pargs.visa_backend)
    resource = C_.pargs.resource
    C_.instrument = C_.manager.open_resource(resource)
    C_.instrument.timeout = max(1, int(C_.pargs.timeout * 1000))
    C_.instrument.write_termination = '\r'
    C_.instrument.read_termination = '\r'
    C_.instrument.encoding = 'ascii'
    if isinstance(C_.instrument, pyvisa.resources.SerialInstrument):
        C_.instrument.baud_rate = 2400
        C_.instrument.data_bits = 7
        C_.instrument.parity = pyvisa.constants.Parity.even
        C_.instrument.stop_bits = pyvisa.constants.StopBits.one
        C_.instrument.flow_control = pyvisa.constants.ControlFlow.none

def _exchange(command: str) -> str:
    """Exchange one checked packet; never retry a potentially executed write."""
    packet = _packet(command)
    with C_.lock:
        try:
            if C_.instrument is None:
                _connect()
            C_.instrument.write(packet)
            reply = C_.instrument.read_raw().decode('ascii')
            return _decode(reply)
        except (pyvisa.errors.VisaIOError, OSError, ValueError):
            _disconnect()
            raise

def _number(command: str) -> float:
    value = float(_exchange(command))
    if not math.isfinite(value):
        raise ValueError(f'{command}: non-finite numeric reply')
    return value

def _integer(command: str, low: int, high: int) -> int:
    value = _number(command)
    if not value.is_integer() or not low <= value <= high:
        raise ValueError(f'{command}: expected integer in {low}..{high}, got {value}')
    return int(value)

def _write(command: str):
    try:
        response = _exchange(command)
        if response:
            raise ValueError(f'Unexpected command acknowledgement: {response!r}')
    except (pyvisa.errors.VisaIOError, OSError, ValueError, RuntimeError) as exc:
        edev.publish('LastError', str(exc))
        edev.publish('PowerFailureSeen', int(C_.power_failure), ifChanged=True)
        raise

def _set_integer(value, *_, command: str, low: int, high: int, width: int = 0):
    number = float(value)
    if not math.isfinite(number) or not number.is_integer() or not low <= number <= high:
        raise ValueError(f'Expected integer in {low}..{high}')
    _write(f'{command}{int(number):0{width}d}')

def _set_action(value, *_, command: str):
    if float(value) not in (0, 1):
        raise ValueError('Expected 0 or 1')
    if float(value) == 1:
        _write(command)

def _read_snapshot() -> dict:
    values = {'Identification': _exchange('@')}
    for name, _description, command in SWITCHES:
        values[name + 'RBV'] = _integer(command + '?', 0, 1)
    for name, _description, command, _units in MEASUREMENTS:
        values[name] = _number(command)
    values['Stage1SetpointRBV'] = _integer('H?', 0, 320)
    values['PowerRecoveryRBV'] = _integer('i?', 0, 2)
    values['RegenState'] = _exchange('O')
    flags = _exchange('v')
    if len(flags) != 1 or not 0 <= ord(flags) - ord('@') <= 7:
        raise ValueError(f'Invalid regeneration flags: {flags!r}')
    values['RegenFlags'] = ord(flags) - ord('@')
    values['PowerRecoveryState'] = _exchange('t?')
    for name, _description, selector, high, _units in REGEN_PARAMETERS:
        low = 25 if selector == '3' else 1 if selector == '4' else 0
        values['Regen:' + name + 'RBV'] = _integer('P' + selector + '?', low, high)
    return values

def poll():
    """Poll for updates from the hardware or other sources."""
    try:
        with C_.lock:
            values = _read_snapshot()
            for name, value in values.items():
                edev.publish(name, value, ifChanged=True)
            edev.publish('Connected', 1, ifChanged=True)
            edev.publish('LastError', '', ifChanged=True)
    except (pyvisa.errors.VisaIOError, OSError, ValueError, RuntimeError) as exc:
        _disconnect()
        edev.publish('Connected', 0, ifChanged=True)
        edev.publish('LastError', str(exc), ifChanged=True)
        edev.printe(f'On-Board polling: {exc}')
    edev.publish('PowerFailureSeen', int(C_.power_failure), ifChanged=True)

def periodic_update():
    """Perform periodic updates."""
    edev.publish('dateTime', time.strftime('%Y-%m-%d %H:%M:%S'), ifChanged=True)

def serverStateChanged(newState: str):
    """Callback for server state transitions."""
    if newState == 'Start':
        edev.printi('Start requested')
    elif newState == 'Stop':
        edev.printi('Stop requested')
    elif newState == 'Exit':
        edev.printi('Exit requested')

def _timeout(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 1:
        raise argparse.ArgumentTypeError('Timeout must be finite and greater than 1 second')
    return number

def main(argv=None):
    """Run the On-Board PVAccess server."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=f'{__version__}, epicsdev:{edev.__version__}',
    )
    # commonly used options
    parser.add_argument('-a', '--autosave', nargs='?', default='', help=
'Autosave control. If omitted, autosave is enabled with default directory.')
    parser.add_argument('-c', '--recall', action='store_false', help=
'If given: do not restore initial PV values from autosave cache.')
    parser.add_argument('-i', '--instance', default='0', help=
'Device instance.')
    parser.add_argument('-p', '--putlogPV', nargs='?', default='', help=
'PV name for logging put operations. Empty means default putlog:dump.')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=
'Increase verbosity (-vv for more).')
    parser.add_argument('device', nargs='?', default=DEVICE, help=
'Device name, the prefix for all generated PVs <prefix><instance>:')

    parser.add_argument('-r', '--resource', default=RESOURCE, help=
'VISA resource name or hostname. Bare hostnames use TCPIP0::<host>::INSTR.')
    parser.add_argument('--visa-backend', default='@py', help='PyVISA backend.')
    parser.add_argument('--timeout', type=_timeout, default=2.0, help=
'VISA transaction timeout in seconds (must exceed the one-second device response limit).')
    
    # Parse command-line arguments and store them in the module state container.
    C_.pargs = parser.parse_args(argv)
    if C_.pargs.putlogPV == '':
        C_.pargs.putlogPV = 'putlog:dump'
    C_.pargs.prefix = f'{C_.pargs.device}{C_.pargs.instance}:'

    # Initialize PV definitions.
    C_.PvDefs = myPVDefs()

    # Initialize the EPICS PVAccess server with the defined PVs.
    PVs = edev.init_epicsdev(
        C_.pargs.prefix,
        C_.PvDefs,
        C_.pargs.verbose,
        serverStateChanged,
        None,# to write list of PVs to /tmp/pvlist/
        C_.pargs.autosave,
        C_.pargs.recall,
        C_.pargs.putlogPV,
    )
    print(f'Using PV prefix: {C_.pargs.prefix}')

    # Start the server and print initial status.
    edev.publish('VERSION', __version__)
    edev.set_server('Start')
    server = edev.Server(providers=[PVs])
    edev.printi((f'Server for {C_.pargs.prefix} started. Sleeping per cycle: '
                 f'{repr(edev.pvv("sleep"))} S.'))

    # Main server loop. Polls for updates and handles server state transitions.
    try:
        while True:
            state = edev.serverState()
            if state.startswith('Exit'):
                break
            if not state.startswith('Stop'):
                poll()
            if not edev.sleep():
                periodic_update()
    except KeyboardInterrupt:
        edev.printi('Keyboard interrupt received, exiting main loop...')
        edev.set_server('Exit')
    except OSError:
        pass
    finally:
        server.stop()
        _disconnect()
        if C_.manager is not None:
            C_.manager.close()
            C_.manager = None

    edev.printi('Server is exited')

if __name__ == '__main__':
    main()
