# SHA-1 compression

FIPS 180-4, 5.3.1. The first block starts with five specified 32-bit initial words. Each later block starts from the preceding block result.

FIPS 180-4, 6.1.2. The first sixteen schedule words come from the block. Each subsequent word rotates the XOR of four earlier words left by one bit.

FIPS 180-4, 4.1.1, 4.2.1 and 6.1.2. Each group of twenty rounds selects a Boolean function and a constant. Each round combines the rotated working word, function, constant, schedule word and fifth working word modulo 2^32.

FIPS 180-4, 6.1.2. After eighty rounds, combine each working word with its corresponding incoming hash word modulo 2^32. Concatenating the five words in order produces the digest.
