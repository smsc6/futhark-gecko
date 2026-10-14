#!/usr/bin/env python3
# COMPARE FUTHARK-GECKO OUTPUT WITH CUDAGECKO VALIDATION-COPY OUTPUT
# Checks revcomp.fut, words.fut and sort.fut against cudagecko's arrays
#
# Usage: python3 compare_with_cudagecko.py <futhark output folder> <cudagecko output folder>
#
# Futhark folder: futhark_revcomp_reference.bin, futhark_sorted_query_words.bin (Futhark binary format)
# cudagecko folder: cudagecko_revcomp_reference.bin (bytes), cudagecko_sorted_query_hashes.bin (uint64),
#                   cudagecko_sorted_query_positions.bin (uint32), all little-endian raw arrays

import array
import os
import struct
import sys

TYPECODES = {b'  u8': 'B', b' u32': 'I', b' u64': 'Q'}
ALL_ONES_U64 = 2**64 - 1
ALL_ONES_U32 = 2**32 - 1

assert array.array('Q').itemsize == 8 and array.array('I').itemsize == 4


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
        if data[i:i + 1] != b'b':
            sys.exit('Not Futhark binary data at byte %d of %s' % (i, path))
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


# Read a raw little-endian array written by cudagecko
def read_raw(path, typecode):
    values_array = array.array(typecode)
    with open(path, 'rb') as f:
        values_array.frombytes(f.read())
    return values_array


# Index of the first position where two arrays differ, or None
def first_mismatch(a, b):
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return None


def compare_revcomp(fut_dir, cg_dir):
    print('== Reverse complement (revcomp.fut vs cudagecko kernel_reverse_complement)')
    fut = read_futhark_values(os.path.join(fut_dir, 'futhark_revcomp_reference.bin'))[0]
    cg = read_raw(os.path.join(cg_dir, 'cudagecko_revcomp_reference.bin'), 'B')
    print('length futhark %d, cudagecko %d' % (len(fut), len(cg)))
    if fut == cg:
        print('RESULT: identical')
        return True
    i = first_mismatch(fut, cg)
    print('RESULT: DIFFERENT, first mismatch at index %s' % i)
    return False


def compare_sorted_words(fut_dir, cg_dir):
    print('== Sorted query words (words.fut + sort.fut vs cudagecko kernel_index_global32 + mergesort)')
    fut_hashes, fut_positions = read_futhark_values(os.path.join(fut_dir, 'futhark_sorted_query_words.bin'))
    cg_hashes = read_raw(os.path.join(cg_dir, 'cudagecko_sorted_query_hashes.bin'), 'Q')
    cg_positions = read_raw(os.path.join(cg_dir, 'cudagecko_sorted_query_positions.bin'), 'I')
    m = len(fut_hashes)
    extra = len(cg_hashes) - m
    print('entries futhark %d, cudagecko %d, cudagecko extra %d (expected 31)' % (m, len(cg_hashes), extra))
    print('invalid words (hash all ones) in futhark output: %d' % sum(1 for h in fut_hashes if h == ALL_ONES_U64))

    tail_ok = all(h == ALL_ONES_U64 for h in cg_hashes[m:]) and all(p == ALL_ONES_U32 for p in cg_positions[m:])
    print('cudagecko extra entries all ones: %s' % tail_ok)

    head_hashes = cg_hashes[:m]
    head_positions = cg_positions[:m]
    if head_hashes == fut_hashes and head_positions == fut_positions:
        print('RESULT: identical (first %d entries), extra entries all ones: %s' % (m, tail_ok))
        return tail_ok and extra == 31

    print('RESULT: DIFFERENT')
    print('first hash mismatch at index %s' % first_mismatch(fut_hashes, head_hashes))
    print('first position mismatch at index %s' % first_mismatch(fut_positions, head_positions))
    same_content = sorted(zip(fut_hashes, fut_positions)) == sorted(zip(head_hashes, head_positions))
    print('same (hash, position) pairs, different order only: %s' % same_content)
    return False


def main():
    fut_dir, cg_dir = sys.argv[1], sys.argv[2]
    print('futhark folder: %s' % fut_dir)
    print('cudagecko folder: %s' % cg_dir)
    revcomp_ok = compare_revcomp(fut_dir, cg_dir)
    words_ok = compare_sorted_words(fut_dir, cg_dir)
    print('== Summary: revcomp %s, words + sort %s' % ('PASS' if revcomp_ok else 'FAIL', 'PASS' if words_ok else 'FAIL'))


main()
