from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import requests
import base64
import json
import re
import subprocess
import os

app = FastAPI()
OLLAMA = "http://localhost:11434/api/chat"


def get_image_bytes(file_bytes, filename):
    # ако е PDF, прво го претвораме во слика со pdftoppm
    if filename.lower().endswith(".pdf"):
        with open("temp_input.pdf", "wb") as f:
            f.write(file_bytes)
        subprocess.run(
            ["pdftoppm", "-png", "-f", "1", "-l", "1", "-r", "150", "temp_input.pdf", "temp_upload"],
            check=True
        )
        with open("temp_upload-1.png", "rb") as f:
            img = f.read()
        os.remove("temp_input.pdf")
        os.remove("temp_upload-1.png")
        return img
    # инаку е слика, ги враќаме bytes како што се
    return file_bytes


def read_invoice(image_bytes):
    # PaddleOCR-VL го чита целиот текст од фактурата
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = requests.post(OLLAMA, json={
        "model": "hf.co/PaddlePaddle/PaddleOCR-VL-1.5-GGUF",
        "messages": [{"role": "user", "content": "OCR:", "images": [image_b64]}],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 1024}
    })
    return response.json()["message"]["content"]


def find_total(ocr_text):
    lines = ocr_text.split("\n")
    total_keywords = ["за наплата", "вкупно за", "balance due", "amount due", "total:"]
    candidates = []
    for line in lines:
        low = line.lower()
        if "%" in line or "ддв" in low or "vat" in low or "subtotal" in low:
            continue
        if any(kw in low for kw in total_keywords):
            nums = re.findall(r"\d[\d.,]*\.\d{2}|\d[\d.,]*,\d{2}", line)
            for n in nums:
                if "," in n and "." in n:
                    cleaned = n.replace(",", "") if n.rindex(".") > n.rindex(",") else n.replace(".", "").replace(",", ".")
                elif "," in n:
                    cleaned = n.replace(",", ".")
                else:
                    cleaned = n
                try:
                    candidates.append(float(cleaned))
                except ValueError:
                    pass
    return max(candidates) if candidates else None


def extract_vendor_date(ocr_text):
    prompt = f"""Here is text extracted from an invoice (may be in Macedonian):

{ocr_text}

Extract these fields and return ONLY valid JSON:
- vendor: the company that issued the invoice (at the top)(Macedonian: Издавач / продавач)
- bill_to: customer the invoice is billed TO (Macedonian: Купувач / Примач / До)
- date: the invoice date EXACTLY as written (do not invent). NOT the invoice number.

Return only the JSON object with vendor, bill_to and date."""
    response = requests.post(OLLAMA, json={
        "model": "qwen2.5:0.5b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0}
    })
    return response.json()["message"]["content"]


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Invoice Parser</title>
    <style>
        body { font-family: sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
        h1 { color: #fff; }
        .box { border: 2px dashed #444; border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 20px; }
        button { padding: 8px 20px; font-size: 15px; border-radius: 6px; border: none; background: #6366f1; color: #fff; cursor: pointer; }
        button:disabled { background: #444; }
        #status { margin: 12px 0; color: #aaa; }
        .tabs { margin-bottom: 10px; }
        .tabs button { background: #16213e; margin-right: 6px; }
        pre { background: #16213e; padding: 16px; border-radius: 8px; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #333; font-size: 14px; }
        th { background: #16213e; color: #fff; }
    </style>
</head>
<body>
    <h1>Invoice Parser</h1>

    <div class="box">
        <input type="file" id="file" accept="image/*,.pdf" multiple>
        <br><br>
        <button id="btn" onclick="parseAll()">Парсирај</button>
    </div>

    <div id="status">Избери една или повеќе фактури.</div>

    <!-- копчиња за префрлање помеѓу JSON и табела -->
    <div class="tabs" id="tabs" style="display:none">
        <button onclick="showJson()">JSON</button>
        <button onclick="showTable()">Табела</button>
    </div>

    <pre id="json" style="display:none"></pre>
    <table id="table" style="display:none"></table>

    <script>
        // тука ги чуваме резултатите од сите фактури
        let results = [];

        async function parseAll() {
            const files = document.getElementById("file").files;
            if (files.length === 0) {
                alert("Избери фактура прво");
                return;
            }

            const btn = document.getElementById("btn");
            const status = document.getElementById("status");
            btn.disabled = true;
            results = [];

            // ги праќаме една по една на серверот
            for (let i = 0; i < files.length; i++) {
                status.innerText = "Парсирам " + (i + 1) + "/" + files.length + "  (" + files[i].name + ")...";
                const form = new FormData();
                form.append("file", files[i]);

                const res = await fetch("/parse", { method: "POST", body: form });
                const data = await res.json();
                data.file = files[i].name;
                results.push(data);
            }

            status.innerText = "Готово - " + results.length + " фактури.";
            document.getElementById("tabs").style.display = "block";
            showJson();  // JSON е главниот приказ
        }

        function showJson() {
            document.getElementById("table").style.display = "none";
            const pre = document.getElementById("json");
            pre.style.display = "block";
            pre.innerText = JSON.stringify(results, null, 2);
        }

        function showTable() {
            document.getElementById("json").style.display = "none";
            const table = document.getElementById("table");
            table.style.display = "table";

            let html = "<tr><th>Фајл</th><th>Vendor</th><th>Bill To</th><th>Датум</th><th>Тотал</th></tr>";
            for (const r of results) {
                html += "<tr>";
                html += "<td>" + r.file + "</td>";
                html += "<td>" + (r.vendor || "-") + "</td>";
                html += "<td>" + (r.bill_to || "-") + "</td>";
                html += "<td>" + (r.date || "-") + "</td>";
                html += "<td>" + (r.total || "-") + "</td>";
                html += "</tr>";
            }
            table.innerHTML = html;
        }
    </script>
</body>
</html>
"""


@app.post("/parse")
async def parse(file: UploadFile = File(...)):
    file_bytes = await file.read()
    image_bytes = get_image_bytes(file_bytes, file.filename)

    text = read_invoice(image_bytes)

    llm_result = extract_vendor_date(text)
    print("LLM RETURNED:", llm_result)  # debug

    match = re.search(r"\{.*\}", llm_result, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = {"vendor": None, "bill_to": None, "date": None}
    else:
        data = {"vendor": None, "bill_to": None, "date": None}

    data["total"] = find_total(text)
    return data