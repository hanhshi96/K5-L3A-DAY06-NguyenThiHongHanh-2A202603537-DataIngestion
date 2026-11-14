"""Run from starter/: python -u -m src.run --check / --split dev / --split test."""
import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
OUT=ROOT/'results'/'lab06_api'
CONFIG={'model':'text-embedding-3-small','dimensions':1536,'A_size':900,'A_overlap':150,
        'B_max_size':900,'top_k':3,'search':'exact cosine pgvector',
        'selection_rule':'Choose using dev Hit@3, then dev Hit@1, then lower chunk count; report manual test labels separately.',
        'split_rule':'Fixed 15 dev/5 test before any retrieval; no test-guided changes.'}

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare():
    print('1/6 Loading dependencies...',flush=True)
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    from src.ingestion import load_pdf
    from src.evaluation import normalized
    manifest=json.loads((ROOT/'data/lab06_corpus/manifest.json').read_text())
    questions=json.loads((ROOT/'benchmark.json').read_text())
    pages=[]
    for doc in manifest['documents']:
        path=ROOT/'data/lab06_corpus'/doc['filename']
        if not path.exists(): raise FileNotFoundError(f'Place PDF here: {path}')
        if digest(path)!=doc['sha256']: raise ValueError(f'PDF snapshot differs: {path.name}; gold pages must be reverified')
        loaded=load_pdf(path,doc['document_id'],doc['source'],
                       {'year':doc['year'],'language':doc['language'],'report_type':'legal_decree' if doc['language']=='vi' else 'research_paper'})
        selected=[p for p in loaded if p.page in doc['pages']]
        if len(selected)!=len(doc['pages']) or any(len(p.text)<200 for p in selected):
            raise ValueError('Selected corpus pages missing or low text')
        pages.extend(selected)
        print(f"  {doc['filename']}: {len(selected)} selected content pages",flush=True)
    if len(pages)<30: raise ValueError('Need 30 content pages')
    lookup={(p.document_id,p.page):p for p in pages}
    if len({q['id'] for q in questions})!=len(questions): raise ValueError('Duplicate query IDs')
    for split,minimum in [('dev',15),('test',5)]:
        if sum(q['split']==split for q in questions)<minimum: raise ValueError('Invalid benchmark split')
    if sum(bool(q['filter']) for q in questions)<3 or not any(q['split']=='test' and q['filter'] for q in questions):
        raise ValueError('Insufficient filter queries')
    for q in questions:
        for g in [dict(source_id=q['gold_source_id'],page=q['gold_page'],evidence_quote=q['evidence_quote'])]+q.get('alternative_gold',[]):
            if not g['evidence_quote'].strip() or normalized(g['evidence_quote']) not in normalized(lookup[g['source_id'],g['page']].text):
                raise ValueError('Gold evidence missing: '+q['id'])
        for k,v in q['filter'].items():
            if k not in {'language','year','report_type','company'}: raise ValueError('Invalid filter')
            if str(lookup[q['gold_source_id'],q['gold_page']].metadata.get(k))!=str(v): raise ValueError('Gold/filter conflict')
    OUT.mkdir(parents=True,exist_ok=True)
    frozen={'config':CONFIG,'benchmark_sha256':digest(ROOT/'benchmark.json'),
            'manifest_sha256':digest(ROOT/'data/lab06_corpus/manifest.json'),
            'code_sha256':{p.name:digest(p) for p in sorted((ROOT/'src').glob('*.py'))},
            'runner_sha256':digest(Path(__file__))}
    lock=OUT/'experiment_lock.json'
    if lock.exists() and json.loads(lock.read_text())!=frozen:
        raise RuntimeError('Experiment changed. Preserve old results; use a new experiment folder and disclose test exposure.')
    save(lock,frozen)
    save(OUT/'pages.json',[asdict(p) for p in pages])
    print(f'2/6 Verified {len(pages)} pages and {len(questions)} gold excerpts.',flush=True)
    return pages,questions,manifest

