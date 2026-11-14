# Bài làm — Nguyễn Thị Hồng Hạnh (2A202603537)

| Thành phần | Đường dẫn |
|---|---|
| Code pipeline | `starter/src/` (`run.py`, `ingestion.py`, `chunking.py`, `embeddings.py`, `store.py`, `evaluation.py`) |
| Corpus + manifest | `starter/data/lab06_corpus/manifest.json` (bản sao: `data/manifest.json`); PDF không commit, tải theo URL trong manifest |
| Benchmark 20 câu (15 dev / 5 test) | `starter/benchmark.json` (bản sao: `benchmark/questions.json`) |
| Kết quả, trace, chỉ số | `starter/results/lab06_api/` (`metrics.json`, `traces_dev.json`, `traces_test.json`, `ingestion_stats.json`, `runtime.json`) |
| Nhãn thủ công (90 dòng) | `starter/results/lab06_api/manual_review.csv`; công cụ chấm `starter/scripts/label_review.py` |
| Experiment log | `artifacts/experiment_log.csv` |
| Báo cáo | `report/individual/2A202603537_NguyenThiHongHanh.md` |

**Chạy lại** (từ `starter/`, cần Docker, Python 3.11+, `OPENAI_API_KEY` trong `.env`):

```bash
cd starter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # điền OPENAI_API_KEY
docker compose up -d
# tải 2 PDF theo URL trong data/lab06_corpus/manifest.json vào data/lab06_corpus/ (nd13_2023.pdf, attention_2017.pdf)
python -u -m src.run --check
python -u -m src.run --split dev
python -u -m src.run --split test
python3 scripts/label_review.py --summary
```

Embedding: OpenAI `text-embedding-3-small` (1536 chiều) · Vector store: PostgreSQL + pgvector, exact cosine · Chi phí: 72.275 token embed tài liệu (≈0,0015 USD ước tính).

---

# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
