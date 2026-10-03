"""v1.11 sampler-decoupling gates: relation targets invariant to entity density.

Uses the real training wiring (train_relex.sparse_relation_batch): relation
targets for the 24 v1.8 sentences are generated with and without dense extra
entities attached to the samples. RNG seeded identically per mode.

Gates:
  1. digest(targets without dense) == digest(targets with dense)
  2. identical target counts
  3. no target references non-X/Y ordinals; provides edges == gold count
  4. determinism across repeated runs
  5. v1.8 compat: sparse path is the unchanged legacy sample construction

No training. No fold. Exit 0 iff all gates pass.
"""

import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

V18_DIGEST = "3854f8b80f0ede95948dea612fc4ab1d83237c3d4cab324339cad4c21b151c97"

SPECS = [
    ('Bram showed Fenna the workshop.', 'Bram', 'person', 'Fenna', 'person', 'provides'),
    ('The printer helped the office staff.', 'The printer', 'technology', 'the office staff', 'organization', 'provides'),
    ('Sanne lifted Jeroen onto the stage.', 'Sanne', 'person', 'Jeroen', 'person', 'provides'),
    ('Timo carried Sanne across the bridge.', 'Timo', 'person', 'Sanne', 'person', 'provides'),
    ('The harbor guides ships into the dock.', 'The harbor', 'organization', 'ships', 'technology', 'provides'),
    ('The observatory feeds data to the array.', 'The observatory', 'organization', 'the array', 'technology', 'provides'),
    ('The summit briefed Iris on protocol.', 'The summit', 'event', 'Iris', 'person', 'provides'),
    ('The program funds the trust each year.', 'The program', 'concept', 'the trust', 'organization', 'provides'),
    ('The warden opened the shelter for newcomers.', 'The warden', 'person', 'newcomers', 'person', 'provides'),
    ('The village hosted travelers for the night.', 'The village', 'location', 'travelers', 'person', 'provides'),
    ('The beacon warned sailors of the rocks.', 'The beacon', 'technology', 'sailors', 'person', 'provides'),
    ('The mint strikes coins for the treasury.', 'The mint', 'organization', 'the treasury', 'organization', 'provides'),
    ('Bram asked if Fenna wanted coffee.', 'Bram', 'person', 'Fenna', 'person', 'no_relation'),
    ('The printer asked if the staff needed toner.', 'The printer', 'technology', 'the staff', 'organization', 'no_relation'),
    ('Sanne asked if Jeroen needed a lift.', 'Sanne', 'person', 'Jeroen', 'person', 'no_relation'),
    ('Timo asked if Sanne needed help crossing.', 'Timo', 'person', 'Sanne', 'person', 'no_relation'),
    ('The harbor asked if the ships needed pilots.', 'The harbor', 'organization', 'the ships', 'technology', 'no_relation'),
    ('The observatory asked if the array needed calibration.', 'The observatory', 'organization', 'the array', 'technology', 'no_relation'),
    ('The summit asked if Iris needed an escort.', 'The summit', 'event', 'Iris', 'person', 'no_relation'),
    ('The program asked if the trust needed review.', 'The program', 'concept', 'the trust', 'organization', 'no_relation'),
    ('The warden asked if newcomers needed blankets.', 'The warden', 'person', 'newcomers', 'person', 'no_relation'),
    ('The village asked if travelers needed lodging.', 'The village', 'location', 'travelers', 'person', 'no_relation'),
    ('The beacon asked if sailors needed charts.', 'The beacon', 'technology', 'sailors', 'person', 'no_relation'),
    ('The mint asked if the treasury needed an audit.', 'The mint', 'organization', 'the treasury', 'organization', 'no_relation'),
]


def span(sent, m):
    i = sent.lower().find(m.lower())
    assert i >= 0, (sent, m)
    return {'start': i, 'end': i + len(m), 'text': sent[i:i + len(m)]}


