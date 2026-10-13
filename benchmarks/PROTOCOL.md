# Benchmark protocol: Futhark GECKO vs cudagecko

## Purpose
Compare per-stage GPU performance of the Futhark implementation against cudagecko (Perez-Wohlfeil et al., 2023).

## Stages compared
| Stage | cudagecko log lines |
|---|---|
| Reverse complement | `rev comp` |
| Words | `words Q`, `words R`, `words RC` |
| Sort words | `sortwords Q`, `sortwords R`, `sortwords RC` |

cudagecko prints each stage time as `t= <nanoseconds>`.

## Datasets
Source: GPUGECKO paper, Supplementary Material, Table 4. Files on Hendrix in `~/gecko/data` (see `~/gecko/data/README.md`).

| # | Query | Reference |
|---|---|---|
| 1 | refseq/NC_006360.1.fasta | refseq/NC_021831.1.fasta |
| 2 | refseq/NZ_CP014268.2.fasta | refseq/NZ_CP009789.1.fasta |
| 3 | ensembl/Gallus_gallus.WASHUC2.70.dna.chromosome.18.fa | ensembl/Meleagris_gallopavo.UMD2.dna.chromosome.20.fa |
| 4 | ensembl/Oryzias_latipes.MEDAKA1.75.dna.chromosome.6.fa | ensembl/Danio_rerio.GRCz11.dna.chromosome.25.fa |
| 5 | ensembl/Sus_scrofa.Sscrofa11.1.dna.chromosome.11.fa | ensembl/Bos_taurus.UMD3.1.dna.chromosome.12.fa |
| 6 | ensembl/Homo_sapiens.GRCh37.75.dna.chromosome.X.fa | ensembl/Mus_musculus.GRCm38.dna.chromosome.X.fa |
| 7 | ensembl/Homo_sapiens.GRCh37.75.dna.chromosome.1.fa | ensembl/Gorilla_gorilla.gorGor3.1.75.dna.chromosome.1.fa |

## Environment
- Cluster: Hendrix (DIKU), jobs submitted with `sbatch` from gate node `hendrixgate04fl`
- Modules: `cuda/11.8`, `gcc/11.2.0`
- cudagecko binary: `~/gecko/cudagecko/bin/gpu_cuda_workflow` (built from `cuda/Makefile`, no `-arch` flag)

## cudagecko settings
- `-dev 0`
- `-ram 4000000000` (caps GPU memory use at 4 GB; without the cap, CPU memory use exceeds 16 GB on a 24 GB GPU)
- Mode: sensitive (default)
- Minimum alignment length: default (64 bp observed in job 3625 log)

## SLURM settings
- `--partition=gpu`
- `--cpus-per-task=2`
- `--mem=16G`
- All runs in one job, so every run uses the same GPU

## Repetitions
- Per pair, per program: 1 warm-up run (discarded) + 10 timed runs
- Report mean and standard deviation per stage

## Correctness before timing
Futhark output for each stage must match cudagecko output on the same input before timings are compared.

## Output naming
- Logs: `<date>_<program>_<dataset>_<gpu>_<settings>_<jobID>.out`
- Results: `<date>_<program>_<dataset>_<gpu>_<settings>_<jobID>.csv`
- Run records: `~/gecko/runs/README.md`

## Open decisions
- GPU type: A100 or Titan RTX
- Timing scope: include or exclude CPU-to-GPU data transfer

## cudagecko built-in timers (from `cuda/gpu_cuda_workflow.cu`, SHOWTIME)
The `t=` stage times include data copying, not only GPU computation:
- `rev comp` (lines 209–319): CPU copies of both sequences into pinned memory, GPU stream setup, reference copy CPU→GPU, reverse-complement kernel, result copy GPU→CPU.
- `words Q` (lines 417–466): query copy CPU→GPU, clearing the full words buffer (`cudaMemset`, sized for the maximum word count, not the sequence length), words kernel.
- `sortwords Q` (lines 486–501): GPU sort (`mergesort`), sorted keys and values copied GPU→CPU.
Consequence: these times cannot be compared directly to Futhark kernel times. Candidate method: measure cudagecko kernels alone with NVIDIA Nsight Systems (`nsys`).

## Kernel-only timing with nsys
- `nsys profile --stats=true` (NVIDIA Nsight Systems, included in module `cuda/11.8`) reports each GPU kernel's and each copy's time separately (job 3705).
- cudagecko's built-in stage timers are dominated by memory clearing: `[CUDA memset]` took 13.5 ms and cleared 8.1 GB in job 3705.
- Sort kernels (ModernGPU, `mgpu::...`) sort both words and hits; separate them by execution order with `nsys stats --report gputrace`.
- `--gres=gpu:1` assigned a Titan RTX (job 3625) and a Quadro RTX 6000 (job 3705): official runs must request one named GPU type.
