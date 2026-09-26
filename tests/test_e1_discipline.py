import copy
import inspect
import pytest
from cliptrace_e1.e1_common import dump,verify
from cliptrace_e1.e1_run import assert_partition_integrity,decision,curve,evaluation_guard
from cliptrace_e1.e1_features import match

def row(score=.9,parent='S1',truth=True,margin=.2,status='evaluated'):
    return dict(candidate_id='c',identity='S1' if truth else 'N1',status=status,length_s=5,severity='moderate',
                visual_ancestry=truth,audio_ancestry=truth,expected_parent='S1' if truth else None,
                methods={'V-C':dict(score=score,top_parent=parent,margin=margin,status=status)})

def test_original_work_and_common_content_cannot_leak():
    assets=[dict(asset_id='a',partition='development',identity_group='work'),dict(asset_id='b',partition='evaluation',identity_group='work')]
    pm=dict(assignments={'a':'development','b':'evaluation'},common_content_components=[])
    with pytest.raises(ValueError,match='identity leakage'): assert_partition_integrity({'assets':assets},pm)
    assets[1]['identity_group']='other'
    pm['common_content_components']=[['a','b']]
    with pytest.raises(ValueError,match='Common-content leakage'): assert_partition_integrity({'assets':assets},pm)

def test_manifest_hash_tampering_rejected(tmp_path):
    p=tmp_path/'partition.json';dump(p,{'a':'evaluation'},immutable=True)
    p.write_text('{"a":"calibration"}')
    with pytest.raises(ValueError,match='Hash mismatch'): verify(p)

def test_immutable_profile_cannot_be_overwritten(tmp_path):
    p=tmp_path/'profile.json';dump(p,{'threshold':.9},immutable=True)
    with pytest.raises(ValueError,match='Immutable'): dump(p,{'threshold':.1},immutable=True)

def test_matcher_signature_has_no_labels_or_ground_truth():
    assert list(inspect.signature(match).parameters)==['c','registry']

def test_high_score_does_not_override_duration_or_ambiguity():
    r=row();op=dict(threshold=.8,minimum_duration_s=5)
    r['length_s']=2
    assert decision(r,'V-C',op)['state']=='insufficient'
    r['length_s']=5;r['methods']['V-C']['margin']=.01
    assert decision(r,'V-C',op)['state']=='AMBIGUOUS'
    assert decision(row(),'V-C',None)['reason']=='no_qualified_operating_point'

def test_wrong_parent_cannot_inflate_calibration_tpr():
    rows=[row(parent='WRONG'),row(score=.1,truth=False)]
    c=curve(rows,'V-C',5)
    assert all(p['tp_correct_parent']==0 for p in c)
    assert any(p['wrong_parent']==1 for p in c)

def test_unavailable_negatives_are_not_counted_as_true_negatives():
    rows=[row(),row(score=None,truth=False,status='failed')]
    c=curve(rows,'V-C',5)
    assert all(p['negative_available_denominator']==0 and p['negative_expected_denominator']==1 and p['fpr'] is None for p in c)

def test_evaluation_requires_profile(tmp_path,monkeypatch):
    import cliptrace_e1.e1_run as module
    monkeypatch.setattr(module,'OUT',tmp_path)
    with pytest.raises(FileNotFoundError): evaluation_guard()

def test_retrieval_recall_cannot_use_injected_pairwise_parent():
    from cliptrace_e1.e1_report import summarize
    r=row();r['methods']['V-C']['retrieval']=[['wrong',.99]]
    r['methods']['V-C']['pairs']=[{'parent':'S1','score':.9}]
    result=summarize([r],'V-C',dict(threshold=.8,minimum_duration_s=5))
    assert result['retrieval_recall']['10']['numerator']==0

def test_wrong_parent_intervals_do_not_get_temporal_credit():
    from cliptrace_e1.e1_report import temporal_rows
    r=row(parent='wrong');r.update(transform='trim',category='interview')
    r['methods']['V-C']['pairs']=[dict(parent='wrong',blocks=[dict(source=[2,7],candidate=[0,5])])]
    truth={'c':dict(source_intervals_s=[[2,7]])}
    result=temporal_rows([r],truth,'V-C',dict(threshold=.8,minimum_duration_s=5))[0]
    assert result['iou']==0 and result['start_error_s'] is None

def test_fusion_combines_same_parent_evidence_only():
    from cliptrace_e1.e1_run import fusion_row
    r=row();r['methods']={'V-C':{'pairs':[dict(parent='a',score=1),dict(parent='b',score=0)]},
                         'A-chromaprint':{'pairs':[dict(parent='a',score=0),dict(parent='b',score=1)]}}
    f=fusion_row(r,'V-C','A-chromaprint',.5)['methods']['F-fusion']
    assert f['score']==.5 and f['margin']==0

def test_audio_gate_retains_harsh_waveform_preserving_examples():
    r=row();r['severity']='harsh'
    r['methods']['A-chromaprint']=r['methods']['V-C']
    assert all(p['positive_denominator']==1 for p in curve([r],'A-chromaprint',5))
    assert all(p['positive_denominator']==0 for p in curve([r],'V-C',5))
