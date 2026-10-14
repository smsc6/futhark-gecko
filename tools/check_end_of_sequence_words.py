#!/usr/bin/env python3
# CHECK WORDS + SORT MISMATCHES AGAINST THE CUDAGECKO END-OF-SEQUENCE BUG
# cudagecko kernel_index_global32 (kernels.cu line 1091): threads past the last word exit before
# copying their base into shared memory, so the last block reads never-written bases
#
# Predicted affected words: start positions max(last block start, n - 62) to n - 32,
# with last block start = 64 * floor((n - 32) / 64), n = sequence length
#
# Usage: python3 check_end_of_sequence_words.py <futhark output folder> <cudagecko output folder> <query .in file>

import array
import os
import sys

futhark_dir, cudagecko_dir, query_path = sys.argv[1], sys.argv[2], sys.argv[3]

seq = open(query_path, 'rb').read()[15:]
n = len(seq)
m = n - 31

fut = open(os.path.join(futhark_dir, 'futhark_sorted_query_words.bin'), 'rb').read()
fut_hashes = array.array('Q'); fut_hashes.frombytes(fut[15:15 + 8 * m])
offset = 15 + 8 * m + 1 + 15
fut_positions = array.array('I'); fut_positions.frombytes(fut[offset:offset + 4 * m])
cg_hashes = array.array('Q'); cg_hashes.frombytes(open(os.path.join(cudagecko_dir, 'cudagecko_sorted_query_hashes.bin'), 'rb').read())
cg_positions = array.array('I'); cg_positions.frombytes(open(os.path.join(cudagecko_dir, 'cudagecko_sorted_query_positions.bin'), 'rb').read())

code = {ord('C'): 1, ord('G'): 2, ord('T'): 3}


# Hash rebuilt directly from the sequence: A=0, C=1, G=2, T=3, base k at bits 2k
def hash_from_sequence(p):
    return sum(code.get(seq[p + k], 0) << (2 * k) for k in range(32))


last_block_start = 64 * ((n - 32) // 64)
predicted = set(range(max(last_block_start, n - 62), n - 31))

fut_pairs = set(zip(fut_hashes, fut_positions))
cg_pairs = set(zip(cg_hashes[:m], cg_positions[:m]))
only_futhark = dict((p, h) for h, p in fut_pairs - cg_pairs)
only_cudagecko = dict((p, h) for h, p in cg_pairs - fut_pairs)

print('query length %d, words %d, last block starts at %d' % (n, m, last_block_start))
print('predicted affected word positions: %d to %d (%d words)' % (min(predicted), max(predicted), len(predicted)))
print('differing pairs: only futhark %d, only cudagecko %d' % (len(only_futhark), len(only_cudagecko)))
print('differing positions all inside predicted range: %s' % set(only_futhark).issubset(predicted))
print('same positions in both difference sets: %s' % (set(only_futhark) == set(only_cudagecko)))
print('futhark hash equals hash from sequence: %d of %d' % (sum(1 for p, h in only_futhark.items() if h == hash_from_sequence(p)), len(only_futhark)))
print('cudagecko hash equals hash from sequence: %d of %d' % (sum(1 for p, h in only_cudagecko.items() if h == hash_from_sequence(p)), len(only_cudagecko)))
print('predicted positions that match anyway (by chance): %s' % sorted(predicted - set(only_futhark)))
explained = set(only_futhark).issubset(predicted) and set(only_futhark) == set(only_cudagecko) \
    and all(h == hash_from_sequence(p) for p, h in only_futhark.items())
print('RESULT: all differences explained by the cudagecko end-of-sequence bug: %s' % explained)
