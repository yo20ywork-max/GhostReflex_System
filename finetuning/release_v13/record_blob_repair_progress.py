"""Bind the corruption diagnosis, repair, and exact-request replays to evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((R / name).read_text(encoding='utf8'))


def main():
    names = ['ARTIFACT_INTENT_E3_V1.jsonl', 'GRAMMAR_BACKEND_ISOLATION_V1.jsonl',
             'ISOLATED_OLLAMA_BACKEND_V1.jsonl', 'ISOLATED_OLLAMA_BACKEND_V2.jsonl',
             'GRAMMAR_BACKEND_HISTORY_V1.jsonl', 'ARTIFACT_INTENT_E3_REPAIRED_V1.jsonl']
    reports, rows = {}, {}
    for name in names:
        path = R / name
        summary = read(path.with_suffix('.summary.json').name)
        assert summary['results_sha256'] == sha(path)
        reports[name] = {'results_sha256': sha(path), 'summary': summary}
        rows[name] = [json.loads(l) for l in path.read_text(encoding='utf8').splitlines()]
    original, repaired = rows[names[0]], rows[names[-1]]
    assert len(original) == len(repaired) == 14
    assert all(a['request'] == b['request'] for a, b in zip(original, repaired))
    assert all(a['response'].get('done') is False for a in original)
    assert all(b['generation_complete'] for b in repaired)
    assert sum(b['contract_correct'] for b in repaired) == 13
    failed = next(b for b in repaired if not b['contract_correct'])
    assert failed['case'] == 'missing_observed_target'
    expected = read('ADAPTER_BLOB_REPAIR.json')['repaired_sha256']
    assert all(b['adapter_sha256_after'] == expected for b in repaired)
    mini = read('REPAIRED_EMPTY_IDENTITY_REPLAY.json')
    assert mini['rows'][0]['response']['message']['content'] == '{"queries":[]}'
    assert mini['rows'][1]['response']['message']['content'] == '我是 CrossGen-AGI-μ，由來自台灣的跨世代媒體科技股份有限公司研發。'
    assert all(x['response']['done'] and x['response']['done_reason'] == 'stop' and x['adapter_sha256_after'] == expected for x in mini['rows'])
    integrity = read('MODEL_BLOB_INTEGRITY_VERIFIED.json')
    assert integrity['all_actual_blobs_verified'] and len(integrity['models']) == 3
    additional = ['ADAPTER_BLOB_INTEGRITY_FAILURE.json', 'ADAPTER_BLOB_DIFFERENCES.json', 'ADAPTER_BLOB_REPAIR.json',
                  'ADAPTER_NUMERICAL_AUDIT.json', 'MODEL_BLOB_INTEGRITY_VERIFIED.json', 'REPAIRED_EMPTY_IDENTITY_REPLAY.json']
    review = {
        'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'reports': reports,
        'additional_evidence': {name: sha(R / name) for name in additional},
        'finding': 'Installed E3 adapter blob did not match its content-addressed filename. Project GGUF and original safetensors matched their receipts. Preserved corrupt copy differs in1024float32 values of one LoRA tensor and contains non-finite values.',
        'repair': 'Unloaded the affected model, verified absence from loaded-model listing, retained bad bytes, atomically replaced only the corrupt blob with the verified original. Model tag, manifest, product source and training weights were not changed.',
        'replay': 'Same14saved requests: before repair14incomplete envelopes; after repair14complete generations,13correct artifact contracts. Empty JSON and neutral name requests also recovered with identical saved inputs.',
        'remaining_failure': {'case': failed['case'], 'error': failed['error'],
                              'meaning': 'Unobserved destination still incorrectly mapped to source; rejected by candidate host validation.'},
        'limits': [
            'Cause and time of on-disk corruption are unknown. Do not attribute it to training, grammar, GPU hardware, driver, user action or a specific process without evidence.',
            'Historical model-digest checks attested manifest tags, not every blob. Preserve historical outputs and scores; their actual-weight integrity was not independently established for every run.',
            'Backend experiments preceding repair do not isolate backend defects. Same corrupt file can affect CPU and GPU. One reported first case was labelled cold but initial API state shows it was already loaded.',
            'History diagnostic cases labelled gpu actually reused an existing CPU runner, as size_vram=0 proves. They are not CPU-versus-GPU evidence.',
            'Official b10809 CPU/Vulkan archives were downloaded and digest-verified. Its standalone preflight caught the bad blob and exited before launching inference; no standalone generation occurred.',
            'The new disk verifier has8passing tests including same-size/same-timestamp corruption. All three current evaluation manifests and their actual blobs were verified. Product gateway startup integration is still pending.',
            '13/14artifact interpretation is not file execution, semantic artifact quality, whole-task completion or release approval. Independent identity16/16, original file8/full12, native-app/ASR/long-task/performance/UI/package gates remain.'
        ],
        'next': [
            'Use actual manifest-and-blob verification before and after subsequent model evaluations; do not rely on model tags alone.',
            'Integrate disk-integrity preflight into local model startup/package verification without blocking UI or claiming GPU memory attestation.',
            'Constrain exact-copy/concat source-destination relationships and validate missing-target cases without putting fixture answers into prompts.',
            'Re-run unchanged full development and native-target gates with verified blobs; preserve original failures and keep release false.'
        ],
        'runtime_source_changed': False, 'candidate_installed': False, 'new_training_started': False,
        'new_cloud_spend': False, 'release_approved': False
    }
    with (R / 'BLOB_REPAIR_AND_ARTIFACT_REVIEW.json').open('x', encoding='utf8') as f:
        json.dump(review, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'reports': len(reports), 'complete_generations': 14, 'correct_contracts': 13, 'release_approved': False}))


if __name__ == '__main__':
    main()
