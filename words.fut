-- EVERY 32-BASE WORD AND ITS START POSITION
-- Matches cudagecko kernel_index_global32 (kernels.cu, line 1086)
-- other characters (including lowercase) count as A;
-- cudagecko's `offset` (chunk start) is 0 here: no chunking
--
-- Test 1: 32×A then C → base 31 lands in bits 62-63
-- Test 2: 32×A then N → word with N is invalid (all ones)
-- ******MORE TESTS******
-- ==
-- input  { [65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,
--           65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,67u8] }
-- output { [0u64, 4611686018427387904u64] [0u32, 1u32] }
-- input  { [65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,
--           65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,65u8,78u8] }
-- output { [0u64, 18446744073709551615u64] [0u32, 4294967295u32] }


-- | 2-bit code of on base - characters other than C, G, T give 0 (same as A)
def base_code (c: u8) :  u64 =
  if c == 'C' then 1
  else if c == 'G' then 2
  else if c == 'T' then 3
  else 0


-- |  Hash and position of the 32-base word, starting at position i
-- Words containing 'N' return all ones for both values
def word_at [n] (s: [n]u8) (i: i64) : (u64, u32) =
  let (hash, bad) =
    loop (hash, bad) = (0u64, false) for k < 32 do
      let c = s[i + k]
      in (hash | (base_code c << (2 * u64.i64 k)), bad ||c == 'N')
  in if bad then (u64.highest, u32.highest)
     else (hash, u32.i64 i)


-- | Hashes and positions of all words in s
-- Number of words = n - 31 (no word starts within the last 31 positions)
def words [n] (s: [n]u8) : ([]u64, []u32) = 
unzip (map (word_at s) (iota (i64.max 0 (n - 31))))


-- | Entry point for futhark test and benchmarking
entry main (s: []u8) : ([]u64, []u32)= words s