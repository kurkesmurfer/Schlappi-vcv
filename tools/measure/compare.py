"""
Query the measurement registry and compare results across platforms/versions.

Usage
-----
  python compare.py btfld --metric thd_db --freq 440
  python compare.py btfld --metric sfdr_db --freq 1000
  python compare.py btmx  --metric lag_us
  python compare.py btmx  --metric correlation
  python compare.py list
"""

import argparse
import registry


def _platforms_versions(entries: list) -> list[str]:
    """Return sorted list of 'platform / vX.Y.Z' labels."""
    seen = {}
    for e in entries:
        key = f"{e.get('platform','?')} / v{e.get('plugin_version','?')}"
        seen[key] = e.get('timestamp', '')
    return sorted(seen.keys())


# ── BTFLD ─────────────────────────────────────────────────────────────────────

def _btfld_table(metric: str, freq: int):
    entries = registry.query(module='BTFLD')
    if not entries:
        print("No BTFLD entries in registry."); return

    cols    = _platforms_versions(entries)
    outputs = ['SAW', 'BIT8', 'BIT4', 'BIT2', 'BIT1', 'STEP']

    print(f"\nBTFLD  metric={metric}  freq={freq} Hz")
    hdr = f"  {'Output':<8}" + ''.join(f"  {c:>22}" for c in cols)
    print(hdr)
    print('  ' + '-' * (len(hdr) - 2))

    for out in outputs:
        row = f"  {out:<8}"
        for col in cols:
            plat, ver = col.split(' / v')
            match = next(
                (e for e in reversed(entries)
                 if e.get('platform') == plat and e.get('plugin_version') == ver),
                None
            )
            val = None
            if match:
                r = next((r for r in match['results'] if r.get('freq_hz') == freq), None)
                if r:
                    val = r.get('outputs', {}).get(out, {}).get(metric)
            row += f"  {val:>21.2f}" if val is not None else f"  {'—':>22}"
        print(row)
    print()


# ── BTMX ──────────────────────────────────────────────────────────────────────

def _btmx_table(metric: str):
    entries = registry.query(module='BTMX')
    if not entries:
        print("No BTMX entries in registry."); return

    cols  = _platforms_versions(entries)
    mixes = ['MIX1', 'MIX2', 'MIX3', 'MIX4']

    print(f"\nBTMX  metric={metric}  (side=A, lowest base_freq)")
    hdr = f"  {'Output':<8}" + ''.join(f"  {c:>22}" for c in cols)
    print(hdr)
    print('  ' + '-' * (len(hdr) - 2))

    for mix in mixes:
        row = f"  {mix:<8}"
        for col in cols:
            plat, ver = col.split(' / v')
            match = next(
                (e for e in reversed(entries)
                 if e.get('platform') == plat and e.get('plugin_version') == ver),
                None
            )
            val = None
            if match:
                r = next((r for r in match['results']
                          if r.get('side') == 'A'), None)
                if r:
                    val = r.get('mix_latency', {}).get(mix, {}).get(metric)
            row += f"  {val:>21.2f}" if val is not None else f"  {'—':>22}"
        print(row)
    print()


# ── list ──────────────────────────────────────────────────────────────────────

def _list_all():
    reg = registry.load()
    entries = reg.get('measurements', [])
    if not entries:
        print("Registry is empty."); return
    print(f"\n{len(entries)} measurement(s) in registry:\n")
    hdr = f"  {'Module':<8} {'Platform':<14} {'Version':<10} {'Timestamp':<28} ID"
    print(hdr)
    print('  ' + '-' * (len(hdr) - 2))
    for e in entries:
        print(f"  {e.get('module','?'):<8} {e.get('platform','?'):<14}"
              f" {e.get('plugin_version','?'):<10}"
              f" {e.get('timestamp','?')[:26]:<28} {e.get('id','?')[:8]}…")
    print()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Query measurement registry')
    parser.add_argument('module', choices=['btfld', 'btmx', 'list'])
    parser.add_argument('--metric', default='thd_db',
                        help='btfld: thd_db | sfdr_db | noise_floor_db | fund_amp_dbfs\n'
                             'btmx:  lag_us | lag_samples | correlation')
    parser.add_argument('--freq', type=int, default=440,
                        help='(BTFLD only) fundamental Hz to compare')
    args = parser.parse_args()

    if args.module == 'btfld':
        _btfld_table(args.metric, args.freq)
    elif args.module == 'btmx':
        _btmx_table(args.metric)
    elif args.module == 'list':
        _list_all()


if __name__ == '__main__':
    main()
