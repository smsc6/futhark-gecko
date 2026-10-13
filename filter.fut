-- FILTER STAGE: remove overlapping hits on the same diagonal
--
-- Matches cudagecko kernel_filter_hits_parallel (kernels.cu, line 70)
-- and the CPU step filter_hits_cpu (cpu_functions.c, line 469)
--
-- Hits are processed in fixed groups of 32 (one CUDA warp in cudagecko)
-- A hit is removed if an earlier kept hit in the same group has the same diagonal and the hit's query position is less than that hit's position + 63
-- Hits in different groups are never compared (matching cudagecko)
-- Output: query positions x and reference  positions y of kept hits
--
--
-- Test 1: diagonal 105 positions 10, 50, 73, 80 keep 10 and 73, diagonal 110 position 20 kept
-- Test 2: 33 hits on one diagonal, positions 0-32: hit 0 kept, hit 32 kept because it starts a new group
-- ==
-- entry: filter_main
-- input  {[450971566090u64, 450971566130u64, 450971566153u64, 450971566160u64, 472446402580u64] 100u32}
-- output {[10u32, 73u32, 20u32] [5u32, 68u32, 10u32]}
-- input  {[429496729600u64, 429496729601u64, 429496729602u64, 429496729603u64, 429496729604u64, 429496729605u64, 429496729606u64, 429496729607u64, 429496729608u64, 429496729609u64, 429496729610u64, 429496729611u64, 429496729612u64, 429496729613u64, 429496729614u64, 429496729615u64, 429496729616u64, 429496729617u64, 429496729618u64, 429496729619u64, 429496729620u64, 429496729621u64, 429496729622u64, 429496729623u64, 429496729624u64, 429496729625u64, 429496729626u64, 429496729627u64, 429496729628u64, 429496729629u64, 429496729630u64, 429496729631u64, 429496729632u64] 100u32}
-- output {[0u32, 32u32] [0u32, 32u32]}


-- | Keep flags for one group of up to 32 hits starting at index lo
-- Hit j is removed if any earlier kept hit i has the same diagonal, and px[j]< px[i] + 63
-- u32 addition wraps on overflow, matching cudagecko
def filter_group [n] (d: [n]u32) (px: [n]u32) (lo: i64)  (len: i64) : [32]bool =
  loop kept = replicate 32 false
  for j < len do
    let removed =
      loop r = false
      for i < j do
        r || (kept[i] && d[lo + i] == d[lo + j] && px[lo + j] < px[lo + i] + 63)
    in kept with [j] = !removed


-- | Remove overlapping hits, split ketp hits into query, and reference positions
-- Input: hits sorted by diagonal, encoded as (diagonal<< 32) + x
def filter_hits [n] (hits: [n]u64) (ref_len: u32) : ([]u32, []u32) =
  let d = map (\v -> u32.u64 (v >> 32)) hits
  let px = map (\v -> u32.u64 v) hits
  let groups = (n + 31) / 32
  let kept =
    map (\g ->
           let lo = g * 32
           in filter_group d px lo (i64.min 32 (n - lo)))
        (iota groups)
    |> flatten
    |> take n


  -- reference position - same as cudagecko
  let py = map2 (\x dd -> ref_len + x - dd) px d



  -- Drop hits with x or y equal to all ones (filter_hits_cpu also )
  let ok = map3 (\k x y -> k && x < u32.highest && y < u32.highest) kept px py
  in zip3 ok px py
     |> filter (.0)
     |> map (\(_, x, y) -> (x, y))
     |> unzip



-- | Entry point for futhark test & benchmarking
entry filter_main [n] (hits: [n]u64) (ref_len: u32) : ([]u32, []u32) =
  filter_hits hits ref_len