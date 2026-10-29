#!/usr/bin/env python3
"""Reproduce every experiment in the report on a SLURM cluster (written for Hendrix, UCPH).

Usage:  python3 reproduce.py <root>
<root> is an empty working folder (e.g. ~/gecko). The script runs on the login node and only
downloads data, clones cudagecko and submits SLURM jobs; all compute runs inside the jobs.

Steps
 1. Download the 14 sequences (NCBI RefSeq, Ensembl) into <root>/data.
 2. Clone cudagecko at revision d473f03 (the revision cited in the GPUGECKO paper) three times:
    original, bug-fixed (patches/cudagecko-bugfixed.patch) and validation copy
    (patches/cudagecko-validation-copy.patch).
 3. Job "prepare": trim and convert the inputs, build futhark-gecko and the three cudagecko builds.
 4. Validation jobs (report Section 4, Table A1), the end-to-end benchmark (Figure 2, Table A2)
    and the nsys profiles (Table 3), each started only after "prepare" succeeds.
 5. Job "summarize": writes the benchmark summary CSV and the per-stage kernel-time CSV.
"""
import os, sys, subprocess, urllib.request, gzip, shutil

REPO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.expanduser(sys.argv[1]))
OLD_ROOT = '/home/cgf146/gecko'          # path used in the original job scripts
DATA = f'{ROOT}/data'

REFSEQ = ['NC_006360.1', 'NC_021831.1', 'NZ_CP014268.2', 'NZ_CP009789.1']
ENSEMBL = [  # (species folder, file, Ensembl release), as listed in the report, Table A3
    ('gallus_gallus', 'Gallus_gallus.WASHUC2.70.dna.chromosome.18.fa', 70),
    ('meleagris_gallopavo', 'Meleagris_gallopavo.UMD2.dna.chromosome.20.fa', 94),
    ('oryzias_latipes', 'Oryzias_latipes.MEDAKA1.75.dna.chromosome.6.fa', 75),
    ('danio_rerio', 'Danio_rerio.GRCz11.dna.chromosome.25.fa', 102),
    ('sus_scrofa', 'Sus_scrofa.Sscrofa11.1.dna.chromosome.11.fa', 102),
    ('bos_taurus', 'Bos_taurus.UMD3.1.dna.chromosome.12.fa', 94),
    ('homo_sapiens', 'Homo_sapiens.GRCh37.75.dna.chromosome.X.fa', 75),
    ('mus_musculus', 'Mus_musculus.GRCm38.dna.chromosome.X.fa', 102),
    ('homo_sapiens', 'Homo_sapiens.GRCh37.75.dna.chromosome.1.fa', 75),
    ('gorilla_gorilla', 'Gorilla_gorilla.gorGor3.1.75.dna.chromosome.1.fa', 75)]

# Job scripts that produced the report's results, in submission order
VALIDATION = ['2026-10-19_job_4225_', '2026-10-19_job_4234_', '2026-10-19_job_4430_']
BENCHMARK, PROFILE = '2026-10-23_job_8787_', '2026-10-27_job_5677_'

def run(cmd):
    print('+', cmd); subprocess.run(cmd, shell=True, check=True)

def download(url, dest):
    if os.path.exists(dest): return
    print('download', url)
    tmp = dest + '.part'
    with urllib.request.urlopen(url) as r, open(tmp, 'wb') as f: shutil.copyfileobj(r, f)
    if url.endswith('.gz'):
        with gzip.open(tmp, 'rb') as g, open(dest, 'wb') as f: shutil.copyfileobj(g, f)
        os.remove(tmp)
    else:
        os.rename(tmp, dest)

def sbatch(script, after=None):
    dep = f'--dependency=afterok:{":".join(after)} ' if after else ''
    out = subprocess.run(f'sbatch --parsable {dep}{script}', shell=True, check=True,
                         capture_output=True, text=True).stdout.strip().split(';')[0]
    print('submitted', os.path.basename(script), 'as job', out); return out

def job_script(prefix):
    """Copy of a committed job script with the original root replaced by <root>."""
    name = [f for f in os.listdir(f'{REPO}/runs/scripts') if f.startswith(prefix)][0]
    text = open(f'{REPO}/runs/scripts/{name}').read().replace(OLD_ROOT, ROOT)
    path = f'{ROOT}/runs/reproduce/{name}'
    open(path, 'w').write(text); return path