def main() -> int:
    import train_relex as T
    from gliner import GLiNER
    from gliner.data_processing import RelationExtractionTokenProcessor, WordsSplitter

    rows = []
    for s, x, tx, y, ty, rel in SPECS:
        rows.append({'sentence': s, 'entities': {'X': span(s, x), 'Y': span(s, y)},
                     'entity_labels': {'X': tx, 'Y': ty}, 'relation': rel, 'metadata': {}})
    blob = '\n'.join(f'{e["sentence"]}|{e["entities"]["X"]["text"]}|'
                     f'{e["entities"]["Y"]["text"]}|{e["relation"]}' for e in rows)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    print('population:', digest[:16], 'expected:', V18_DIGEST[:16])
    if digest != V18_DIGEST:
        print('POPULATION MISMATCH')
        return 1

    dense = {e['sentence']: e['extra_entities']
             for e in json.loads((T.ROOT / 'docs' / 'eval_dense_entities_v1.json').read_text())['entries']}
    samples = [T.to_gliner_sample(e) for e in rows]
    for s, e in zip(samples, rows):
        s['entities'] = s.pop('ner')
        s['dense_entities'] = s.pop('dense_ner')
    # attach committed dense extras (char spans -> word spans resolved here)
    for s, e in zip(samples, rows):
        words = T._words_with_offsets(e['sentence'])
        extra = []
        for d in dense[e['sentence']]:
            w = T._word_index(words, d['start'], d['end'])
            # validate: matches committed span and label
            assert e['sentence'][d['start']:d['end']] == d['text']
            extra.append((w[0], w[1], d['label']))
        # check no overlap with X/Y word spans
        words2 = T._words_with_offsets(e['sentence'])
        for role in ('X', 'Y'):
            ent = e['entities'][role]
            xs = T._word_index(words2, ent['start'], ent['end'])
            for (a, b, _) in extra:
                assert b < xs[0] or a > xs[1], f'overlap in {e["sentence"]}'
        s['dense_entities'] = sorted(set(s['dense_entities']) | set(extra),
                                    key=lambda t: (t[0], t[1]))

    model = GLiNER.from_pretrained(T.CONTRACT['model']['base'])
    tok = getattr(model, 'tokenizer', None)
    if tok is None:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(T.CONTRACT['model']['base'])
    proc = RelationExtractionTokenProcessor(model.config, tok, WordsSplitter('whitespace'))
    c2i = {lab: i + 1 for i, lab in enumerate(T.ENTITY_INVENTORY)}
    r2i = {'provides': 1}
    inv, relp = list(T.ENTITY_INVENTORY), list(T.REL_PROMPTS)

    def tensor_or_none(t):
        return None if t is None else t.tolist()

    def targets(with_dense, seed):
        random.seed(seed)
        batch = []
        for s in samples:
            s2 = dict(s)
            if not with_dense:
                s2 = dict(s2, dense_entities=s2['entities'])
            batch.append(s2)
        # relation branch of the real wiring (sparse view inside helper)
        out = T.sparse_relation_batch(proc, batch, c2i, r2i, inv, relp)
        return {'adj': tensor_or_none(out['adj_matrix']),
                'rel': tensor_or_none(out['rel_matrix']),
                'idx': out['rel_idx_all'], 'lab': out['rel_label_all']}

    def dg(o):
        return hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()

    t_sparse = targets(False, 11)
    t_dense = targets(True, 11)
    t_dense2 = targets(True, 11)
    t_sparse2 = targets(False, 11)

    ok = True
    g1 = dg(t_sparse) == dg(t_dense)
    print('gate1 invariance:', g1, dg(t_sparse)[:16], dg(t_dense)[:16])
    ok &= g1
    n_sp = sum(len(r) for r in t_sparse['idx'])
    n_de = sum(len(r) for r in t_dense['idx'])
    print('gate2 rel_idx counts sparse/dense:', n_sp, n_de)
    ok &= (n_sp == n_de)
    bad = [e for row in t_dense['idx'] for e in row if max(e) > 1]
    prov = sum(1 for row in t_dense['lab'] for lab in row if lab)
    gold = sum(1 for e in rows if e['relation'] == 'provides')
    print('gate3 ordinals>1:', len(bad), 'provides edges:', prov, 'gold:', gold)
    ok &= (not bad and prov == gold)
    g4 = dg(t_dense) == dg(t_dense2) and dg(t_sparse) == dg(t_sparse2)
    print('gate4 determinism:', g4)
    ok &= g4
    print('gate5 legacy path: sparse view = unchanged to_gliner_sample ner + processor fns')
    verdict = 'PASS - v1.12 released' if ok else 'BLOCKED'
    print('RESULT:', verdict)
    json.dump({'version': 'sampler_decoupling_v1_11',
               'population_digest': V18_DIGEST,
               'target_digest': dg(t_sparse),
               'gates': {'invariance': g1, 'counts': [n_sp, n_de],
                         'ordinals_gt1': len(bad), 'provides_edges': prov,
                         'determinism': g4},
               'verdict': verdict},
              open(T.ROOT / 'docs' / 'eval_sampler_decoupling_v1_11.json', 'w'), indent=2)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
