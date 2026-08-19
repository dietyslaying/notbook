"""Clinical case work-up framework (Phase 8 — ported into Notbook AI).

Locked format contract (client, 2026-08-14) — "always this exact format, this
exact order":

  PATIENT PRESENTATION 👤 · INITIAL TRIAGE / STABILIZATION 🚨 ·
  HISTORY 📑 · PHYSICAL EXAMINATION 🩺 · CLINICAL ASSESSMENT 🧠 ·
  PROBLEM LIST 📋 · DIFFERENTIAL DIAGNOSIS 🔍 · INVESTIGATIONS 🧪 ·
  INTERPRETATION 📊 · WORKING DIAGNOSIS 🎯 · MANAGEMENT 💊 ·
  BEDSIDE GUIDANCE 🛌 · DISPOSITION & FOLLOW-UP 🏠 ·
  CORE CLINICAL PRINCIPLES ⚖️ · REFERENCES 📚 · BOTTOM LINE ⭐
(sample-case order: REFERENCES before the closing BOTTOM LINE)

- Three item types per section: "~Label" → bold+underline sub-heading;
  "- text" → plain prose line (lead-ins / takeaways / A→B reasoning);
  anything else → "•" bullet. Auto-bold "Label:" prefixes.
- Inline [cN]/[N] cites resolve to bold [p.X] from the actual retrieved
  citations; REFERENCES is grouped per book and built by the bot (never LLM).
- Rich text only: headings, sub-headings, blockquote, bold, italic, emojis,
  bullets, underline, [p.X]. No expandables/checklists/tables (Telegram HTML
  has no <details>).
- Situation lens (archetypes): acute 🚨 → obstetric 🤰 → pediatric 🧒 →
  psychiatric 🧠 → geriatric 👴 → chronic 🗓️ → general (first match wins).
  Detection: age/sex=3, complaint wording=2, duration=1, threshold 4;
  age/sex + (complaint OR duration) always qualifies. English + Malayalam.
- Tunable in config.yaml → case_framework (threshold, caps, show_lens,
  archetypes.*).
"""

from __future__ import annotations

import html
import json
import re
from typing import Any, Optional

from config import config


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)

# ── Case-vignette detection ─────────────────────────────────────────
# Score: age/sex = 3, complaint wording = 2, duration = 1. Threshold 4.
# age/sex + (complaint OR duration) always qualifies (covers "42M chest pain").

_AGE_SEX_RE = re.compile(
    r"\b(\d{1,3})[\s-]*(?:year(?:s|-old)?[\s-]*|yo\b[\s-]*|yr\b[\s-]*|month(?:s|-old)?[\s-]*)?"
    r"(?:old[\s-]*)?(?:male|female|man|woman|gentleman|lady|boy|girl|baby|infant|child)\b"
    r"|\b(\d{1,3})[\s-]*[MmFf]\b",
    re.I,
)

_AGE_SEX_ML_RE = re.compile(
    r"\b(\d{1,3})\s*(?:വയസ്സുകാരൻ|വയസ്സുകാരി|കാരനായ|കാരിയായ|കാരൻ|കാരി)\b"
    r"|\b(\d{1,3})\s*(?:വയസ്സുള്ള|വയസ്സ്)?\s*(?:പുരുഷൻ|സ്ത്രീ|ആൺ|പെൺ)\b",
    re.I,
)

_DURATION_ML_RE = re.compile(
    r"\b\d+\s*(?:ആഴ്ച|ദിവസം|മാസം|വർഷം|മണിക്കൂർ)\w*\b",
    re.I,
)

_PRESENT_RE = re.compile(
    r"\b(?:presents? with|presented with|complains? of|complaint of|"
    r"chief complaint|c/o\b|h/o\b|history of|known case|brought in|"
    r"seen in (?:opd|ed|emergency|casualty))\b",
    re.I,
)

_DURATION_RE = re.compile(
    r"\b(?:for|over|since|lasting|duration of)?\s*\d+\s*-?\s*"
    r"(?:days|weeks|months|hours|years)\b(?: ago)?|\b×\s*\d+\b",
    re.I,
)


