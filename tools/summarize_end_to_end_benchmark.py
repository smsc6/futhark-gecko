#!/usr/bin/env python3
# Summarise the end-to-end benchmark job (A100, 7 pairs, 3 programs)
# Usage: python3 summarize_end_to_end_benchmark.py <job results folder> <output csv>
# cudagecko time per run = sum of built-in stage timers (copies included), filterFrags (CPU step) excluded
# cudagecko: run 0 = warm-up (dropped), runs 1-10 used
# Futhark time per run = executable -t time (input copy to GPU and result copy back excluded, see benchmarks/PROTOCOL.md)
# Futhark: 10 timed runs expected; if 11 lines, the first (warm-up) is dropped
# cudagecko hits = sum of "Generated N hits" log lines in run 1 (hits before filtering, both strands, all batches)
# Standard deviation = sample standard deviation over the timed runs
import csv
import os
import re
import statistics
import sys

folder, out_csv = sys.argv[1], sys.argv[2]
pairs = ['mycoplasma', 'ecoli', 'gallus-meleagris', 'oryzias-danio', 'sus-bos', 'human-mouse-chrX', 'human-gorilla-chr1']
stage = re.compile(r'^\[INFO\] (.+?) t= (\d+) ns')
generated = re.compile(r'Generated (\d+) hits')


def cudagecko_run(path):
    seconds, hits = 0, 0
    for line in open(path):
        m = stage.match(line)
        if m and m.group(1).split()[0] != 'filterFrags':
            seconds += int(m.group(2))
        g = generated.search(line)
        if g:
            hits += int(g.group(1))
    return seconds / 1e9, hits


rows = []
for pair in pairs:
    for program in ('cudagecko-original', 'cudagecko-bugfixed'):
        d = os.path.join(folder, program, pair)
        runs = [cudagecko_run(os.path.join(d, f'run_{k}.log')) for k in range(1, 11)]
        times = [t for t, _ in runs]
        rows.append([pair, program, len(times), statistics.mean(times), statistics.stdev(times), min(times), max(times), runs[0][1]])
    lines = [l for l in open(os.path.join(folder, 'futhark-gecko', pair, 'futhark_runtimes_microseconds.txt')) if l.strip()]
    if len(lines) == 11:
        lines = lines[1:]
    times = [int(l) / 1e6 for l in lines]
    rows.append([pair, 'futhark-gecko', len(times), statistics.mean(times), statistics.stdev(times), min(times), max(times), ''])

with open(out_csv, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['pair', 'program', 'runs', 'mean_s', 'std_s', 'min_s', 'max_s', 'cudagecko_generated_hits'])
    w.writerows(rows)

print('job folder:', folder)
print(f'{"pair":<20}{"program":<20}{"runs":>5}{"mean (s)":>11}{"std (s)":>10}{"generated hits":>16}')
for r in rows:
    print(f'{r[0]:<20}{r[1]:<20}{r[2]:>5}{r[3]:>11.3f}{r[4]:>10.3f}{str(r[7]):>16}')
print()
print(f'{"pair":<20}{"futhark / original":>20}{"futhark / bug-fixed":>21}')
for pair in pairs:
    m = {r[1]: r[3] for r in rows if r[0] == pair}
    print(f'{pair:<20}{m["futhark-gecko"] / m["cudagecko-original"]:>20.3f}{m["futhark-gecko"] / m["cudagecko-bugfixed"]:>21.3f}')
