-- REVERSE COMPLEMENT of a DNA sequence
-- Written/ tested first for dependencies (words requires revcomp), match cudagecko pipeline order
-- MATCHES: cudagecko kernel_reverse_complement (kernels.cu, line 1186):
-- A<->T, C<->G, any other character -> N
-- 
-- ==
-- input  { [65u8, 67u8, 71u8, 84u8, 78u8] }
-- output { [78u8, 65u8, 67u8, 71u8, 84u8] }


-- | Complement of one DNA base: A<->T, C<->G
-- Any other cahracter (lowercase, N, other) becomes 'N', matching cudagecko
def complement (c: u8) : u8 =
  if c == 'A' then 'T'
  else if c == 'C' then 'G'
  else if c == 'G' then 'C'
  else if c == 'T' then 'A'
  else 'N'


-- | Reverse complement of a sequence of length  n
-- `[n]`= size parameter - output has the same length as input
def revcomp [n] (s: [n]u8) : [n]u8 =
  map complement (reverse s)

entry main (s: []u8) : []u8 = revcomp s