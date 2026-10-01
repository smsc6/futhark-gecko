# NOTES — GECKO in Futhark

## Environment (reproducibility)
- cudagecko: commit d473f03, branch gpuhits (matches paper ref [27])
- Futhark: 0.25.24
- sorts library (github.com/diku-dk/sorts): 0.7.3
- Hendrix GPU model: TBD (run `nvidia-smi` on GPU node)
- Hendrix CUDA version: TBD (run `nvidia-smi` on GPU node)

## Kernel mapping (CUDA → Futhark)
| cudagecko kernel | Futhark file | Notes |
|---|---|---|

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