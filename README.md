# futhark-gecko

GECKO, the seed-and-extend DNA sequence comparison algorithm, implemented in [Futhark](https://futhark-lang.org) and compared with [cudagecko](https://github.com/estebanpw/cudagecko), its hand-written CUDA implementation (Perez-Wohlfeil et al., 2023). This repository holds the code, validation tools, job scripts and result summaries behind the report *GECKO in Futhark: Performance and Expressiveness of a High-Level Data-Parallel Language for GPU Sequence Comparison* (Sabrina Schum, DIKU, 2026).

## Reproduce all results

On a SLURM cluster with the modules `cuda/11.8`, `gcc/11.2.0` and `futhark/0.25.8` (written for Hendrix, UCPH):

```bash
git clone -b main https://github.com/smsc6/futhark-gecko.git
python3 futhark-gecko/reproduce.py ~/gecko
```

`reproduce.py` downloads the data, clones and patches cudagecko, and submits all jobs with dependencies, so one command runs everything. It prints where each result is written.

| Report item | Produced by | Output |
|---|---|---|
| Validation (Section 4, Table A1) | jobs from `runs/scripts/*4225*`, `*4234*`, `*4430*` | comparison printed in each job log |
| Figure 2, Table A2 | `runs/scripts/*8787*` + `tools/summarize_end_to_end_benchmark.py` | `benchmark-end-to-end-summary_<job>.csv` |
| Table 3 | `runs/scripts/*5677*` + `tools/summarize_kernel_stages.py` | `kernel-stage-summary_<job>.csv` |

The summaries from the report's own runs are in `results/`.

## Repository layout

| Path | Contents |
|---|---|
| `futhark/` | Futhark implementation: `revcomp.fut`, `words.fut`, `sort.fut`, `hits.fut`, `filter.fut`, `extend.fut`, one file per stage |
| `futhark/gecko.fut` | full pipeline; entry points `gecko` (one batch) and `gecko_batched` |
| `futhark/futhark.pkg`, `futhark/lib/` | Futhark packages (`sorts`, `segmented`) |
| `tools/` | input preparation, comparison with cudagecko, result summaries |
| `patches/` | cudagecko changes: bug-fixed build (bugs 2 and 3) and validation copy (writes intermediate arrays) |
| `runs/scripts/` | the exact SLURM scripts of the jobs reported |
| `results/` | small result summaries from those jobs |
| `benchmarks/PROTOCOL.md` | benchmark protocol and decisions |

## Notes

- Inputs are trimmed by 1 to 55 bases at the end (`tools/trim_for_full_blocks.py`) so that cudagecko's words kernel never runs a partial last block (bug 1).
- cudagecko is used at revision d473f03, the revision cited in the GPUGECKO paper.
- Hendrix nodes can hold several A100 models and SLURM cannot request one; check `nvidia-smi` in each job log. The report's benchmark ran on an A100 80GB PCIe and the profiles on an A100 PCIe 40GB.
- Hendrix reuses job numbers, so jobs are identified by number and date.
- Job 4362 (batch loop run as one batch) reused cudagecko output from job 4234 by path and is not resubmitted.

## Cite

Perez-Wohlfeil, E., Trelles, O., Guil, N. (2023). Irregular alignment of arbitrarily long DNA sequences on GPU. *The Journal of Supercomputing* 79, 8699–8728.
