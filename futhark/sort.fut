--SORT: WORDS BY HAS, HITS BY DIAGONAL
-- Corresponds to cudagecko's moderngpu mergesort calls (gpu_cuda_workflow.cu lines 489, 601, 1125, 892, 1406)
-- Radix sort is stable like mergesort: equal keys keep their input order
-- Invalid words (hash all ones) sort to the end, as in cudagecko
-- 
-- Test 1:  words, equal hashes (1, 1) keep position order 11, then 13
-- Test 2: hits, plain ascending sort
-- ******MORE TESTS******
-- ==
-- entry: sort_words_main
-- input  { [3u64, 1u64, 2u64, 1u64] [10u32, 11u32, 12u32, 13u32] }
-- output { [1u64, 1u64, 2u64, 3u64] [11u32, 13u32, 12u32, 10u32] }

-- ==
-- entry: sort_hits_main
-- input  { [5u64, 2u64, 9u64, 2u64] }
-- output { [2u64, 2u64, 5u64, 9u64] }


-- | Import futhark sort library
import "lib/github.com/diku-dk/sorts/radix_sort"


-- | Sort words by hash, carrying each word's position along
def sort_words [n] (hashes: [n]u64) (positions: [n]u32) : ([n]u64, [n]u32) =
  zip hashes positions  -- ******** REVIEW ******
  |> radix_sort_by_key (.0) u64.num_bits u64.get_bit
  |> unzip


-- | Sort hit diagonals, ascending
def sort_hits [n] (diagonals: [n]u64) : [n]u64 =
  radix_sort u64.num_bits u64.get_bit diagonals


-- | Entry points for futhark test and benchmarking
entry sort_words_main [n] (hashes: [n]u64) (positions: [n]u32) : ([n]u64, [n]u32) =
  sort_words hashes positions

entry sort_hits_main [n] (diagonals: [n]u64) : [n]u64 =
  sort_hits diagonals