#!/usr/bin/env python3
# Summarise nsys --stats=true output (gpukernsum, gpumemtimesum) per pair, Futhark and cudagecko
# Usage: python3 summarize_nsys_profiles.py <job results folder>
# cudagecko kernels grouped by name; mgpu merge sort kernels sort both words and hits (not separable by name)
# Futhark kernel names are compiler-generated; word-sort (radix sort) kernels identified on sus-bos (job 4997)
# from instance counts = batches x 32 passes; same gecko binary, so same kernel names on every pair
import os
import sys

folder = sys.argv[1]
pairs = ['mycoplasma', 'ecoli', 'gallus-meleagris', 'oryzias-danio', 'sus-bos', 'human-mouse-chrX', 'human-gorilla-chr1']
futhark_word_sort = {'segmap_26269', 'segmap_27555', 'segscan_27541', 'segscan_26255', 'segscan_26117',
                     'segred_nonseg_27553', 'segred_nonseg_26267', 'segmap_26131', 'segred_nonseg_26129'}


def sections(path):
    kern, mem, part = [], [], None
    for line in open(path):
        if "'gpukernsum'" in line:
            part = kern
            continue
        if "'gpumemtimesum'" in line:
            part = mem
            continue
        if "'gpumemsizesum'" in line:
            part = None
        if part is not None:
            t = line.split()
            if len(t) > 3 and t[1].isdigit():
                part.append(t)
    return kern, mem


def cudagecko_stage(name):
    n = name.lower()
    for key, stage in (('index_global', 'words'), ('mgpu', 'sort (words + hits)'), ('merge', 'sort (words + hits)'),
                       ('hits', 'hits'), ('compact', 'hits'), ('filter', 'filter'), ('frag', 'extend'),
                       ('extend', 'extend'), ('rev', 'revcomp')):
        if key in n:
            return stage
    return 'other'


for pair in pairs:
    print('=====', pair)
    for program in ('futhark-gecko', 'cudagecko-original'):
        path = os.path.join(folder, program, pair, 'nsys_stats.txt')
        kern, mem = sections(path)
        stages = {}
        for t in kern:
            name = ' '.join(t[14:])
            if program == 'futhark-gecko':
                short = name.split('zi')[-1]
                stage = 'word sort (radix)' if short in futhark_word_sort else 'all other kernels'
            else:
                stage = cudagecko_stage(name)
            stages[stage] = stages.get(stage, 0) + int(t[1])
        total = sum(stages.values())
        print(f'  {program}: kernels total {total / 1e9:.3f} s')
        for s, v in sorted(stages.items(), key=lambda x: -x[1]):
            print(f'    {s:<22}{v / 1e9:>9.3f} s{100 * v / total:>7.1f}%')
        for t in mem:
            print(f'    copy {t[-1]:<17}{int(t[1]) / 1e9:>9.3f} s')
