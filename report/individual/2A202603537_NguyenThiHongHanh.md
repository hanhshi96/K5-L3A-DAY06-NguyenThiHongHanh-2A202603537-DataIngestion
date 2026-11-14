# Lab 06 — Đánh giá ba chiến lược ingestion và truy xuất

**Corpus:** Nghị định 13/2023/NĐ-CP và *Attention Is All You Need*.  
**Kết luận từ dev:** chọn cấu hình A theo quy tắc ưu tiên Evidence Hit@3, rồi Hit@1, rồi số chunk thấp hơn.  
**Trạng thái đánh giá:** số đo retrieval và tài nguyên lấy từ lần chạy thật. Nhãn coherence, grounding và rà metadata dưới đây do ChatGPT đề xuất sau khi đọc evidence và đối chiếu PDF; **người học chưa xác nhận, không phải chấm thủ công độc lập**. File `manual_review_ai_suggested.csv` ghi phương pháp và trạng thái từng dòng.

## 1. Dữ liệu và phương pháp

| Tài liệu | Trang PDF sử dụng | Số trang | Metadata ngôn ngữ |
|---|---|---:|---|
| Nghị định 13/2023/NĐ-CP | 1–29 | 29 | `vi` |
| Attention Is All You Need | 1–9 | 9 | `en` |
| Tổng | | **38** | |

Đếm trang có nội dung, không lấy các trang biểu mẫu trống và trang chỉ có tài liệu tham khảo. Trang đầu hai tài liệu vẫn chứa nội dung quy định hoặc abstract, không chỉ là bìa. Số trang gold là **trang vật lý trong PDF**; chẳng hạn ND13 PDF 29 được in số Công báo 31. Manifest lưu nguồn, checksum, danh sách trang và số ký tự.

Bộ benchmark gồm 20 câu, được chuẩn bị với AI hỗ trợ và cố định trước truy xuất: 15 dev và 5 test. Có 3 câu dev và 2 câu test cung cấp filter ngôn ngữ. Gold evidence được kiểm tra tồn tại ở đúng trang sau chuẩn hóa. Filter là phạm vi được nêu trong câu hỏi trước truy xuất, không được suy từ đáp án. Chia tập trong cùng hai tài liệu, chưa bảo đảm độc lập theo chủ đề.

Pipeline: đọc bằng pypdf → chuẩn hóa Unicode/whitespace → chia chunk → OpenAI embedding → PostgreSQL/pgvector → exact cosine top-3 → chấm tự động và lưu trace. Model `text-embedding-3-small`, cấu hình rõ **1536 chiều**, dùng giống nhau cho query và document. Gọi API qua thư viện chuẩn Python, không dùng vector giả. Có giới hạn input 6000 UTF-8 bytes, báo lỗi thay vì âm thầm cắt nội dung. Token thực tế do API trả về; không gọi đây là chunking theo token.

| Cấu hình | Chunking | Truy xuất |
|---|---|---|
| A | Cửa sổ 900 ký tự, overlap 150 | Không filter |
| B | Gom đoạn, tối đa 900 ký tự; đoạn quá dài tách gần whitespace | Không filter |
| C | Dùng đúng chunk và vector của B | Áp dụng filter khi câu hỏi cung cấp; câu khác không filter |

Bảng lưu là `lab06_api_chunks`. Mỗi chunk có ID ổn định, document_id, source, page, metadata và ranh giới ký tự. Upsert toàn bộ snapshot từng tài liệu để thay chunk cũ; runner dọn tài liệu không còn trong snapshot. Bảng `lab06_chunks` cũ không bị sửa.

## 2. Độ chính xác truy xuất

Một hit tự động phải đúng document/page và chứa **toàn bộ gold evidence trong một chunk**. So khớp chuẩn hóa NFC và bỏ whitespace nhưng giữ chữ, dấu và nội dung. Có hỗ trợ alternative gold nếu khai báo. Không tính hợp evidence của nhiều chunk vào chỉ số Hit@3 bắt buộc. Phép so khớp này có thể bỏ sót bằng chứng tương đương chưa khai báo; không xem nó là thước đo ngữ nghĩa tuyệt đối.

