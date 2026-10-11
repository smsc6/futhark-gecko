// Hits: every pair of equal words between the query and the reference
// High-level version of cudagecko kernel_find_leftmost_items (kernels.cu, line 153),
// kernel_hits_load_balancing (line 214) and kernel_compact_hits (line 171)
// Irregular step: each query word produces a different number of hits (flatMap)
// Hit encoding matches cudagecko: ((refLen + x - y) << 32) + x, wrapping 64-bit arithmetic
// cudagecko hashes are unsigned 64-bit; Scala Long is signed, so comparisons use compareUnsigned
// Invalid word: all ones, stored as -1L in a Long
// Positions are unsigned 32-bit in cudagecko, stored here in a Long
// Futhark: has native u64 and u32 types, so no signed workaround or compareUnsigned is needed
// Run tests: scala-cli run --server=false hits.scala

object Hits:
  // Futhark: u64.highest
  val Invalid: Long = -1L

  // Index of the first element >= k in sorted xs, unsigned order (xs.length if none)
  // Futhark: ports directly; the tail-recursive go becomes `loop (lo, hi) while lo < hi`
  // Futhark: each binary search runs sequentially inside one parallel task
  def lowerBound(xs: Vector[Long], k: Long): Int =
    @annotation.tailrec
    def go(lo: Int, hi: Int): Int =
      if lo >= hi then lo
      else
        val mid = (lo + hi) / 2
        if java.lang.Long.compareUnsigned(xs(mid), k) < 0 then go(mid + 1, hi) else go(lo, mid)
    go(0, xs.length)

  // Index of the first element > k in sorted xs, unsigned order (xs.length if none)
  // Futhark: ports directly, same as lowerBound
  def upperBound(xs: Vector[Long], k: Long): Int =
    @annotation.tailrec
    def go(lo: Int, hi: Int): Int =
      if lo >= hi then lo
      else
        val mid = (lo + hi) / 2
        if java.lang.Long.compareUnsigned(xs(mid), k) <= 0 then go(mid + 1, hi) else go(lo, mid)
    go(0, xs.length)

  // 64-bit hit value, same encoding as cudagecko
  // Futhark: ports directly; u64 arithmetic wraps the same way
  def hitValue(refLen: Long, x: Long, y: Long): Long =
    ((refLen + x - y) << 32) + x

  // All hits between sorted query words (qh, qp) and sorted reference words (rh, rp)
  // Invalid query words produce no hits; invalid reference words never match a valid hash
  // Futhark: zip and filter port directly
  // Futhark: flatMap does NOT port, because a map cannot return arrays of different lengths
  // Futhark replacement: map gives each word's count (hi - lo), an exclusive scan gives each word's
  // output offset, then expand (diku-dk/segmented) or scan + scatter + scan builds the flat array
  // Futhark: expand's size function = hi - lo, its get function = the i-th hit of that word
  def hits(qh: Vector[Long], qp: Vector[Long], rh: Vector[Long], rp: Vector[Long], refLen: Long): Vector[Long] =
    qh.zip(qp)
      .filter((h, _) => h != Invalid)
      .flatMap((h, x) =>
        (lowerBound(rh, h) until upperBound(rh, h)).map(j => hitValue(refLen, x, rp(j))))

// Tests: hand calculated with cudagecko's hit encoding
// Test 1: query word 1 matches 2 reference words, query word 3 (twice) matches 1, invalid word gives no hits
// Test 2: no equal words, empty output
// Test 3: first query word has no match, later words still get correct hits
// ***FUTHARK***: port as futhark test blocks with the same inputs and expected outputs
@main def testHits(): Unit =
  import Hits.*
  val u64Max = -1L
  val u32Max = 4294967295L
  val t1 = hits(
    Vector(1L, 3L, 3L, u64Max), Vector(10L, 20L, 21L, u32Max),
    Vector(1L, 1L, 3L, 5L, u64Max), Vector(5L, 7L, 2L, 9L, u32Max), 100L)
  assert(t1 == Vector(450971566090L, 442381631498L, 506806140948L, 511101108245L), s"test 1: $t1")
  val t2 = hits(Vector(2L), Vector(0L), Vector(1L, 3L), Vector(0L, 1L), 100L)
  assert(t2.isEmpty, s"test 2: $t2")
  val t3 = hits(
    Vector(0L, 1L, 2L), Vector(7L, 8L, 9L),
    Vector(1L, 1L, 2L), Vector(3L, 4L, 5L), 100L)
  assert(t3 == Vector(450971566088L, 446676598792L, 446676598793L), s"test 3: $t3")
  println("hits: 3 passed")