# EquiGrade AI - Teacher's Evaluation Assistant

EquiGrade AI is a desktop-based application designed to help teachers evaluate handwritten answer sheets efficiently and consistently. It uses the power of the Google Gemini Multimodal API to read handwritten text, compare it against a teacher-defined marking scheme, and suggest marks with detailed feedback. The teacher always retains full control to review and finalize the marks.

## Features
- **Upload Documents**: Support for Question Papers (PDF/Images) and Student Answer Sheets (Images).
- **Teacher-Defined Marking Scheme**: Flexible manual input for defining rubrics.
- **AI Processing (Gemini)**: Reads handwritten answers, extracts clean typed text, and evaluates based on the rubric.
- **Evaluation Engine**: Breaks down marks per point, lists missing concepts, and provides AI feedback.
- **Teacher Control**: Full UI to review AI suggestions, manually edit marks, and approve final grades.
- **Clean View Mode**: Toggle to view only the extracted typed answer to focus purely on content.

## Prerequisites
- Python 3.8+
- Google Gemini API Key (Get it from [Google AI Studio](https://aistudio.google.com/))

## Installation & Setup

1. **Clone or Download** this directory.
2. **Open a terminal/command prompt** in this directory.
3. **(Optional but recommended)** Create a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

1. Ensure your virtual environment is activated.
2. Run the application:
   ```bash
   python equigrade.py
   ```
3. When the app opens:
   - Enter your **Gemini API Key**.
   - Optionally upload a **Question Paper** (PDF or Image).
   - Upload the **Student Answer Sheet** (Image format like JPG/PNG).
   - Enter your **Marking Scheme** in the text box. Example format:
     ```
     Q1: What is DBMS? (5 marks)
     - Definition -> 2 marks
     - Features -> 2 marks
     - Example -> 1 mark
     ```
   - Click **Evaluate Answer Sheet**.
4. Once processing completes, switch to the **Evaluation Engine** tab to review, edit, and finalize marks.

## Tech Stack
- **Python**
- **Tkinter** (Native Desktop UI)
- **Google Generative AI** (Gemini 1.5 Pro)
- **Pillow / PyMuPDF** (Image & PDF processing)
