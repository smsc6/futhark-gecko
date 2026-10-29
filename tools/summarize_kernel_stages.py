"""Kernel time per pipeline stage for Futhark and original cudagecko, from nsys .sqlite profiles.

Usage: python3 summarize_kernel_stages.py <nsys_profile_dir> <output.csv>
<nsys_profile_dir> holds futhark-gecko/<pair>/futhark_<pair>.sqlite and
cudagecko-original/<pair>/cudagecko_<pair>.sqlite (layout of job 5677).

Stages (Table 3): word sort, hit sort, extend, other (revcomp, words, hits, filter).
Kernel time only; copies and memsets are not kernels and are not counted.
Any kernel that is not mapped to a named stage is counted as "other" and printed,
so new or renamed kernels cannot be misattributed silently.
"""
import csv, sqlite3, sys, os

PAIRS = ['mycoplasma', 'ecoli', 'gallus-meleagris', 'oryzias-danio', 'sus-bos',
         'human-mouse-chrX', 'human-gorilla-chr1']

# Futhark: kernel names are fixed by the compiled program (gecko_batched entry point).
# Radix sort = 32 passes (64-bit keys, 2 bits per pass); the five 32-instance kernel sets are
# the five sorts in pipeline order: query words, reference words (forward), hits (forward),
# reference words (reverse), hits (reverse). Word sorts are key-value (hash, position) and larger.
FUTHARK_STAGE = {}
for k in ['segscan_26117', 'segred_nonseg_26129', 'segmap_26131',
          'segscan_26255', 'segred_nonseg_26267', 'segmap_26269',
          'segscan_27541', 'segred_nonseg_27553', 'segmap_27555',
          'gpuseq_33119', 'gpuseq_33572', 'gpuseq_34865']:
    FUTHARK_STAGE[k] = 'word sort'
for k in ['segscan_26456', 'segred_nonseg_26468', 'segmap_26470',
          'segscan_27742', 'segred_nonseg_27754', 'segmap_27756',
          'gpuseq_34181', 'gpuseq_35454']:
    FUTHARK_STAGE[k] = 'hit sort'
# Extend: map over groups of 32 hits with an in-order loop, one kernel per strand
for k in ['segmap_intragroup_26747', 'segmap_intragroup_28033']:
    FUTHARK_STAGE[k] = 'extend'

# cudagecko: kernels are named after their stage
CUDAGECKO_STAGE = [('kernel_reverse_complement', 'revcomp'), ('kernel_index_global32', 'words'),
                   ('kernel_find_leftmost_items', 'hits'), ('kernel_hits_load_balancing', 'hits'),
                   ('kernel_compact_hits', 'hits'), ('kernel_filter_hits_parallel', 'filter'),
                   ('kernel_frags_', 'extend')]

def kernels(db, name_col):
    c = sqlite3.connect(db)
    q = (f'SELECT k.start, k.end, s.value FROM CUPTI_ACTIVITY_KIND_KERNEL k '
         f'JOIN StringIds s ON k.{name_col}=s.id ORDER BY k.start')
    return list(c.execute(q))

def futhark_stages(db):
    t, unmapped = {}, {}
    for start, end, name in kernels(db, 'shortName'):
        key = name.split('zi', 1)[1] if 'zi' in name else name
        stage = FUTHARK_STAGE.get(key, 'other')
        t[stage] = t.get(stage, 0) + (end - start) / 1e9
        if stage == 'other':
            unmapped[name] = unmapped.get(name, 0) + (end - start) / 1e9
    return t, unmapped

def mergesort_kind(name):
    # mergesort<empty_t, key, value, less>: value 'unsigned int' = word sort (hash, position),
    # value 'mgpu::empty_t' = keys only = hit sort
    args = name.split('mgpu::mergesort<', 1)[1]
    value = args.split(',')[2].strip()
    return 'word sort' if value == 'unsigned int' else 'hit sort'

def cudagecko_stages(db):
    rows = kernels(db, 'demangledName')
    sorts = [(s, mergesort_kind(n)) for s, e, n in rows if 'mgpu::mergesort<' in n]
    t, unmapped = {}, {}
    for start, end, name in rows:
        if 'mgpu::mergesort<' in name:
            stage = mergesort_kind(name)
        elif 'merge_sort_partitions' in name:
            # partition kernels are shared by both sorts; assign each to the next mergesort launch
            nxt = [k for s, k in sorts if s >= start]
            stage = nxt[0] if nxt else sorts[-1][1]
        else:
            stage = next((st for pat, st in CUDAGECKO_STAGE if pat in name), 'other')
            if stage == 'other':
                unmapped[name[:120]] = unmapped.get(name[:120], 0) + (end - start) / 1e9
        t[stage] = t.get(stage, 0) + (end - start) / 1e9
    return t, unmapped

d, out = sys.argv[1], sys.argv[2]
with open(out, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['pair', 'program', 'stage', 'kernel_time_s'])
    for p in PAIRS:
        for prog, fn, path in [
                ('cudagecko-original', cudagecko_stages, f'{d}/cudagecko-original/{p}/cudagecko_{p}.sqlite'),
                ('futhark-gecko', futhark_stages, f'{d}/futhark-gecko/{p}/futhark_{p}.sqlite')]:
            t, unmapped = fn(path)
            total = sum(t.values())
            for stage, sec in sorted(t.items()):
                w.writerow([p, prog, stage, f'{sec:.6f}'])
            w.writerow([p, prog, 'total', f'{total:.6f}'])
            print(f'{p:20s} {prog:20s} total {total:8.3f} s  ' +
                  '  '.join(f'{k} {v:.3f}' for k, v in sorted(t.items())))
            big = {n: s for n, s in unmapped.items() if s > 0.01 * total}
            for n, s in big.items():
                print(f'    UNMAPPED >1% of total: {s:.3f} s  {n}')
