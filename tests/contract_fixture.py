"""Writes a Detect output directory exactly as handoff contract v1 describes (labels, spans, linkage, manifest)."""
import hashlib
import json
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(data_dir) -> tuple[dict, str]:
    files = {f.stem: f for f in sorted(Path(data_dir).glob('*.csv')) if not f.stem.startswith(('rowmap_', '_'))}
    shas = {t: sha(f.read_bytes()) for t, f in files.items()}
    return shas, sha('\n'.join(f'{t}:{shas[t]}' for t in sorted(shas)).encode())


def span(fp, table, column, row_index, start, end, entity_type='PERSON', entity_id='e1'):
    span_id = sha(f'{fp}|{table}|{column}|{row_index}|{start}|{end}'.encode())[:16]
    return {'span_id': span_id, 'table': table, 'column': column, 'row_index': row_index, 'start': start, 'end': end,
            'entity_type': entity_type, 'entity_id': entity_id, 'confidence': 0.9, 'needs_review': False}


def write_detect_dir(out, data_dir, labels, spans=(), relations=(), dataset=None, vocabulary=None, scanned=None,
                     linkage=True):
    """labels: DataFrame; spans: dicts from span(); relations: linkage relation dicts; scanned: optional
    artifacts.spans.columns map {"t.c": {"cells", "spans"}}; linkage=False omits the linkage artifact.
    Returns labels.csv path."""
    out = Path(out)
    out.mkdir(parents=True)
    shas, fp = fingerprint(data_dir)
    labels.to_csv(out / 'labels.csv', index=False)
    (out / 'spans.jsonl').write_text(''.join(json.dumps(s) + '\n' for s in spans))
    (out / 'linkage.json').write_text(json.dumps({'schema': 'pets.detect.linkage/1', 'relations': list(relations)}))
    inputs = {}
    for t in shas:
        header = (Path(data_dir) / f'{t}.csv').read_text().splitlines()
        inputs[t] = {'file': f'{t}.csv', 'sha256': shas[t], 'rows': len(header) - 1, 'columns': header[0].split(',')}
    art = lambda name: {'file': name, 'sha256': sha((out / name).read_bytes())}  # noqa: E731
    manifest = {
        'schema': 'pets.detect.manifest/1', 'dataset': dataset or Path(data_dir).name, 'dataset_fingerprint': fp,
        'inputs': inputs,
        'detector': {'name': 'pets_detect_v3', 'version': 'test', 'model_sha256': sha(b'model'), 'config': {}},
        'label_vocabulary': vocabulary if vocabulary is not None else
        sorted({(r, s) for r, s in zip(labels['privacy_role'], labels['subtype'])}),
        'artifacts': {'labels': art('labels.csv'),
                      'spans': {**art('spans.jsonl'), 'schema': 'pets.detect.spans/1',
                                **({'columns': scanned} if scanned is not None else {})},
                      **({'linkage': art('linkage.json')} if linkage else {})},
        'created_at': '2026-11-07T00:00:00Z'}
    (out / 'manifest.json').write_text(json.dumps(manifest))
    return out / 'labels.csv'
