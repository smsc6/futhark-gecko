# futhark-gecko

GECKO, the seed-and-extend DNA sequence comparison algorithm, implemented in [Futhark](https://futhark-lang.org) and compared with [cudagecko](https://github.com/estebanpw/cudagecko), its hand-written CUDA implementation (Perez-Wohlfeil et al., 2023). This repository holds the code, validation tools, job scripts and result summaries behind the report *GECKO in Futhark: Performance and Expressiveness of a High-Level Data-Parallel Language for GPU Sequence Comparison* (Sabrina Schum, DIKU, 2026).

## Requirements

- SLURM cluster with an NVIDIA GPU (results in the report: NVIDIA A100)
- Modules `cuda/11.8`, `gcc/11.2.0`, `futhark/0.25.8`
- Python 3 (standard library only)
- About 3 GB of disk space for the sequences

## Build

```bash
# Futhark implementation
cd futhark && futhark pkg sync && futhark cuda -o gecko gecko.fut && cd ..

# cudagecko (revision d473f03): original, bug-fixed and validation copy
git clone https://github.com/estebanpw/cudagecko.git && git -C cudagecko checkout d473f03
cp -r cudagecko cudagecko-bugfixed && patch -p5 -d cudagecko-bugfixed < patches/cudagecko-bugfixed.patch
cp -r cudagecko cudagecko-validation-copy && patch -p5 -d cudagecko-validation-copy < patches/cudagecko-validation-copy.patch
for v in cudagecko cudagecko-bugfixed cudagecko-validation-copy; do make all -C $v/cuda; done
```

## Run one comparison

```bash
# Trim the inputs (see Notes) and convert them to Futhark input format
python3 tools/trim_for_full_blocks.py query.fasta query.trimmed.fasta
python3 tools/fasta_to_futhark.py query.trimmed.fasta query.in
python3 tools/trim_for_full_blocks.py ref.fasta ref.trimmed.fasta
python3 tools/fasta_to_futhark.py ref.trimmed.fasta ref.in

# Futhark: batch size in words, then query and reference
mkdir -p futhark_out
( echo 32459520i64; cat query.in ref.in ) | futhark/gecko -e gecko_batched -b > futhark_out/futhark_pipeline_output.bin

# cudagecko with the same batch size
cudagecko/bin/gpu_cuda_workflow -query query.trimmed.fasta -ref ref.trimmed.fasta -dev 0 -ram 4000000000
```

`futhark_pipeline_output.bin` holds eight arrays in Futhark's binary format: kept hit query positions, reference positions, left offsets and right offsets for the forward strand, then the same four for the reverse strand.

## Validate a run against cudagecko

The validation copy writes cudagecko's intermediate arrays into the folder it runs in. Run it on the same inputs, then compare element by element:

```bash
mkdir -p cudagecko_out && cd cudagecko_out
../cudagecko-validation-copy/bin/gpu_cuda_workflow -query ../query.trimmed.fasta -ref ../ref.trimmed.fasta -dev 0 -ram 4000000000
cd ..
python3 tools/compare_pipeline_with_cudagecko.py futhark_out cudagecko_out
```

## Reproduce all results

```bash
git clone -b main https://github.com/smsc6/futhark-gecko.git
python3 futhark-gecko/reproduce.py ~/gecko
```

`reproduce.py` downloads the 14 sequences (NCBI RefSeq and Ensembl, listed in the script and in Table A3 of the report), builds all programs and submits every job with dependencies. The benchmark job takes about 2 hours on an A100, and the profiling and validation jobs under 1 hour together. The script prints where each result is written.

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
| `prototypes/scala/` | Scala prototype used to design the high-level formulation of hits and extend before the Futhark version (not used for results) |
| `reproduce.py` | runs every experiment of the report |

## Notes

- Inputs are trimmed by 1 to 55 bases at the end (`tools/trim_for_full_blocks.py`) so that cudagecko's words kernel never runs a partial last block (bug 1).
- cudagecko is used at revision d473f03, the revision cited in the GPUGECKO paper.
- Hendrix nodes can hold several A100 models and SLURM cannot request one; check `nvidia-smi` in each job log. The report's benchmark ran on an A100 80GB PCIe and the profiles on an A100 PCIe 40GB.
- Hendrix reuses job numbers, so jobs are identified by number and date.
- Job 4362 (batch loop run as one batch) reused cudagecko output from job 4234 by path and is not resubmitted.

## License

GPL-3.0, as cudagecko, which the patches in `patches/` modify. The Futhark libraries in `futhark/lib/` keep their own licenses.

## Citation

Perez-Wohlfeil, E., Trelles, O., Guil, N. (2023). Irregular alignment of arbitrarily long DNA sequences on GPU. *The Journal of Supercomputing* 79, 8699–8728.