import os
import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import customtkinter as ctk
from dotenv import load_dotenv
import tenacity

from google import genai
from google.genai import types
import fitz  # PyMuPDF

load_dotenv()

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

ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"


class EquiGradeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EquiGrade AI – Professional Evaluation Assistant")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

        # ── State ────────────────────────────────────────────────────────────
        self.qp_path_var      = ctk.StringVar(value="No file selected")
        self.as_path_var      = ctk.StringVar(value="No file selected")
        self.as_paths         = []  # Store multiple paths
        self.evaluations      = []
        self.current_eval_idx = 0
        self.clean_view_mode  = ctk.BooleanVar(value=True)
        
        self.status_var       = ctk.StringVar(value="Ready.")

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        
        ctk.CTkLabel(header_frame, text="EquiGrade AI", font=ctk.CTkFont(size=24, weight="bold")).pack(side=tk.LEFT)
        ctk.CTkLabel(header_frame, text="Teacher's Evaluation Assistant", font=ctk.CTkFont(size=14, slant="italic"), text_color="gray").pack(side=tk.LEFT, padx=10, pady=(6,0))
        
        # Global Bottom Action Bar
        self.bottom_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        self.bottom_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 15))

        ctk.CTkLabel(self.bottom_bar, textvariable=self.status_var, font=ctk.CTkFont(slant="italic"), text_color="#d35400").pack(side=tk.LEFT)

        self.progress = ctk.CTkProgressBar(self.bottom_bar, mode="indeterminate", width=200)
        self.progress.pack(side=tk.LEFT, padx=20)
        self.progress.set(0)

        self.eval_btn = ctk.CTkButton(self.bottom_bar, text="▶ Evaluate Answer Sheet", font=ctk.CTkFont(weight="bold"), height=40, command=self._start_evaluation)
        self.eval_btn.pack(side=tk.RIGHT)

        # Tabs
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.tab_input = self.tabview.add("1. Input Module")
        self.tab_eval  = self.tabview.add("2. Evaluation Engine")

        self._build_input_tab()
        self._build_eval_tab()

    # ── Tab 1 ─────────────────────────────────────────────────────────────────
    def _build_input_tab(self):
        # Settings Bar
        settings_f = ctk.CTkFrame(self.tab_input, fg_color="transparent")
        settings_f.pack(fill=tk.X, pady=(0, 15))
        


        # Main Columns
        cols_f = ctk.CTkFrame(self.tab_input, fg_color="transparent")
        cols_f.pack(fill=tk.BOTH, expand=True)

        # Left Column - Uploads
        left = ctk.CTkFrame(cols_f)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        ctk.CTkLabel(left, text="Upload Documents", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor=tk.W, padx=15, pady=(15, 10))

        # QP
        ctk.CTkLabel(left, text="Question Paper (PDF / Image) — Optional:", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=15)
        qp_row = ctk.CTkFrame(left, fg_color="transparent")
        qp_row.pack(fill=tk.X, padx=15, pady=(5, 15))
        ctk.CTkButton(qp_row, text="Browse...", command=self._browse_qp, width=100).pack(side=tk.LEFT)
        ctk.CTkLabel(qp_row, textvariable=self.qp_path_var, text_color="gray", wraplength=250, justify=tk.LEFT).pack(side=tk.LEFT, padx=10)

        # AS
        ctk.CTkLabel(left, text="Student Answer Sheet (Image) — Mandatory:", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=15)
        as_row = ctk.CTkFrame(left, fg_color="transparent")
        as_row.pack(fill=tk.X, padx=15, pady=(5, 15))
        ctk.CTkButton(as_row, text="Browse...", command=self._browse_as, width=100).pack(side=tk.LEFT)
        ctk.CTkLabel(as_row, textvariable=self.as_path_var, text_color="gray", wraplength=250, justify=tk.LEFT).pack(side=tk.LEFT, padx=10)

        # Thumbnail
        self.thumb_label = ctk.CTkLabel(left, text="")
        self.thumb_label.pack(pady=10, padx=15, expand=True)

        # Right Column - Marking Scheme
        right = ctk.CTkFrame(cols_f)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        ctk.CTkLabel(right, text="Define Marking Scheme (Mandatory)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor=tk.W, padx=15, pady=(15, 5))
        example_text = "Example:\nQ1: What is DBMS? (5 marks)\n  - Definition → 2 marks\n  - Features → 2 marks\n  - Example → 1 mark"
        ctk.CTkLabel(right, text=example_text, text_color="gray", justify=tk.LEFT, font=ctk.CTkFont(size=12)).pack(anchor=tk.W, padx=15, pady=(0, 10))

        self.scheme_text = ctk.CTkTextbox(right, font=ctk.CTkFont(family="Consolas", size=13))
        self.scheme_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))



    # ── Tab 2 ─────────────────────────────────────────────────────────────────
    def _build_eval_tab(self):
        # Top bar
        top = ctk.CTkFrame(self.tab_eval, fg_color="transparent")
        top.pack(fill=tk.X, pady=(0, 10))

        ctk.CTkSwitch(top, text="Clean View Mode (Typed answer only)", variable=self.clean_view_mode, command=self._safe_update_view).pack(side=tk.LEFT)

        nav = ctk.CTkFrame(top, fg_color="transparent")
        nav.pack(side=tk.RIGHT)
        ctk.CTkButton(nav, text="◀ Prev", command=self._prev_q, width=80).pack(side=tk.LEFT, padx=5)
        self.q_indicator = ctk.CTkLabel(nav, text="Q — of —", font=ctk.CTkFont(weight="bold"))
        self.q_indicator.pack(side=tk.LEFT, padx=15)
        ctk.CTkButton(nav, text="Next ▶", command=self._next_q, width=80).pack(side=tk.LEFT, padx=5)

        # Content split
        pane = tk.PanedWindow(self.tab_eval, orient=tk.HORIZONTAL, bg=self.root._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]), bd=0, sashwidth=4)
        pane.pack(fill=tk.BOTH, expand=True)

        # Left: answer view
        left = ctk.CTkFrame(pane)
        pane.add(left, width=500)

        ctk.CTkLabel(left, text="Student Answer", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor=tk.W, padx=15, pady=(15, 5))

        self.answer_container = ctk.CTkFrame(left, fg_color="transparent")
        self.answer_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        self.answer_text = ctk.CTkTextbox(self.answer_container, font=ctk.CTkFont(size=14), state=tk.DISABLED, wrap=tk.WORD)
        self.answer_text.pack(fill=tk.BOTH, expand=True)

        self.answer_img_label = ctk.CTkLabel(self.answer_container, text="")

        # Right: feedback & grading
        right = ctk.CTkFrame(pane)
        pane.add(right, width=500)

        ctk.CTkLabel(right, text="Evaluation Details", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor=tk.W, padx=15, pady=(15, 5))

        # Marks breakdown (Using Scrollable Frame instead of Treeview for modern look)
        self.marks_frame = ctk.CTkScrollableFrame(right, height=120)
        self.marks_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        # Headers for marks breakdown
        header_f = ctk.CTkFrame(self.marks_frame, fg_color="transparent")
        header_f.pack(fill=tk.X, pady=2)
        ctk.CTkLabel(header_f, text="Key Point", font=ctk.CTkFont(weight="bold")).pack(side=tk.LEFT)
        ctk.CTkLabel(header_f, text="Marks", font=ctk.CTkFont(weight="bold")).pack(side=tk.RIGHT, padx=10)

        ctk.CTkLabel(right, text="Missing Points:", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=15)
        self.missing_text = ctk.CTkTextbox(right, height=60, font=ctk.CTkFont(size=13), state=tk.DISABLED, wrap=tk.WORD, fg_color=("#ffdddd", "#4a1c1c"))
        self.missing_text.pack(fill=tk.X, padx=15, pady=(2, 10))

        ctk.CTkLabel(right, text="AI Feedback:", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=15)
        self.feedback_text = ctk.CTkTextbox(right, height=80, font=ctk.CTkFont(size=13), state=tk.DISABLED, wrap=tk.WORD, fg_color=("#ddffdd", "#1c4a1c"))
        self.feedback_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(2, 10))

        # Teacher control panel
        ctrl = ctk.CTkFrame(right, border_width=1)
        ctrl.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=15)
        
        inner_ctrl = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner_ctrl.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        ctk.CTkLabel(inner_ctrl, text="AI Suggested Marks:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ai_marks_var = ctk.StringVar(value="— / —")
        ctk.CTkLabel(inner_ctrl, textvariable=self.ai_marks_var, font=ctk.CTkFont(size=14, weight="bold"), text_color="#2980b9").grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)

        ctk.CTkLabel(inner_ctrl, text="Final Marks (editable):", font=ctk.CTkFont(size=12, weight="bold")).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.final_marks_var = ctk.StringVar()
        self.marks_entry = ctk.CTkEntry(inner_ctrl, textvariable=self.final_marks_var, width=80, font=ctk.CTkFont(size=14))
        self.marks_entry.grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)

        btn_row = ctk.CTkFrame(inner_ctrl, fg_color="transparent")
        btn_row.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(15, 0))

        ctk.CTkButton(btn_row, text="✔ Approve & Finalize", fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(weight="bold"), command=self._finalize_marks).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ctk.CTkButton(btn_row, text="⬇ Export Results", fg_color="#455a64", hover_color="#263238", command=self._export_results).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

    # ── File browsing ─────────────────────────────────────────────────────────
    def _browse_qp(self):
        path = filedialog.askopenfilename(
            title="Select Question Paper",
            filetypes=[("PDF / Image", "*.pdf *.png *.jpg *.jpeg")])
        if path:
            self.qp_path_var.set(path)

    def _browse_as(self):
        paths = filedialog.askopenfilenames(
            title="Select Answer Sheet Pages",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg")])
        if paths:
            self.as_paths = list(paths)
            if len(paths) == 1:
                self.as_path_var.set(paths[0])
            else:
                self.as_path_var.set(f"{len(paths)} pages selected")
            self._show_thumb(paths[0])

    def _show_thumb(self, path):
        try:
            img = Image.open(path)
            img.thumbnail((400, 300))
            self._thumb_photo = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.thumb_label.configure(image=self._thumb_photo)
        except Exception:
            pass

    # ── Evaluation pipeline ───────────────────────────────────────────────────
    def _start_evaluation(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        scheme  = self.scheme_text.get("1.0", tk.END).strip()
        as_path = self.as_path_var.get()
        qp_path = self.qp_path_var.get()

        if not api_key:
            messagebox.showerror("Missing Configuration", "GEMINI_API_KEY environment variable not found. Please add it to your .env file.")
            return
        if not scheme:
            messagebox.showerror("Missing Input", "Please define a Marking Scheme.")
            return
        if not self.as_paths:
            messagebox.showerror("Missing Input", "Please upload at least one Student Answer Sheet image.")
            return

        self.eval_btn.configure(state=tk.DISABLED)
        self.status_var.set("⏳ Processing with Gemini AI — please wait...")
        self.progress.start()
        self.root.update_idletasks()

        threading.Thread(
            target=self._run_gemini_eval,
            args=(api_key, scheme, qp_path, as_path),
            daemon=True
        ).start()

    def _load_pdf_images(self, pdf_path):
        images = []
        try:
            doc = fitz.open(pdf_path)
            for i in range(min(3, len(doc))):
                page = doc.load_page(i)
                pix  = page.get_pixmap()
                mode = "RGBA" if pix.alpha else "RGB"
                images.append(Image.frombytes(mode, [pix.width, pix.height], pix.samples))
        except Exception as exc:
            print(f"PDF load error: {exc}")
        return images

    def _run_gemini_eval(self, api_key, scheme, qp_path, as_path):
        try:
            client = genai.Client(
                api_key=api_key,
            )

            parts = []

            # Optional question paper
            if qp_path != "No file selected" and os.path.exists(qp_path):
                parts.append(types.Part.from_text(text="Context — Question Paper:"))
                if qp_path.lower().endswith(".pdf"):
                    for img in self._load_pdf_images(qp_path):
                        import io
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        parts.append(types.Part.from_bytes(
                            data=buf.getvalue(), mime_type="image/png"))
                else:
                    with open(qp_path, "rb") as f:
                        raw = f.read()
                    mime = "image/png" if qp_path.lower().endswith(".png") else "image/jpeg"
                    parts.append(types.Part.from_bytes(data=raw, mime_type=mime))

            # Answer sheet
            parts.append(types.Part.from_text(text="Student Answer Sheet to Evaluate:"))
            for path in self.as_paths:
                with open(path, "rb") as f:
                    raw = f.read()
                mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
                parts.append(types.Part.from_bytes(data=raw, mime_type=mime))

            # Marking scheme prompt
            prompt = (
                f"Here is the strict marking scheme:\n\n{scheme}\n\n"
                "Please evaluate the student answer sheet against this marking scheme. "
                "Return ONLY the raw JSON as specified — no markdown fences."
            )
            parts.append(types.Part.from_text(text=prompt))

            MODELS = [
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-1.5-pro",
            ]

            def update_status(msg):
                self.root.after(0, lambda: self.status_var.set(msg))

            @tenacity.retry(
                stop=tenacity.stop_after_attempt(5),
                wait=tenacity.wait_exponential(multiplier=2, min=4, max=30),
                retry=tenacity.retry_if_exception(lambda e: "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)),
                before_sleep=lambda retry_state: update_status(f"⏳ Rate limit hit. Waiting {retry_state.next_action.sleep:.0f}s to retry...")
            )
            def _call_api_for_model(model_name):
                update_status(f"⏳ Evaluating with {model_name}...")
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
                    response = _call_api_for_model(model_name)
                    result_text = response.text.strip()
                    break  # Success!
                except tenacity.RetryError as e:
                    last_err = e.last_attempt.exception()
                    print(f"Model {model_name} failed after retries: {last_err}")
                except Exception as e:
                    last_err = e
                    print(f"Model {model_name} failed: {e}")
                    
            if not result_text:
                if last_err:
                    raise last_err
                else:
                    raise ValueError("All models failed without returning an error.")

            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[-1]
                if result_text.endswith("```"):
                    result_text = result_text[:-3].strip()

            try:
                data = json.loads(result_text)
            except json.JSONDecodeError as e:
                # Fallback: attempt to find JSON within the text if parsing fails
                import re
                match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    raise ValueError(f"Failed to parse JSON response: {e}\nResponse:\n{result_text}")
            evaluations = data.get("evaluations", [])

            self.root.after(0, lambda: self._on_eval_success(evaluations))

        except Exception as exc:
            err_msg = str(exc)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                friendly = (
                    f"⚠️ Quota Exhausted (429 RESOURCE_EXHAUSTED)\n\n"
                    f"All models have exhausted their free-tier request limits and retries.\n\n"
                    f"What to do:\n"
                    f"  1. Wait a few minutes, then try again.\n"
                    f"  2. Check your quota at: https://ai.dev/rate-limit\n"
                    f"  3. Upgrade your Google AI Studio plan for higher limits."
                )
                err_msg = friendly
            self.root.after(0, lambda: self._on_eval_error(err_msg))

    # ── Callbacks (main thread) ───────────────────────────────────────────────
    def _on_eval_success(self, evaluations):
        self.eval_btn.configure(state=tk.NORMAL)
        self.progress.stop()
        if not evaluations:
            self.status_var.set("No evaluations returned.")
            messagebox.showinfo("Result", "Gemini returned no evaluation data.\n\n"
                                          "Check that the marking scheme matches the answer sheet.")
            return

        for ev in evaluations:
            ev.setdefault("teacher_approved_marks", ev.get("suggested_marks", 0))
            ev["is_finalized"] = False

        self.evaluations      = evaluations
        self.current_eval_idx = 0
        self.status_var.set(f"✅ Evaluation complete — {len(evaluations)} question(s) found.")
        self.tabview.set("2. Evaluation Engine")
        self._update_eval_view()

    def _on_eval_error(self, error_msg):
        self.eval_btn.configure(state=tk.NORMAL)
        self.progress.stop()
        self.status_var.set("❌ Evaluation failed.")
        messagebox.showerror("API Error",
                             f"An error occurred during evaluation:\n\n{error_msg}\n\n"
                             "Tips:\n• Verify your API key\n"
                             "• Check internet connectivity\n"
                             "• Ensure the answer sheet image is clear and readable")

    # ── Eval view helpers ─────────────────────────────────────────────────────
    def _safe_update_view(self):
        if self.evaluations:
            self._update_eval_view()

    def _update_eval_view(self):
        if not self.evaluations:
            return

        ev      = self.evaluations[self.current_eval_idx]
        total_q = len(self.evaluations)

        self.q_indicator.configure(
            text=f"Question {ev.get('question_number', '?')}  ({self.current_eval_idx + 1} of {total_q})",
            text_color="#2e7d32" if ev.get("is_finalized") else "SystemButtonText"
        )

        # Answer panel
        if self.clean_view_mode.get():
            self.answer_img_label.pack_forget()
            self.answer_text.pack(fill=tk.BOTH, expand=True)
            self.answer_text.configure(state=tk.NORMAL)
            self.answer_text.delete("1.0", tk.END)
            self.answer_text.insert(tk.END, ev.get("extracted_answer", "(no answer extracted)"))
            self.answer_text.configure(state=tk.DISABLED)
        else:
            self.answer_text.pack_forget()
            self.answer_img_label.pack(fill=tk.BOTH, expand=True)
            if self.as_paths and os.path.exists(self.as_paths[0]):
                img = Image.open(self.as_paths[0])
                img.thumbnail((600, 800))
                self._sheet_photo = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.answer_img_label.configure(image=self._sheet_photo)

        # Marks breakdown list
        for child in self.marks_frame.winfo_children():
            if child != self.marks_frame.winfo_children()[0]: # Keep header
                child.destroy()
                
        breakdown = ev.get("marks_breakdown", {})
        for point, marks in breakdown.items():
            row_f = ctk.CTkFrame(self.marks_frame, fg_color="transparent")
            row_f.pack(fill=tk.X, pady=2)
            ctk.CTkLabel(row_f, text=point, wraplength=350, justify=tk.LEFT).pack(side=tk.LEFT)
            ctk.CTkLabel(row_f, text=str(marks)).pack(side=tk.RIGHT, padx=10)

        # Missing points
        self._set_text_widget(self.missing_text, "\n".join(f"• {p}" for p in ev.get("missing_points", [])))

        # Feedback
        self._set_text_widget(self.feedback_text, ev.get("feedback", ""))

        # Teacher control
        self.ai_marks_var.set(f"{ev.get('suggested_marks', 0)} / {ev.get('total_marks', 0)}")
        self.final_marks_var.set(str(ev.get("teacher_approved_marks", 0)))

    def _set_text_widget(self, widget, content):
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, content)
        widget.configure(state=tk.DISABLED)

    # ── Navigation ────────────────────────────────────────────────────────────
    def _prev_q(self):
        if self.evaluations and self.current_eval_idx > 0:
            self._save_marks()
            self.current_eval_idx -= 1
            self._update_eval_view()

    def _next_q(self):
        if self.evaluations and self.current_eval_idx < len(self.evaluations) - 1:
            self._save_marks()
            self.current_eval_idx += 1
            self._update_eval_view()

    def _save_marks(self):
        if not self.evaluations:
            return
        try:
            val = float(self.final_marks_var.get())
            self.evaluations[self.current_eval_idx]["teacher_approved_marks"] = val
        except ValueError:
            pass

    # ── Finalize ──────────────────────────────────────────────────────────────
    def _finalize_marks(self):
        if not self.evaluations:
            messagebox.showwarning("Nothing to Finalize", "Please run an evaluation first.")
            return
        self._save_marks()
        ev = self.evaluations[self.current_eval_idx]
        ev["is_finalized"] = True
        self.q_indicator.configure(text_color="#2e7d32")
        messagebox.showinfo("Finalized", f"Marks for {ev.get('question_number', 'this question')} finalized at {ev['teacher_approved_marks']} / {ev.get('total_marks', '?')}.")

    # ── Export ────────────────────────────────────────────────────────────────
    def _export_results(self):
        if not self.evaluations:
            messagebox.showwarning("Nothing to Export", "Please run an evaluation first.")
            return

        self._save_marks()

        save_path = filedialog.asksaveasfilename(
            title="Save Results",
            defaultextension=".txt",
            filetypes=[("Text File", "*.txt"), ("JSON File", "*.json")])
        if not save_path:
            return

        if save_path.lower().endswith(".json"):
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({"evaluations": self.evaluations}, f, indent=2)
        else:
            lines = ["EquiGrade AI – Evaluation Report", "=" * 50, ""]
            grand_total = 0
            grand_max   = 0
            for ev in self.evaluations:
                lines.append(f"Question: {ev.get('question_number', '?')}")
                lines.append(f"  Extracted Answer : {ev.get('extracted_answer', '')}")
                lines.append(f"  AI Suggested     : {ev.get('suggested_marks', 0)} / {ev.get('total_marks', 0)}")
                lines.append(f"  Teacher Approved : {ev.get('teacher_approved_marks', 0)}")
                lines.append(f"  Finalized        : {'Yes' if ev.get('is_finalized') else 'No'}")
                lines.append("  Marks Breakdown:")
                for pt, mk in ev.get("marks_breakdown", {}).items():
                    lines.append(f"    • {pt}: {mk}")
                if ev.get("missing_points"):
                    lines.append("  Missing Points:")
                    for mp in ev["missing_points"]:
                        lines.append(f"    ✗ {mp}")
                lines.append(f"  Feedback : {ev.get('feedback', '')}")
                lines.append("")
                grand_total += float(ev.get("teacher_approved_marks", 0))
                grand_max   += float(ev.get("total_marks", 0))

            lines.append("=" * 50)
            lines.append(f"GRAND TOTAL: {grand_total} / {grand_max}")
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

        messagebox.showinfo("Export Complete", f"Results saved to:\n{save_path}")


if __name__ == "__main__":
    root = ctk.CTk()
    app  = EquiGradeApp(root)
    root.mainloop()
