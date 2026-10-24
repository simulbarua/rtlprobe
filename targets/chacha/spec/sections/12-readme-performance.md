source: secworks-chacha-readme
section: Performance, lines 53-54, first sentence

Classification: repository_claim. Secworks, revision 7eaba360df9fed9fc2db98d5f3df81cf01e5b604, BSD-2-Clause.
Only the identified excerpt is reproduced. The bench checks 128/256-bit keys and 8/12/20 rounds, without an exact-latency assertion.

The core has four separate quarterround modules, which means that
one round takes one cycle.
