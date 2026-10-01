# NOTES — GECKO in Futhark

## Environment (reproducibility)
- cudagecko: commit d473f03, branch gpuhits (matches paper ref [27])
- Futhark: 0.25.24
- sorts library (github.com/diku-dk/sorts): 0.7.3
- Hendrix GPU model: TBD (run `nvidia-smi` on GPU node)
- Hendrix CUDA version: TBD (run `nvidia-smi` on GPU node)


## Method: finding the stage list
Source: cudagecko `cuda/` folder, commit d473f03 (gpuhits).

1. `grep -n "<<<" gpu_cuda_workflow.cu`
   - `<<<` marks every CUDA kernel launch, so the output lists all GPU stages in execution order.
2. `grep -n "sort" gpu_cuda_workflow.cu`
   - Sorting runs through a library call (moderngpu `mergesort`), not a `<<<` launch, so step 1 missed the sort stages.
3. `grep -n "kernel_reverse_complement" kernels.cu`
   - Finds the line where each kernel's code starts, so the kernel body can be read for porting.
4. `sed -n '1186,1230p' kernels.cu`
   - Prints only the kernel body (lines 1186–1230), avoiding reading the full file.

Result: ordered stage list in the mapping table below. Steps 3–4 repeat per kernel, with the kernel name and line range changed.



## Kernel mapping (CUDA → Futhark)
| cudagecko kernel | line(s) | Futhark file | Notes |
|---|---|---|---|
| kernel_reverse_complement | 280, 306 | revcomp.fut | builds opposite DNA strand |
| kernel_index_global32 | 455, 571 | words.fut | query, then reference |
| mergesort (moderngpu), key-value | 489, 601, 1125 | sort.fut | sort words: key = 64-bit word, value = position |
| kernel_find_leftmost_items | 701 | hits.fut | runs on 1 thread; likely finds start of overlapping key ranges |
| kernel_hits_load_balancing | 734 | hits.fut | match equal words |
| kernel_compact_hits | 791 | hits.fut | remove empty slots |
| mergesort (moderngpu), keys only | 892, 1406 | sort.fut | sort hits by diagonal, before filter |
| kernel_filter_hits_parallel | 916 | filter.fut | remove redundant hits |
| kernel_frags_forward_register | 993 | extend.fut | extend hits into fragments |
| (lines 1099–1498) | — | — | repeat of pipeline for reverse strand |

## Log
### 2026-10-01
- Set up repo smsc6/futhark-gecko on Hendrix
- Created stage files: words, sort, hits, extend, gecko
- Added sorts library
- Cloned cudagecko reference at d473f03 (gpuhits)
- Created revcomp.fut, filter.fut
- Working on `dev` branch; squash-merge finished stages into `main`
- Mapped cudagecko kernels and sort calls (see table)

## Expressiveness

## Correctness

## Performance
- cudagecko prints per-stage timings ([INFO] lines) → compare per stage

## Compiler limitations