def store_client():
    import psycopg
    from psycopg import sql
    from src.store import PgVectorStore
    class APIStore(PgVectorStore):
        TABLE_NAME='lab06_api_chunks'
    url=os.getenv('DATABASE_URL','').strip()
    if not url: raise RuntimeError('DATABASE_URL missing in .env')
    store=APIStore(url,1536)
    store.create_schema()
    with psycopg.connect(url,connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='lab06_api_chunks'::regclass AND attname='embedding' AND NOT attisdropped")
            if cur.fetchone()[0]!='vector(1536)': raise RuntimeError('API table dimension mismatch; no data modified')
    return store

def count(store,strategy):
    import psycopg
    with psycopg.connect(store.database_url,connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM {store.TABLE_NAME} WHERE strategy=%s',(strategy,))
            return cur.fetchone()[0]

def manual_files(traces,chunks,pages):
    # Deterministic ten locations, independent of query labels or retrieval scores.
    selected=[p for p in pages if p.document_id=='nd13_2023'][:5]+[p for p in pages if p.document_id=='attention_2017'][:5]
    rows=[]
    preview=['# Manual assessment evidence','Scores must be entered by the student; no automatic human scores.']
    for p in selected:
        pos=min(450,len(p.text)-1)
        for strategy in ['A','B','C']:
            cover=[c for c in chunks[strategy] if c.document_id==p.document_id and c.page==p.page and c.metadata['start_char']<=pos<c.metadata['end_char']]
            # Score every chunk covering the same anchor; aggregate per location then average ten locations.
            for c in cover:
                rid=f"coherence:{strategy}:{p.document_id}:{p.page}:{c.chunk_id}"
                rows.append({'id':rid,'kind':'coherence','strategy':strategy,'source_or_question':f'{p.document_id} PDF {p.page} char {pos}','score_0_2':'','metadata_correct':'','reason':''})
                preview.extend([f'\n## {rid}',f'Source: {p.source}; PDF page {p.page}; anchor {pos}',c.text])
    for t in traces:
        if t['split']!='test': continue
        rid=f"grounding:{t['strategy']}:{t['id']}"
        rows.append({'id':rid,'kind':'grounding','strategy':t['strategy'],'source_or_question':t['id'],'score_0_2':'','metadata_correct':'','reason':''})
        preview.extend([f'\n## {rid}',t['question']['question'],'Expected: '+t['question']['expected_answer'],'Gold: '+t['question']['evidence_quote']])
        for rank,h in enumerate(t['hits'],1):
            mid=f"metadata:{t['strategy']}:{t['id']}:{rank}"
            rows.append({'id':mid,'kind':'metadata','strategy':t['strategy'],'source_or_question':t['id'],'score_0_2':'','metadata_correct':'','reason':''})
            preview.extend([f'### {mid}',f"{h['document_id']} PDF {h['page']} | {h['source']} | {h['metadata']}",h['text']])
    path=OUT/'manual_review.csv'
    old={}
    if path.exists():
        with path.open(encoding='utf-8-sig',newline='') as f: old={r['id']:r for r in csv.DictReader(f)}
    for r in rows:
        if r['id'] in old:
            for k in ['score_0_2','metadata_correct','reason']:r[k]=old[r['id']].get(k,'')
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (OUT/'manual_evidence.md').write_text('\n\n'.join(preview))

def report(traces,stats):
    from src.evaluation import summarize
    metrics=summarize(traces); save(OUT/'metrics.json',metrics)
    lines=['# Lab 06: API embedding retrieval experiment',
      'Automatic results below are generated from actual runs. Manual assessment is pending unless completed in manual_review.csv.',
      '## 1. Retrieval accuracy','|Strategy|Split|Hit@1|Evidence Hit@3|Filter compliance|','|---|---|---|---|---|']
    for r in metrics:
        n=r['n'];fc=f"{r['filter_compliant_queries']}/{r['filter_queries']}" if r['filter_queries'] else 'N/A'
        lines.append(f"|{r['strategy']}|{r['split']}|{r['hit1_count']}/{n} ({r['hit1_count']/n:.1%})|{r['hit3_count']}/{n} ({r['hit3_count']/n:.1%})|{fc}|")
    lines+=['','Matching requires gold document/page and a full normalized quote inside one chunk. Whitespace is ignored; accents, punctuation and case are preserved. Human equivalent evidence may require adjudication; auto scores can underestimate valid paraphrases. Cross-chunk unions do not count as the required Hit@3.',
    '## 2. Chunk coherence','Complete coherence rows in manual_review.csv using manual_evidence.md and source PDFs. Same ten fixed anchors across A/B/C. Score 0=cut/unclear, 1=partly understandable, 2=self-contained. If multiple chunks cover one anchor, score all and average within the anchor before averaging the ten anchors.',
    '## 3. Metadata usefulness','Complete metadata rows for the five test queries × top-3 × three strategies. Enter metadata_correct as 1/0, verify source/page/language against PDF. Report correct/checked, not merely presence. Filter values are explicit user-language scopes supplied before search. Empty result sets fail filter compliance. A/B intentionally do not apply filters; C applies only supplied filters.',
    '## 4. Grounding quality','Complete all 15 grounding rows: 0=no evidence, 1=incomplete/context missing, 2=sufficient and traceable. Report counts at 0/1/2 and mean /2 per strategy. Do not substitute automated Hit@3 for these labels. Student is the reviewer; disclose self-assessment bias.',
    '## 5. Strategy impact','A: fixed 900 characters, overlap 150. B: paragraph grouping with 900-character maximum, whitespace fallback for long paragraphs. C: reuses exactly B chunks/vectors and applies language filter only when supplied. Same API model and exact cosine store. PDF paragraph structure may be weak, reducing the distinction between A and B.',
    'Use metrics and ingestion_stats.json to compare A–B and B–C. C reuses B embeddings, so its incremental embedding cost is zero; do not interpret cache reuse as independent speed superiority.',
    '## Scope and reproducibility','38 content pages: NĐ13 physical PDF pages 1–29; paper pages 1–9. Gold uses physical PDF page numbers, not printed Công báo numbers. 15 dev + 5 test fixed before runs. Questions/evidence were AI-assisted and require student review. Mixed legal/ML topics deviate from the suggested narrow topic and make filter benefits harder to demonstrate. Small test and shared topics across splits limit generalization.',
    'NĐ13 is a historical snapshot and has ceased to be effective from 2026-01-01 under Article 42 of NĐ356/2025. Do not present answers as current legal advice.',
    'Model text-embedding-3-small; dimensions explicitly 1536. UTF-8 input guard; no silent truncation. Query/document use same endpoint. Real API usage is recorded per invocation; no mocked vectors. API cost is not assumed zero: compute actual billed tokens using applicable account pricing. Cache reuse and retries may cause billing totals to differ from successful-response token counts.',
    'Database table lab06_api_chunks; exact pgvector cosine. Upserts repeated and count-checked. Full current snapshot per document is supplied; stale chunks removed by store. Removed documents cleaned for each strategy. Original lab06_chunks is untouched.',
    'See experiment_lock, manifest, runtime, run usage, traces and error log. Keep .env and cache out of public git. PDFs not included; use source URLs and checksums.',
    '## Dev selection (predeclared rule)']
    dev=[r for r in metrics if r['split']=='dev']
    if dev:
        chosen=sorted(dev,key=lambda r:(-r['hit3_count'],-r['hit1_count'],stats[r['strategy']]['chunks'],r['strategy']))[0]['strategy']
        lines.append('Suggested by fixed dev-only rule: '+chosen+'. Test must not be used to change the configuration.')
    # Aggregate only labels actually supplied by a human.
    manual=OUT/'manual_review.csv'
    if manual.exists():
        with manual.open(encoding='utf-8-sig',newline='') as f: labels=list(csv.DictReader(f))
        lines+=['## Manual label completion (no imputation)']
        for strategy in ['A','B','C']:
            for kind in ['coherence','grounding','metadata']:
                subset=[r for r in labels if r['strategy']==strategy and r['kind']==kind]
                key='metadata_correct' if kind=='metadata' else 'score_0_2'
                allowed={'0','1'} if kind=='metadata' else {'0','1','2'}
                done=[r for r in subset if r.get(key,'') in allowed and r.get('reason','').strip()]
                line=f'{strategy} {kind}: {len(done)}/{len(subset)} labeled with reason.'
                if done:
                    if kind=='coherence':
                        grouped={}
                        for r in done: grouped.setdefault(r['source_or_question'],[]).append(int(r[key]))
                        line+=f' Mean per source anchor (completed labels only): {statistics.mean(statistics.mean(v) for v in grouped.values()):.3f}/2; complete all anchors before reporting final score.'
                    elif kind=='metadata': line+=f' Correct/checked: {sum(int(r[key]) for r in done)}/{len(done)}.'
                    else:
                        scores=[int(r[key]) for r in done]
                        line+=f' Mean {statistics.mean(scores):.3f}/2; counts 0/1/2={[scores.count(i) for i in range(3)]}.'
                lines.append(line)
    (OUT/'REPORT.md').write_text('\n\n'.join(lines),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--split',choices=['dev','test'],default='dev');parser.add_argument('--report-only',action='store_true');args=parser.parse_args()
    if args.report_only:
        traces=[]
        for p in sorted(OUT.glob('traces_*.json')):traces+=json.loads(p.read_text())
        report(traces,json.loads((OUT/'ingestion_stats.json').read_text()));print('REPORT refreshed. Manual labels remain in CSV.');return
    pages,questions,manifest=prepare()
    from src.embeddings import MyEmbedder
    class CachedEmbedder(MyEmbedder):
        """Cache wrapper compatible with the API adapter in src/embeddings.py."""
        def __init__(self, model_name, cache_dir):
            super().__init__(model_name)
            self.cache_dir=Path(cache_dir)
            self.cache_dir.mkdir(parents=True,exist_ok=True)
            self.cache_hits=0
            self.api_calls=0

        @property
        def tokens(self):
            return self.total_tokens

        def embed_documents(self, texts):
            import math
            found={}
            pending=[]
            paths={}
            for text in dict.fromkeys(texts):
                if not isinstance(text,str) or not text.strip():
                    raise ValueError('Empty embedding input')
                key=json.dumps([self.model_name,self.dimensions,text],ensure_ascii=False)
                path=self.cache_dir/(hashlib.sha256(key.encode()).hexdigest()+'.json')
                paths[text]=path
                if path.exists():
                    vector=json.loads(path.read_text())
                    if len(vector)!=self.dimensions or not all(math.isfinite(x) for x in vector) or not any(vector):
                        raise RuntimeError('Invalid cached vector: '+path.name)
                    found[text]=vector
                    self.cache_hits+=1
                else:
                    pending.append(text)
            for i in range(0,len(pending),32):
                batch=pending[i:i+32]
                print(f'API batch {i+1}-{i+len(batch)}/{len(pending)} new texts',flush=True)
                values=super().embed_documents(batch)
                self.api_calls+=1
                for text,vector in zip(batch,values):
                    path=paths[text]
                    tmp=path.with_suffix('.tmp')
                    tmp.write_text(json.dumps(vector))
                    tmp.replace(path)
                    found[text]=vector
            return [found[text] for text in texts]

        def embed_query(self,question):
            return self.embed_documents([question])[0]

    from src.chunking import fixed_size,by_paragraph
    from src.evaluation import evaluate_query
    embedder=CachedEmbedder(CONFIG['model'],OUT/'cache')
    print('3/6 Checking database...',flush=True);store=store_client()
    if args.check:
        v=embedder.embed_query('Connection test for Lab 06.')
        print(f'CHECK OK: real API vector={len(v)}, database=ready. No corpus indexed.',flush=True);return
    if args.split=='test' and not (OUT/'traces_dev.json').exists():raise RuntimeError('Run dev first; freeze strategy before test.')
    start=time.perf_counter();chunks={};vectors={};stats={}
    print('4/6 Chunking and embedding...',flush=True)
    for strategy in ['A','B','C']:
        t=time.perf_counter();tok0=embedder.tokens;hit0=embedder.cache_hits
        if strategy=='A':chunks[strategy]=[c for p in pages for c in fixed_size(p,900,150)]
        elif strategy=='B':chunks[strategy]=[c for p in pages for c in by_paragraph(p,900)]
        else:chunks[strategy]=chunks['B']
        current=chunks[strategy]
        if not current: raise RuntimeError('No chunks')
        if strategy=='C':vectors[strategy]=vectors['B']
        else:vectors[strategy]=embedder.embed_documents([c.text for c in current])
        embed_seconds=time.perf_counter()-t
        # Full snapshot ingestion; remove documents no longer present, then upsert all chunks.
        import psycopg
        with psycopg.connect(store.database_url,connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {store.TABLE_NAME} WHERE strategy=%s AND NOT(document_id=ANY(%s))',(strategy,sorted({c.document_id for c in current})))
        store.upsert(strategy,current,vectors[strategy]);before=count(store,strategy)
        store.upsert(strategy,current,vectors[strategy]);after=count(store,strategy)
        if before!=after or after!=len(current):raise RuntimeError('Idempotency/count check failed')
        lengths=[len(c.text) for c in current]
        stats[strategy]={'chunks':len(current),'characters':sum(lengths),'min_chars':min(lengths),'median_chars':statistics.median(lengths),'max_chars':max(lengths),'embed_and_chunk_seconds':embed_seconds,'total_seconds_with_two_upserts':time.perf_counter()-t,'new_api_tokens':embedder.tokens-tok0,'cache_hits':embedder.cache_hits-hit0,'idempotent_counts':[before,after],'vector_reuse_from':'B' if strategy=='C' else None}
        save(OUT/f'chunks_{strategy}.json',[asdict(c) for c in current])
    # Preserve first ingestion resource measurement instead of overwriting with warm cache test run.
    if not (OUT/'ingestion_stats.json').exists():save(OUT/'ingestion_stats.json',stats)
    runstamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    save(OUT/f'ingestion_{runstamp}.json',stats)
    print('5/6 Retrieving '+args.split+' questions...',flush=True)
    traces=[]
    for q in [q for q in questions if q['split']==args.split]:
        v=embedder.embed_query(q['question'])
        for strategy in ['A','B','C']:
            filters=q['filter'] if strategy=='C' else {}
            t=time.perf_counter();hits=store.search(strategy,v,top_k=3,filters=filters)
            traces.append({'id':q['id'],'strategy':strategy,'split':q['split'],'question':q,'applied_filter':filters,'hits':hits,'search_seconds':time.perf_counter()-t,'evaluation':evaluate_query(q,hits)})
        print('  Finished '+q['id'],flush=True)
    save(OUT/f'traces_{args.split}.json',traces)
    all_traces=[]
    for path in sorted(OUT.glob('traces_*.json')):all_traces+=json.loads(path.read_text())
    manual_files(all_traces,chunks,pages)
    report(all_traces,json.loads((OUT/'ingestion_stats.json').read_text()))
    versions={}
    for name in ['pypdf','psycopg','python-dotenv']:
        versions[name]=importlib.metadata.version(name)
    with psycopg.connect(store.database_url,connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute('SHOW server_version');versions['postgres']=cur.fetchone()[0]
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'");versions['pgvector']=cur.fetchone()[0]
    save(OUT/'runtime.json',{'python':sys.version,'platform':platform.platform(),'packages':versions,'config':CONFIG})
    save(OUT/f'usage_{runstamp}.json',{'utc':runstamp,'split':args.split,'seconds':time.perf_counter()-start,'new_api_tokens':embedder.tokens,'successful_api_calls':embedder.api_calls,'cache_hits':embedder.cache_hits,'cost_usd':None,'cost_note':'Use account billing/current price; not zero, not yet measured.'})
    print('6/6 DONE. Open results/lab06_api/REPORT.md and complete manual_review.csv.',flush=True)

if __name__=='__main__':
    try: main()
    except Exception:
        OUT.mkdir(parents=True,exist_ok=True)
        with (OUT/'errors.log').open('a') as f: f.write(datetime.now(timezone.utc).isoformat()+'\n'+traceback.format_exc()+'\n')
        traceback.print_exc();sys.exit(1)
