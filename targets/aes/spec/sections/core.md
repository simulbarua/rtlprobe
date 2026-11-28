# AES core requirements

FIPS 197 sections 5.1–5.3 describe the cipher, key expansion and inverse
cipher. The target supports 128-bit blocks with 128-bit and 256-bit keys.
The cipher applies forward substitution, row shifting, column mixing and
round-key addition, omitting column mixing in the final round. The inverse
cipher uses inverse transformations and the corresponding reverse order of
round keys. Section F.1 of SP 800-38A supplies ECB known-answer examples.

The secworks usage instructions define a sequential key initialization and
block processing interface. Drive input and control changes while ready.
Read the completed block before the next transaction.
