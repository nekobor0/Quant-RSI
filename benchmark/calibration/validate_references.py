"""Validate local original-paper identity before any T2 oracle is built."""
from pathlib import Path
import hashlib
import json
import pdfplumber
import yaml

ROOT = Path(__file__).resolve().parents[2]
rows = []
for key in ('P10', 'P20'):
    manifest_path = ROOT / f'benchmark/calibration/REFERENCE_{key}.yaml'
    item = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    source = ROOT / item['source_file']
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with pdfplumber.open(source) as pdf:
        pages_valid = all(1 <= row['pdf_page'] <= len(pdf.pages) for row in item['source_pages'])
        opening = ' '.join((pdf.pages[i].extract_text() or '') for i in range(min(2, len(pdf.pages))))
        title_valid = item['exact_paper_title'].casefold() in ' '.join(opening.split()).casefold()
    required = {'original_universe_market', 'formation_period', 'holding_period',
                'skip_period', 'weighting', 'rebalance', 'benchmark',
                'transaction_execution_assumptions', 'original_exclusions', 'exact_formula'}
    row = dict(paper_id=key, manifest=str(manifest_path.relative_to(ROOT)).replace('\\', '/'),
               source_sha256=actual_hash, source_hash_match=actual_hash == item['source_sha256'],
               title_match=title_valid, pages_valid=pages_valid,
               original_fields_complete=required <= set(item['ORIGINAL_PAPER_DEFINITION']),
               concept_only=item['QUANT_RSI_CONCEPT_ADAPTATION']['replication_label'] ==
               'CONCEPT_REPLICATION_ONLY_NOT_EXACT_PAPER_REPLICATION')
    rows.append(row)
status = 'PASS' if all(all(value is True for name, value in row.items() if name in
    ('source_hash_match','title_match','pages_valid','original_fields_complete','concept_only'))
    for row in rows) else 'FAIL'
result = dict(status=status, checks=rows, scope='source_identity_and_manifest_structure_not_formula_truth')
output = ROOT / 'artifacts/stage_c1/C1-01/reference_validation.json'
output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(status=status, paper_count=len(rows))))
raise SystemExit(0 if status == 'PASS' else 1)
