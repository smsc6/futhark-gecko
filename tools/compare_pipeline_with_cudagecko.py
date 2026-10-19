#!/usr/bin/env python3
# COMPARE FUTHARK-GECKO PIPELINE OUTPUT (gecko.fut) WITH CUDAGECKO VALIDATION-COPY OUTPUT
# Per strand: kept hit positions x and y, left and right extension offsets
# These are the arrays cudagecko passes to its CPU step filter_and_write_frags
#
# Usage: python3 compare_pipeline_with_cudagecko.py <futhark output folder> <cudagecko output folder>

import array
import os
import struct
import sys

TYPECODES = {b'  u8': 'B', b' u32': 'I', b' u64': 'Q'}


# Read every value in a Futhark binary file: 'b', version, rank, type, dimensions, data
def read_futhark_values(path):
    with open(path, 'rb') as f:
        data = f.read()
    values = []
    i = 0
    while i < len(data):
        if data[i:i + 1].isspace():
            i += 1
            continue
        rank = data[i + 2]
        type_name = data[i + 3:i + 7]
        dims = struct.unpack('<%dq' % rank, data[i + 7:i + 7 + 8 * rank])
        i += 7 + 8 * rank
        count = 1
        for d in dims:
            count *= d
        values_array = array.array(TYPECODES[type_name])
        size = values_array.itemsize * count
        values_array.frombytes(data[i:i + size])
        i += size
        values.append(values_array)
    return values


def read_raw_u32(path):
    values_array = array.array('I')
    with open(path, 'rb') as f:
        values_array.frombytes(f.read())
    return values_array


def compare_strand(name, fut, cg):
    fx, fy, fl, fr = fut
    cx, cy, cl, cr = cg
    print('== %s strand' % name)
    print('kept hits: futhark %d, cudagecko %d' % (len(fx), len(cx)))
    if (fx, fy, fl, fr) == (cx, cy, cl, cr):
        print('RESULT: identical')
        return True
    fut_pairs = set(zip(fx, fy))
    cg_pairs = set(zip(cx, cy))
    only_f = sorted(fut_pairs - cg_pairs)
    only_c = sorted(cg_pairs - fut_pairs)
    print('hits only in futhark: %d, only in cudagecko: %d' % (len(only_f), len(only_c)))
    print('first hits only in futhark (x, y): %s' % only_f[:5])
    print('first hits only in cudagecko (x, y): %s' % only_c[:5])
    fut_off = dict(((x, y), (l, r)) for x, y, l, r in zip(fx, fy, fl, fr))
    cg_off = dict(((x, y), (l, r)) for x, y, l, r in zip(cx, cy, cl, cr))
    common = fut_pairs & cg_pairs
    diff_off = [p for p in common if fut_off[p] != cg_off[p]]
    print('hits in both: %d, of which different offsets: %d' % (len(common), len(diff_off)))
    for p in sorted(diff_off)[:5]:
        print('  hit %s: futhark offsets %s, cudagecko offsets %s' % (p, fut_off[p], cg_off[p]))
    same_order = list(zip(fx, fy)) == [p for p in zip(cx, cy) if p in fut_pairs] if not only_f else None
    print('RESULT: DIFFERENT')
    return False


def main():
    fut_dir, cg_dir = sys.argv[1], sys.argv[2]
    print('futhark folder: %s' % fut_dir)
    print('cudagecko folder: %s' % cg_dir)
    v = read_futhark_values(os.path.join(fut_dir, 'futhark_pipeline_output.bin'))
    results = []
    for name, fut in (('forward', v[0:4]), ('reverse', v[4:8])):
        cg = [read_raw_u32(os.path.join(cg_dir, 'cudagecko_%s_%s.bin' % (part, name)))
              for part in ('filtered_hits_x', 'filtered_hits_y', 'offsets_left', 'offsets_right')]
        results.append(compare_strand(name, fut, cg))
    print('== Summary: forward %s, reverse %s' % tuple('PASS' if ok else 'FAIL' for ok in results))


main()
