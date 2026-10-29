-- GECKO PIPELINE: full GPU pipeline, both strands, same order as cudagecko
--
-- Forward strand: query vs reference
-- Reverse strand: query vs reverse complement of the reference
-- Per strand: words -> sort words -> hits -> sort hits -> filter -> extend
-- Query words are computed and sorted once and used for both strands, as in cudagecko
-- Not included: cudagecko's CPU step filter_and_write_frags (minimum length, CSV output)
--
-- Batching, as in cudagecko gpu_cuda_workflow.cu:
-- Batches do not overlap: each starts where the previous one ended (lines 435, 511)
-- Outer loop over query batches; per query batch, all reference batches on the forward strand,
-- then all reference batches on the reverse strand (lines 525, 1048)
-- Reference words are recomputed for every query batch, as in cudagecko
-- Extend stops at the batch bounds (lines 994-995)
-- Positions are absolute, so hits and filter use the full reference length (line 649)
--
-- Input: query and reference as u8 arrays (Futhark data files from tools/fasta_to_futhark.py)
-- Output per strand: kept hit positions x and y, left and right extension offsets

module revcomp_stage = import "revcomp"
module words_stage = import "words"
module sort_stage = import "sort"
module hits_stage = import "hits"
module filter_stage = import "filter"
module extend_stage = import "extend"


-- | Start and end of batch b; the last batch is shorter if len is not a multiple of batch_size
def batch_bounds (len: i64) (batch_size: i64) (b: i64) : (i64, i64) =
  let start = b * batch_size
  in (start, i64.min len (start + batch_size))


-- | Words of one batch, sorted by hash
-- offset: batch start in the whole sequence, so positions are absolute
-- words_batch returns both arrays with size (l - 31), so sort_words accepts them directly
def sorted_words [l] (s: [l]u8) (offset: i64) : ?[n].([n]u64, [n]u32) =
  let (h, p) = words_stage.words_batch s offset
  in sort_stage.sort_words h p


-- | One strand for one query batch: loop over reference batches, results concatenated in batch order
-- Per reference batch: hits between the query words and the reference words, then sort, filter, extend
-- qh, qp: sorted query words of this query batch; sr: whole reference sequence for this strand
-- filter_hits returns x and y with the same size, so extend accepts them directly
def strand [lq] [lr] [nq] (sq: [lq]u8) (sr: [lr]u8) (batch_size: i64) (q_start: i64) (q_end: i64)
           (qh: [nq]u64) (qp: [nq]u32) : ([]u32, []u32, []u32, []u32) =
  let ref_len = u32.i64 lr
  let r_batches = (lr + batch_size - 1) / batch_size
  in loop (xs_all: []u32, ys_all: []u32, left_all: []u32, right_all: []u32) = ([], [], [], [])
     for b < r_batches do
       let (r_start, r_end) = batch_bounds lr batch_size b
       let (rh, rp) = sorted_words sr[r_start:r_end] r_start
       let sorted_hits = hits_stage.hits qh qp rh rp ref_len |> sort_stage.sort_hits
       let (xs, ys) = filter_stage.filter_hits sorted_hits ref_len
       let (left, right) = extend_stage.extend_batch sq sr q_start r_start q_end r_end xs ys
       in (xs_all ++ xs, ys_all ++ ys, left_all ++ left, right_all ++ right)


-- | Full pipeline with batches of batch_size bases: per query batch, forward strand, then reverse strand
def gecko_batches [lq] [lr] (batch_size: i64) (sq: [lq]u8) (sr: [lr]u8)
    : ([]u32, []u32, []u32, []u32, []u32, []u32, []u32, []u32) =
  let sr_revcomp = revcomp_stage.revcomp sr
  let q_batches = (lq + batch_size - 1) / batch_size
  in loop (fx: []u32, fy: []u32, fl: []u32, fr: []u32, rx: []u32, ry: []u32, rl: []u32, rr: []u32)
       = ([], [], [], [], [], [], [], [])
     for b < q_batches do
       let (q_start, q_end) = batch_bounds lq batch_size b
       let (qh, qp) = sorted_words sq[q_start:q_end] q_start
       let (fx', fy', fl', fr') = strand sq sr batch_size q_start q_end qh qp
       let (rx', ry', rl', rr') = strand sq sr_revcomp batch_size q_start q_end qh qp
       in (fx ++ fx', fy ++ fy', fl ++ fl', fr ++ fr', rx ++ rx', ry ++ ry', rl ++ rl', rr ++ rr')


-- | Full pipeline, one batch (batch size = longer sequence length)
entry gecko [lq] [lr] (sq: [lq]u8) (sr: [lr]u8)
    : ([]u32, []u32, []u32, []u32, []u32, []u32, []u32, []u32) =
  gecko_batches (i64.max 1 (i64.max lq lr)) sq sr


-- | Full pipeline with batch size as the first input, for validating batching against cudagecko
entry gecko_batched [lq] [lr] (batch_size: i64) (sq: [lq]u8) (sr: [lr]u8)
    : ([]u32, []u32, []u32, []u32, []u32, []u32, []u32, []u32) =
  gecko_batches batch_size sq sr