#!/usr/bin/env python3
# FASTA TO FUTHARK INPUT
# Cleans a FASTA file the same way as cudagecko's from_ram_load (cpu_functions.c, line 806)
# and writes the sequence as a Futhark binary []u8 array
#
# Cleaning rules, same as cudagecko:
# - everything up to and including the first header line is skipped
# - every later header line becomes one N
# - lowercase letters become uppercase
# - only A-Z are kept (line breaks, digits, spaces dropped)
#
# Usage: python3 fasta_to_futhark.py input.fasta output.in

import struct
import sys

UPPERCASE = bytes(range(ord('A'), ord('Z') + 1))
NOT_UPPERCASE = bytes(b for b in range(256) if b not in UPPERCASE)


# Uppercase, then drop every byte that is not A-Z
def clean(text):
    return text.upper().translate(None, NOT_UPPERCASE)


# Same result as cudagecko's from_ram_load
def from_ram_load(data):
    first_header = data.index(b'>')
    first_newline = data.index(b'\n', first_header)
    parts = data[first_newline + 1:].split(b'>')
    out = [clean(parts[0])]
    for part in parts[1:]:
        newline = part.find(b'\n')
        out.append(b'N')
        if newline >= 0:
            out.append(clean(part[newline + 1:]))
    return b''.join(out)


# Futhark binary format: 'b', version 2, 1 dimension, type "  u8", length as 64-bit integer, then the bytes
def write_futhark_u8(path, seq):
    header = b'b' + bytes([2, 1]) + b'  u8' + struct.pack('<q', len(seq))
    with open(path, 'wb') as f:
        f.write(header)
        f.write(seq)


def main():
    with open(sys.argv[1], 'rb') as f:
        seq = from_ram_load(f.read())
    write_futhark_u8(sys.argv[2], seq)
    print(sys.argv[2], len(seq))


main()