| Cấu hình | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 |
|---|---:|---:|---:|---:|
| **A** | 7/15 (46,7%) | **11/15 (73,3%)** | 2/5 (40,0%) | **5/5 (100,0%)** |
| B | 7/15 (46,7%) | 10/15 (66,7%) | 2/5 (40,0%) | 3/5 (60,0%) |
| C | 7/15 (46,7%) | 10/15 (66,7%) | 2/5 (40,0%) | 3/5 (60,0%) |

A hơn B/C một câu Hit@3 trên dev, là cơ sở chọn cấu hình theo quy tắc đã khai báo. Kết quả test xác nhận lợi thế trên mẫu nhỏ này, nhưng không dùng để chỉnh lại cấu hình. Hit@3 100% chỉ nghĩa là top-3 có chunk đạt gold cho 5 câu test; không phải độ chính xác câu trả lời LLM. Không có bước sinh câu trả lời được đánh giá trong thí nghiệm này.

## 3. Tính mạch lạc của chunk — nhãn AI đề xuất

Chấm cùng 10 vị trí đã cố định: ký tự 450 trên 5 trang đầu của mỗi tài liệu. Mỗi cấu hình có 10 chunk bao phủ các vị trí này. Thang điểm: 0 = không hiểu vì cắt/thiếu chủ thể; 1 = hiểu một phần nhưng thiếu ngữ cảnh hoặc cắt ý; 2 = tự hiểu được và trọn ý. Đánh giá toàn chunk, không chỉ một câu quanh điểm neo.

| Cấu hình | Số mẫu | Số mức 0 / 1 / 2 | Điểm trung bình /2 |
|---|---:|---|---:|
| A | 10 | 0 / 10 / 0 | 1,00 |
| B | 10 | 0 / 9 / 1 | 1,10 |
| C | 10 | 0 / 9 / 1 | 1,10 |

B/C giữ trọn phần căn cứ trên trang đầu ND13 tốt hơn A, trong khi A kết thúc ở “2. Nghị”. Tuy vậy, phần lớn chunk vẫn cắt giữa câu hoặc danh sách do giới hạn 900 ký tự. Ở bài báo PDF 4, cả A và B/C dừng công thức tại dấu bằng; ở PDF 3, câu về kích thước output chưa trọn ý. B có fallback khi đoạn dài và PDF không giữ tốt dòng trống, nên tên “theo đoạn” không bảo đảm trọn nghĩa.

Mẫu có điểm neo thuộc phần tác giả/căn cứ ở trang đầu, thiên lệch về đầu tài liệu. Không thay điểm neo sau khi xem kết quả. Nhãn và lý do từng dòng trong CSV cần người học rà lại; chưa được coi là hoàn thành tiêu chí chấm thủ công độc lập.

## 4. Tính hữu dụng của metadata

Đã đối chiếu 45 hit test (5 câu × top-3 × 3 cấu hình) với hai PDF: URL nguồn theo manifest, trang PDF, ngôn ngữ, năm và đoạn text ở ranh giới start/end đều khớp. Đây là kiểm tra bằng mã kết hợp rà evidence có AI hỗ trợ, chưa phải người học tự kiểm tra từng bản ghi.

| Cấu hình | Metadata được đối chiếu đúng / số hit | Câu dev tuân thủ phạm vi filter | Câu test tuân thủ phạm vi filter |
|---|---:|---:|---:|
| A | 15/15 | 3/3 | 2/2 |
| B | 15/15 | 3/3 | 2/2 |
| C | 15/15 | 3/3 | 2/2 |

A/B không thực thi filter, nhưng các kết quả quan sát vẫn đúng ngôn ngữ được yêu cầu. Vì vậy chưa có bằng chứng filter giúp tăng điểm. C bảo đảm điều kiện ngôn ngữ ở truy vấn; trong cả 5 câu test, thứ tự và nội dung top-3 B/C cũng giống nhau.

