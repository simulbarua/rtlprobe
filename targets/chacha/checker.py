"""Strict adapter for the unchanged pinned ChaCha core testbench."""
import re

# Expected words are copied from the existing upstream TB, not generated results.
CASES = [{'id': 'case01_tc1_1',
  'printed_label': '1-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': 'e28a5fa4a67f8c5defed3e6fb7303486aa8427d31419a729572d777953491120b64ab8e72b8deb85cd6aea7cb6089a101824beeb08814a428aab1fa2c816081b'},
 {'id': 'case02_tc1_2',
  'printed_label': '1-2',
  'key_bits': 128,
  'rounds': 12,
  'expected': 'e1047ba9476bf8ff312c01b4345a7d8ca5792b0ad467313f1dc412b5fdce32410dea8b68bd774c36a920f092a04d3f95274fbeff97bc8491fcef37f85970b450'},
 {'id': 'case03_tc1_3',
  'printed_label': '1-3',
  'key_bits': 128,
  'rounds': 20,
  'expected': '89670952608364fd00b2f90936f031c8e756e15dba04b8493d00429259b20f46cc04f111246b6c2ce066be3bfb32d9aa0fddfbc12123d4b9e44f34dca05a103f'},
 {'id': 'case04_tc1_4',
  'printed_label': '1-4',
  'key_bits': 256,
  'rounds': 8,
  'expected': '3e00ef2f895f40d67f5bb8e81f09a5a12c840ec3ce9a7f3b181be188ef711a1e984ce172b9216f419f445367456d5619314a42a3da86b001387bfdb80e0cfe42'},
 {'id': 'case05_tc1_5',
  'printed_label': '1-5',
  'key_bits': 256,
  'rounds': 12,
  'expected': '9bf49a6a0755f953811fce125f2683d50429c3bb49e074147e0089a52eae155f0564f879d27ae3c02ce82834acfa8c793a629f2ca0de6919610be82f411326be'},
 {'id': 'case06_tc1_6',
  'printed_label': '1-6',
  'key_bits': 256,
  'rounds': 20,
  'expected': '76b8e0ada0f13d90405d6ae55386bd28bdd219b8a08ded1aa836efcc8b770dc7da41597c5157488d7724e03fb8d84a376a43b8f41518a11cc387b669b2ee6586'},
 {'id': 'case07_tc2_1',
  'printed_label': '2-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': '03a7669888605a0765e8357475e58673f94fc8161da76c2a3aa2f3caf9fe5449e0fcf38eb882656af83d430d410927d55c972ac4c92ab9da3713e19f761eaa14'},
 {'id': 'case08_tc2_1',
  'printed_label': '2-1',
  'key_bits': 256,
  'rounds': 8,
  'expected': 'cf5ee9a0494aa9613e05d5ed725b804b12f4a465ee635acc3a311de8740489ea289d04f43c7518db56eb4433e498a1238cd8464d3763ddbb9222ee3bd8fae3c8'},
 {'id': 'case09_tc3_1',
  'printed_label': '3-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': '25f5bec6683916ff44bccd12d102e692176663f4cac53e719509ca74b6b2eec85da4236fb29902012adc8f0d86c8187d25cd1c486966930d0204c4ee88a6ab35'},
 {'id': 'case10_tc4_1',
  'printed_label': '4-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': '2204d5b81ce662193e00966034f91302f14a3fb047f58b6e6ef0d721132304163e0fb640d76ff9c3b9cd99996e6e38fad13f0e31c82244d33abbc1b11e8bf12d'},
 {'id': 'case11_tc5_1',
  'printed_label': '5-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': 'f0a23bc36270e18ed0691dc384374b9b2c5cb60110a03f56fa48a9fbbad961aa6bab4d892e96261b6f1a0919514ae56f86e066e17c71a4176ac684af1c931996'},
 {'id': 'case12_tc6_1',
  'printed_label': '6-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': '312d95c0bc38eff4942db2d50bdc500a30641ef7132db1a8ae838b3bea3a7ab03815d7a4cc09dbf5882a3433d743aced48136ebab73299506855c0f5437a36c6'},
 {'id': 'case13_tc7_1',
  'printed_label': '7-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': 'a7a6c81bd8ac106e8f3a46a1bc8ec702e95d18c7e0f424519aeafb54471d83a2bf888861586b73d228eaaf82f9665a5a155e867f93731bfbe24fab495590b231'},
 {'id': 'case14_tc7_2',
  'printed_label': '7-2',
  'key_bits': 256,
  'rounds': 8,
  'expected': '60fdedbd1a280cb741d0593b6ea0309010acf18e1471f68968f4c9e311dca149b8e027b47c81e0353db013891aa5f68ea3b13dd2f3b8dd0873bf3746e7d6c567'},
 {'id': 'case15_tc8_1',
  'printed_label': '8-1',
  'key_bits': 128,
  'rounds': 8,
  'expected': '6a870108859f679118f3e205e2a56a6826ef5a60a4102ac8d4770059fcb7c7bae02f5ce004a6bfbbea53014dd82107c0aa1c7ce11b7d78f2d50bd3602bbd2594'}]

