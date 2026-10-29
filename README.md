# futhark-gecko

A Futhark implementation of GECKO, a seed-and-extend DNA sequence comparison algorithm, benchmarked against [cudagecko](https://github.com/estebanpw/cudagecko), its hand-written CUDA implementation (Perez-Wohlfeil et al., 2023). Developed by Sabrina Schum as an MSc project at DIKU, University of Copenhagen (2026).


## Results

All numbers come from the files in `results/`, measured on NVIDIA A100 GPUs.

**Correctness.** Futhark's output is identical to the cudagecko validation copy's on both strands for Mycoplasma, E. coli, and E. coli split into batches (jobs 4225, 4234 and 4430).

**End-to-end runtime** (mean of 10 timed runs, job 8787):

| Sequence pair | Futhark (s) | cudagecko, original (s) | cudagecko, bug-fixed (s) | Futhark / original |
|---|---|---|---|---|
| Mycoplasma | 0.026 | 0.021 | 0.021 | 1.24 |
| E. coli | 0.108 | 0.077 | 0.078 | 1.41 |
| Gallus vs Meleagris | 0.178 | 0.148 | 0.145 | 1.20 |
| Oryzias vs Danio | 1.154 | 1.046 | 1.044 | 1.10 |
| Sus vs Bos | 3.343 | 1.574 | 1.552 | 2.12 |
| Human vs mouse chrX | 16.433 | 8.615 | 8.509 | 1.91 |
| Human vs gorilla chr1 | 43.824 | 43.144 | 43.859 | 1.02 |

Futhark's time is the executable's own runtime measurement, which excludes copying input to the GPU and results back. cudagecko's time is the sum of its built-in stage timers, which include data copies and exclude its final CPU filtering step. `benchmarks/PROTOCOL.md` describes both methods.

**GPU kernel time per stage** (job 5677):
- Sorting (word sort and hit sort) accounts for 74–92% of Futhark's kernel time on all 7 pairs.
- Hit generation is cudagecko's largest stage on the 5 largest pairs.


## Requirements

- SLURM cluster with an NVIDIA GPU (all results were measured on NVIDIA A100 GPUs)
- Modules `cuda/11.8`, `gcc/11.2.0`, `futhark/0.25.8`
- Python 3 (standard library only)

## Build

Run the Build, Compare and Validate commands inside a SLURM job with one GPU, not on a login node:

```bash
srun --partition=gpu --gres=gpu:1 --pty bash
module unload cuda && module load cuda/11.8 gcc/11.2.0 futhark/0.25.8
```

```bash
# Futhark implementation
cd futhark && futhark pkg sync && futhark cuda -o gecko gecko.fut && cd ..

# cudagecko at revision d473f03: original, bug-fixed build and validation copy
git clone https://github.com/estebanpw/cudagecko.git && git -C cudagecko checkout d473f03
cp -r cudagecko cudagecko-bugfixed && patch -p5 -d cudagecko-bugfixed < patches/cudagecko-bugfixed.patch
cp -r cudagecko cudagecko-validation-copy && patch -p5 -d cudagecko-validation-copy < patches/cudagecko-validation-copy.patch
for v in cudagecko cudagecko-bugfixed cudagecko-validation-copy; do make all -C $v/cuda; done
```

## Compare two sequences

```bash
# Trim each sequence (see Notes) and convert it to Futhark's input format
python3 tools/trim_for_full_blocks.py query.fasta query.trimmed.fasta
python3 tools/fasta_to_futhark.py query.trimmed.fasta query.in
python3 tools/trim_for_full_blocks.py ref.fasta ref.trimmed.fasta
python3 tools/fasta_to_futhark.py ref.trimmed.fasta ref.in

# Futhark: batch size in words, followed by the query and reference sequences
mkdir -p futhark_out
( echo 32459520i64; cat query.in ref.in ) | futhark/gecko -e gecko_batched -b > futhark_out/futhark_pipeline_output.bin

# cudagecko, with the memory limit that gives the same batch size
cudagecko/bin/gpu_cuda_workflow -query query.trimmed.fasta -ref ref.trimmed.fasta -dev 0 -ram 4000000000
```

`futhark_pipeline_output.bin` contains eight arrays in Futhark's binary format: query positions, reference positions, left offsets and right offsets of the kept hits on the forward strand, followed by the same four arrays for the reverse strand.

## Validate against cudagecko

The validation copy of cudagecko has bugs 2 and 3 fixed (see cudagecko bugs below) and writes its intermediate arrays to the folder it runs from. It appends to these files once per batch, so each run needs a new, empty folder. Run it on the same inputs and compare both outputs element by element:

```bash
mkdir cudagecko_out && cd cudagecko_out
../cudagecko-validation-copy/bin/gpu_cuda_workflow -query ../query.trimmed.fasta -ref ../ref.trimmed.fasta -dev 0 -ram 4000000000
cd ..
python3 tools/compare_pipeline_with_cudagecko.py futhark_out cudagecko_out
```

## Reproduce all results

Run on a login node. `reproduce.py` only downloads data and submits jobs; all computation runs inside SLURM jobs.

```bash
git clone -b main https://github.com/smsc6/futhark-gecko.git
python3 futhark-gecko/reproduce.py ~/gecko
```

`reproduce.py` downloads the 14 sequences from NCBI RefSeq and Ensembl, then submits jobs to SLURM in dependency order:
1. A preparation job trims and converts the inputs and builds all programs.
2. The validation, benchmark and profiling jobs start after the preparation job succeeds.
3. A summary job runs after the benchmark and profiling jobs finish.

Time limits from the job scripts are 15 minutes per validation job, 6 hours for the benchmark job and 45 minutes for the profiling job.

| Experiment | SLURM script | Summary script | Output |
|---|---|---|---|
| Validation: Futhark output compared element by element with the cudagecko validation copy (Mycoplasma, E. coli, batched E. coli) | `runs/scripts/*job_4225*`, `*job_4234*`, `*job_4430*` | `tools/compare_pipeline_with_cudagecko.py`, called in each job | `runs/results/*_pipeline_comparison_*_<job>.txt` |
| End-to-end runtime of Futhark, original cudagecko and bug-fixed cudagecko, and cudagecko's hit count before filtering; 7 sequence pairs, 10 timed runs each | `runs/scripts/*job_8787*` | `tools/summarize_end_to_end_benchmark.py` | `runs/results/benchmark-end-to-end-summary_<job>.csv` |
| GPU kernel time per pipeline stage, measured with the NVIDIA Nsight Systems profiler (nsys); 7 sequence pairs | `runs/scripts/*job_5677*` | `tools/summarize_kernel_stages.py` | `runs/results/kernel-stage-summary_<job>.csv` |

`results/` contains the benchmark summary, the kernel-stage summary and the validation comparison files from the original runs. Each file name ends with the SLURM job number, except one early Mycoplasma comparison file.

## cudagecko bugs

Three bugs in cudagecko d473f03 were found while validating the Futhark implementation:

1. **Partial final block in the words kernel** (`kernel_index_global32`). Threads past the last word exit before copying their base into shared memory, so the last block of a sequence reads never-written shared memory and produces wrong words at the sequence end. This bug is avoided by trimming the inputs (see Notes), not patched.
2. **Overlapping job ranges in hit generation** (`kernel_hits_load_balancing`). Jobs after the first half of the grid use half-size ranges whose start positions overlap the full-size ranges, so some query words are processed twice and their hits are duplicated.
3. **Skipped matches in hit generation** (`kernel_hits_load_balancing`). When the scan for one query word stops, the reference start pointer moves to the current 32-word chunk, so the next query word skips its matches before that chunk boundary.

`patches/cudagecko-bugfixed.patch` fixes bugs 2 and 3 and is used for the bug-fixed benchmark runs.

## Repository layout

| Path | Contents |
|---|---|
| `futhark/` | Futhark implementation, one file per pipeline stage: `revcomp.fut`, `words.fut`, `sort.fut`, `hits.fut`, `filter.fut`, `extend.fut` |
| `futhark/gecko.fut` | Full pipeline with entry points `gecko` (single batch) and `gecko_batched` |
| `futhark/futhark.pkg`, `futhark/lib/` | Futhark package dependencies (`sorts`, `segmented`) |
| `tools/` | Input preparation, comparison with cudagecko, benchmark and profile summaries |
| `patches/` | Changes to cudagecko: bug-fixed build (bugs 2 and 3) and validation copy (bugs 2 and 3 fixed, writes intermediate arrays) |
| `runs/scripts/` | SLURM scripts of the validation, benchmark and profiling jobs |
| `results/` | Benchmark, profile and validation summaries from the original runs |
| `benchmarks/PROTOCOL.md` | Benchmark protocol and design decisions |
| `prototypes/scala/` | Scala prototype of the hits and extend stages, written before the Futhark version (not used for results) |
| `reproduce.py` | Runs all experiments |

## Notes

- Each input sequence is trimmed at its end so that (length − 31) is a multiple of 64 (`tools/trim_for_full_blocks.py`). This ensures that cudagecko's words kernel never processes a partial final thread block (bug 1).
- cudagecko is used at revision d473f03, the revision cited in Perez-Wohlfeil et al. (2023).
- SLURM on Hendrix cannot request a specific A100 model, and node hendrixgpu14fl holds both A100 80GB PCIe and A100 PCIe 40GB cards. The benchmark job (8787) ran on an A100 80GB PCIe. The profiling job (5677) ran on an A100 PCIe 40GB, although its script name records the 80GB card. `nvidia-smi` records the GPU model of each run in the job log.

## License

GPL-3.0, the license of cudagecko, which the files in `patches/` modify. The packages in `futhark/lib/` retain their own licenses.

## Citation

Perez-Wohlfeil, E., Trelles, O., Guil, N. (2023). Irregular alignment of arbitrarily long DNA sequences on GPU. *The Journal of Supercomputing* 79(8), 8699–8728. https://doi.org/10.1007/s11227-022-05007-z