`source` và `page` giúp kiểm tra lại bằng chứng, `language` cho phép giới hạn phạm vi. Tuy nhiên, metadata đúng không đồng nghĩa nội dung hữu ích: ở Q10 của B/C, cả ba hit chỉ có tiêu đề Công báo. Không nhầm ngày in Công báo với ngày hiệu lực của nghị định.

## 5. Chất lượng grounding — nhãn AI đề xuất

Đọc toàn bộ top-3 cho cùng 5 câu test, đánh giá đủ bằng chứng trả lời và truy nguồn: 0 = không có evidence trả lời; 1 = có nhưng thiếu ý/điều kiện; 2 = đủ. Không suy nhãn này trực tiếp từ exact match; đã đọc nội dung các hit. Các điểm dưới đây vẫn chờ người học xác nhận.

| Câu test | A | B | C | Bằng chứng/lỗi chính |
|---|---:|---:|---:|---|
| Q08 — cơ quan, 72 giờ, thông báo muộn | 2 | 2 | 2 | Top-1 ở ND13 PDF 18 đủ cả ba ý |
| Q09 — thời điểm áp dụng biện pháp bảo vệ | 2 | 2 | 2 | A top-2, B/C top-1 ở ND13 PDF 23 đủ ý |
| Q10 — ngày bắt đầu hiệu lực Điều 43 | 2 | 0 | 0 | A top-1 PDF 29; B/C chỉ trả tiêu đề Công báo |
| Q19 — label smoothing và tác động | 2 | 2 | 2 | Top-2 bài báo PDF 8 nêu 0.1 và đủ tác động |
| Q20 — số checkpoint và khoảng thời gian | 2 | 0 | 0 | A top-3 PDF 8 đủ; B/C thiếu đoạn cần thiết |
| **Trung bình /2** | **2,00** | **1,20** | **1,20** | |

Phân bố mức 0/1/2: A = 0/0/5; B = 2/0/3; C = 2/0/3. Ở Q20, đoạn “no checkpoint averaging” mà B/C trả về thuộc thí nghiệm biến thể ở trang 9, không trả lời câu hỏi về base model ở trang 8. Cần phân biệt ngữ cảnh để không đưa ra câu trả lời sai dù từ khóa tương đồng.

## 6. Tài nguyên và tác động của chiến lược

Số đo từ `ingestion_stats.json`, lần ingest đầu; thời gian tổng gồm **hai lượt upsert** phục vụ kiểm tra idempotency, không phải latency truy vấn.

| Đại lượng | A | B | C |
|---|---:|---:|---:|
| Số chunk | 121 | 137 | 137 |
| Tổng ký tự chunk | 93.832 | 81.295 | 81.295 |
| Độ dài nhỏ nhất / trung vị / lớn nhất | 185 / 899 / 900 | 9 / 890 / 899 | 9 / 890 / 899 |
| Chia chunk + embedding (giây) | 4,005 | 5,025 | ~0,000003 (tái sử dụng) |
| Tổng gồm hai upsert (giây) | 4,480 | 5,537 | 0,479 |
| Token API embedding mới | 39.264 | 33.011 | 0 |
| Đoạn lấy từ cache | 0 | 4 | Dùng lại vector B |
| Số bản ghi sau hai lần nạp | 121 → 121 | 137 → 137 | 137 → 137 |

A có overlap nên tổng ký tự gửi xử lý nhiều hơn B, dù ít chunk hơn. B tạo cả những chunk rất ngắn: min 9 ký tự; lỗi Q10 minh họa rủi ro các mẩu header thiếu nội dung được xếp hạng cao. Giải thích này dựa vào evidence đã thấy, không khẳng định đó là nguyên nhân duy nhất của mọi chênh lệch.

C không tạo embedding mới vì dùng lại B. Thời gian gần bằng 0 của bước chia/embedding C không chứng minh thuật toán C tự thân nhanh hơn: đây là phép tái sử dụng có chủ đích. Thời gian A/B là một lần chạy và B có 4 cache hits, nên chưa phải benchmark tốc độ độc lập có kiểm soát.

