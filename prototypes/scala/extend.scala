// EXTEND: grow each hit into an ungapped alignment
//
// Irregular step: each hit extends a different num of 32-base steps
// Hits processed in groups of 32 - inside a group, hits run in order
// A hit is skipped (offsets 0, 0) if it lies on the same diagonal as the previous extended hit
// in its group and inside that hit's alignment
// No chunking: sequence offsets are 0, limits are the sequence lengths
// Input: query positions xs and reference positions ys of filtered hits (output of filter)
// Output: left and right offsets per hit
// 
// Futhark: sequences become [n]u8 arrays instead of Strings; indexing ports directly
// Run tests: scala-cli run --server=false extend.scala

object Extend:
  // Futhark translation: 
  val MinPIdent = 80


  // Matching bases in one 32 base step.  N on either side counts as a mismatch
  // Futhark translation: ports directly as i32.sum - fixed size, so regular
  def idents(sx: String,  sy: String, px: Int, py: Int): Int =
    (0 until 32).count(t =>
      sx(px + t) == sy(py + t) && sx(px + t) != 'N' && sy(py + t) != 'N')


  // Leftmost accepted alignment start for the hit at (x, y) - same rules as left_extend
  // Score starts at 32, each step adds matches minus mismatches, stops at score <= 0 OR seq start
  // Best position updates only if the score improves and identity >=80%
  //
  // Futhark translation: ports directly, tail-recursive go becomes
  // Futhark translation: a different loop count per hit is allowed inside a map (irregular work, not irregular arrays),
  // but threads with short extensions wait for long ones (load imbalance)
  def leftEnd(sx: String, sy: String, x: Int, y: Int): Int =
    @annotation.tailrec
    def go(px: Int, py: Int, score: Int, best: Int, total: Int, bestPos: Int): Int =
      if score <= 0 || px - 32 < 0 || py - 32 < 0 then bestPos
      else
        val nx = px - 32
        val ny = py - 32
        val id = idents(sx, sy, nx, ny)
        val s = score + id - (32 - id)
        val t = total + id
        val p = 100 * t / (x- nx + 16)
        if s > best && p >= MinPIdent then go(nx, ny, s, s, t, nx)
        else go(nx, ny, s, best, t, bestPos) 
    go(x, y, 32, 32, 16, x)



  // Rightmost accepted alignment end for the hit at (x, y), same rules as right_extend
  // Starts after the 32 base hit, stops at score <= 0 or within 32 bases of the sequence end
  // Futhark translation: ports directly, same as leftEnd
  def rightEnd(sx: String, sy: String, x: Int, y: Int): Int =
    @annotation.tailrec
    def go(px: Int, py: Int, score: Int, best: Int, total: Int, bestPos: Int): Int =
      if score <= 0 || px + 32 >= sx.length || py + 32 >= sy.length then bestPos
      else
        val id = idents(sx, sy, px, py)
        val s = score + id - (32 - id)
        val t = total + id
        val p = 100 * t / (px - x + 16)
        val nx = px + 32
        val ny = py + 32
        if s > best && p >= MinPIdent then go(nx, ny, s, s, t, nx)
        else go(nx, ny, s, best, t, bestPos)
    go(x + 32, y + 32, 32, 32, 16, x + 32)



  // Diagonal and alignment range of the last extended hit in a group
  // Futhark tranlstion: a tuple or record {d, x_begin, x_finish}
  final case class Prev(d: Int, xBegin: Int, xFinish: Int)



  // Offsets for one group of up to 32 hits, processed in order (sequential dependency on Prev)
  // Futhark translate: foldLeft becomes 'loop' over j < len, carrying Prev
  // Futhark translate: appending (:+) does NOT port; instead write into a fixed [32] array with in-place update
  // (with [j] = ) - same pattern as filter_group in filter.fut
  def extendGroup(sx: String, sy: String, group: Vector[(Int, Int)]): Vector[(Int, Int)] =
    group

      .foldLeft((Prev(-1, -1, -1), Vector.empty[(Int, Int)])) { case ((prev, out), (x, y)) =>
        val d = x - y
        if prev.d == d && prev.xBegin <= x && x <= prev.xFinish then (prev, out :+ (0, 0))
        else
          val l = leftEnd(sx,  sy, x, y)
          val r = rightEnd(sx, sy, x, y)
          (Prev(d, l, r), out :+ (x - l, r - x))
      }
      ._2


  // Left and right offsets for all hits: groups of 32 are independent (map), then concatenate
  // Futhark translation: grouped(32) becomes map over iota groups with start index g * 32 and length min 32 (n - start)
  // Futhark translation: every group returns a fixed [32] array, so flatten + take n ports directly (regular),
  // same as filter.fut
  def extend(sx: String, sy: String, xs: Vector[Int], ys: Vector[Int]): (Vector[Int], Vector[Int]) =
    xs.zip(ys)
      .grouped(32)
      .toVector
      .map(g => extendGroup(sx, sy, g))
      .flatten
      .unzip

// Tests: expected values from a direct transliation of the cudagecko kernel
// Test 1: identical sequences, hit at 64 extends left to 0 and right to 192 - hit at 100 is skipped
// Test 2: no matching bases, offsets stay at the hit itself (0 left, 32 right)
// Futhark correspondence: port as futhark test blocks, sequences as u8 arrays
@main def testExtend(): Unit = 
  import Extend.*
  val s = "ACGT" * 50
  val t1 = extend(s, s, Vector(64, 100), Vector(64, 100))  
  assert(t1 == (Vector(64, 0), Vector(128, 0)), s"test 1: $t1")
  val t2 = extend("A"*200, "C" * 200, Vector(64), Vector(64))
  assert(t2 == (Vector(0), Vector(32)), s"test 2: $t2")
  println("extend: 2 passed")