def is_case_prompt(text: str) -> bool:
    cfg = config.raw_config.get("case_framework") or {}
    if not cfg.get("enabled", True):
        return False
    t = (text or "").strip()
    if not t:
        return False

    has_age_sex = bool(_AGE_SEX_RE.search(t) or _AGE_SEX_ML_RE.search(t))
    has_pres = bool(_PRESENT_RE.search(t))
    has_dur = bool(_DURATION_RE.search(t) or _DURATION_ML_RE.search(t))

    score = (3 if has_age_sex else 0) + (2 if has_pres else 0) + (1 if has_dur else 0)
    thresh = int(cfg.get("detection_threshold") or 4)
    if has_age_sex and (has_pres or has_dur):
        score = max(score, thresh)
    return score >= thresh


# ── Situation archetypes ────────────────────────────────────────────
# The 15-section skeleton is fixed; the archetype tunes what the model
# prioritizes and which extra "~" sub-headings it may use.
# Overridable per-archetype in config.yaml → case_framework.archetypes.

ARCHETYPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "acute": {
        "label": "Acute / red-flag",
        "emoji": "🚨",
        "focus": (
            "This is an acute presentation. If unstable, prioritize ABCDE, vitals, "
            "immediate life threats and stabilization. If stable, make must-not-miss "
            "diagnoses explicit (ACS, PE, aortic dissection, sepsis), list red flags "
            "and escalation criteria, and state admission thresholds."
        ),
        "suggest": ["What not to miss", "First steps"],
    },
    "obstetric": {
        "label": "Pregnancy / obstetric",
        "emoji": "🤰",
        "focus": (
            "Include pregnancy status and gestation. Prioritize obstetric red flags "
            "(bleeding, pre-eclampsia, reduced fetal movements), fetal assessment, "
            "and urgent referral thresholds."
        ),
        "suggest": ["Obstetric red flags", "Fetal assessment"],
    },
    "pediatric": {
        "label": "Pediatric",
        "emoji": "🧒",
        "focus": (
            "Age-specific priorities: hydration and feeding, fever handling, growth, "
            "weight-based drug dosing, and red flags in children (meningism, sepsis, "
            "dehydration). State admission criteria and safeguarding."
        ),
        "suggest": ["Red flags in children", "Hydration & feeding"],
    },
    "psychiatric": {
        "label": "Psychiatric",
        "emoji": "🧠",
        "focus": (
            "Prioritize risk to self and others, safety plan, capacity, safeguarding, "
            "admission criteria and follow-up. Cover substance use when relevant."
        ),
        "suggest": ["Risk assessment", "Safety plan"],
    },
    "geriatric": {
        "label": "Geriatric",
        "emoji": "👴",
        "focus": (
            "Include baseline function, frailty, falls, polypharmacy and de-prescribing, "
            "delirium vs dementia, social support and capacity. Adjust management to "
            "function, not just age."
        ),
        "suggest": ["Baseline function", "Polypharmacy"],
    },
    "chronic": {
        "label": "Chronic care",
        "emoji": "🗓️",
        "focus": (
            "Long-standing problem: deepen history (adherence, lifestyle), monitoring "
            "plan, treatment ladder, and prevention / secondary prevention. Give a "
            "realistic follow-up timeline."
        ),
        "suggest": ["Monitoring", "Prevention"],
    },
    "general": {
        "label": "General",
        "emoji": "📘",
        "focus": "Balanced work-up across all sections.",
        "suggest": [],
    },
}

_ARCHETYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "acute",
        re.compile(
            r"\b(chest pain|crushing chest|short(?:ness)? of breath|breathless|dyspn[oe]a|"
            r"collapse|unconscious|unresponsive|cardiac arrest|myocardial|rti\b|road traffic|"
            r"trauma|accident|seizure|fits?\b|stroke|anaphyla\w*|bleeding|haemorrhage|"
            r"hemorrhage|haematemesis|hematemesis|mel[ae]na|sepsis|septic\w*|shock|overdose|"
            r"poison\w*|palpitations|syncope)\b",
            re.I,
        ),
    ),
    (
        "obstetric",
        re.compile(
            r"\b(pregnan\w*|obstetric\w*|antenatal|postnatal|postpartum|labou?r\b|gravida|"
            r"para \d|gestational|miscarriage|confinement|puerper\w*|reduced fetal movements)\b",
            re.I,
        ),
    ),
    (
        "pediatric",
        re.compile(
            r"\b(child|children|baby|babies|infant|toddler|neonate|newborn|"
            r"school[- ]?child|paediatric|pediatric)\b",
            re.I,
        ),
    ),
    (
        "psychiatric",
        re.compile(
            r"\b(anxiet\w*|depress\w*|suicid\w*|self[- ]harm|psychos\w*|psychiatric|"
            r"schizo\w*|bipolar|panic\w*|hallucinat\w*|delusion\w*|addict\w*|alcohol\w*|"
            r"withdraw\w*|behaviou?r|low mood)\b",
            re.I,
        ),
    ),
    (
        "geriatric",
        re.compile(
            r"\b(elderly|geriatric|nursing home|care home|dementia|confusion|frail\w*|"
            r"polypharmacy|fall\w*)\b|\b([78]\d|9\d)\s*(?:yo\b|years?\b|year[- ]old)",
            re.I,
        ),
    ),
    (
        "chronic",
        re.compile(
            r"\b(chronic|long[- ]standing|long term|recurrent|stable\b|diabetes|"
            r"hypertension|copd|asthma|arthritis|osteoarthritis|gord\b|gerd\b|reflux|"
            r"hypothyroid|obesity|ischemic heart|ischaemic heart)\b",
            re.I,
        ),
    ),
]


def _detect_archetype(text: str) -> str:
    t = (text or "").lower()
    for key, pat in _ARCHETYPE_RULES:
        if pat.search(t):
            return key
    return "general"


def detect_archetype(text: str) -> str:
    return _detect_archetype(text)


def _archetype_meta(key: str) -> dict[str, Any]:
    cfg = (config.raw_config.get("case_framework") or {}).get("archetypes") or {}
    meta = dict(ARCHETYPE_DEFAULTS.get(key) or ARCHETYPE_DEFAULTS["general"])
    over = cfg.get(key)
    if isinstance(over, dict):
        for k in ("label", "emoji", "focus"):
            if over.get(k):
                meta[k] = over[k]
        if isinstance(over.get("suggest"), list):
            meta["suggest"] = [str(s) for s in over["suggest"] if str(s).strip()]
    return meta


def _lens_block(key: str) -> str:
    meta = _archetype_meta(key)
    parts = [f"Type: {meta['label']}", f"Focus: {meta['focus']}"]
    sugs = [s if s.startswith("~") else f"~{s}" for s in (meta.get("suggest") or [])]
    if sugs:
        parts.append("When relevant, include these extra sub-headings: " + ", ".join(sugs))
    return "\n".join(parts)


def _mode_hint(mode: str) -> str:
    hints = {
        "brief": "User is in 30-second mode — keep bullets very short, max 4 per section.",
        "exam": "User is in Exam mode — make facts high-yield and testable (numbers, names, criteria, traps).",
        "ward": "User is in Practical mode — always produce the full case work-up format.",
    }
    return hints.get(mode, "")


# ── Gemini JSON schema (15 content sections; REFERENCES built by the bot) ──

CASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "presentation": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "PATIENT PRESENTATION: demographics, chief complaint, duration, "
                "setting (OPD/ED/Ward/ICU), stable or unstable. End with one "
                "'Immediate read:' bullet plus 1-2 short supporting lines."
            ),
        },
        "triage": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "INITIAL TRIAGE / STABILIZATION: if unstable → ABCDE, vitals, life "
                "threats, initial emergency management. If stable → '-' line saying so, "
                "bullets on what would change that, clinical takeaway line."
            ),
        },
        "history": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "HISTORY: HPI (OPQRST/SOCRATES where appropriate), associated symptoms, "
                "red flags, PMH, drug & allergy history, family/social/occupational "
                "history, review of systems, past procedures/admissions, adherence, "
                "pregnancy, baseline function. Group with '~Label' sub-heading lines."
            ),
        },
        "exam": {
            "type": "array",
            "items": {"type": "string"},
            "description": "PHYSICAL EXAMINATION: general exam, vitals, systemic exam, focused bedside tests.",
        },
        "assessment": {
            "type": "array",
            "items": {"type": "string"},
            "description": "CLINICAL ASSESSMENT: clinical summary, severity, stability, organ systems, risk assessment.",
        },
        "problem_list": {
            "type": "array",
            "items": {"type": "string"},
            "description": "PROBLEM LIST: active problems, prioritized.",
        },
        "differential": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "DIFFERENTIAL DIAGNOSIS: MUST use exactly three sub-headings "
                "'~Most likely', '~Common alternatives', '~Must-not-miss'."
            ),
        },
        "investigations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "INVESTIGATIONS: bedside, laboratory, imaging, special tests.",
        },
        "interpretation": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "INTERPRETATION: key findings, rule in, rule out, clinical correlation; "
                "use short 'A → B' reasoning '-' lines."
            ),
        },
        "working_diagnosis": {
            "type": "array",
            "items": {"type": "string"},
            "description": "WORKING DIAGNOSIS: primary diagnosis + alternatives still under consideration.",
        },
        "management": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "MANAGEMENT: immediate, medical, surgical/procedural, non-pharmacological, "
                "patient education, lifestyle advice, referral/consultation."
            ),
        },
        "bedside": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "BEDSIDE GUIDANCE: monitoring, reassessment, response to treatment, "
                "escalation criteria, warning signs, complication surveillance, "
                "when to escalate, expected clinical course."
            ),
        },
        "disposition": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "DISPOSITION & FOLLOW-UP: admit/discharge/ICU-HDU transfer, referral, "
                "follow-up plan, prevention/secondary prevention, safety-net advice, "
                "review timeline."
            ),
        },
        "principles": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "CORE CLINICAL PRINCIPLES: documentation, ethical & legal, evidence-based "
                "practice, shared decision-making, patient safety."
            ),
        },
        "bottom_line": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "BOTTOM LINE: 3-5 bullets with labels fitting the case: "
                "'Diagnosis:', 'Alternatives:', 'Reasoning:', 'Action:', 'Safety:'."
            ),
        },
    },
    "required": [
        "presentation",
        "triage",
        "history",
        "exam",
        "assessment",
        "problem_list",
        "differential",
        "investigations",
        "interpretation",
        "working_diagnosis",
        "management",
        "bedside",
        "disposition",
        "principles",
        "bottom_line",
    ],
}

