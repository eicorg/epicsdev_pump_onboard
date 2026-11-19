"""Pypeto PVAccess control page for the On-Board cryopump IOC.

Run with python -m pypeto -c opi -f pump_onboard -i pump_onboard:0:
"""

PREFIX = 'pump_onboard:0:'


class PyPage:
    def __init__(self, instance=None, title='On-Board cryopump'):
        prefix = instance or PREFIX
        if not prefix.endswith(':'):
            prefix += ':'

        self.namespace = 'PVA'
        self.title = f'{title} ({prefix[:-1]})'
        self.page = {'color': [240, 240, 240]}
        self.columns = {
            1: {'width': 195, 'justify': 'right'},
            2: {'width': 105},
            3: {'width': 105},
            4: {'width': 195, 'justify': 'right'},
            5: {'width': 105},
            6: {'width': 105},
        }

        def readback(name, span=1, **attributes):
            return {prefix + name: {
                'features': 'R', 'span': [span, 1], **attributes}}

        def setting(name, low, high):
            return {prefix + name: {
                'widget': 'spinbox', 'opLimits': [low, high], 'format': '%d'}}

        def action(name, text, color):
            return {prefix + name: {
                'widget': 'button', 'text': text,
                'span': [2, 1], 'color': color}}

        def section(text):
            return [{'ATTRIBUTES': {'color': [211, 227, 233]}},
                    {text: {'span': [6, 1], 'justify': 'left'}}]

        def control(name, label, low=0, high=1):
            return [label, setting(name, low, high), readback(name + 'RBV')]

        self.rows = [
            section('On-Board cryopump'),
            ['Connected', readback('Connected'), '',
             'IOC state', prefix + 'server', ''],
            ['Resource', readback('Resource', 5)],
            ['Identification', readback('Identification', 5)],
            ['Last error', readback('LastError', 5)],
            ['IOC status', readback('status', 5)],
            section('Temperatures and pressures'),
            [{'Stage 1 (K)': {'span': [2, 1]}},
             readback('Stage1Temperature', format='%.1f'),
             {'Stage 2 (K)': {'span': [2, 1]}},
             readback('Stage2Temperature', format='%.1f')],
            [{'Cryopump (mTorr)': {'span': [2, 1]}},
             readback('CryoPressure', format='%.3g'),
             {'Auxiliary (mTorr)': {'span': [2, 1]}},
             readback('AuxPressure', format='%.3g')],
            section('Pump controls'),
            ['0 = Off/Closed, 1 = On/Open', 'Command', 'Readback',
             '', 'Command', 'Readback'],
            control('Pump', 'Pump motor') + control('KeypadLock', 'Keypad lock'),
            control('CryoTC', 'Cryopump TC') + control('AuxTC', 'Auxiliary TC'),
            control('RoughValve', 'Rough valve')
            + control('PurgeValve', 'Purge valve'),
            control('Stage1Setpoint', 'Stage 1 setpoint (K)', 0, 320)
            + control('PowerRecovery', 'Power recovery mode', 0, 2),
            section('Regeneration'),
            [action('StartRegen', 'Start regeneration', 'lightGreen'),
             action('AbortRegen', 'Abort regeneration', 'lightSalmon'),
             'Step code', readback('RegenState')],
            ['Phase remaining (min)', readback('RegenTimeRemaining'), '',
             'Flags', readback('RegenFlags'), ''],
            ['Failed purge cycles', readback('FailedPurgeCycles'), '',
             'Failed ROR cycles', readback('FailedRORCycles'), ''],
            ['Rate of rise (mTorr/min)', readback('RateOfRise'), '',
             'Power recovery state', readback('PowerRecoveryState'), ''],
            section('Regeneration settings'),
            ['', 'Command', 'Readback', '', 'Command', 'Readback'],
            control('Regen:RestartDelay', 'Restart delay (min)', 0, 59994)
            + control('Regen:ExtendedPurgeTime', 'Extended purge (min)', 0, 9999),
            control('Regen:RepurgeCycles', 'Repurge cycles', 0, 20)
            + control('Regen:RepurgeTime', 'Repurge time (min)', 0, 9999),
            control('Regen:RoughPressure', 'Rough pressure (mTorr)', 25, 200)
            + control('Regen:RateOfRiseLimit', 'ROR limit (mTorr/min)', 1, 100),
            control('Regen:RORCycles', 'ROR cycle limit', 0, 40)
            + control('Regen:RecoveryTemperature', 'Recovery temp. (K)', 0, 80),
            section('Usage and diagnostics'),
            ['Elapsed time (h)', readback('ElapsedHours'), '',
             'Time since regen (h)', readback('HoursSinceRegen'), ''],
            ['Completed regens', readback('RegenCount'), '',
             'Power failure seen', readback('PowerFailureSeen'), ''],
            ['Poll interval (s)', prefix + 'sleep', '',
             'Version', readback('VERSION', 2)],
            ['Server time', readback('dateTime', 5)],
        ]