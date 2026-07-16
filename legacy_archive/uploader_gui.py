#!/usr/bin/env python3
"""
NotBook — Admin Uploader  |  Grey × Orange Matte Edition
Drop PDFs → Pinecone with real-time progress and library management.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import threading
import os
import re
import time
import queue
import math
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
import yaml

load_dotenv(Path(__file__).parent / ".env")

# ── Load config ────────────────────────────────────────────────────────────────
try:
    with open(Path(__file__).parent / "config.yaml", encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f)
except Exception:
    CONFIG = {
        "pinecone": {
            "index_name": "library-index",
            "embedding_model": "multilingual-e5-large",
        }
    }

# ── Appearance ─────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Palette ────────────────────────────────────────────────────────────────────
BG0    = "#0C0C0C"
BG1    = "#141414"
BG2    = "#1C1C1C"
BG3    = "#242424"
BG4    = "#2C2C2C"
BGHVR  = "#343434"

OG     = "#E05E1A"   # primary orange
OGLT   = "#FF7835"   # lighter orange
OGDIM  = "#6B2E0C"   # dark orange tint
OGMID  = "#A84010"   # mid orange

BORDER = "#282828"
BORDHI = "#3C3C3C"

TH  = "#F0F0F0"      # text high
TM  = "#9A9A9A"      # text mid
TL  = "#484848"      # text low

GN  = "#4A9E4A"      # success green
RD  = "#C84040"      # error red
YL  = "#C88020"      # warning yellow

FT  = ("Segoe UI", 20, "bold")
FH  = ("Segoe UI", 13, "bold")
FS  = ("Segoe UI", 11, "bold")
FB  = ("Segoe UI", 10)
FSM = ("Segoe UI",  9)
FMO = ("Consolas",  9)

# ──────────────────────────────────────────────────────────────────────────────
#  Pinecone helpers (inline — no import from admin_ingest to keep GUI portable)
# ──────────────────────────────────────────────────────────────────────────────

def _get_pinecone():
    """Return (pc, index) or raise."""
    from pinecone import Pinecone
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    key = os.getenv("PINECONE_API_KEY")
    if not key:
        raise EnvironmentError(
            "PINECONE_API_KEY not set. Add it to .env or the environment (never hardcode)."
        )
    pc = Pinecone(api_key=key)
    idx = pc.Index(CONFIG["pinecone"]["index_name"])
    return pc, idx


def _fetch_stats(pc, idx):
    stats = idx.describe_index_stats()
    total = stats.get("total_vector_count", 0)
    ns_raw = stats.get("namespaces", {})
    namespaces = []
    for ns, info in ns_raw.items():
        if ns.startswith("_"):
            continue
        count = info.get("vector_count", 0) if isinstance(info, dict) else 0
        if "|" in ns:
            parts = ns.split("|", 1)
            scope = parts[0]
            name  = parts[1]
        else:
            scope = "global"
            name  = ns
        namespaces.append({"ns": ns, "scope": scope, "name": name, "vectors": count})
    return total, namespaces


# ──────────────────────────────────────────────────────────────────────────────
#  Upload worker (runs in a thread, reports via queue)
# ──────────────────────────────────────────────────────────────────────────────

def upload_worker(pdf_path: str, namespace: str, user_id: str, msg_q: queue.Queue):
    """Full ingestion pipeline with progress events posted to msg_q."""
    import pypdfium2 as pdfium

    def emit(kind, **kw):
        msg_q.put({"kind": kind, **kw})

    def log(text, level="info"):
        emit("log", text=text, level=level)

    try:
        # ── step 0: connect ────────────────────────────────────────────────
        log("Connecting to Pinecone…")
        emit("phase", label="Connecting", pct=0)
        pc, idx = _get_pinecone()
        log("✓ Pinecone connected")

        target_ns = (f"{user_id}|{namespace}" if user_id else f"global|{namespace}").strip()
        log(f"Namespace → {target_ns}")

        # ── step 1: clear old namespace ────────────────────────────────────
        emit("phase", label="Clearing old data", pct=3)
        try:
            idx.delete(delete_all=True, namespace=target_ns)
            log(f"✓ Old namespace cleared")
        except Exception as e:
            log(f"  (no prior data or clear skipped: {e})", "warn")

        # ── step 2: extract pages ──────────────────────────────────────────
        emit("phase", label="Reading PDF", pct=6)
        log(f"Opening: {Path(pdf_path).name}")
        doc = pdfium.PdfDocument(pdf_path)
        total_pages_raw = len(doc)
        log(f"  {total_pages_raw} raw pages found")

        pages = []
        skipped = 0
        for pn, page in enumerate(doc, start=1):
            emit("progress_page", current=pn, total=total_pages_raw)
            tp   = page.get_textpage()
            text = tp.get_text_range()
            if not text:
                skipped += 1; continue
            text = re.sub(r'\r\n|\r', '\n', text)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            # garbage filter
            lines = [l for l in text.splitlines() if l.strip()]
            if len(text) < 100 or not lines:
                skipped += 1; continue
            short = sum(1 for l in lines if len(l.strip()) < 35)
            dotted= sum(1 for l in lines if re.search(r'[.\s]{4,}\d+\s*$', l))
            if len(lines) > 5 and short / len(lines) > 0.65:
                skipped += 1; continue
            if len(lines) > 5 and dotted / len(lines) > 0.40:
                skipped += 1; continue
            pages.append({"page": pn, "text": text})

        log(f"✓ {len(pages)} content pages extracted, {skipped} skipped")

        # ── step 3: chunk ──────────────────────────────────────────────────
        emit("phase", label="Chunking text", pct=20)
        chunks = []
        max_chars, overlap = 600, 80
        for pd_ in pages:
            pnum = pd_["page"]
            paras = [p.strip() for p in pd_["text"].split("\n\n") if p.strip()]
            pending = ""
            for para in paras:
                if len(pending) + len(para) + 2 <= max_chars:
                    pending = (pending + "\n\n" + para).strip()
                else:
                    if pending:
                        chunks.append({"text": pending, "page": pnum})
                        pending = pending[-overlap:].strip()
                    if len(para) > max_chars:
                        sents = re.split(r'(?<=[.!?])\s+', para)
                        for s in sents:
                            if len(pending) + len(s) + 1 <= max_chars:
                                pending = (pending + " " + s).strip()
                            else:
                                if pending:
                                    chunks.append({"text": pending, "page": pnum})
                                    pending = pending[-overlap:].strip()
                                while len(s) > max_chars:
                                    chunks.append({"text": s[:max_chars], "page": pnum})
                                    s = s[max_chars - overlap:]
                                pending = s
                    else:
                        pending = para
            if pending:
                chunks.append({"text": pending, "page": pnum})
        chunks = [c for c in chunks if len(c["text"].strip()) >= 80]
        log(f"✓ {len(chunks)} chunks created")

        # ── step 4: embed + upsert ─────────────────────────────────────────
        batch_size   = 96
        total_batches= math.ceil(len(chunks) / batch_size)
        emit("phase", label="Embedding & uploading", pct=25)
        log(f"Uploading {len(chunks)} chunks in {total_batches} batch(es)…")

        for bi in range(total_batches):
            batch  = chunks[bi * batch_size : (bi + 1) * batch_size]
            texts  = [c["text"] for c in batch]
            pct    = 25 + int(70 * (bi / total_batches))
            emit("phase", label=f"Batch {bi+1}/{total_batches}", pct=pct)
            emit("progress_chunk", current=bi+1, total=total_batches)

            # embed with retry
            for attempt in range(5):
                try:
                    embeddings = pc.inference.embed(
                        model=CONFIG["pinecone"]["embedding_model"],
                        inputs=texts,
                        parameters={"input_type": "passage", "truncate": "END"},
                    )
                    break
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        wait = 60 * (attempt + 1)
                        log(f"  Rate limited — sleeping {wait}s…", "warn")
                        emit("rate_limit", seconds=wait)
                        time.sleep(wait)
                    else:
                        raise

            vectors = [
                {
                    "id": f"chunk_{bi * batch_size + j}",
                    "values": emb.values,
                    "metadata": {"text": batch[j]["text"], "page": batch[j]["page"],
                                 "source": Path(pdf_path).name},
                }
                for j, emb in enumerate(embeddings)
            ]
            idx.upsert(vectors=vectors, namespace=target_ns)
            log(f"  ✓ Batch {bi+1}/{total_batches} uploaded ({len(vectors)} vectors)")

        # ── done ───────────────────────────────────────────────────────────
        emit("phase", label="Complete!", pct=100)
        log(f"\n✅  Done! '{Path(pdf_path).name}' ingested as '{namespace}'")
        log(f"    Namespace: {target_ns}  |  {len(chunks)} vectors")
        emit("done", namespace=target_ns, chunks=len(chunks))

    except Exception as exc:
        log(f"❌  Error: {exc}", "error")
        emit("error", message=str(exc))


# ══════════════════════════════════════════════════════════════════════════════
#  Custom Widgets
# ══════════════════════════════════════════════════════════════════════════════

class DropZone(tk.Canvas):
    """Click-to-browse drop zone (+ optional DnD via tkinterdnd2)."""

    def __init__(self, master, on_file, **kw):
        super().__init__(master,
                         bg=BG3, highlightthickness=0,
                         cursor="hand2", **kw)
        self.on_file   = on_file
        self._hovering = False
        self._file     = None
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>",  self._browse)
        self.bind("<Enter>",     lambda e: self._set_hover(True))
        self.bind("<Leave>",     lambda e: self._set_hover(False))

        # enable tkinterdnd2 if available
        try:
            self.drop_target_register("DND_Files")
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DragEnter>>", lambda e: self._set_hover(True))
            self.dnd_bind("<<DragLeave>>", lambda e: self._set_hover(False))
            self._dnd_ok = True
        except Exception:
            self._dnd_ok = False

    def _set_hover(self, v):
        self._hovering = v
        self._redraw()

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        if path.lower().endswith(".pdf"):
            self._set_file(path)
        return event.action

    def _browse(self, _=None):
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if path:
            self._set_file(path)

    def _set_file(self, path):
        self._file = path
        self._redraw()
        self.on_file(path)

    def clear(self):
        self._file = None
        self._redraw()

    def _redraw(self, _=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return

        border_col = OGMID if self._hovering else BORDER
        dash_col   = OG    if self._hovering else TL
        # dashed border
        for i in range(0, w, 14):
            self.create_line(i, 0, min(i+8, w), 0,            fill=dash_col, width=2)
            self.create_line(i, h, min(i+8, w), h,            fill=dash_col, width=2)
        for i in range(0, h, 14):
            self.create_line(0, i, 0, min(i+8, h),            fill=dash_col, width=2)
            self.create_line(w, i, w, min(i+8, h),            fill=dash_col, width=2)

        if self._file:
            name = Path(self._file).name
            size = Path(self._file).stat().st_size / (1024*1024)
            # file icon area
            self.create_rectangle(w//2-22, h//2-30, w//2+22, h//2+10,
                                   fill=BG4, outline=OGMID, width=1)
            self.create_text(w//2, h//2-10, text="PDF", fill=OG,
                             font=("Segoe UI", 9, "bold"))
            self.create_text(w//2, h//2+28,
                             text=name[:40] + ("…" if len(name) > 40 else ""),
                             fill=TH, font=("Segoe UI", 10, "bold"))
            self.create_text(w//2, h//2+48,
                             text=f"{size:.1f} MB  •  Click to change",
                             fill=TM, font=FSM)
        else:
            # upload icon (arrow)
            cx, cy = w//2, h//2 - 16
            self.create_polygon(cx, cy-20, cx-14, cy+4, cx-6, cy+4,
                                 cx-6, cy+18, cx+6, cy+18, cx+6, cy+4, cx+14, cy+4,
                                 fill=OG if self._hovering else TL, outline="")
            hint = "Drop PDF here" if self._dnd_ok else "Click to browse PDF"
            self.create_text(w//2, h//2+20, text=hint, fill=TM,
                             font=("Segoe UI", 11, "bold"))
            self.create_text(w//2, h//2+40, text="Supports any size",
                             fill=TL, font=FSM)


class LogConsole(ctk.CTkFrame):
    """Scrollable monospaced log panel."""

    COLORS = {"info": TH, "warn": YL, "error": RD}

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=BG2, corner_radius=6, **kw)
        self._text = tk.Text(self, bg=BG2, fg=TH,
                             font=FMO, state="disabled", wrap="word",
                             borderwidth=0, highlightthickness=0,
                             selectbackground=BG4)
        self._sb   = ctk.CTkScrollbar(self, command=self._text.yview,
                                      fg_color=BG2, button_color=BG4,
                                      button_hover_color=BGHVR)
        self._text.configure(yscrollcommand=self._sb.set)
        self._text.tag_configure("info",  foreground=TH)
        self._text.tag_configure("warn",  foreground=YL)
        self._text.tag_configure("error", foreground=RD)
        self._text.tag_configure("ts",    foreground=TL)
        self._sb.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True, padx=4, pady=4)

    def write(self, text: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._text.configure(state="normal")
        self._text.insert("end", f"[{ts}] ", "ts")
        self._text.insert("end", text + "\n", level)
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")


class StatCard(ctk.CTkFrame):
    """Small stat display card."""

    def __init__(self, master, label, value="—", icon="", color=TH, **kw):
        super().__init__(master, fg_color=BG3, corner_radius=8, **kw)
        self._color = color
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 2))
        ctk.CTkLabel(top, text=icon + " " + label if icon else label,
                     font=FSM, text_color=TM).pack(side="left")
        self._val = ctk.CTkLabel(self, text=str(value),
                                  font=FH, text_color=color)
        self._val.pack(anchor="w", padx=14, pady=(0, 14))

    def set(self, value, color=None):
        self._val.configure(text=str(value),
                            text_color=color or self._color)


# ══════════════════════════════════════════════════════════════════════════════
#  Upload Page
# ══════════════════════════════════════════════════════════════════════════════

class UploadPage(ctk.CTkFrame):
    def __init__(self, master, status_cb, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._status_cb = status_cb
        self._q         = queue.Queue()
        self._uploading = False
        self._pdf_path  = None

        self._build()
        self._poll()

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(hdr, text="Upload PDF", font=FH, text_color=TH).pack(side="left")
        ctk.CTkLabel(hdr, text="  →  Pinecone Ingestion", font=FB, text_color=TM).pack(side="left")

        # ── Drop Zone (full width) ─────────────────────────────────────────────
        dz_card = ctk.CTkFrame(self, fg_color=BG3, corner_radius=10)
        dz_card.pack(fill="x", pady=(0, 10))
        self._dz = DropZone(dz_card, on_file=self._on_file, height=170)
        self._dz.pack(fill="both", expand=True, padx=10, pady=10)

        # ── Form row: file info | book name | user id | buttons ───────────────
        form_row = ctk.CTkFrame(self, fg_color=BG3, corner_radius=10)
        form_row.pack(fill="x", pady=(0, 10))

        # file info (left)
        fi_wrap = ctk.CTkFrame(form_row, fg_color="transparent")
        fi_wrap.pack(side="left", fill="y", padx=(14, 6), pady=14)
        ctk.CTkLabel(fi_wrap, text="Selected File", font=FSM, text_color=TM).pack(anchor="w")
        self._finfo = ctk.CTkLabel(fi_wrap, text="None",
                                    font=FB, text_color=TL, wraplength=200, justify="left")
        self._finfo.pack(anchor="w", pady=(2, 0))

        # thin divider
        ctk.CTkFrame(form_row, fg_color=BORDER, width=1).pack(side="left", fill="y", padx=8, pady=14)

        # Book name
        bn_wrap = ctk.CTkFrame(form_row, fg_color="transparent")
        bn_wrap.pack(side="left", fill="y", expand=True, pady=14, padx=4)
        ctk.CTkLabel(bn_wrap, text="Book Name", font=FSM, text_color=TM).pack(anchor="w")
        self._book_var = tk.StringVar()
        ctk.CTkEntry(bn_wrap, textvariable=self._book_var,
                     placeholder_text="e.g. Anatomy 2024",
                     fg_color=BG4, border_color=BORDER,
                     text_color=TH, height=36, width=200).pack(anchor="w", pady=(4, 0))

        # thin divider
        ctk.CTkFrame(form_row, fg_color=BORDER, width=1).pack(side="left", fill="y", padx=8, pady=14)

        # User ID
        uid_wrap = ctk.CTkFrame(form_row, fg_color="transparent")
        uid_wrap.pack(side="left", fill="y", expand=True, pady=14, padx=4)
        ctk.CTkLabel(uid_wrap, text="User ID  (blank = global)", font=FSM, text_color=TM).pack(anchor="w")
        self._uid_var = tk.StringVar()
        ctk.CTkEntry(uid_wrap, textvariable=self._uid_var,
                     placeholder_text="Telegram user_id",
                     fg_color=BG4, border_color=BORDER,
                     text_color=TH, height=36, width=180).pack(anchor="w", pady=(4, 0))

        # thin divider
        ctk.CTkFrame(form_row, fg_color=BORDER, width=1).pack(side="left", fill="y", padx=8, pady=14)

        # Buttons (right side)
        btn_wrap = ctk.CTkFrame(form_row, fg_color="transparent")
        btn_wrap.pack(side="left", fill="y", pady=14, padx=(4, 14))
        self._btn = ctk.CTkButton(btn_wrap,
                                   text="⬆  Upload to Pinecone",
                                   fg_color=OG, hover_color=OGLT,
                                   text_color=BG0, font=FS,
                                   height=44, width=210, corner_radius=8,
                                   command=self._start_upload)
        self._btn.pack(pady=(4, 6))
        ctk.CTkButton(btn_wrap, text="✕  Clear",
                      fg_color=BG4, hover_color=BGHVR,
                      text_color=TM, font=FSM,
                      height=26, width=210, corner_radius=6,
                      command=self._clear).pack()

        # ── Progress bar card ─────────────────────────────────────────────────
        prog_card = ctk.CTkFrame(self, fg_color=BG3, corner_radius=10)
        prog_card.pack(fill="x", pady=(0, 10))

        prog_top = ctk.CTkFrame(prog_card, fg_color="transparent")
        prog_top.pack(fill="x", padx=14, pady=(10, 4))
        self._phase_lbl = ctk.CTkLabel(prog_top, text="Ready", font=FSM, text_color=TM)
        self._phase_lbl.pack(side="left")
        self._pct_lbl = ctk.CTkLabel(prog_top, text="", font=FSM, text_color=OG)
        self._pct_lbl.pack(side="right")

        self._pbar = ctk.CTkProgressBar(prog_card, fg_color=BG4,
                                         progress_color=OG, height=10, corner_radius=4)
        self._pbar.pack(fill="x", padx=14, pady=(0, 6))
        self._pbar.set(0)

        sub_row = ctk.CTkFrame(prog_card, fg_color="transparent")
        sub_row.pack(fill="x", padx=14, pady=(0, 10))
        self._chunk_lbl = ctk.CTkLabel(sub_row, text="", font=FSM, text_color=TL)
        self._chunk_lbl.pack(side="left")
        self._page_lbl = ctk.CTkLabel(sub_row, text="", font=FSM, text_color=TL)
        self._page_lbl.pack(side="right")

        # ── Log console ───────────────────────────────────────────────────────
        log_hdr = ctk.CTkFrame(self, fg_color="transparent")
        log_hdr.pack(fill="x")
        ctk.CTkLabel(log_hdr, text="OUTPUT LOG", font=FSM, text_color=TL).pack(side="left")
        ctk.CTkButton(log_hdr, text="Clear log", fg_color="transparent",
                      hover_color=BG3, text_color=TL, font=FSM,
                      height=20, width=60, corner_radius=4,
                      command=lambda: self._log.clear()).pack(side="right")
        self._log = LogConsole(self)
        self._log.pack(fill="both", expand=True, pady=(4, 0))

    # ── file selection ────────────────────────────────────────────────────────
    def _on_file(self, path):
        self._pdf_path = path
        name = Path(path).name
        size = Path(path).stat().st_size / (1024 * 1024)
        self._finfo.configure(text=f"📄 {name}\n{size:.1f} MB", text_color=TH)
        # auto-fill book name from filename (strip extension)
        if not self._book_var.get():
            auto = Path(path).stem.replace("_", " ").replace("-", " ")
            self._book_var.set(auto[:40])

    # ── upload ────────────────────────────────────────────────────────────────
    def _start_upload(self):
        if self._uploading:
            return
        if not self._pdf_path:
            self._log.write("Select a PDF file first.", "warn"); return
        book = self._book_var.get().strip()
        if not book:
            self._log.write("Enter a book name.", "warn"); return

        self._uploading = True
        self._btn.configure(state="disabled", text="Uploading…", fg_color=OGDIM)
        self._pbar.set(0)
        self._log.clear()
        self._status_cb("Uploading…", YL)

        uid = self._uid_var.get().strip()
        t = threading.Thread(target=upload_worker,
                             args=(self._pdf_path, book, uid, self._q),
                             daemon=True)
        t.start()

    def _clear(self):
        if self._uploading: return
        self._pdf_path = None
        self._book_var.set("")
        self._uid_var.set("")
        self._finfo.configure(text="No file selected", text_color=TL)
        self._pbar.set(0)
        self._phase_lbl.configure(text="Ready")
        self._pct_lbl.configure(text="")
        self._chunk_lbl.configure(text="")
        self._page_lbl.configure(text="")
        self._log.clear()
        self._dz.clear()

    # ── queue poll ────────────────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg["kind"]

                if kind == "log":
                    self._log.write(msg["text"], msg.get("level", "info"))

                elif kind == "phase":
                    pct = msg["pct"] / 100
                    self._phase_lbl.configure(text=msg["label"])
                    self._pct_lbl.configure(text=f"{msg['pct']}%")
                    self._pbar.set(pct)

                elif kind == "progress_page":
                    self._page_lbl.configure(
                        text=f"Page {msg['current']}/{msg['total']}")

                elif kind == "progress_chunk":
                    self._chunk_lbl.configure(
                        text=f"Batch {msg['current']}/{msg['total']}")

                elif kind == "rate_limit":
                    self._phase_lbl.configure(
                        text=f"Rate limited — waiting {msg['seconds']}s…")

                elif kind == "done":
                    self._uploading = False
                    self._btn.configure(state="normal",
                                        text="⬆  Upload to Pinecone",
                                        fg_color=GN)
                    self._status_cb("Upload complete", GN)
                    self.after(3000, lambda: self._btn.configure(fg_color=OG))

                elif kind == "error":
                    self._uploading = False
                    self._btn.configure(state="normal",
                                        text="⬆  Upload to Pinecone",
                                        fg_color=RD)
                    self._status_cb(f"Error: {msg['message'][:60]}", RD)
                    self.after(3000, lambda: self._btn.configure(fg_color=OG))

        except queue.Empty:
            pass
        self.after(80, self._poll)


# ══════════════════════════════════════════════════════════════════════════════
#  Library Page
# ══════════════════════════════════════════════════════════════════════════════

class LibraryPage(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._build()
        self.refresh()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(hdr, text="Library", font=FH, text_color=TH).pack(side="left")
        ctk.CTkButton(hdr, text="⟳ Refresh", fg_color=BG4,
                      hover_color=BGHVR, text_color=TM, font=FSM,
                      height=30, width=90, corner_radius=6,
                      command=self.refresh).pack(side="right")

        self._status = ctk.CTkLabel(self, text="", font=FSM, text_color=TM)
        self._status.pack(anchor="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               label_text="")
        self._scroll.pack(fill="both", expand=True, pady=(10, 0))

    def refresh(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._status.configure(text="Loading…", text_color=YL)
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            pc, idx = _get_pinecone()
            total, books = _fetch_stats(pc, idx)
            self.after(0, lambda: self._render(total, books))
        except Exception as e:
            self.after(0, lambda: self._status.configure(
                text=f"Error: {e}", text_color=RD))

    def _render(self, total, books):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._status.configure(
            text=f"{len(books)} book(s)  •  {total:,} total vectors", text_color=TM)

        if not books:
            ctk.CTkLabel(self._scroll, text="No books uploaded yet.",
                         text_color=TL, font=FB).pack(pady=40)
            return

        # sort by scope then name
        books.sort(key=lambda b: (b["scope"], b["name"].lower()))

        for b in books:
            card = ctk.CTkFrame(self._scroll, fg_color=BG3, corner_radius=8)
            card.pack(fill="x", pady=4)

            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=14, pady=10)

            scope_col = OGMID if b["scope"] != "global" else TL
            scope_lbl = f"👤 uid:{b['scope']}" if b["scope"] != "global" else "🌐 global"
            ctk.CTkLabel(left, text=scope_lbl,
                         font=FSM, text_color=scope_col).pack(anchor="w")
            ctk.CTkLabel(left, text=b["name"],
                         font=FS, text_color=TH).pack(anchor="w")
            ctk.CTkLabel(left, text=f"Namespace: {b['ns']}",
                         font=FSM, text_color=TL).pack(anchor="w")

            ctk.CTkLabel(card, text=f"{b['vectors']:,}\nvectors",
                         font=FSM, text_color=OG,
                         justify="center").pack(side="right", padx=18, pady=10)


# ══════════════════════════════════════════════════════════════════════════════
#  Stats Page
# ══════════════════════════════════════════════════════════════════════════════

class StatsPage(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._build()
        self.refresh()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(hdr, text="Index Stats", font=FH, text_color=TH).pack(side="left")
        ctk.CTkButton(hdr, text="⟳ Refresh", fg_color=BG4,
                      hover_color=BGHVR, text_color=TM, font=FSM,
                      height=30, width=90, corner_radius=6,
                      command=self.refresh).pack(side="right")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure((0, 1, 2, 3), weight=1)

        self._c_total   = StatCard(grid, "Total Vectors", icon="⬡", color=OG)
        self._c_books   = StatCard(grid, "Books",         icon="📚", color=OGLT)
        self._c_users   = StatCard(grid, "Users",         icon="👤", color=TH)
        self._c_global  = StatCard(grid, "Global Books",  icon="🌐", color=TM)

        for i, c in enumerate([self._c_total, self._c_books, self._c_users, self._c_global]):
            c.grid(row=0, column=i, padx=(0 if i else 0, 10 if i < 3 else 0), sticky="nsew")

        ctk.CTkLabel(self, text="Index Details",
                     font=FS, text_color=TM).pack(anchor="w", pady=(20, 6))

        self._detail = ctk.CTkFrame(self, fg_color=BG3, corner_radius=8)
        self._detail.pack(fill="x")
        self._detail_lbl = ctk.CTkLabel(self._detail, text="Loading…",
                                         text_color=TM, font=FB, justify="left")
        self._detail_lbl.pack(anchor="w", padx=16, pady=14)

    def refresh(self):
        self._c_total.set("…")
        self._c_books.set("…")
        self._c_users.set("…")
        self._c_global.set("…")
        self._detail_lbl.configure(text="Fetching from Pinecone…", text_color=YL)
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            pc, idx = _get_pinecone()
            total, books = _fetch_stats(pc, idx)

            idx_info  = pc.describe_index(CONFIG["pinecone"]["index_name"])
            dim       = getattr(idx_info, "dimension", "?")
            metric    = getattr(idx_info, "metric", "?")
            host      = getattr(idx_info, "host", "?")

            n_books  = len(books)
            n_users  = len({b["scope"] for b in books if b["scope"] != "global"})
            n_global = len([b for b in books if b["scope"] == "global"])

            detail = (f"Index:      {CONFIG['pinecone']['index_name']}\n"
                      f"Dimension:  {dim}\n"
                      f"Metric:     {metric}\n"
                      f"Host:       {host}\n"
                      f"Model:      {CONFIG['pinecone']['embedding_model']}")

            self.after(0, lambda: (
                self._c_total.set(f"{total:,}"),
                self._c_books.set(str(n_books)),
                self._c_users.set(str(n_users)),
                self._c_global.set(str(n_global)),
                self._detail_lbl.configure(text=detail, text_color=TH,
                                           font=FMO),
            ))
        except Exception as e:
            self.after(0, lambda: self._detail_lbl.configure(
                text=f"Error: {e}", text_color=RD))


# ══════════════════════════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════════════════════════

class Sidebar(ctk.CTkFrame):
    ITEMS = [
        ("📤", "Upload"),
        ("📚", "Library"),
        ("📊", "Stats"),
    ]

    def __init__(self, master, on_select, **kw):
        super().__init__(master, fg_color=BG2, corner_radius=0,
                         width=180, **kw)
        self.pack_propagate(False)
        self._on_select = on_select
        self._active    = None
        self._btns      = {}

        # branding
        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(20, 24))
        ctk.CTkLabel(brand, text="◆", font=("Segoe UI", 22, "bold"),
                     text_color=OG).pack(side="left")
        wrap = ctk.CTkFrame(brand, fg_color="transparent")
        wrap.pack(side="left", padx=8)
        ctk.CTkLabel(wrap, text="NotBook",
                     font=("Segoe UI", 13, "bold"), text_color=TH).pack(anchor="w")
        ctk.CTkLabel(wrap, text="Admin Uploader",
                     font=FSM, text_color=TM).pack(anchor="w")

        # divider
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=(0, 16))

        # nav
        for icon, label in self.ITEMS:
            self._make_btn(icon, label)

        # bottom: env status
        ctk.CTkFrame(self, fg_color="transparent").pack(fill="both", expand=True)
        self._env_lbl = ctk.CTkLabel(self, text="", font=FSM,
                                      text_color=TL, wraplength=150)
        self._env_lbl.pack(padx=12, pady=12, anchor="w")
        self._check_env()

    def _check_env(self):
        key = os.getenv("PINECONE_API_KEY")
        if key:
            self._env_lbl.configure(
                text=f"● Pinecone key set\n  ···{key[-6:]}",
                text_color=GN)
        else:
            self._env_lbl.configure(text="⚠ PINECONE_API_KEY missing",
                                    text_color=RD)

    def _make_btn(self, icon, label):
        f = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        f.pack(fill="x", padx=10, pady=2)

        inner = ctk.CTkFrame(f, fg_color="transparent", corner_radius=6)
        inner.pack(fill="x")

        ico_l = ctk.CTkLabel(inner, text=icon, font=("Segoe UI", 14),
                              text_color=TM, width=30)
        ico_l.pack(side="left", padx=(10, 4), pady=8)
        txt_l = ctk.CTkLabel(inner, text=label, font=FB, text_color=TM)
        txt_l.pack(side="left")

        self._btns[label] = (inner, ico_l, txt_l)

        def on_click(lbl=label, frm=inner, il=ico_l, tl=txt_l):
            self._select(lbl, frm, il, tl)

        for w in (f, inner, ico_l, txt_l):
            w.bind("<Button-1>", lambda e, fn=on_click: fn())
            w.bind("<Enter>",    lambda e, frm=inner: frm.configure(fg_color=BG4))
            w.bind("<Leave>",    lambda e, frm=inner, lbl=label:
                    frm.configure(fg_color=OGDIM if self._active == lbl else "transparent"))

    def _select(self, label, frm, ico_l, txt_l):
        # deselect previous
        if self._active and self._active in self._btns:
            pf, pi, pt = self._btns[self._active]
            pf.configure(fg_color="transparent")
            pi.configure(text_color=TM)
            pt.configure(text_color=TM, font=FB)

        self._active = label
        frm.configure(fg_color=OGDIM)
        ico_l.configure(text_color=OG)
        txt_l.configure(text_color=TH, font=FS)
        self._on_select(label)

    def select(self, label):
        if label in self._btns:
            f, i, t = self._btns[label]
            self._select(label, f, i, t)


# ══════════════════════════════════════════════════════════════════════════════
#  Main Application
# ══════════════════════════════════════════════════════════════════════════════

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # enable tkinterdnd2 if present
        try:
            from tkinterdnd2 import TkinterDnD
            TkinterDnD._require(self)
        except Exception:
            pass

        self.title("NotBook — Admin Uploader")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(fg_color=BG1)

        # try to set icon (skip gracefully if no ico file)
        try:
            self.iconbitmap(Path(__file__).parent / "icon.ico")
        except Exception:
            pass

        self._build()
        self._sidebar.select("Upload")

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # status bar at very bottom
        sb = ctk.CTkFrame(self, fg_color=BG0, corner_radius=0, height=28)
        sb.pack(side="bottom", fill="x")
        sb.pack_propagate(False)
        self._sb_dot = ctk.CTkLabel(sb, text="●", font=FSM, text_color=TM)
        self._sb_dot.pack(side="left", padx=(12, 4), pady=4)
        self._sb_txt = ctk.CTkLabel(sb, text="Ready", font=FSM, text_color=TM)
        self._sb_txt.pack(side="left")
        ctk.CTkLabel(sb, text=f"  •  {CONFIG['pinecone']['index_name']}  •  {CONFIG['pinecone']['embedding_model']}",
                     font=FSM, text_color=TL).pack(side="left", padx=8)

        # main row
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="both", expand=True)

        # sidebar
        self._sidebar = Sidebar(row, on_select=self._switch_page)
        self._sidebar.pack(side="left", fill="y")

        # thin divider
        ctk.CTkFrame(row, fg_color=BORDER, width=1, corner_radius=0).pack(side="left", fill="y")

        # content area
        self._content = ctk.CTkFrame(row, fg_color=BG1, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        # pages
        self._pages = {
            "Upload":  UploadPage(self._content,
                                   status_cb=self._set_status),
            "Library": LibraryPage(self._content),
            "Stats":   StatsPage(self._content),
        }
        self._active_page = None

    def _switch_page(self, name):
        if self._active_page:
            self._active_page.pack_forget()
        page = self._pages[name]
        page.pack(fill="both", expand=True, padx=24, pady=20)
        self._active_page = page

        # refresh data pages on visit
        if name == "Library":
            page.refresh()
        elif name == "Stats":
            page.refresh()

    def _set_status(self, text, color=TM):
        self._sb_dot.configure(text_color=color)
        self._sb_txt.configure(text=text, text_color=color)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