CASE_PROMPT = """You are a clinical tutor for medical students preparing a structured case work-up for phone study.

The user posted a PATIENT CASE PRESENTATION:
{question}

Produce the complete work-up framework below — every section, in this exact order, filled for THIS patient.

FRAMEWORK (headings/emojis are added automatically — write ONLY content):
1. PATIENT PRESENTATION — demographics, chief complaint, duration, setting (OPD/ED/Ward/ICU), stable or unstable. End with an "Immediate read:" bullet (one-line verdict: stable/unstable, crash risk) followed by 1–2 short supporting lines ("-" lines).
2. INITIAL TRIAGE / STABILIZATION — if unstable: ABCDE, vitals, immediate life threats, initial emergency management. If stable: open with a "-" line saying so, bullet what would change that decision, and end with a clinical takeaway "-" line (e.g. "In chest pain, a normal ECG does not exclude ACS…").
3. HISTORY — HPI (OPQRST/SOCRATES where appropriate), associated symptoms, red flags, PMH, drug & allergy history, family/social/occupational history, review of systems, past procedures/admissions, adherence, pregnancy if relevant, baseline function in geriatrics/chronic disease. Ask-but-missing items as "?" bullets (e.g. "Worse on lying down?"). Group with "~Label" lines (e.g. "~RISK HISTORY").
4. PHYSICAL EXAMINATION — general exam, vitals, systemic exam, focused bedside tests.
5. CLINICAL ASSESSMENT — clinical summary, severity, stability, organ systems involved, risk assessment. End with what must not be ignored.
6. PROBLEM LIST — active problems, prioritized.
7. DIFFERENTIAL DIAGNOSIS — MUST use exactly three sub-headings: "~Most likely", "~Common alternatives", "~Must-not-miss".
8. INVESTIGATIONS — bedside, laboratory, imaging, special tests. After each test group add a "-" line explaining why/for what (e.g. "If GORD most likely → trial of full-dose PPI 4–8 weeks").
9. INTERPRETATION — key findings, rule in, rule out, clinical correlation. Use short "A → B" reasoning "-" lines (e.g. "After meals → supports GORD", "Better sitting forward → supports pericarditis", "Normal ECG → reassuring but does not exclude ACS").
10. WORKING DIAGNOSIS — primary working diagnosis + alternatives still under consideration.
11. MANAGEMENT — immediate, medical, surgical/procedural, non-pharmacological, patient education, lifestyle advice, referral/consultation. Group by condition with "~Label" lines (e.g. "~If GORD-predominant", "~If pericarditis becomes likely", "~If Anxiety:").
12. BEDSIDE GUIDANCE — monitoring, reassessment, response to treatment, escalation criteria, warning signs, complication surveillance, when to escalate, expected clinical course. Open with a "-" lead line (e.g. "Reassess if pain becomes:") then bullet the triggers.
13. DISPOSITION & FOLLOW-UP — conditional lines: "Discharge if…", "Refer/test if…", "Admit if…", then follow-up plan, prevention/secondary prevention, safety-net advice, review timeline.
14. CORE CLINICAL PRINCIPLES — documentation, ethical & legal, evidence-based practice, shared decision-making, patient safety.
15. BOTTOM LINE — 3–5 bullets, labels fit the case ("Diagnosis:", "Alternatives:", "Reasoning:", "Action:", "Safety:" — use the ones that apply).

LANGUAGE: all content in the SAME language as the user's message (Malayalam if they write Malayalam; medical terms may stay English).

SOURCING:
- CONTEXT is from the student's textbooks; each block is labeled [n] Book, p.X.
- Cite inline as [n] wherever an excerpt supports the statement, e.g. "...reflux-type chest pain [3]" — it is converted to [p.X] automatically.
- CONTEXT is the primary source of facts. Where CONTEXT does not cover a step, complete it with standard clinical reasoning — but never invent page citations.
- If the excerpts contain nothing relevant to the case, say so plainly in CLINICAL ASSESSMENT.

FORMAT:
- JSON only. No markdown, no HTML, no emojis inside the JSON text.
- Three item types per section: "~Label" → sub-heading (bold + underline); "- text" → plain prose line (lead-ins, takeaways, A → B reasoning); anything else → "•" bullet. Every section must be readable in the sample-case style.
- Bullets short (max ~150 chars), max 8 per section.
- No filler ("it is important to note", "in conclusion"). Keep it tight.

SCOPE: {scope}
SITUATION LENS:
{lens}

MODE HINT: {mode_hint}
CONTEXT:
{context}
"""


def _clean(text: str, max_len: int = 0) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if max_len and len(t) > max_len:
        cut = t[: max_len - 1].rsplit(" ", 1)[0]
        t = (cut or t[: max_len - 1]).rstrip(".,;:") + "…"
    return t


# ── Renderer ─────────────────────────────────────────────────────────

