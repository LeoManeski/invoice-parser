# Invoice Parser

Чита фактура (слика или PDF) и враќа JSON со `vendor`, `bill_to`, `date` и `total`.
Работи локално, само на CPU, чита и англиски и македонски фактури.

Пример:
```json
{ "vendor": "SuperStore", "bill_to": "Aaron Bergman", "date": "Mar 06 2012", "total": 50.1 }
```

## Како работи

PaddleOCR-VL го чита текстот од фактурата (го фаќа и кирилица), qwen2.5 ги вади
vendor/bill_to/date, а total се вади со код бидејќи на фактура има многу бројки
и правилата се посигурни од мал модел.

## Setup

Треба [Ollama](https://ollama.com) и Poppler (за `pdftoppm`, конверзија на PDF во слика).
На Windows Poppler се симнува [оттука](https://github.com/oschwartz10612/poppler-windows/releases)
и `bin` папката се додава во PATH. На Linux: `sudo apt install poppler-utils`.

```bash
git clone https://github.com/LeoManeski/invoice-parser.git
cd invoice-parser

ollama pull hf.co/PaddlePaddle/PaddleOCR-VL-1.5-GGUF
ollama pull qwen2.5:0.5b

python -m venv venv
venv\Scripts\activate
pip install fastapi uvicorn python-multipart requests
```

## Пуштање

Во два терминала:
```bash
ollama serve
uvicorn server:app --port 8000
```

Отвори http://localhost:8000, избери фактури, клик на Парсирај. Резултатот излегува
како JSON (или табела). На CPU секоја фактура трае околу минута.

## Забелешки

Најдобро работи на чисти скенови и PDF-и; накривени слики од телефон знаат да го
збунат OCR-от. qwen2.5:0.5b е доста мал па понекогаш меша vendor/bill_to — ако
треба поточно, qwen2.5:1.5b е посигурен. Тоталот вреди да се проверува рачно.
