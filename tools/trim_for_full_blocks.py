#!/usr/bin/env python3
# TRIM A FASTA SEQUENCE SO CUDAGECKO'S WORDS KERNEL HAS NO PARTIAL LAST BLOCK
# cudagecko kernel_index_global32 uses blocks of 64 words; a partial last block reads never-written shared memory
# Trimming the sequence end so that (length - 31) is a multiple of 64 makes every block full
# Cleans the sequence like cudagecko's from_ram_load (skip first header, later headers become N, uppercase, keep A-Z)
#
# Usage: python3 trim_for_full_blocks.py input.fasta output.fasta

import sys


def clean(text):
    upper = bytes(range(ord('A'), ord('Z') + 1))
    return text.upper().translate(None, bytes(b for b in range(256) if b not in upper))


def from_ram_load(data):
    first_newline = data.index(b'\n', data.index(b'>'))
    parts = data[first_newline + 1:].split(b'>')
    out = [clean(parts[0])]
    for part in parts[1:]:
        newline = part.find(b'\n')
        out.append(b'N')
        if newline >= 0:
            out.append(clean(part[newline + 1:]))
    return b''.join(out)


def main():
    with open(sys.argv[1], 'rb') as f:
        data = f.read()
    header = data[data.index(b'>'):data.index(b'\n', data.index(b'>'))]
    seq = from_ram_load(data)
    removed = (len(seq) - 31) % 64
    seq = seq[:len(seq) - removed]
    with open(sys.argv[2], 'wb') as f:
        f.write(header + b' trimmed to %d bases for full cudagecko word blocks\n' % len(seq))
        for i in range(0, len(seq), 80):
            f.write(seq[i:i + 80] + b'\n')
    print(sys.argv[2], 'length', len(seq), 'removed', removed, 'words', len(seq) - 31, 'blocks', (len(seq) - 31) // 64)


main()