_SECTION_ORDER: list[tuple[str, str, str]] = [
    ("👤", "PATIENT PRESENTATION", "presentation"),
    ("🚨", "INITIAL TRIAGE / STABILIZATION", "triage"),
    ("📑", "HISTORY", "history"),
    ("🩺", "PHYSICAL EXAMINATION", "exam"),
    ("🧠", "CLINICAL ASSESSMENT", "assessment"),
    ("📋", "PROBLEM LIST", "problem_list"),
    ("🔍", "DIFFERENTIAL DIAGNOSIS", "differential"),
    ("🧪", "INVESTIGATIONS", "investigations"),
    ("📊", "INTERPRETATION", "interpretation"),
    ("🎯", "WORKING DIAGNOSIS", "working_diagnosis"),
    ("💊", "MANAGEMENT", "management"),
    ("🛌", "BEDSIDE GUIDANCE", "bedside"),
    ("🏠", "DISPOSITION & FOLLOW-UP", "disposition"),
    ("⚖️", "CORE CLINICAL PRINCIPLES", "principles"),
]

# Sample case order: REFERENCES sits before the closing BOTTOM LINE.
_BOTTOM_LINE_SECTION: tuple[str, str, str] = ("⭐", "BOTTOM LINE", "bottom_line")

_LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z &'/-]{0,28}):\s")
_CITE_RE = re.compile(r"\[p\.\s*\d+[\s,\d.]*\]")


def _resolve_page_cites(text: str, citations: list[dict]) -> str:
    """Convert inline [cN]/[N] context refs → real [p.X] using retrieved pages."""
    pages: dict[str, str] = {}
    for i, c in enumerate(citations[:12]):
        ref = str(c.get("ref") or "").strip()
        page = c.get("page")
        if ref and page not in (None, "", "N/A"):
            pages[ref.lower()] = str(page)
        if page not in (None, "", "N/A"):
            pages[f"#{i + 1}"] = str(page)

    def _rep(m: re.Match) -> str:
        key = m.group(1).lower()
        page = pages.get(key) or pages.get(f"#{key}")
        return f"[p.{page}]" if page else m.group(0)

    return re.sub(r"\[(c\d+|\d+)\]", _rep, text)


def _style_cites(text: str) -> str:
    return _CITE_RE.sub(lambda m: f"<b>{m.group(0)}</b>", text)


def _bullet(text: str) -> str:
    """Escaped bullet; bold [p.X] cites and short label prefixes like 'Diagnosis:'."""
    t = _esc(text)
    t = _style_cites(t)
    m = _LABEL_RE.match(t)
    if m:
        label = m.group(0)[:-1]
        rest = t[m.end() :]
        return f"• <b>{label}</b> {rest}"
    return f"• {t}"


def _section_html(
    emoji: str,
    title: str,
    items: list[str],
    *,
    citations: list[dict],
    max_bullets: int,
    max_chars: int,
) -> str:
    lines: list[str] = []
    for it in items[:max_bullets]:
        t = _clean(str(it), max_chars)
        if not t:
            continue
        t = _resolve_page_cites(t, citations)
        if t.startswith("~"):
            sub = t[1:].strip()
            lines.append(f"<u><b>{_esc(sub)}</b></u>")
        elif t.startswith("-"):
            prose = _style_cites(_esc(t[1:].strip()))
            pm = _LABEL_RE.match(prose)
            if pm:
                label = pm.group(0)[:-1]
                rest = prose[pm.end() :]
                lines.append(f"<b>{label}</b> {rest}")
            else:
                lines.append(prose)
        else:
            lines.append(_bullet(t))
    if not lines:
        return ""
    return "\n\n\n".join((f"<b>{emoji} {_esc(title)}</b>", "\n".join(lines)))


def _references_html(citations: list[dict], *, max_pages: int = 8) -> str:
    per_book: dict[str, list[str]] = {}
    order: list[str] = []
    for c in citations[:12]:
        book = str(c.get("book") or c.get("namespace") or "Textbook")
        page = c.get("page")
        if book not in per_book:
            per_book[book] = []
            order.append(book)
        if page not in (None, "", "N/A") and page not in per_book[book]:
            per_book[book].append(str(page))
    if not order:
        return ""
    lines: list[str] = []
    for book in order:
        pages = per_book[book]
        if pages:
            lines.append(
                f"• <b>{_esc(book)}</b>: [{', '.join(f'p.{p}' for p in pages[:max_pages])}]"
            )
        else:
            lines.append(f"• <b>{_esc(book)}</b>")
    return "\n\n\n".join((f"<b>📚 REFERENCES</b>", "\n".join(lines)))


