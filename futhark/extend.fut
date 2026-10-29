-- EXTEND: grow each hit into an ungapped alignment
-- Futhark port of scala/extend.scala
--
-- Irregular step: each hit extends a different number of 32-base steps
-- Futhark allows different loop counts inside a map (irregular work, not irregular arrays)
-- Hits processed in groups of 32; inside a group, hits run in order
-- A hit is skipped (offsets 0, 0) if it lies on the same diagonal as the previous extended hit
-- in its group and inside that hit's alignment
-- *** XXX *** No chunking: sequence offsets are 0, limits are the sequence lengths
-- Inputs: query sequence sx, reference sequence sy (u8 bytes), hit positions xs and ys (output of filter.fut)
-- Output: left and right offsets per hit
--
-- Test 1: identical sequences (ACGT x 50), hit at 64 extends left to 0 and right to 192; hit at 100 is skipped
-- Test 2: no matching bases (A x 200 vs C x 200), offsets stay at the hit itself (0 left, 32 right)
-- Same inputs and expected outputs as the Scala tests
-- Tests use extend_repeat_main, which builds each sequence by repeating a short pattern,
-- so the 200-base sequences fit in the test block
-- ==
-- entry: extend_repeat_main
-- input  { [65u8, 67u8, 71u8, 84u8] [65u8, 67u8, 71u8, 84u8] 50i64 [64u32, 100u32] [64u32, 100u32] }
-- output { [64u32, 0u32] [128u32, 0u32] }
-- input  { [65u8] [67u8] 200i64 [64u32] [64u32] }
-- output { [0u32] [32u32] }

-- | Minimum identity (%) for an alignment end point to be accepted
-- Scala: MinPIdent
def min_p_ident : i32 = 80

-- | Matching bases in one 32-base step; N on either side counts as a mismatch
-- Scala: idents; count becomes i32.sum over a map, fixed size 32, so regular
def idents [lx] [ly] (sx: [lx]u8) (sy: [ly]u8) (px: i64) (py: i64) : i32 =
  i32.sum (map (\t ->
                  let a = sx[px + t]
                  let b = sy[py + t]
                  in if a == b && a != 'N' && b != 'N' then 1 else 0)
               (iota 32))

-- | Leftmost accepted alignment start for the hit at (x, y), same rules as cudagecko left_extend
-- Score starts at 32, each step adds matches minus mismatches, stops at score <= 0 or batch start
-- Best position updates only if the score improves and identity >= 80%
-- Scala: leftEnd; tail-recursive go becomes a while loop carrying the same six values
def left_end [lx] [ly] (sx: [lx]u8) (sy: [ly]u8) (x_off: i64) (y_off: i64) (x: i64) (y: i64): i64 =
  let (_, _, _, _, _, best_pos) =
    loop (px, py, score, best, total, best_pos) = (x, y, 32i32, 32i32, 16i32, x)
    while score > 0 && px - 32 >= x_off && py - 32 >= y_off do
      let nx = px - 32
      let ny = py - 32
      let id = idents sx sy nx ny
      let s = score + id - (32 - id)
      let t = total + id
      let p = 100 * t / i32.i64 (x - nx + 16)
      in if s > best && p >= min_p_ident
         then (nx, ny, s, s, t, nx)
         else (nx, ny, s, best, t, best_pos)
  in best_pos

-- | Rightmost accepted alignment end for the hit at (x, y), same rules as cudagecko right_extend
-- Starts after the 32-base hit, stops at score <= 0 or within 32 bases of the batch end
-- Scala: rightEnd; same while loop as left_end, moving right
def right_end [lx] [ly] (sx: [lx]u8) (sy: [ly]u8) (x_lim: i64) (y_lim: i64) (x: i64) (y: i64) : i64 =
  let (_, _, _, _, _, best_pos) =
    loop (px, py, score, best, total, best_pos) = (x + 32, y + 32, 32i32, 32i32, 16i32, x + 32)
    while score > 0 && px + 32 < x_lim && py + 32 < y_lim do
      let id = idents sx sy px py
      let s = score + id - (32 - id)
      let t = total + id
      let p = 100 * t / i32.i64 (px - x + 16)
      let nx = px + 32
      let ny = py + 32
      in if s > best && p >= min_p_ident
         then (nx, ny, s, s, t, nx)
         else (nx, ny, s, best, t, best_pos)
  in best_pos

