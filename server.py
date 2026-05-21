import os
import io
import json
import tenacity
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from dotenv import load_dotenv

from google import genai
from google.genai import types
import fitz  # PyMuPDF
from PIL import Image

load_dotenv()

app = FastAPI(title="EquiGrade AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/public", StaticFiles(directory="public"), name="public")

SYSTEM_INSTRUCTION = """You are 'EquiGrade AI', an expert grading assistant.
Your task is to evaluate handwritten student answer sheets against a teacher's marking scheme.
You must strictly output ONLY valid JSON matching this exact structure:
{
  "evaluations": [
    {
      "question_number": "Q1",
      "extracted_answer": "typed version of the student's handwritten answer",
      "suggested_marks": 4,
      "total_marks": 5,
      "marks_breakdown": {
        "Key Point 1": 2,
        "Key Point 2": 2
      },
      "missing_points": ["What the student missed"],
      "feedback": "Overall constructive feedback."
    }
  ]
}
Ensure you process ALL questions present in the answer sheet that match the marking scheme.
Do NOT include markdown code fences like ```json in the output, just raw JSON.
"""

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
]

def load_pdf_images(pdf_bytes: bytes, max_pages=3):
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for i in range(min(max_pages, len(doc))):
            page = doc.load_page(i)
            pix = page.get_pixmap()
            mode = "RGBA" if pix.alpha else "RGB"
            images.append(Image.frombytes(mode, [pix.width, pix.height], pix.samples))
    except Exception as exc:
        print(f"PDF load error: {exc}")
    return images

@app.post("/api/evaluate")
async def evaluate(
    scheme: str = Form(...),
    qp_file: Optional[UploadFile] = File(None),
    as_file: UploadFile = File(...)
):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured in backend.")

    client = genai.Client(api_key=api_key)
    parts = []

    if qp_file and qp_file.filename:
        qp_bytes = await qp_file.read()
        parts.append(types.Part.from_text(text="Context — Question Paper:"))
        if qp_file.filename.lower().endswith(".pdf"):
            for img in load_pdf_images(qp_bytes, max_pages=3):
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"))
        else:
            mime = "image/png" if qp_file.filename.lower().endswith(".png") else "image/jpeg"
            parts.append(types.Part.from_bytes(data=qp_bytes, mime_type=mime))

    as_bytes = await as_file.read()
    parts.append(types.Part.from_text(text="Student Answer Sheet to Evaluate:"))
    if as_file.filename.lower().endswith(".pdf"):
        for img in load_pdf_images(as_bytes, max_pages=10):
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"))
    else:
        mime = "image/png" if as_file.filename.lower().endswith(".png") else "image/jpeg"
        parts.append(types.Part.from_bytes(data=as_bytes, mime_type=mime))

    prompt = (
        f"Here is the strict marking scheme:\n\n{scheme}\n\n"
        "Please evaluate the student answer sheet against this marking scheme. "
        "Return ONLY the raw JSON as specified — no markdown fences."
    )
    parts.append(types.Part.from_text(text=prompt))

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=2, min=4, max=30),
        retry=tenacity.retry_if_exception(lambda e: "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e))
    )
    def _call_api(model_name):
        return client.models.generate_content(
            model=model_name,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

    result_text = None
    last_err = None

    for model_name in MODELS:
        try:
            response = _call_api(model_name)
            result_text = response.text.strip()
            break
        except tenacity.RetryError as e:
            last_err = e.last_attempt.exception()
            print(f"Model {model_name} failed after retries: {last_err}")
        except Exception as e:
            last_err = e
            print(f"Model {model_name} failed: {e}")

    if not result_text:
        err_msg = str(last_err) if last_err else "All models failed."
        raise HTTPException(status_code=500, detail=err_msg)

    if result_text.startswith("```"):
        result_text = result_text.split("\n", 1)[-1]
        if result_text.endswith("```"):
            result_text = result_text[:-3].strip()

    try:
        data = json.loads(result_text)
    except json.JSONDecodeError as e:
        import re
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            raise HTTPException(status_code=500, detail="Failed to parse JSON response.")

    return JSONResponse(content=data)

@app.get("/")
async def root():
    return FileResponse("public/index.html")
