#!/usr/bin/env python3
"""Compare two DNA sequences with futhark-gecko and write the alignments as CSV.

Usage:
  python3 run_gecko.py QUERY.fasta REFERENCE.fasta -o OUTDIR [options]

On a SLURM login node the script submits itself as a one-GPU job and returns.
Inside a SLURM job, or with --local, it runs directly:
  1. builds futhark/gecko.fut with the chosen backend (only when the build is missing or outdated)
  2. converts both FASTA files to Futhark input
  3. runs the gecko_batched entry point
  4. writes OUTDIR/alignments.csv

Output files in OUTDIR:
  alignments.csv               one row per alignment: strand, query_start, query_end,
                               ref_start, ref_end, length (0-based, end exclusive;
                               ref coordinates on the forward reference strand)
  futhark_pipeline_output.bin  raw Futhark output: positions and extension offsets of every kept hit
  runtime_microseconds.txt     pipeline runtime reported by the Futhark executable
"""
import argparse
import array
import os
import shlex
import shutil
import struct
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
FUTHARK_DIR = os.path.join(REPO, 'futhark')
DEFAULT_MODULES = 'cuda/11.8 gcc/11.2.0 futhark/0.25.8'
GPU_BACKENDS = ('cuda', 'opencl')
CHUNK = 1 << 20  # values read per array at a time when writing the CSV


def parse_args():
    p = argparse.ArgumentParser(description='Compare two DNA sequences with futhark-gecko.')
    p.add_argument('query', help='query sequence, FASTA')
    p.add_argument('reference', help='reference sequence, FASTA')
    p.add_argument('-o', '--out', required=True, help='output folder (created if missing)')
    p.add_argument('--batch-size', type=int, default=32459520,
                   help='bases per batch (default 32459520, fits a 40 GB GPU)')
    p.add_argument('--min-length', type=int, default=0,
                   help='write only alignments of at least this many bases (default 0: all)')
    p.add_argument('--backend', default='cuda', choices=['cuda', 'opencl', 'multicore', 'c'],
                   help='Futhark backend (default cuda)')
    p.add_argument('--local', action='store_true',
                   help='run here instead of submitting a SLURM job')
    p.add_argument('--partition', default='gpu', help='SLURM partition (default gpu)')
    p.add_argument('--time', default='06:00:00', help='SLURM time limit (default 06:00:00)')
    p.add_argument('--mem', default='32G', help='SLURM CPU memory (default 32G)')
    p.add_argument('--modules', default=DEFAULT_MODULES,
                   help='environment modules loaded in the SLURM job (default "%s"; "" for none)'
                        % DEFAULT_MODULES)
    return p.parse_args()


def submit(args):
    """Submit this script as a SLURM job that runs the same command with --local."""
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    cmd = [sys.executable if os.path.isabs(sys.executable) else 'python3', os.path.abspath(__file__),
           os.path.abspath(args.query), os.path.abspath(args.reference), '-o', out,
           '--batch-size', str(args.batch_size), '--min-length', str(args.min_length),
           '--backend', args.backend, '--local']
    setup = ''
    if args.modules.strip():
        setup = 'module unload cuda; module load %s && ' % args.modules
    wrap = setup + ' '.join(shlex.quote(c) for c in cmd)
    sbatch = ['sbatch', '--parsable', '--job-name=futhark-gecko',
              '--partition=' + args.partition, '--time=' + args.time, '--mem=' + args.mem,
              '--cpus-per-task=2', '--output=' + os.path.join(out, 'gecko_%j.log')]
    if args.backend in GPU_BACKENDS:
        sbatch.append('--gres=gpu:1')
    sbatch.append('--wrap=' + wrap)
    job = subprocess.run(sbatch, check=True, stdout=subprocess.PIPE, universal_newlines=True).stdout.strip().split(';')[0]
    print('Submitted job %s. Log: %s' % (job, os.path.join(out, 'gecko_%s.log' % job)))
    print('Results: %s' % os.path.join(out, 'alignments.csv'))


def build(backend):
    """Compile gecko.fut into build/<backend>/gecko unless the binary is newer than every .fut file."""
    binary = os.path.join(REPO, 'build', backend, 'gecko')
    sources = [os.path.join(FUTHARK_DIR, f) for f in os.listdir(FUTHARK_DIR) if f.endswith('.fut')]
    if os.path.exists(binary) and os.path.getmtime(binary) > max(os.path.getmtime(s) for s in sources):
        return binary
    if shutil.which('futhark') is None:
        sys.exit('futhark not found: load the Futhark module or add futhark to PATH')
    os.makedirs(os.path.dirname(binary), exist_ok=True)
    if not os.path.isdir(os.path.join(FUTHARK_DIR, 'lib')):
        subprocess.run(['futhark', 'pkg', 'sync'], cwd=FUTHARK_DIR, check=True)
    print('Building %s backend' % backend, flush=True)
    subprocess.run(['futhark', backend, '-o', binary, 'gecko.fut'], cwd=FUTHARK_DIR, check=True)
    return binary


