# epicsdev_pump_onboard
EPICS PVAccess server for On-Board cryo pumps

## Running

```sh
uv sync
uv run epicsdev-pump-onboard
```

The default VISA resource is `TCPIP::ctrl-901mp7-mds01.pbn.bnl.gov::2104::SOCKET`, 
Use `--resource` for a full VISA resource, `--instance`
for another instance, or the positional device argument for another prefix.

```sh
uv run epicsdev-pump-onboard --resource ASRL/dev/ttyUSB0::INSTR
uv run epicsdev-pump-onboard --resource TCPIP0::ctrl-901mp7-mds01.pbn.bnl.gov::4001::SOCKET
```

## PVs

All names below follow the configured prefix. Commands use integer values;
`RBV` PVs report hardware state independently of the last requested value.

| PV | Meaning |
| --- | --- |
| `Pump`, `CryoTC`, `AuxTC`, `KeypadLock` | Write 0/1 to disable/enable; separate `RBV` PVs |
| `RoughValve`, `PurgeValve` | Write 0/1 to close/open; separate `RBV` PVs |
| `Stage1Setpoint` | First-stage control, 0-320 K; 0 disables control; separate `RBV` |
| `Stage1Temperature`, `Stage2Temperature` | Temperature in kelvin |
| `CryoPressure`, `AuxPressure` | TC pressure in mTorr (manual's microns) |
| `PowerRecovery` | 0 off, 1 on, 2 below recovery temperature limit; separate `RBV` |
| `StartRegen`, `AbortRegen` | Write 1 to request the action; 0 does nothing |
| `RegenState` | Raw Appendix C regeneration step code |
| `RegenFlags` | Bit 0 waiting for rough valve, bit 1 purge failure, bit 2 heater failure |
| `PowerRecoveryState` | Raw `t?` response, not automatically acknowledged or cleared |
| `PowerFailureSeen` | Latches on a power-failure response until IOC restart |
| `RegenTimeRemaining`, `FailedPurgeCycles`, `FailedRORCycles`, `RateOfRise` | Regeneration progress and diagnostics |
| `ElapsedHours`, `HoursSinceRegen`, `RegenCount` | Pump usage counters |
| `Regen:RestartDelay`, `Regen:ExtendedPurgeTime`, `Regen:RepurgeCycles` | Writable regeneration settings; separate `RBV` PVs |
| `Regen:RoughPressure`, `Regen:RateOfRiseLimit`, `Regen:RORCycles` | Writable regeneration limits; separate `RBV` PVs |
| `Regen:RecoveryTemperature`, `Regen:RepurgeTime` | Writable recovery and purge settings; separate `RBV` PVs |
| `Resource`, `Identification`, `Connected`, `LastError`, `dateTime` | Connection and server diagnostics |

Polling is read-only and does not clear power-failure status using `S` or `t=`.
Only complete, checksum-validated snapshots are published. On failure, telemetry
retains its last value, `Connected` becomes 0, and `LastError` records the failure.
Subsequent polls reconnect. Writes are never automatically retried, because an
acknowledgement can be lost after a command has already executed. Cached control
values may be displayed after restart, but are not replayed to hardware.

Reference: [CTI On-Board Programming and Operation Manual](misc/CTI-OnBoard-Programming-Op-Manual.pdf),
P/N 8040410, Appendices B and C. Use the existing device interlocks and local
operating procedures when commanding valves, pump operation, or regeneration.

## Tests

```sh
uv run python -m unittest discover -s tests -v
```

Tests simulate VISA traffic; they do not contact the pump.
