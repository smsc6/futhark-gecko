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
- Outputs are not kept: human vs gorilla chr1 writes a 23 GB cudagecko CSV and 14 GB of Futhark output per run (job 4454), so 11 runs per program would fill the disk
- Each run: Futhark output to /dev/null; cudagecko CSV deleted after the run (outside the timed region)

## Correctness before timing
Futhark output for each stage must match cudagecko output on the same input before timings are compared.

## Output naming
- Logs: `<date>_<program>_<dataset>_<gpu>_<settings>_<jobID>.out`
- Results: `<date>_<program>_<dataset>_<gpu>_<settings>_<jobID>.csv`
- Run records: `~/gecko/runs/README.md`

## Open decisions
- GPU type (decided): A100 (NVIDIA A100-PCIE-40GB in job 4454), all runs in one SLURM job
- Timing scope (decided): cudagecko = sum of its built-in stage timers, filterFrags (CPU step) excluded, data copies included (tools/sum_cudagecko_stage_times.py); Futhark = executable -t time, which excludes copying input to the GPU and results back (gecko.c generated code: futhark_new_u8_1d and sync before t_start, results read after t_end) and includes the whole GPU pipeline and all batches; report both scopes, per supervisor
- Difference to report: Futhark keeps all batches on the GPU; cudagecko copies data between CPU and GPU in every batch

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

## Separating sort-words kernels
- One mergesort call launches many mgpu kernels (19 per words sort for the Mycoplasma pair in job 3705).
- A words sort = the block of mgpu kernels directly after each kernel_index_global32 call in the kernel timeline (nsys stats --report gputrace), in the order query, reference, reverse-complemented reference.
- Kernel-only sort-words time = sum of that block's kernel durations. The copy of sorted query words to the CPU (memcpy DtoH directly after the block) is excluded.
- Check: all words-sort and hits-sort blocks together must equal the summed mgpu kernels in the nsys summary.

## Correctness validation
- Tools: futhark-gecko/tools/fasta_to_futhark.py (input), tools/compare_with_cudagecko.py (comparison)
- Reference arrays from ~/gecko/cudagecko-validation-copy (writes reverse complement and sorted query words to files)
- Mycoplasma pair, 2026-10-13 (jobs 3788 and 3807): revcomp identical; words + sort identical except 30 words
- The 30 words are the last word positions of the query; futhark's hashes match hashes recomputed from the sequence, cudagecko's do not (cudagecko bug: kernel_index_global32 threads exit before filling shared memory, so the last block reads never-written bases; see runs/results/2026-10-13_validation_diagnosis_mycoplasma_3807_vs_3788.txt)
- futhark words.fut returns n - 31 words; cudagecko sorts n entries, the extra 31 are all ones (confirmed)
- Pass criterion: identical output, apart from documented cudagecko differences
- E. coli pair, 2026-10-13 (job 3893): revcomp identical; words + sort identical except 15 words
- tools/check_end_of_sequence_words.py predicts the words affected by the cudagecko bug from the kernel's block layout (last block start = 64 * floor((n - 32) / 64); affected word starts max(last block start, n - 62) to n - 32); E. coli: predicted 15, observed exactly these 15, futhark matches the sequence for all
- Validation result: revcomp.fut, words.fut and sort.fut correct on both pairs; all differences explained by the cudagecko end-of-sequence bug
- cudagecko hit counts vary between runs on identical input (Mycoplasma jobs 3625, 3705, 3788, 5001: forward hits 486,866 to 551,788); final alignment counts nearly stable. Validation therefore feeds each futhark stage the exact input cudagecko's stage received in the same run

## cudagecko hits kernel: duplicate hits (bug 2), found 2026-10-19
- kernel_hits_load_balancing processes a range of sorted query words twice (overlapping job ranges); every hit from those words is written twice
- Size of the overlap depends on the GPU (G = 64 x number of SMs) and the sequence length; Mycoplasma on a 142-SM GPU: 134,151 duplicate hits of 551,616
- cudagecko also misses 81 real hits on the trimmed Mycoplasma pair (cause open)
- Correction: the large differences in cudagecko hit counts between earlier runs follow the GPU's SM count (bug 2), not bug 1
- Validation: futhark-gecko is compared stage by stage on cudagecko's own input, and end to end against the validation copy with bugs 2 and 3 fixed
- Benchmarks: against both the original cudagecko (published tool) and a separate build with only the bug 2 and 3 fixes (no validation file output), which does the same work as futhark-gecko; original: ~/gecko/cudagecko/bin/gpu_cuda_workflow, bug-fixed: ~/gecko/cudagecko-bugfixed/bin/gpu_cuda_workflow (see README_bugfixed_build.md there)
- Report with every benchmark: cudagecko's hit count (including duplicates) next to futhark-gecko's, since the extra hits are extra work
- See runs/results/2026-10-19_hits_diagnosis_mycoplasma-trimmed.txt
- Bug 3 (same kernel): cudagecko skips matches when a run of equal reference hashes straddles a 32-word chunk boundary (reference start pointer moved past the run start); trimmed Mycoplasma: 81 missed real hits from 64 query words; futhark finds them
- End-to-end validation (job 4225, trimmed Mycoplasma pair): gecko.fut identical to cudagecko with bugs 2 and 3 fixed, both strands (kept hits and extension offsets)
- End-to-end validation (job 4234, trimmed E. coli pair): gecko.fut identical to cudagecko with bugs 2 and 3 fixed, both strands
- End-to-end validation after adding the batch loop (job 4362, trimmed E. coli pair, one batch): gecko.fut identical to job 4234, both strands
- Batched end-to-end validation (job 4430, trimmed E. coli pair, 3 batches per sequence, batch size 1,999,583 = cudagecko -ram 344807544): gecko_batched identical to cudagecko with bugs 2 and 3 fixed, both strands; input 2 bases shorter than the trimmed files so every batch is full 64-word blocks (avoids bug 1)