**Chi phí:** ghi nhận **72.275 token embedding tài liệu mới** trong lần ingest đầu (39.264 + 33.011). Chưa bao gồm embedding câu hỏi, kiểm tra kết nối và các lần chạy khác. Chưa có toàn bộ `usage_*.json` hoặc billing, nên chưa xác định tổng tiền thực trả. Công thức cho riêng phần token này là `72.275 / 1.000.000 × đơn giá áp dụng cho 1 triệu token`; không ghi API cost bằng 0. Không thay tổng token này bằng tổng chi phí toàn bài.

## 7. Lựa chọn, giới hạn và tái lập

Chọn A theo dev: Hit@3 cao nhất và số chunk thấp hơn. B/C nhỉnh hơn 0,1 điểm coherence trong mẫu AI đề xuất, nhưng không bù được lợi thế retrieval của A. Dữ liệu hai chủ đề và hai ngôn ngữ cách biệt làm filter dễ tuân thủ ngay cả khi không áp dụng, lệch gợi ý corpus chủ đề hẹp. Test chỉ 5 câu, chia trong cùng corpus, phần chấm định tính chưa xác nhận độc lập, nên không suy rộng lựa chọn ra các bộ dữ liệu khác.

Nghị định 13 được dùng như snapshot lịch sử; đã hết hiệu lực từ 01/01/2026 theo khoản 2 Điều 42 NĐ356/2025. Câu hỏi chỉ hỏi nội dung văn bản này, không tư vấn pháp luật hiện hành. Giữ checksum của bản bài báo đã sử dụng; không mặc định URL arXiv luôn trả cùng phiên bản.

Các hướng cải thiện cho **thí nghiệm sau**: bỏ header/footer, loại hoặc ghép chunk ngắn thiếu ngữ nghĩa, chia theo điều/khoản hoặc câu, cải thiện xử lý bảng/công thức, xây corpus có phạm vi gần nhau để đo filter. Không áp dụng các thay đổi này lên test hiện tại rồi báo như lần đánh giá chưa từng thấy.

Lệnh chạy từ `starter/`:

```bash
python -u -m src.run --check
python -u -m src.run --split dev
python -u -m src.run --split test
```

Nộp kèm mã nguồn, manifest, benchmark, `metrics.json`, `traces_dev.json`, `traces_test.json`, `ingestion_stats.json`, `experiment_lock.json`, `runtime.json`, các log usage và mẫu review. `.env` và cache vector không đưa vào git. Phiên bản backend/thư viện xem `runtime.json` của máy chạy; báo cáo này không tự điền phiên bản chưa được cung cấp.

**Lưu ý cập nhật:** đây là báo cáo phân tích bổ sung, giữ tên `REPORT_FINAL.md`. Lệnh `--report-only` chỉ tái sinh `REPORT.md` mẫu và không cập nhật nội dung phân tích này. Nếu người học đổi nhãn, cần sửa bảng tổng hợp định tính tương ứng và ghi trạng thái xác nhận.

## Nguồn và minh chứng

- `REPORT.md` người học gửi: số đo retrieval dev/test; `ingestion_stats.json`: số đo tài nguyên.
- `manual_evidence.md`: 30 chunk coherence và top-3 của 15 lượt test; `manual_review.csv`: mẫu nhãn ban đầu trống.
- `manual_review_ai_suggested.csv`: 90 dòng nhãn/lý do đề xuất, ghi rõ AI-assisted và pending_human_review.
- Nghị định 13 bản Công báo: https://congbao.cdnchinhphu.vn/CongBaoCP/VanBan/2023/4/39228/44543-1-2023685-68613-2023-nd-cp.pdf
- Vaswani et al., *Attention Is All You Need*: https://arxiv.org/pdf/1706.03762
- NĐ356/2025, Điều 42 (chỉ để xác định trạng thái văn bản, không thuộc corpus): https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/01/356-nd.signed.pdf

Chỉ nộp/phát hành nội dung nguồn trong phạm vi được phép; không tự gán giấy phép CC cho bài báo. Việc nhãn được AI đề xuất đã được công bố; cần người học kiểm tra để hoàn tất phần chấm thủ công mà đề yêu cầu.
