# futhark-gecko

A Futhark implementation of GECKO, a seed-and-extend DNA sequence comparison algorithm, benchmarked against [cudagecko](https://github.com/estebanpw/cudagecko), its hand-written CUDA implementation (Perez-Wohlfeil et al., 2023). Developed by Sabrina Schum as an MSc project at DIKU, University of Copenhagen (2026).

## Results

All numbers come from the files in `results/`, measured on NVIDIA A100 GPUs.

### Correctness

Futhark's output is identical to the cudagecko validation copy's on both strands for Mycoplasma, E. coli, and E. coli split into batches (jobs 4225, 4234 and 4430).

### End-to-end runtime

Mean of 10 timed runs, job 8787:

| Sequence pair | Futhark (s) | cudagecko (s) | cudagecko, bug-fixed (s) | Futhark / cudagecko |
|---|---|---|---|---|
| Mycoplasma | 0.026 | 0.021 | 0.021 | 1.24 |
| E. coli | 0.108 | 0.077 | 0.078 | 1.41 |
| Gallus vs Meleagris | 0.178 | 0.148 | 0.145 | 1.20 |
| Oryzias vs Danio | 1.154 | 1.046 | 1.044 | 1.10 |
| Sus vs Bos | 3.343 | 1.574 | 1.552 | 2.12 |
| Human vs mouse chrX | 16.433 | 8.615 | 8.509 | 1.91 |
| Human vs gorilla chr1 | 43.824 | 43.144 | 43.859 | 1.02 |

Futhark's time is the executable's own runtime measurement, which excludes copying input to the GPU and results back. cudagecko's time is the sum of its built-in stage timers, which include data copies and exclude its final CPU filtering step. `benchmarks/PROTOCOL.md` describes both methods.

### GPU kernel time per stage

Measured with the NVIDIA Nsight Systems profiler (nsys), job 5677:
- Sorting (word sort and hit sort) accounts for 74–92% of Futhark's kernel time on all 7 pairs.
- Hit generation is cudagecko's largest stage on the 5 largest pairs.

## Requirements

- SLURM cluster with an NVIDIA GPU (all results were measured on NVIDIA A100 GPUs)
- Modules `cuda/11.8`, `gcc/11.2.0`, `futhark/0.25.8`
- Python 3 (standard library only)

## Usage

```bash
python3 run_futhark_gecko.py query.fasta reference.fasta -o results
```

On a SLURM login node, `run_futhark_gecko.py` submits itself as a one-GPU job, loads the modules above and returns the job number. Inside a SLURM job, or with `--local`, it runs directly. The first run compiles `futhark/gecko.fut` into `build/<backend>/gecko`; later runs reuse the build until a `.fut` file changes.

| Option | Default | Effect |
|---|---|---|
| `--batch-size` | 32459520 | Bases per batch; 32459520 fits a 40 GB GPU |
| `--min-length` | 0 | Write only alignments of at least this many bases |
| `--backend` | `cuda` | Futhark backend: `cuda`, `opencl`, `multicore` or `c` |
| `--local` | off | Run here instead of submitting a SLURM job |
| `--partition`, `--time`, `--mem` | `gpu`, `06:00:00`, `32G` | SLURM job settings |
| `--modules` | `cuda/11.8 gcc/11.2.0 futhark/0.25.8` | Modules loaded in the SLURM job; `""` for none |

Output in the `-o` folder:

| File | Contents |
|---|---|
| `alignments.csv` | One row per ungapped alignment: `strand`, `query_start`, `query_end`, `ref_start`, `ref_end`, `length`. Positions are 0-based with exclusive ends; reference positions are on the forward strand for both strands |
| `futhark_pipeline_output.bin` | Raw output: query positions, reference positions, left offsets and right offsets of the kept hits, forward strand then reverse strand, in Futhark's binary format |
| `runtime_microseconds.txt` | Pipeline runtime measured by the Futhark executable, excluding input and output copies |
| `gecko_<job>.log` | SLURM log, when submitted as a job |

## Validate against cudagecko

Build cudagecko at revision d473f03 with the validation patch. The validation copy has bugs 2 and 3 fixed (see cudagecko bugs below) and writes its intermediate arrays to the folder it runs from. It appends to these files once per batch, so each run needs a new, empty folder. Trim both inputs (see Notes), then run both programs inside a SLURM job with one GPU and compare their outputs element by element:

```bash
srun --partition=gpu --gres=gpu:1 --pty bash
module unload cuda && module load cuda/11.8 gcc/11.2.0 futhark/0.25.8

git clone https://github.com/estebanpw/cudagecko.git && git -C cudagecko checkout d473f03
cp -r cudagecko cudagecko-validation-copy && patch -p5 -d cudagecko-validation-copy < patches/cudagecko-validation-copy.patch
make all -C cudagecko-validation-copy/cuda

python3 tools/trim_for_full_blocks.py query.fasta query.trimmed.fasta
python3 tools/trim_for_full_blocks.py ref.fasta ref.trimmed.fasta
python3 run_futhark_gecko.py query.trimmed.fasta ref.trimmed.fasta -o futhark_out --local

mkdir cudagecko_out && cd cudagecko_out
../cudagecko-validation-copy/bin/gpu_cuda_workflow -query ../query.trimmed.fasta -ref ../ref.trimmed.fasta -dev 0 -ram 4000000000
cd ..
python3 tools/compare_pipeline_with_cudagecko.py futhark_out cudagecko_out
```

The bug-fixed build used in the benchmarks is made the same way with `patches/cudagecko-bugfixed.patch`.

## Experiments

| Experiment | SLURM script | Output |
|---|---|---|
| Validation | `*job_4225*`, `*job_4234*`, `*job_4430*` | `*_pipeline_comparison_*_<job>.txt` |
| End-to-end runtime | `*job_8787*` | `benchmark-end-to-end-summary_<job>.csv` |
| Kernel time per stage | `*job_5677*` | `kernel-stage-summary_<job>.csv` |

The SLURM scripts in `runs/scripts/` are the scripts of the original runs, with their original absolute paths. The validation jobs run `tools/compare_pipeline_with_cudagecko.py`. The benchmark and profile summaries come from `tools/summarize_end_to_end_benchmark.py` and `tools/summarize_kernel_stages.py`. `results/` contains the outputs of the original runs. Each file name ends with the SLURM job number, except one early Mycoplasma comparison file.

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
| `run_futhark_gecko.py` | Compares two FASTA files and writes the alignments |

## Notes

- Each input sequence is trimmed at its end so that (length − 31) is a multiple of 64 (`tools/trim_for_full_blocks.py`). This ensures that cudagecko's words kernel never processes a partial final thread block (bug 1).
- cudagecko is used at revision d473f03, the revision cited in Perez-Wohlfeil et al. (2023).
- SLURM on Hendrix cannot request a specific A100 model, and node hendrixgpu14fl holds both A100 80GB PCIe and A100 PCIe 40GB cards. The benchmark job (8787) ran on an A100 80GB PCIe. The profiling job (5677) ran on an A100 PCIe 40GB, although its script name records the 80GB card. `nvidia-smi` records the GPU model of each run in the job log.

## License

GPL-3.0, the license of cudagecko, which the files in `patches/` modify. The packages in `futhark/lib/` retain their own licenses.

## Citation

Perez-Wohlfeil, E., Trelles, O., Guil, N. (2023). Irregular alignment of arbitrarily long DNA sequences on GPU. *The Journal of Supercomputing* 79(8), 8699–8728. https://doi.org/10.1007/s11227-022-05007-z
