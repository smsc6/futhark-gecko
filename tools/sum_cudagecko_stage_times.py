#!/usr/bin/env python3
# Sum cudagecko's built-in stage timers (SHOWTIME lines "[INFO] <stage> t= <ns> ns") from a SLURM log
# Usage: python3 sum_cudagecko_stage_times.py <log file>
# Stage times include cudagecko's data copies (see benchmarks/PROTOCOL.md)
# filterFrags = CPU step filter_and_write_frags (filtering + CSV writing): shown, but excluded from the pipeline total
# INIT lines without an ns unit are not counted
import re
import sys

pattern = re.compile(r'^\[INFO\] (.+?) t= (\d+) ns')
sums = {}
counts = {}
for line in open(sys.argv[1]):
    m = pattern.match(line)
    if not m:
        continue
    stage = m.group(1)
    sums[stage] = sums.get(stage, 0) + int(m.group(2))
    counts[stage] = counts.get(stage, 0) + 1

print('log:', sys.argv[1])
print(f'{"stage":<22}{"calls":>7}{"total (s)":>14}')
for stage in sums:
    print(f'{stage:<22}{counts[stage]:>7}{sums[stage] / 1e9:>14.3f}')
pipeline = sum(v for s, v in sums.items() if s.split()[0] != 'filterFrags')
excluded = sum(v for s, v in sums.items() if s.split()[0] == 'filterFrags')
print(f'pipeline total, filterFrags excluded (s): {pipeline / 1e9:.3f}')
print(f'filterFrags total, CPU step, excluded (s): {excluded / 1e9:.3f}')
