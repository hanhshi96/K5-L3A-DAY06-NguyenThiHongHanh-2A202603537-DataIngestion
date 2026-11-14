"""Hỗ trợ chấm thủ công manual_review.csv.
Người chấm: tác giả (tự đọc và nhập nhãn). Script chỉ hiển thị dữ liệu, gợi ý kiểm tra tự động và lưu nhãn.
Chạy:   python3 starter/scripts/label_review.py
Tổng kết: python3 starter/scripts/label_review.py --summary
"""
import csv, json, re, sys, unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results" / "lab06_api"
CSV_PATH = R / "manual_review.csv"
BENCH = ROOT / "benchmark.json"
MANIFEST = ROOT / "data" / "lab06_corpus" / "manifest.json"


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip().lower()


def load(p):
    d = json.load(open(p, encoding="utf-8"))
    if isinstance(d, dict):
        for k in ("chunks", "pages", "traces", "results", "questions"):
            if k in d:
                return d[k]
    return d


chunks = {c["chunk_id"]: c for s in "ABC" for c in load(R / f"chunks_{s}.json")}
pages = {(p["document_id"], int(p["page"])): norm(p.get("text") or p.get("content"))
         for p in load(R / "pages.json")}
questions = {q["id"]: q for q in load(BENCH)}
manifest = {d["document_id"]: d for d in json.load(open(MANIFEST, encoding="utf-8"))["documents"]}
traces = [load(R / "traces_dev.json"), load(R / "traces_test.json")]


def walk(o, strat=None):
    if isinstance(o, dict):
        strat = o.get("strategy", strat)
        yield o, strat
        for k, v in o.items():
            yield from walk(v, k if k in ("A", "B", "C") else strat)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, strat)


def top3(strategy, qid):
    rows = []
    for t in traces:
        for d, s in walk(t):
            if s != strategy or qid not in (d.get("id"), d.get("qid"), d.get("question_id")):
                continue
            for k in ("results", "top3", "top_k", "hits", "retrieved", "chunks"):
                if isinstance(d.get(k), list):
                    return [full(r) for r in d[k][:3]]
            if "chunk_id" in d:
                rows.append(d)
    rows.sort(key=lambda r: r.get("rank", 0))
    return [full(r) for r in rows[:3]]


def full(r):
    cid = r.get("chunk_id") or r.get("id")
    c = dict(chunks.get(cid, {}))
    c.update({k: v for k, v in r.items() if v not in (None, "")})
    c["chunk_id"] = cid
    return c


def show_chunk(c, i=None):
    md = c.get("metadata", {})
    head = f"[{i}] " if i else ""
    print(f"{head}{c['chunk_id']} | doc={c.get('document_id')} page={c.get('page')} "
          f"score={c.get('score', '')} year={md.get('year')} lang={md.get('language')}")
    print("-" * 80)
    print(c.get("text", "(không có text)"))
    print("-" * 80)


def ask(prompt, valid):
    while True:
        a = input(prompt).strip()
        if a == "q":
            sys.exit("Đã lưu. Chạy lại để tiếp tục.")
        if a in valid:
            return a


def summary(rows):
    s = defaultdict(lambda: defaultdict(list))
    for r in rows:
        k, st = r["kind"], r["strategy"]
        if k in ("coherence", "grounding") and r["score_0_2"] != "":
            s[st][k].append(int(r["score_0_2"]))
        if k == "metadata" and r["metadata_correct"]:
            s[st][k].append(r["metadata_correct"] == "yes")
    for st in "ABC":
        coh, gr, md = s[st]["coherence"], s[st]["grounding"], s[st]["metadata"]
        print(f"\n== {st} ==")
        if coh: print(f"Coherence: TB {sum(coh)/len(coh):.2f}/2 (n={len(coh)})")
        if gr: print(f"Grounding: 0/1/2 = {gr.count(0)}/{gr.count(1)}/{gr.count(2)}, TB {sum(gr)/len(gr):.2f}/2")
        if md: print(f"Metadata đủ & đúng: {sum(md)}/{len(md)}")
    print("\nFilter tuân thủ: lấy từ metrics.json (C test: filter_compliant_queries/filter_queries).")


rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
fields = list(rows[0].keys())


def save():
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if "--summary" in sys.argv:
    summary(rows)
    sys.exit()

memo = {}
for r in rows:  # ghi nhớ nhãn đã có để gợi ý cho nội dung trùng (vd. C giống B)
    if r["reason"]:
        memo[r["id"].split(":", 2)[2] + r["kind"]] = r

todo = [r for r in rows if not (r["score_0_2"] or r["metadata_correct"])]
print(f"Còn {len(todo)}/{len(rows)} dòng cần chấm. Gõ q để thoát (đã lưu).")

for n, r in enumerate(todo, 1):
    kind, st = r["kind"], r["strategy"]
    p = r["id"].split(":")
    print("\n" + "=" * 80 + f"\n({n}/{len(todo)}) {kind.upper()} | strategy {st} | {r['source_or_question']}")

    if kind == "coherence":
        c = full({"chunk_id": p[-1]})
        show_chunk(c)
        key = ("coh", c["chunk_id"])
        print("Thang: 0 = cắt giữa ý/thiếu chủ thể, không hiểu | 1 = hiểu một phần, thiếu ngữ cảnh | 2 = tự hiểu, trọn ý")
    elif kind == "grounding":
        q = questions[p[2]]
        print(f"CÂU HỎI: {q['question']}\nĐÁP ÁN: {q['expected_answer']}\n"
              f"GOLD: {q['gold_source_id']} p{q['gold_page']} | EVIDENCE: {q['evidence_quote']}\nFILTER: {q.get('filter')}")
        t = top3(st, p[2])
        for i, c in enumerate(t, 1):
            show_chunk(c, i)
        key = ("gr", p[2], tuple(c["chunk_id"] for c in t))
        print("Thang: 0 = không có bằng chứng | 1 = có nhưng thiếu điều kiện/ngữ cảnh | 2 = đủ để trả lời và truy nguồn")
    else:
        q = questions[p[2]]
        t = top3(st, p[2])
        c = t[int(p[3]) - 1]
        show_chunk(c)
        md, m = c.get("metadata", {}), manifest.get(c.get("document_id"), {})
        page_ok = norm(c.get("text", ""))[:120] in pages.get((c.get("document_id"), int(c.get("page", 0))), "")
        print(f"Gợi ý tự động (vẫn cần bạn xác nhận):\n"
              f"  source khớp manifest: {c.get('source') == m.get('source')}\n"
              f"  đầu chunk nằm trong trang {c.get('page')}: {page_ok}\n"
              f"  year {md.get('year')} vs manifest {m.get('year')} | language {md.get('language')} vs {m.get('language')}\n"
              f"  filter của câu hỏi: {q.get('filter')}")
        key = ("md", c["chunk_id"])

    prev = memo.get(key)
    if prev and input(f"Đã chấm nội dung giống hệt: {prev}. Enter để dùng lại, n để chấm mới: ").strip() != "n":
        r["score_0_2"], r["metadata_correct"] = prev
        r["reason"] = prev_reason = memo[key + ("reason",)]
    else:
        if kind == "metadata":
            r["metadata_correct"] = {"y": "yes", "n": "no"}[ask("Metadata ĐỦ và ĐÚNG? (y/n): ", {"y", "n"})]
        else:
            r["score_0_2"] = ask("Điểm (0/1/2): ", {"0", "1", "2"})
        while not (reason := input("Lý do: ").strip()):
            print("Lý do là bắt buộc.")
        r["reason"] = reason
    memo[key] = (r["score_0_2"], r["metadata_correct"])
    memo[key + ("reason",)] = r["reason"]
    save()

print("\nXONG. Tổng kết:")
summary(rows)