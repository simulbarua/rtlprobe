"""Independent known answers and transcript regression for the extended SHA-1 suite."""
import hashlib
from pathlib import Path
import re
import runpy
import unittest

SUITE = Path(__file__).resolve().parents[1]/'targets/sha1/extended'
ADAPTER = runpy.run_path(str(SUITE/'checker.py'))
EXPECTED = ADAPTER['EXPECTED']


class SHA1ExtendedTests(unittest.TestCase):
    def test_frozen_inputs_and_final_digests_match_hashlib(self):
        messages = {
            'tc1': b'abc', 'tc2_block2': b'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq',
            'empty': b'', 'boundary55': bytes(range(55)),
            'chain128': bytes((i*73+19)%256 for i in range(128)), 'restart': bytes.fromhex('8000ff7f'),
        }
        bench = (SUITE/'tb_sha1_extended.v').read_text()
        chunks = re.split(r'begin_check\("(\w+)"\);', bench)
        submitted = {}
        for name, body in zip(chunks[1::2], chunks[2::2]):
            submitted[name] = re.findall(r"hash_block\(1'b([01]), 512'h([0-9a-f]{128})\);", body)
            self.assertIn(f'check_digest("{name}", 160\'h{EXPECTED[name]});', body)
        self.assertEqual(list(submitted), list(EXPECTED))
        for name, msg in messages.items():
            with self.subTest(name=name):
                blocks = (submitted['tc2_block1'] if name == 'tc2_block2' else []) + submitted[name]
                self.assertEqual([first for first, _ in blocks], ['1']+['0']*(len(blocks)-1))
                padded = msg+b'\x80'+bytes((55-len(msg)) % 64)+(len(msg)*8).to_bytes(8,'big')
                self.assertEqual(bytes.fromhex(''.join(b for _,b in blocks)), padded)
                self.assertEqual(EXPECTED[name], hashlib.sha1(msg).hexdigest())
        self.assertEqual(EXPECTED['tc2_block1'], 'f4286818c37b27ae0408f581846771484a566572')

    def test_final_only_mismatch_and_malformed_results(self):
        lines = []
        for name, expected in EXPECTED.items():
            actual = '0'*40 if name == 'tc2_block2' else expected
            lines.extend([f'SHA1 BEGIN {name}', f'SHA1 DIGEST {name} expected={expected} actual={actual}'])
        lines.append('SHA1 DONE checks=7 failures=1')
        parse = ADAPTER['classify']
        text = '\n'.join(lines)
        self.assertEqual([f['id'] for f in parse(text)['signature']], ['tc2_block2'])
        for bad in (text.replace('failures=1','failures=0'), text.replace('SHA1 BEGIN empty','SHA1 BEGIN tc1'),
                    text.replace('SHA1 BEGIN restart','WARNING: interrupted'), text+'\nunexpected'):
            self.assertEqual(parse(bad)['outcome'], 'infrastructure_error')