# The case table above preserves invocation order, including the repeated TC2-1.

def classify(stdout, stderr='', returncode=0, timed_out=False):
    result = dict(outcome='infrastructure_error', reason='incomplete_or_inconsistent_log',
                  signature=None, checkpoints=[])
    if timed_out:
        return dict(result, outcome='timeout_unclassified', reason='wall_clock_timeout')
    if returncode != 0 or stderr.strip():
        return dict(result, reason='simulator_error')
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    begin, end = '-- Testbench for chacha_core started --', '*** chacha_core simulation done ***'
    if lines.count(begin) != 1 or lines.count(end) != 1:
        return result
    starts = [(i, m[1]) for i, line in enumerate(lines)
              if (m := re.fullmatch(r'\*\*\* TC (\d+-\d+) started\.', line))]
    if [label for _, label in starts] != [case['printed_label'] for case in CASES]:
        return result
    summaries = [(i, line) for i, line in enumerate(lines) if re.fullmatch(
        r'\*\*\* (?:All test cases completed successfully|\d+ test cases did not complete successfully\.)', line)]
    if len(summaries) != 1:
        return result
    summary_position, summary = summaries[0]
    if not lines.index(begin) < starts[0][0] < starts[-1][0] < lines.index(end) < summary_position:
        return result
    known_errors = {f"*** ERROR: TC {case['printed_label']} not successful" for case in CASES}
    if any(re.search(r'error|fatal|warning', line, re.I) and line not in known_errors for line in lines):
        return dict(result, reason='unexpected_diagnostic')
    all_verdicts = [line for line in lines if re.fullmatch(r'\*\*\* (?:ERROR: )?TC \d+-\d+ (?:successful|not successful)', line)]
    if len(all_verdicts) != len(CASES):
        return result
    checks = []
    for n, case in enumerate(CASES):
        start = starts[n][0]
        stop = starts[n+1][0] if n+1 < len(starts) else lines.index(end)
        section = lines[start+1:stop]
        good = f"*** TC {case['printed_label']} successful"
        bad = f"*** ERROR: TC {case['printed_label']} not successful"
        verdicts = [line for line in section if line in all_verdicts]
        if verdicts not in ([good], [bad]):
            return result
        check = dict(id=case['id'], outcome='pass' if verdicts == [good] else 'functional_fail')
        if check['outcome'] == 'functional_fail':
            index = section.index(bad)
            expected = re.fullmatch(r'Expected:\s+0x([0-9a-fA-F]{128})', section[index+1]) if index+1 < len(section) else None
            actual = re.fullmatch(r'Got:\s+0x([0-9a-fA-FxXzZ]{128})', section[index+2]) if index+2 < len(section) else None
            if not expected or not actual or expected[1].lower() != case['expected'] or expected[1].lower() == actual[1].lower():
                return result
            check.update(expected=expected[1].lower(), actual=actual[1].lower())
        checks.append(check)
    failed = [c for c in checks if c['outcome'] == 'functional_fail']
    if any(sum(line.startswith(prefix) for line in lines) != len(failed) for prefix in ('Expected:', 'Got:')):
        return result
    wanted = '*** All test cases completed successfully' if not failed else f'*** {len(failed):02d} test cases did not complete successfully.'
    if summary != wanted:
        return result
    return dict(result, outcome='functional_fail' if failed else 'pass', reason='checker_completed',
                checkpoints=checks, signature=failed or None, tests_completed=len(CASES), comparisons_completed=len(CASES))
