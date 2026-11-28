"""Review and manifest gates execute inside the mutation transaction."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rtlprobe import batch, execution, pilot
from rtlprobe.evidence import filehash, manifest, save


def receipt(bundle, decisions):
    save(bundle/'plan_review.json', dict(schema_version='plan-review-1',
        plan_manifest_sha256=filehash(bundle/'manifest.json'), reviewer='Fixture reviewer',
        reviewed_at='2026-10-29T00:00:00+00:00', decisions=[
            dict(proposal_id=pid, decision=decision, note='Fixture only') for pid, decision in decisions.items()]))


class ExecutionTests(unittest.TestCase):
    def test_explicit_workspace_root_overrides_process_revocation_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();primary=root/'primary';secondary=root/'secondary'
            bundle=secondary/'plan';bundle.mkdir(parents=True)
            (bundle/'mutations.jsonl').write_text('{"proposal_id":"p1"}\n')
            manifest(bundle);receipt(bundle,{'p1':'approve'})
            marker=secondary/'data/reviews/revocations'/('plan-'+filehash(bundle/'manifest.json')+'.json')
            save(marker,{})
            with patch.object(execution,'ROOT',primary):
                self.assertEqual(execution.review_decisions(bundle,[{'proposal_id':'p1'}]),set())
                with self.assertRaisesRegex(ValueError,'revoked'):
                    execution.review_decisions(bundle,[{'proposal_id':'p1'}],root=secondary)

    def test_review_hash_revocation_and_changed_reviewer_stop_running_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();bundle=root/'bundle';bundle.mkdir()
            (bundle/'mutations.jsonl').write_text('{"proposal_id":"p1"}\n');manifest(bundle);receipt(bundle,{'p1':'approve'})
            def run(path,validate_plan,execution_guard):
                self.assertEqual(validate_plan([{'proposal_id':'p1'}],{},{},{}),set())
                self.assertIs(execution_guard(),True)
                marker=root/'data/reviews/revocations'/('review-'+filehash(bundle/'plan_review.json')+'.json')
                marker.parent.mkdir(parents=True);marker.symlink_to(root/'missing')
                with self.assertRaisesRegex(ValueError,'revoked'):execution_guard()
                marker.unlink()
                value=json.loads((bundle/'plan_review.json').read_text());value['reviewer']='different fixture reviewer'
                save(bundle/'plan_review.json',value)
                with self.assertRaisesRegex(ValueError,'changed'):execution_guard()
            with patch.object(execution,'ROOT',root),patch.object(execution.batch,'run',side_effect=run):
                execution.run(bundle)

    def test_retired_automatic_and_mixed_reviews_cannot_authorize_a_new_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            proposals = [{'proposal_id': 'p1'}]
            manifest(bundle)
            for reviewer, note in [('campaign-ai:fixture', 'advisory'),
                                   ('basic:fixture', 'AI review ' + 'a'*64 + ' · historical decision')]:
                with self.subTest(reviewer=reviewer):
                    receipt(bundle, {'p1': 'approve'})
                    path = bundle/'plan_review.json'
                    review = json.loads(path.read_text())
                    review['reviewer'] = reviewer
                    review['decisions'][0]['note'] = note
                    save(path, review)
                    with self.assertRaisesRegex(ValueError, 'human'):
                        execution.review_decisions(bundle, proposals, root=bundle.resolve())

    def test_future_dated_review_cannot_authorize_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'mutations.jsonl').write_text('{"proposal_id":"p1"}\n');manifest(bundle);receipt(bundle,{'p1':'approve'})
            path=bundle/'plan_review.json';value=json.loads(path.read_text())
            value['reviewed_at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat();save(path,value)
            with self.assertRaises(ValueError):execution.review_decisions(bundle,[{'proposal_id':'p1'}])

    def test_live_guard_revocation_preserves_first_report_and_prevents_second_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'plan';bundle.mkdir()
            items=[{'proposal_id':f'p{i}','path':'rtl.v','target':{'line':i},
                    'baseline_fingerprint':'fp','registry_sha256':'reg','primary_test':'test',
                    'fallback_tests':[],'limits':{'campaign_seconds':100,'cpu_seconds':100,'disk_bytes':100000}}
                   for i in (1,2)]
            (bundle/'mutations.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in items));manifest(bundle)
            receipt(bundle,{'p1':'approve','p2':'approve'})
            config={'target_id':'toy','limits':items[0]['limits'],'test_id':'test','case_prefix':'toy'}
            enabled=[True];attempts=[]
            def execute(proposal,*args,**kwargs):
                self.assertIs(kwargs['execution_guard'](),True)
                attempts.append(proposal['proposal_id']);enabled[0]=False
                return {'state':'unexposed','case_id':'case-first'}
            def publish(*args):return {'case_id':'case-first','state':'unexposed'}
            original_hash=batch.filehash
            def filehash(path):return 'reg' if Path(path)==pilot.REGISTRY else original_hash(path)
            with patch.object(batch,'ROOT',root),patch.object(batch,'workspace_lock'), \
                 patch.object(pilot,'qualified',return_value=({},config,{'sha256':'fp'})), \
                 patch.object(batch,'existing_cases',return_value={}), \
                 patch.object(batch,'preflight',side_effect=lambda p,*args:('key-'+p['proposal_id'],b'a',b'b')), \
                 patch.object(batch,'filehash',side_effect=filehash), \
                 patch.object(batch,'campaign_usage',return_value=(0,0,0)), \
                 patch.object(batch,'reserve_attempt',return_value=({},root/'case',False)) as reserve, \
                 patch.object(batch,'execute',side_effect=execute),patch.object(batch,'publish',side_effect=publish), \
                 patch.object(batch,'complete_attempt'):
                with self.assertRaisesRegex(ValueError,'readiness guard'):
                    execution.run(bundle,execution_guard=lambda:enabled[0])
            self.assertEqual(attempts,['p1']);self.assertEqual(reserve.call_count,1)
            report=json.loads(next((root/'outputs/toy/batches').glob('*/report.json')).read_text())
            self.assertEqual(report['processed_candidates'],1);self.assertEqual(report['status'],'running')
            self.assertEqual(report['cases'][0]['case_id'],'case-first')

    def test_live_guard_requires_literal_true_before_qualification(self):
        with patch.object(pilot,'qualified') as qualify:
            with self.assertRaisesRegex(ValueError,'readiness guard'):
                batch.run('unused',execution_guard=lambda:1)
            qualify.assert_not_called()
    def test_sealed_bundle_checked_inside_execution_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'mutations.jsonl').write_text('{"proposal_id": "p1"}\n');manifest(bundle)
            receipt(bundle, {'p1':'approve'})
            accepted=[]
            def run(path,validate_plan,**kwargs):
                self.assertIs(kwargs['execution_guard'](),True)
                items=[json.loads(s) for s in Path(path).read_text().splitlines()]
                self.assertEqual(validate_plan(items,{}, {}, {}),set());accepted.append(items);return {'permitted':True}
            with patch.object(execution.batch,'run',side_effect=run):
                self.assertEqual(execution.run(bundle),{'permitted':True})
                (bundle/'mutations.jsonl').write_text('{"proposal_id": "changed"}\n')
                with self.assertRaises(ValueError):execution.run(bundle)
                self.assertEqual(len(accepted),1)
    def test_bundle_hash_pins_the_client_validated_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'mutations.jsonl').write_text('{}\n');manifest(bundle)
            def run(path,validate_plan,**kwargs):
                validate_plan([{}],{}, {}, {})
            with patch.object(execution.batch,'run',side_effect=run):
                with self.assertRaisesRegex(ValueError,'caller-validated'):
                    execution.run(bundle,'0'*64)
    def test_plain_proposals_cannot_bypass_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'proposals.jsonl';file.write_text('{}\n')
            with patch.object(execution.batch,'run') as run:
                with self.assertRaisesRegex(ValueError,'sealed bundle'):
                    execution.run(file)
                run.assert_not_called()
    def test_missing_stale_incomplete_edit_and_duplicate_review_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'mutations.jsonl').write_text('{"proposal_id":"p1"}\n');manifest(bundle)
            items=[{'proposal_id':'p1'}]
            with self.assertRaisesRegex(ValueError,'required'):
                execution.review_decisions(bundle,items)
            receipt(bundle,{'p1':'approve'})
            value=json.loads((bundle/'plan_review.json').read_text())
            variants=[{**value,'plan_manifest_sha256':'0'*64}, {**value,'decisions':[]},
                      {**value,'decisions':[dict(proposal_id='p1',decision='edit',note='')]},
                      {**value,'decisions':value['decisions']*2}, {**value,'reviewer':' '}]
            for changed in variants:
                save(bundle/'plan_review.json',changed)
                with self.assertRaises(ValueError):execution.review_decisions(bundle,items)
            (bundle/'plan_review.json').write_text('{"schema_version":"plan-review-1","schema_version":"plan-review-1"}')
            with self.assertRaisesRegex(ValueError,'Duplicate'):execution.review_decisions(bundle,items)
    def test_only_declared_sidecars_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'mutations.jsonl').write_text('{}\n');manifest(bundle)
            (bundle/'PLAN_REVIEW.md').write_text('report');receipt(bundle,{})
            execution.verify_bundle(bundle)
            (bundle/'extra.txt').write_text('unsealed')
            with self.assertRaisesRegex(ValueError,'manifest mismatch'):execution.verify_bundle(bundle)
    def test_rejected_proposal_skipped_and_reported_without_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'plan';bundle.mkdir()
            proposal={'proposal_id':'p1','path':'rtl.v','target':{'line':1}}
            (bundle/'mutations.jsonl').write_text(json.dumps(proposal)+'\n');manifest(bundle)
            receipt(bundle,{'p1':'reject'})
            config={'target_id':'toy','limits':{}}
            with patch.object(batch,'ROOT',root),patch.object(batch,'workspace_lock'), \
                 patch.object(pilot,'qualified',return_value=({},config,{})), \
                 patch.object(batch,'existing_cases',return_value={}),patch.object(batch,'preflight') as preflight, \
                 patch.object(batch,'execute') as execute:
                report=execution.run(bundle)
            preflight.assert_not_called();execute.assert_not_called()
            self.assertEqual(report['cases'][0]['disposition'],'rejected_at_review')
            self.assertEqual(report['executed_this_invocation'],0)
            self.assertEqual(report['status'],'completed')
    def test_condition_inversion_waits_for_adopted_candidate_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);p={'proposal_id':'p1','operator':{'id':'condition_invert'}}
            (bundle/'mutations.jsonl').write_text(json.dumps(p)+'\n');manifest(bundle)
            receipt(bundle,{'p1':'approve'})
            def run(path,validate_plan,**kwargs):
                validate_plan([p],{}, {}, {})
            with patch.object(execution.batch,'run',side_effect=run):
                with self.assertRaisesRegex(ValueError,'T-19'):execution.run(bundle)
            receipt(bundle,{'p1':'reject'})
            with patch.object(execution.batch,'run',side_effect=run):
                execution.run(bundle)
    def test_main_cli_has_no_agent_actions(self):
        import subprocess,sys
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(root/'scripts/rtlprobe.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        for action in ['prepare','provenance','--prompt']:
            self.assertNotIn(action,result.stdout)

if __name__=='__main__':unittest.main()
