# NOTES — GECKO in Futhark

## Environment (reproducibility)
- cudagecko: commit d473f03, branch gpuhits (matches paper ref [27])
- Futhark: 0.25.24
- sorts library (github.com/diku-dk/sorts): 0.7.3
- Hendrix GPU model: TBD (run `nvidia-smi` on GPU node)
- Hendrix CUDA version: TBD (run `nvidia-smi` on GPU node)

## Kernel mapping (CUDA → Futhark)
| cudagecko kernel | line(s) | Futhark file | Notes |
|---|---|---|---|
| kernel_reverse_complement | 280, 306 | revcomp.fut | new file needed |
| kernel_index_global32 | 455, 571 | words.fut | query, then reference |
| (library sort call) | TBD | sort.fut | confirm with grep "sort" |
| kernel_find_leftmost_items | 701 | hits.fut | runs on 1 thread; likely finds start of overlapping key ranges |
| kernel_hits_load_balancing | 734 | hits.fut | match equal words |
| kernel_compact_hits | 791 | hits.fut | remove empty slots |
| kernel_filter_hits_parallel | 916 | filter.fut | new file needed |
| kernel_frags_forward_register | 993 | extend.fut | extend hits into fragments |
| (lines 1099–1498) | — | — | repeat of pipeline for reverse strand |

## Log
### 2026-10-01
- Set up repo smsc6/futhark-gecko on Hendrix
- Created stage files: words, sort, hits, extend, gecko
- Added sorts library
- Cloned cudagecko reference at d473f03 (gpuhits)

## Expressiveness

## Correctness

## Performance

## Compiler limitations