def render_case(
    data: dict[str, Any],
    citations: list[dict],
    *,
    scope_label: str = "all books",
    archetype: str = "general",
) -> str:
    cfg = config.raw_config.get("case_framework") or {}
    max_bullets = int(cfg.get("max_bullets") or 8)
    max_chars = int(cfg.get("max_bullet_chars") or 170)

    parts: list[str] = ["<i>Based on Provided Excerpts…</i>"]
    if cfg.get("show_lens", True) and archetype and archetype != "general":
        meta = _archetype_meta(archetype)
        parts.append(f"<b>{meta['emoji']} Situation · {_esc(meta['label'])}</b>")
    for emoji, title, key in _SECTION_ORDER:
        items = data.get(key)
        if not isinstance(items, list):
            continue
        sec = _section_html(
            emoji,
            title,
            items,
            citations=citations,
            max_bullets=max_bullets,
            max_chars=max_chars,
        )
        if sec:
            parts.append(sec)
    refs = _references_html(citations)
    if refs:
        parts.append(refs)
    items = data.get(_BOTTOM_LINE_SECTION[2])
    if isinstance(items, list):
        bl = _section_html(
            _BOTTOM_LINE_SECTION[0],
            _BOTTOM_LINE_SECTION[1],
            items,
            citations=citations,
            max_bullets=max_bullets,
            max_chars=max_chars,
        )
        if bl:
            parts.append(bl)
    return "\n\n\n".join(parts)


# ── Prompt assembly + JSON validation (used by CaseWorkspace) ─────────


def scope_label(namespaces: Optional[list[str]]) -> str:
    if not namespaces:
        return "all books"
    if len(namespaces) == 1:
        return f"{namespaces[0]} only"
    return " + ".join(namespaces) if len(namespaces) <= 3 else f"{len(namespaces)} books"


def build_prompt(
    *,
    query: str,
    archetype: str = "general",
    study_mode: str = "standard",
    context: str,
    namespaces: Optional[list[str]] = None,
) -> str:
    return CASE_PROMPT.format(
        question=(query or "").strip(),
        scope=scope_label(namespaces),
        lens=_lens_block(archetype),
        mode_hint=_mode_hint(study_mode) or "None.",
        context=context,
    )


_REQUIRED_CASE_KEYS = [
    "presentation",
    "triage",
    "history",
    "exam",
    "assessment",
    "problem_list",
    "differential",
    "investigations",
    "interpretation",
    "working_diagnosis",
    "management",
    "bedside",
    "disposition",
    "principles",
    "bottom_line",
]

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON object extraction (fences, prose, trailing commas)."""
    text = (text or "").strip()
    text = _FENCE.sub("", text).strip()
    candidates: list[str] = []
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        for attempt in (cand, _TRAILING_COMMA.sub(r"\1", cand)):
            try:
                data = json.loads(attempt)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return None


def validate_case_json(raw_llm_output: str) -> dict[str, Any]:
    """Parse + soft-validate the case JSON. Returns {"error": ...} on failure."""
    data = _extract_json(raw_llm_output)
    if data is None:
        return {"error": "Model returned unparseable JSON for the case work-up."}
    if not isinstance(data, dict):
        return {"error": "Model returned non-object JSON for the case work-up."}

    for key in _REQUIRED_CASE_KEYS:
        if not isinstance(data.get(key), list):
            data[key] = []
        else:
            data[key] = [str(x).strip() for x in data[key] if str(x).strip()]
    if not data["presentation"]:
        return {"error": "Case work-up came back empty. Please try again."}
    return data


def title_for(query: str) -> str:
    t = re.sub(r"\s+", " ", (query or "").strip())
    return t[:80] or "Clinical case work-up"


def one_line(data: dict[str, Any]) -> str:
    bl = data.get("bottom_line") or []
    if bl:
        return _clean(str(bl[0]), 220)
    wd = data.get("working_diagnosis") or []
    if wd:
        return _clean(str(wd[0]), 220)
    return "Structured clinical case work-up."
