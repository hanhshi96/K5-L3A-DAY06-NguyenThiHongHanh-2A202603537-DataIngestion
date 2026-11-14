# Báo cáo cá nhân — Day 6

**Học viên:** Nguyễn Thị Hồng Hạnh · **MSSV:** 2A202603537 · **Lớp:** L3A
**Corpus:** Nghị định 13/2023/NĐ-CP và *Attention Is All You Need* · **Chiến lược chọn:** A (chọn trên dev)

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** corpus song ngữ gồm 2 tài liệu, tổng **38 trang nội dung**. Số trang tính theo **trang vật lý trong PDF** (vd. trang PDF 29 của Nghị định 13 mang số trang Công báo 31).

  | Tài liệu | Nguồn | Trang dùng | Số trang | Trang loại |
  |---|---|---|---:|---|
  | Nghị định 13/2023/NĐ-CP, `vi`, 2023 | [Công báo](https://congbao.cdnchinhphu.vn/CongBaoCP/VanBan/2023/4/39228/44543-1-2023685-68613-2023-nd-cp.pdf) | 1–29 | 29 | 30–37 (biểu mẫu) |
  | Attention Is All You Need, `en`, 2017 | [arXiv 1706.03762](https://arxiv.org/abs/1706.03762) | 1–9 | 9 | 10–15 (tài liệu tham khảo, phụ lục hình) |
  | **Tổng** | | | **38** | |

  Trang đầu của cả hai tài liệu có nội dung thật (phần căn cứ của Nghị định, abstract của bài báo), không chỉ là bìa. Quyền sử dụng: Nghị định là văn bản quy phạm pháp luật, không thuộc đối tượng bảo hộ quyền tác giả. Bài báo dùng theo license arXiv cho mục đích học thuật, có ghi nguồn, **không phân phối lại PDF**; PDF nằm trong `.gitignore`, manifest lưu URL và sha256 để tải lại đúng bản. Nghị định 13 chỉ được dùng như một snapshot lịch sử, không dùng để tư vấn pháp luật hiện hành. Manifest: `starter/data/lab06_corpus/manifest.json`.
- **Chuẩn hóa, lỗi và giới hạn:** đọc PDF bằng `pypdf`, chuẩn hóa Unicode NFC và khoảng trắng. Mỗi trang được ghi các cờ `has_text`, `low_text`, `extraction_status`. Không có trang rỗng hoặc lỗi trong 38 trang đã chọn. Các giới hạn còn lại: trích xuất tiếng Việt đôi khi tách chữ (vd. "trách nhi ệm"); chưa loại header Công báo; công thức toán bị cắt; PDF không giữ dòng trống ổn định nên việc tách đoạn chưa chính xác.
- **Embedding và vector store:** OpenAI `text-embedding-3-small`, **1536 chiều**, dùng cùng model cho query và document; không dùng vector giả. Input giới hạn 6000 byte UTF-8, vượt giới hạn thì báo lỗi thay vì âm thầm cắt. Vector store: PostgreSQL + pgvector (`docker-compose.yml`, `init.sql`), bảng `lab06_api_chunks`, tìm kiếm **exact cosine** top-3. Phiên bản thư viện/backend xem `starter/results/lab06_api/runtime.json`. Chi phí: **72.275 token** embedding tài liệu ở lần ingest đầu (A 39.264 + B 33.011), ước tính khoảng 0,0015 USD theo đơn giá công bố 0,02 USD/1 triệu token. Con số này chưa gồm token embedding câu hỏi và chưa đối chiếu hóa đơn.
- **Metadata:** các trường bắt buộc là `chunk_id` (ổn định), `document_id`, `source`, `page`, `start_char`/`end_char`. Trường lọc bổ sung: `language` (`vi`/`en`), `year` (2023/2017), `report_type` (`legal_decree`/`paper`); giá trị lấy từ manifest và đã kiểm chứng với nguồn. Chọn `language` làm trường lọc vì người dùng thường nêu rõ ngôn ngữ hoặc văn bản cần hỏi ngay từ đầu, trước khi truy xuất.

## Cấu hình và benchmark

- **A / B / C:**

  | Cấu hình | Chunking | Truy xuất |
  |---|---|---|
  | A | Cửa sổ cố định 900 ký tự, overlap 150 | Không filter |
  | B | Gom theo đoạn, tối đa 900 ký tự; đoạn quá dài tách gần khoảng trắng | Không filter |
  | C | **Dùng đúng chunk và vector của B** (đã kiểm tra: cùng 137 chunk, text giống hệt) | Filter `language` khi câu hỏi có filter; câu không có filter chạy như B |

  B–C chỉ khác nhau ở bước lọc; A–B chỉ khác nhau ở cách chunk. Cả ba dùng cùng model, cùng store, cùng benchmark.
- **Benchmark:** 20 câu (`starter/benchmark.json`), chia **15 dev / 5 test**, khóa trước khi truy xuất (`experiment_lock.json`). Có 5 câu có filter `language`: Q01, Q11, Q15 thuộc dev và **Q08, Q19 thuộc test**. Mỗi câu có `expected_answer`, `gold_source_id`, `gold_page`, `evidence_quote`, kèm `alternative_gold` nếu có. Evidence được kiểm tra là có mặt ở đúng trang sau chuẩn hóa. Giá trị filter được nêu sẵn trong câu hỏi trước khi truy xuất, không suy ra từ đáp án. Benchmark soạn với hỗ trợ của AI và do tác giả kiểm tra lại. Dev và test chia trong cùng hai tài liệu, nên có nguy cơ rò rỉ chủ đề.
- **Tiêu chí chọn chiến lược (chốt trước khi xem test):** Evidence Hit@3 trên dev, rồi đến Hit@1 trên dev, cuối cùng là số chunk ít hơn.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian chunk + embed | Chi phí (token embed) |
|---|---|---|---|---|---|---|
| A | dev | 7/15 | **11/15** | 121 | 4,005 s | 39.264 |
| A | test | 2/5 | **5/5** | 121 | | |
| B | dev | 7/15 | 10/15 | 137 | 5,025 s | 33.011 |
| B | test | 2/5 | 3/5 | 137 | | |
| C | dev | 7/15 | 10/15 | 137 (dùng lại B) | ~0 s (tái sử dụng vector B) | 0 |
| C | test | 2/5 | 3/5 | 137 (dùng lại B) | | |

Một lượt được tính là hit khi chunk đúng tài liệu/trang gold và chứa **toàn bộ** evidence trong một chunk (so khớp sau chuẩn hóa NFC; có tính `alternative_gold`). Bằng chứng nằm rải trên nhiều chunk không được tính. Hit@3 đo khả năng truy xuất evidence, không phải độ chính xác câu trả lời của LLM.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,10 (10) | 15/15 | 2/2 (không lọc; top-3 tự đúng ngôn ngữ) | 0/0/5 — **2,00** |
| B | 1,10 (10) | 15/15 | 2/2 (không lọc; top-3 tự đúng ngôn ngữ) | 0/2/3 — 1,60 |
| C | 1,10 (10) | 15/15 | 2/2 | 0/2/3 — 1,60 |

**Coherence:** phân bố điểm 0/1/2 của cả A, B và C đều là **0 / 9 / 1**. Phần lớn chunk của cả hai cách chia đều bị cắt giữa câu hoặc giữa danh sách do giới hạn 900 ký tự. Ví dụ, chunk A ở trang 1 Nghị định 13 kết thúc ở "2. Nghị"; ở trang 4 bài báo, chunk dừng ngay giữa công thức.

**Grounding từng câu test:**

| Câu | A | B | C | Lý do (người chấm) |
|---|---:|---:|---:|---|
| Q08 | 2 | 2 | 2 | Cả hai đều có Điều 23 khoản 1: cơ quan nhận thông báo, thời hạn 72 giờ, giải trình khi thông báo muộn |
| Q09 | 2 | 1 | 1 | A: chunk [2] trang 23 (Điều 26 khoản 1) chứa nguyên văn đáp án; B/C: thông tin bị cắt |
| Q10 | 2 | 2 | 2 | Cả hai chứa nguyên văn, khớp đáp án |
| Q19 | 2 | 2 | 2 | Chunk [2] trang 8: label smoothing 0.1, giảm perplexity nhưng tăng accuracy/BLEU |
| Q20 | 2 | 1 | 1 | A: chunk [3] trang 8 nêu 5 checkpoint cuối, cách nhau 10 phút; B/C: bị cắt câu |

**Metadata:** cả 45 bản ghi (5 câu test × top-3 × 3 cấu hình) đều có `source`, `page`, `year`, `language` khớp manifest và trang nguồn. Có 6 bản ghi metadata đúng nhưng **nội dung chunk không đủ để trả lời** (A: Q08 rank 2 và 3, Q09 rank 3, Q10 rank 1; B/C: Q09 rank 1). Như vậy, metadata đúng chưa có nghĩa là chunk hữu ích.

**Tài nguyên** (lấy từ `ingestion_stats.json`):

| Đại lượng | A | B | C |
|---|---:|---:|---:|
| Số chunk | 121 | 137 | 137 |
| Tổng ký tự chunk | 93.832 | 81.295 | 81.295 |
| Độ dài nhỏ nhất / trung vị / lớn nhất | 185 / 899 / 900 | 9 / 890 / 899 | 9 / 890 / 899 |
| Tổng thời gian gồm hai lượt upsert (s) | 4,480 | 5,537 | 0,479 |
| Số bản ghi sau hai lần nạp | 121 → 121 | 137 → 137 | 137 → 137 |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace: `starter/results/lab06_api/traces_dev.json`, `traces_test.json`; chỉ số: `metrics.json`; tài nguyên: `ingestion_stats.json`.
- Nhãn: `starter/results/lab06_api/manual_review.csv`, gồm 90 dòng, mỗi dòng có điểm và lý do. Công cụ hỗ trợ chấm: `starter/scripts/label_review.py`.
- Coherence: 10 vị trí được cố định trước khi xem điểm (ký tự thứ 450 trên 5 trang đầu của mỗi tài liệu), áp dụng giống nhau cho cả 3 cấu hình. Mẫu này thiên về phần đầu tài liệu.
- Metadata và grounding: 5 câu test × top-3. Metadata được đối chiếu với manifest và text trang, có gợi ý tự động hỗ trợ.
- **Người chấm là tác giả**, nên có nguy cơ thiên lệch. Với C, nhãn của B được dùng lại vì chunk và top-3 giống hệt nhau.

## Phân tích và kết luận

- **So sánh A–B (thay chunking):** A truy xuất tốt hơn: Hit@3 dev 11/15 so với 10/15, test 5/5 so với 3/5; Hit@1 bằng nhau. Grounding A đạt 2,00/2. B chỉ đạt 1,60/2 vì có 2 câu mà evidence bị cắt ở ranh giới chunk. Overlap 150 ký tự giúp A giữ được trọn câu nằm ở ranh giới. Coherence bằng nhau (1,10/2): chia "theo đoạn" chưa giúp trọn ý, vì PDF không giữ dòng trống ổn định và B có bước tách dự phòng cho đoạn dài. Metadata của cả hai đều đúng 15/15, nên cách chunk không ảnh hưởng đến khả năng truy vết. Về tài nguyên, A tốn nhiều ký tự và token hơn (93.832 ký tự, 39.264 token so với 81.295 ký tự, 33.011 token) dù ít chunk hơn. B sinh ra cả những chunk rất ngắn (ngắn nhất 9 ký tự, chủ yếu là mẩu header).
- **So sánh B–C (chỉ thay filter):** mọi chỉ số giống hệt nhau, và top-3 của B và C trùng nhau ở cả 5 câu test. Ngay cả khi không lọc, kết quả của B đã tuân thủ filter (3/3 câu dev, 2/2 câu test), vì truy vấn tiếng Việt tự trả về Nghị định 13 và truy vấn tiếng Anh tự trả về bài báo. Mỗi giá trị `language`/`year` chỉ ứng với một tài liệu, nên filter thực chất là chọn tài liệu, và **chưa có bằng chứng filter cải thiện kết quả** trên corpus này. Metadata vẫn hữu ích cho việc truy vết: `source` và `page` dẫn thẳng đến trang PDF để kiểm chứng.
- **Hai ví dụ sai:**
  1. **Q09** (test, gold: Nghị định 13 trang 23, Điều 26 khoản 1). A có nguyên văn đáp án ở chunk [2]. Ở B/C, chunk chứa evidence bị cắt nên thiếu thông tin (grounding 1).
  2. **Q20** (test, gold: bài báo trang 8). A có đủ thông tin "5 checkpoint cuối, cách nhau 10 phút" ở chunk [3]. Ở B/C, câu chứa evidence bị cắt (grounding 1).
- **Chiến lược chọn: A**, theo đúng tiêu chí đã chốt: Hit@3 dev cao nhất (11/15), Hit@1 bằng nhau, ít chunk hơn (121 so với 137). Kết quả test (Hit@3 5/5, grounding 2,00) nhất quán với lựa chọn này nhưng không được dùng để chỉnh cấu hình. Đánh đổi: overlap làm tăng khoảng 19% số token embedding. Điều kiện áp dụng: corpus nhỏ, ưu tiên độ phủ evidence.
- **Hạn chế:** test chỉ có 5 câu (chênh 1 câu tương đương 20 điểm %) và dev chỉ chênh 1 câu, nên khác biệt A–B chưa chắc có ý nghĩa thống kê. Hai tài liệu khác hẳn nhau về chủ đề và ngôn ngữ, nên filter dễ tuân thủ ngay cả khi không lọc. Nhãn do một người chấm, cũng là tác giả. Mẫu coherence thiên về đầu tài liệu. Thời gian chỉ đo một lần chạy và B có 4 lượt lấy từ cache, nên chưa phải benchmark tốc độ có kiểm soát. Chi phí chỉ là ước tính từ số token. Kết luận chỉ áp dụng cho corpus này.
- **Nếu làm lại hoặc mở rộng:** bỏ header/footer Công báo; ghép hoặc loại chunk quá ngắn; chunk theo Điều/Khoản cho văn bản luật; xử lý công thức và bảng; xây corpus cùng ngôn ngữ nhưng khác năm hoặc phiên bản để filter có tác dụng thật; mở rộng tập test, tạo tập test mới cho các thay đổi trên thay vì dùng lại test hiện tại; thử hybrid BM25.

## Tái lập

Chạy từ thư mục `starter/`. Cần file `.env` có `OPENAI_API_KEY` (xem `.env.example`) và tải PDF theo URL trong manifest.

```bash
docker compose up -d
python -u -m src.run --check
python -u -m src.run --split dev
python -u -m src.run --split test
python3 scripts/label_review.py --summary
```

Nạp lại không tạo bản ghi trùng: dữ liệu được upsert theo `chunk_id` ổn định, và số bản ghi sau hai lần nạp không đổi (121 → 121, 137 → 137). `.env`, PDF và cache embedding không đưa vào git.

## Sử dụng AI

Dùng ChatGPT và Claude để hỗ trợ viết code, soạn benchmark và trình bày báo cáo. Tác giả đã chạy pipeline, kiểm tra evidence và **tự chấm toàn bộ 90 nhãn thủ công**; nhãn do AI đề xuất trước đó đã bị loại, không dùng trong báo cáo này. Mọi số liệu lấy từ các file kết quả của lần chạy thật.