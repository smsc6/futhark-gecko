-- HITS: every pair of equal words between the query and the reference
-- Futhark port of scala/hits.scala
--
-- Irregular step: each query word produces a different number of hits
-- Scala uses flatMap; Futhark replaces flatMap with expand (diku-dk/segmented)
-- Hit encoding matches cudagecko: ((ref_len + x - y) << 32) + x, wrapping 64-bit
-- Invalid words: all 64 bits set (u64.highest), same marker as cudagecko
-- Inputs: query and reference words, each sorted by hash (output of sort.fut)
-- Output: one u64 hit per pair of equal valid words, grouped by query word
--
-- Test 1: query word 1 matches 2 reference words, query word 3 (twice) matches 1, invalid word gives no hits
-- Test 2: no equal words, empty output
-- Test 3: first query word has no match, later words still get correct hits
-- Same inputs and expected outputs as the Scala tests
-- ==
-- entry: hits_main
-- input  { [1u64, 3u64, 3u64, 18446744073709551615u64]
--          [10u32, 20u32, 21u32, 4294967295u32]
--          [1u64, 1u64, 3u64, 5u64, 18446744073709551615u64]
--          [5u32, 7u32, 2u32, 9u32, 4294967295u32]
--          100u32 }
-- output { [450971566090u64, 442381631498u64, 506806140948u64, 511101108245u64] }
-- input  { [2u64] [0u32] [1u64, 3u64] [0u32, 1u32] 100u32 }
-- output { empty([0]u64) }
-- input  { [0u64, 1u64, 2u64] [7u32, 8u32, 9u32] [1u64, 1u64, 2u64] [3u32, 4u32, 5u32] 100u32 }
-- output { [450971566088u64, 446676598792u64, 446676598793u64] }

import "lib/github.com/diku-dk/segmented/segmented"

-- | Marker for invalid words (all 64 bits set)
-- Scala: Invalid = -1L
def invalid : u64 = u64.highest

-- | First position in sorted xs with a value >= k (m if none)
-- Scala: lowerBound; recursive go becomes a loop, compareUnsigned becomes a plain < on u64
def lower_bound [m] (xs: [m]u64) (k: u64) : i64 =
  let (lo, _) =
    loop (lo, hi) = (0, m)
    while lo < hi do
      let mid = (lo + hi) / 2
      in if xs[mid] < k then (mid + 1, hi) else (lo, mid)
  in lo

-- | First position in sorted xs with a value > k (m if none)
-- Scala: upperBound; same loop as lower_bound, with <= instead of <
def upper_bound [m] (xs: [m]u64) (k: u64) : i64 =
  let (lo, _) =
    loop (lo, hi) = (0, m)
    while lo < hi do
      let mid = (lo + hi) / 2
      in if xs[mid] <= k then (mid + 1, hi) else (lo, mid)
  in lo

-- | 64-bit hit value, same encoding as cudagecko
-- Scala: hitValue; positions are u32, so convert with u64.u32 before shifting
def hit_value (ref_len: u32) (x: u32) (y: u32) : u64 =
  ((u64.u32 ref_len + u64.u32 x - u64.u32 y) << 32) + u64.u32 x

-- | All hits between sorted query words (qh, qp) and sorted reference words (rh, rp)
-- Invalid query words produce no hits; invalid reference words never match a valid hash
-- Scala: zip and filter port directly
-- Scala: flatMap does not port, because a map cannot return arrays of different lengths
-- Replacement: a map computes each word's matching range (lo, hi), then expand builds the flat array
--   size function: number of hits for a word = hi - lo
--   get function: the i-th hit of a word = hit with reference position rp[lo + i]
def hits [n] [m] (qh: [n]u64) (qp: [n]u32) (rh: [m]u64) (rp: [m]u32) (ref_len: u32) : []u64 =
  zip qh qp
  |> filter (\(h, _) -> h != invalid)
  |> map (\(h, x) -> (x, lower_bound rh h, upper_bound rh h))
  |> expand (\(_, lo, hi) -> hi - lo)
            (\(x, lo, _) i -> hit_value ref_len x rp[lo + i])

-- | Entry point for futhark test and benchmarking
entry hits_main [n] [m] (qh: [n]u64) (qp: [n]u32) (rh: [m]u64) (rp: [m]u32) (ref_len: u32) : []u64 =
  hits qh qp rh rp ref_len