# futhark-gecko

A Futhark implementation of GECKO, a seed-and-extend DNA sequence comparison algorithm, benchmarked against [cudagecko](https://github.com/estebanpw/cudagecko), its hand-written CUDA implementation (Perez-Wohlfeil et al., 2023). Code and results for the report *GECKO in Futhark: Performance and Expressiveness of a High-Level Data-Parallel Language for GPU Sequence Comparison* (Sabrina Schum, DIKU, 2026).

## Requirements

- SLURM cluster with an NVIDIA GPU (the report's results were measured on NVIDIA A100 GPUs)
- Modules `cuda/11.8`, `gcc/11.2.0`, `futhark/0.25.8`
- Python 3 (standard library only)
- About 3 GB of disk space for the sequences

## Build

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

The validation copy of cudagecko writes its intermediate arrays to the working directory. Run it on the same inputs and compare both outputs element by element:

```bash
mkdir -p cudagecko_out && cd cudagecko_out
../cudagecko-validation-copy/bin/gpu_cuda_workflow -query ../query.trimmed.fasta -ref ../ref.trimmed.fasta -dev 0 -ram 4000000000
cd ..
python3 tools/compare_pipeline_with_cudagecko.py futhark_out cudagecko_out
```

## Reproduce the report

```bash
git clone -b main https://github.com/smsc6/futhark-gecko.git
python3 futhark-gecko/reproduce.py ~/gecko
```

`reproduce.py` downloads the 14 sequences from NCBI RefSeq and Ensembl, builds all programs, and submits the validation, benchmark and profiling jobs to SLURM with dependencies between them. The benchmark job runs for about 2 hours on an A100; the validation and profiling jobs take under 1 hour combined.

| Report item | SLURM script | Summary script | Output |
|---|---|---|---|
| Validation (Section 4, Table A1) | `runs/scripts/*job_4225*`, `*job_4234*`, `*job_4430*` | comparison included in each job | job log |
| Figure 2, Table A2 | `runs/scripts/*job_8787*` | `tools/summarize_end_to_end_benchmark.py` | `benchmark-end-to-end-summary_<job>.csv` |
| Table 3 | `runs/scripts/*job_5677*` | `tools/summarize_kernel_stages.py` | `kernel-stage-summary_<job>.csv` |

`results/` contains the summary files from the runs reported in the report.

## Repository layout

| Path | Contents |
|---|---|
| `futhark/` | Futhark implementation, one file per pipeline stage: `revcomp.fut`, `words.fut`, `sort.fut`, `hits.fut`, `filter.fut`, `extend.fut` |
| `futhark/gecko.fut` | Full pipeline with entry points `gecko` (single batch) and `gecko_batched` |
| `futhark/futhark.pkg`, `futhark/lib/` | Futhark package dependencies (`sorts`, `segmented`) |
| `tools/` | Input preparation, comparison with cudagecko, benchmark and profile summaries |
| `patches/` | Changes to cudagecko: bug-fixed build (bugs 2 and 3) and validation copy (writes intermediate arrays) |
| `runs/scripts/` | SLURM scripts of the validation, benchmark and profiling jobs in the report |
| `results/` | Benchmark, profile and validation summaries from the report's runs |
| `benchmarks/PROTOCOL.md` | Benchmark protocol and design decisions |
| `prototypes/scala/` | Scala prototype of the hits and extend stages, written before the Futhark version (not used for results) |
| `reproduce.py` | Runs all experiments in the report |

## Notes

- Each input sequence is trimmed by 1 to 55 bases at its end (`tools/trim_for_full_blocks.py`), so that cudagecko's words kernel never processes a partial final thread block (bug 1 in the report).
- cudagecko is used at revision d473f03, the revision cited in the GPUGECKO paper.
- SLURM cannot request a specific A100 model on Hendrix. The report's benchmark ran on an A100 80GB PCIe and its profiles on an A100 PCIe 40GB; the GPU model of each run is recorded by `nvidia-smi` in the job log.

## License

GPL-3.0, the license of cudagecko, which the files in `patches/` modify. The packages in `futhark/lib/` retain their own licenses.

## Citation

Perez-Wohlfeil, E., Trelles, O., Guil, N. (2023). Irregular alignment of arbitrarily long DNA sequences on GPU. *The Journal of Supercomputing* 79, 8699–8728.