for d in ['refseq', 'ensembl', 'trimmed', 'futhark-input']: os.makedirs(f'{DATA}/{d}', exist_ok=True)
for d in ['logs', 'results', 'reproduce']: os.makedirs(f'{ROOT}/runs/{d}', exist_ok=True)

# 1. Data
for acc in REFSEQ:
    download(f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id={acc}&rettype=fasta&retmode=text',
             f'{DATA}/refseq/{acc}.fasta')
for sp, f, rel in ENSEMBL:
    download(f'https://ftp.ensembl.org/pub/release-{rel}/fasta/{sp}/dna/{f}.gz', f'{DATA}/ensembl/{f}')

# 2. cudagecko sources
if not os.path.isdir(f'{ROOT}/cudagecko'):
    run(f'git clone https://github.com/estebanpw/cudagecko.git {ROOT}/cudagecko && git -C {ROOT}/cudagecko checkout d473f03')
for v in ['bugfixed', 'validation-copy']:
    if not os.path.isdir(f'{ROOT}/cudagecko-{v}'):
        run(f'cp -r {ROOT}/cudagecko {ROOT}/cudagecko-{v} && patch -p5 -d {ROOT}/cudagecko-{v} < {REPO}/patches/cudagecko-{v}.patch')

# 3. Prepare job: trim, convert, build
prep = f'{ROOT}/runs/reproduce/prepare.sh'
open(prep, 'w').write(f"""#!/bin/bash
#SBATCH --job-name=reproduce-prepare
#SBATCH --partition=gpu
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output={ROOT}/runs/logs/%x_%j.out
set -e
module unload cuda; module load cuda/11.8; module load gcc/11.2.0; module load futhark/0.25.8
cd {DATA}
for f in refseq/*.fasta ensembl/*.fa; do
  s=$(basename $f); s=${{s%.fasta}}; s=${{s%.fa}}
  python3 {REPO}/tools/trim_for_full_blocks.py $f trimmed/$s.trimmed.fasta
  python3 {REPO}/tools/fasta_to_futhark.py trimmed/$s.trimmed.fasta futhark-input/$s.trimmed.in
done
# Batched validation input (job 4430): E. coli pair, 2 more bases removed
for s in NZ_CP014268.2 NZ_CP009789.1; do
  python3 - <<PY
seq = ''.join(l.strip() for l in open('trimmed/$s.trimmed.fasta') if not l.startswith('>'))[:-2]
open('trimmed/$s.trimmed-batch1999583.fasta', 'w').write('>$s trimmed-batch1999583\\n' + seq + '\\n')
PY
  python3 {REPO}/tools/fasta_to_futhark.py trimmed/$s.trimmed-batch1999583.fasta futhark-input/$s.trimmed-batch1999583.in
done
mkdir -p {ROOT}/builds/futhark-gecko-cuda
cd {REPO} && futhark pkg sync && futhark cuda -o {ROOT}/builds/futhark-gecko-cuda/gecko gecko.fut
for v in cudagecko cudagecko-bugfixed cudagecko-validation-copy; do make all -C {ROOT}/$v/cuda; done
""")
prep_id = sbatch(prep)

# 4. Validation, benchmark and profiling jobs
val_ids = [sbatch(job_script(p), [prep_id]) for p in VALIDATION]
bench_id = sbatch(job_script(BENCHMARK), [prep_id])
prof_id = sbatch(job_script(PROFILE), [prep_id])

# 5. Summary job
summ = f'{ROOT}/runs/reproduce/summarize.sh'
open(summ, 'w').write(f"""#!/bin/bash
#SBATCH --job-name=reproduce-summarize
#SBATCH --partition=gpu
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output={ROOT}/runs/logs/%x_%j.out
set -e
R={ROOT}/runs/results
python3 {REPO}/tools/summarize_end_to_end_benchmark.py $(ls -d $R/*benchmark-end-to-end*_{bench_id}) $R/benchmark-end-to-end-summary_{bench_id}.csv
python3 {REPO}/tools/summarize_kernel_stages.py $(ls -d $R/*nsys-profile*_{prof_id}) $R/kernel-stage-summary_{prof_id}.csv
""")
sbatch(summ, [bench_id, prof_id])
print(f'\nValidation results: {ROOT}/runs/logs and {ROOT}/runs/results (jobs {", ".join(val_ids)})')
print(f'Benchmark summary (Figure 2, Table A2): {ROOT}/runs/results/benchmark-end-to-end-summary_{bench_id}.csv')
print(f'Kernel times per stage (Table 3): {ROOT}/runs/results/kernel-stage-summary_{prof_id}.csv')
