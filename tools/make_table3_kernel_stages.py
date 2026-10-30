"""Write Table 3 (kernel time per stage, cudagecko and Futhark) as a LaTeX table.

Usage: python3 make_table3_kernel_stages.py <kernel-stage-summary.csv> <output.tex>
Input: CSV from summarize_kernel_stages.py. Times are printed in ms.
cudagecko 'other' = revcomp + words + hits + filter, matching Futhark's unsplittable 'other'.
"""
import csv, sys
from collections import defaultdict

PAIRS = [('mycoplasma', r'\emph{Mycoplasma}'), ('ecoli', r'\emph{E.~coli}'),
         ('gallus-meleagris', r'\emph{Gallus} vs \emph{Meleagris}'),
         ('oryzias-danio', r'\emph{Oryzias} vs \emph{Danio}'), ('sus-bos', r'\emph{Sus} vs \emph{Bos}'),
         ('human-mouse-chrX', 'Human vs mouse chrX'), ('human-gorilla-chr1', 'Human vs gorilla chr1')]

t = defaultdict(float)
for r in csv.DictReader(open(sys.argv[1])):
    prog, stage, sec = r['program'], r['stage'], float(r['kernel_time_s'])
    if prog == 'cudagecko-original' and stage in ('revcomp', 'words', 'hits', 'filter', 'other'):
        stage = 'other'
    t[(r['pair'], prog, stage)] += sec * 1e3   # ms

def ms(v):
    return f'{v:,.1f}' if v < 100 else f'{v:,.0f}'

lines = [r'\begin{table}[t]', r'\centering', r'\footnotesize',
         r'\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrrrr@{}}', r'\toprule',
         r'Pair & Program & Word sort & Hit sort & Extend & Other & Total & Futhark / cudagecko \\', r'\midrule']
for i, (p, label) in enumerate(PAIRS):
    c = {s: t[(p, 'cudagecko-original', s)] for s in ('word sort', 'hit sort', 'extend', 'other')}
    f = {s: t[(p, 'futhark-gecko', s)] for s in ('word sort', 'hit sort', 'extend', 'other')}
    ct, ft = sum(c.values()), sum(f.values())
    share = 100 * f['word sort'] / ft
    lines.append(f"{label} & cudagecko & {ms(c['word sort'])} & {ms(c['hit sort'])} & {ms(c['extend'])} & {ms(c['other'])} & {ms(ct)} & \\\\")
    lines.append(f" & Futhark & {ms(f['word sort'])} ({share:.0f}\\%) & {ms(f['hit sort'])} & {ms(f['extend'])} & {ms(f['other'])} & {ms(ft)} & {ft/ct:.1f} \\\\")
    if i < len(PAIRS) - 1:
        lines.append(r'\addlinespace')
lines += [r'\bottomrule', r'\end{tabular*}',
          r'\caption{Kernel time per stage in ms, measured with nsys on an NVIDIA A100 PCIe 40GB, one run per program per pair, CPU--GPU copies excluded. Original cudagecko. The percentage is the share of Futhark kernel time spent in word sort. Other covers reverse complement, words, hits and filter, which Futhark compiles into shared kernels.}',
          r'\label{tab:kernel-stages}', r'\end{table}']
open(sys.argv[2], 'w').write('\n'.join(lines) + '\n')