def read_sequence(path):
    """Sequence as cudagecko reads it: first header skipped, later headers become N,
    uppercase, only A-Z kept."""
    with open(path, 'rb') as f:
        data = f.read()
    if b'>' not in data:
        sys.exit('%s: no FASTA header found' % path)
    keep = bytes(range(ord('A'), ord('Z') + 1))
    drop = bytes(b for b in range(256) if b not in keep)
    first = data.index(b'\n', data.index(b'>')) if b'\n' in data[data.index(b'>'):] else len(data)
    parts = data[first + 1:].split(b'>')
    out = [parts[0].upper().translate(None, drop)]
    for part in parts[1:]:
        nl = part.find(b'\n')
        out.append(b'N')
        if nl >= 0:
            out.append(part[nl + 1:].upper().translate(None, drop))
    return b''.join(out)


def futhark_u8(seq):
    """One []u8 value in Futhark's binary data format."""
    return b'b' + bytes([2, 1]) + b'  u8' + struct.pack('<q', len(seq)) + seq


def array_offsets(path):
    """(data offset, length) of each one-dimensional u32 array in a Futhark binary output file."""
    arrays = []
    with open(path, 'rb') as f:
        size = os.fstat(f.fileno()).st_size
        pos = 0
        while pos < size:
            f.seek(pos)
            c = f.read(1)
            if c.isspace():
                pos += 1
                continue
            head = c + f.read(6)
            if head[0:1] != b'b' or head[2] != 1 or head[3:7] != b' u32':
                sys.exit('unexpected value in %s at byte %d' % (path, pos))
            n = struct.unpack('<q', f.read(8))[0]
            arrays.append((pos + 15, n))
            pos += 15 + 4 * n
    if len(arrays) != 8:
        sys.exit('%s: expected 8 arrays, found %d' % (path, len(arrays)))
    return arrays


def read_chunk(f, offset, start, count):
    a = array.array('I')
    f.seek(offset + 4 * start)
    a.frombytes(f.read(4 * count))
    if sys.byteorder == 'big':
        a.byteswap()
    return a


def write_alignments(raw, csv_path, ref_len, min_length):
    """One CSV row per extended hit. Hits skipped by extend (both offsets 0) are left out.
    Reverse-strand reference coordinates are converted to the forward reference strand."""
    arrays = array_offsets(raw)
    files = [open(raw, 'rb') for _ in range(4)]
    rows = 0
    with open(csv_path, 'w') as out:
        out.write('strand,query_start,query_end,ref_start,ref_end,length\n')
        for strand, first in (('+', 0), ('-', 4)):
            (ox, n), (oy, _), (ol, _), (orr, _) = arrays[first:first + 4]
            for start in range(0, n, CHUNK):
                count = min(CHUNK, n - start)
                xs, ys, ls, rs = (read_chunk(files[k], o, start, count)
                                  for k, o in enumerate((ox, oy, ol, orr)))
                lines = []
                for x, y, l, r in zip(xs, ys, ls, rs):
                    if l == 0 and r == 0:
                        continue
                    length = l + r
                    if length < min_length:
                        continue
                    qs, qe, rs_, re_ = x - l, x + r, y - l, y + r
                    if strand == '-':
                        rs_, re_ = ref_len - re_, ref_len - rs_
                    lines.append('%s,%d,%d,%d,%d,%d\n' % (strand, qs, qe, rs_, re_, length))
                out.writelines(lines)
                rows += len(lines)
    for f in files:
        f.close()
    return rows


def run_local(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    binary = build(args.backend)

    query = read_sequence(args.query)
    ref = read_sequence(args.reference)
    print('Query %d bases, reference %d bases, batch size %d' % (len(query), len(ref), args.batch_size),
          flush=True)

    raw = os.path.join(out, 'futhark_pipeline_output.bin')
    runtime = os.path.join(out, 'runtime_microseconds.txt')
    stdin = ('%di64\n' % args.batch_size).encode() + futhark_u8(query) + futhark_u8(ref)
    with open(raw, 'wb') as f:
        subprocess.run([binary, '-e', 'gecko_batched', '-b', '-t', runtime],
                       input=stdin, stdout=f, check=True)

    csv_path = os.path.join(out, 'alignments.csv')
    rows = write_alignments(raw, csv_path, len(ref), args.min_length)
    with open(runtime) as f:
        us = int(f.read().split()[0])
    print('Pipeline time %.3f s' % (us / 1e6))
    print('%d alignments written to %s' % (rows, csv_path))


def main():
    args = parse_args()
    if args.batch_size < 32:
        sys.exit('--batch-size must be at least 32 (one word)')
    for path in (args.query, args.reference):
        if not os.path.isfile(path):
            sys.exit('file not found: %s' % path)
    if args.local or 'SLURM_JOB_ID' in os.environ or shutil.which('sbatch') is None:
        run_local(args)
    else:
        submit(args)


if __name__ == '__main__':
    main()