-- | Diagonal and alignment range of the last extended hit in a group
-- Scala: Prev case class becomes a record
type prev = {d: i64, x_begin: i64, x_finish: i64}

-- | Offsets for one group of up to 32 hits starting at index lo, processed in order
-- Sequential dependency: each hit's skip check uses the previous extended hit
-- Scala: extendGroup; foldLeft becomes a loop over j < len, carrying prev
-- Scala: appending (:+) does not port; output is a fixed [32] array filled with in-place updates (with [j] = ...)
-- Same pattern as filter_group in filter.fut
def extend_group [lx] [ly] [n]
                 (sx: [lx]u8)
                 (sy: [ly]u8)
                 (x_off: i64) (y_off: i64) (x_lim: i64) (y_lim: i64) -- for batching
                 (xs: [n]i64)
                 (ys: [n]i64)
                 (lo: i64)
                 (len: i64) : [32](u32, u32) =
  let start: prev = {d = -1, x_begin = -1, x_finish = -1}
  let (_, out) =
    loop (p: prev, out) = (start, replicate 32 (0u32, 0u32))
    for j < len do
      let x = xs[lo + j]
      let y = ys[lo + j]
      let d = x - y
      in if p.d == d && p.x_begin <= x && x <= p.x_finish
         then (p, out with [j] = (0, 0))
         else let l = left_end sx sy x_off y_off x y
              let r = right_end sx sy x_lim y_lim x y
              in ({d = d, x_begin = l, x_finish = r}, out with [j] = (u32.i64 (x - l), u32.i64 (r - x)))
  in out

-- | Left and right offsets for all hits: groups of 32 are independent (map), then concatenated
-- Scala: grouped(32) becomes a map over group numbers; group g starts at g * 32 with length min 32 (n - g * 32)
-- Scala: every group returns a fixed [32] array, so flatten + take n ports directly (regular), same as filter.fut
-- Batch bounds x_off, y_off (start) and x_lim, y_lim (end): alignments stop at the batch bounds, as in cudagecko
def extend_batch [lx] [ly] [n] (sx: [lx]u8) (sy: [ly]u8) (x_off: i64) (y_off: i64) (x_lim: i64) (y_lim: i64)
                 (xs: [n]u32) (ys: [n]u32) : ([n]u32, [n]u32) =
  let xs' = map i64.u32 xs
  let ys' = map i64.u32 ys
  let groups = (n + 31) / 32
  in map (\g ->
            let lo = g * 32
            in extend_group sx sy x_off y_off x_lim y_lim xs' ys' lo (i64.min 32 (n - lo)))
         (iota groups)
     |> flatten
     |> take n
     |> unzip

-- | Unbatched case: the whole sequences are one batch (offsets 0, limits the sequence lengths)
def extend [lx] [ly] [n] (sx: [lx]u8) (sy: [ly]u8) (xs: [n]u32) (ys: [n]u32) : ([n]u32, [n]u32) =
  extend_batch sx sy 0 0 lx ly xs ys

-- | Entry point for benchmarking: sequences passed in directly
entry extend_main [lx] [ly] [n] (sx: [lx]u8) (sy: [ly]u8) (xs: [n]u32) (ys: [n]u32) : ([n]u32, [n]u32) =
  extend sx sy xs ys

-- | Entry point for tests: builds each sequence by repeating a short pattern reps times
entry extend_repeat_main [n] (px: []u8) (py: []u8) (reps: i64) (xs: [n]u32) (ys: [n]u32) : ([n]u32, [n]u32) =
  extend (flatten (replicate reps px)) (flatten (replicate reps py)) xs ys