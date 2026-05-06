"""
VEEG Triage App v2 - שאלון מובנה למטופל
הרץ עם: streamlit run veeg_triage_v2.py
"""

import streamlit as st
from groq import Groq, AuthenticationError
import json
from datetime import date, timedelta

# ── הגדרות עמוד ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VEEG Triage – שאלון מטופל",
    page_icon="🧠",
    layout="centered",
)

# ── CSS מינימלי ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
.score-card {
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 18px;
    border-left: 7px solid;
}
.score-low  { background:#eafbe7; border-color:#2e7d32; color:#2e7d32; }
.score-mid  { background:#fff8e1; border-color:#f57c00; color:#f57c00; }
.score-high { background:#fdecea; border-color:#c62828; color:#c62828; }
.avail-badge {
    display:inline-block;
    background:#e8f5e9; color:#2e7d32;
    border-radius:20px; padding:4px 14px;
    font-size:13px; font-weight:600;
    margin-top:6px;
}
</style>
""", unsafe_allow_html=True)

# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
אתה עוזר רפואי חכם המתמחה בטריאז' ליחידת וידאו-EEG בבית חולים.
קיבלת נתוני שאלון מובנה ממטופל. נתח את רמת הדחיפות וצור סיכום מנהלי.

לוגיקת תעדוף (Scoring 1-10):
1. מטרת ההפניה: הערכה טרום-ניתוחית = קדימות גבוהה ביותר.
2. תדירות התקפים: יומי > שבועי > חודשי > נדיר.
3. מספר תרופות אנטי-אפילפטיות: ≥2 = עמידות תרופתית = קדימות גבוהה.
4. תאריך התקף אחרון: קרוב יותר = דחיפות גבוהה יותר.
5. פציעות / drop attacks / סטטוס אפילפטיקוס בעבר = מעלה דחיפות.

IMPORTANT: output ONLY a raw JSON object. No markdown fences, no backticks, no explanation before or after.
Use exactly these keys:
{
  "urgency_score": <integer 1-10>,
  "score_label": "<דחיפות נמוכה or דחיפות בינונית or דחיפות גבוהה>",
  "patient_summary": "<one line in Hebrew>",
  "clinical_highlights": ["<item1>", "<item2>", "<item3>"],
  "clinical_justification": "<Hebrew explanation>",
  "logistics_note": "<Hebrew note for secretary>"
}
"""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ הגדרות מערכת")
    api_key = st.text_input(
        "Groq API Key",
        type="password",
        placeholder="gsk_...",
        help="קבל מפתח חינמי: console.groq.com",
    )
    model_choice = st.selectbox(
        "מודל",
        ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"],
    )
    st.divider()
    st.markdown("**מדריך ציון:**")
    st.markdown("🟢 1–3 — דחיפות נמוכה")
    st.markdown("🟡 4–6 — דחיפות בינונית")
    st.markdown("🔴 7–10 — דחיפות גבוהה")
    st.divider()
    st.info("המפתח נשמר בזיכרון הסשן בלבד.", icon="🔒")

# ── כותרת ────────────────────────────────────────────────────────────────────
st.title("🧠 VEEG Triage")
st.subheader("שאלון הפניה למטופל")
st.caption("מלא את השאלון ולחץ 'שלח' — המערכת תקבע סדר עדיפות קליני.")
st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# שלב 1 – פרטי מטופל
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### 👤 פרטי מטופל")
col1, col2 = st.columns(2)
with col1:
    patient_name = st.text_input("שם מלא *", placeholder="ישראל ישראלי")
with col2:
    patient_id = st.text_input("מספר ת.ז.", placeholder="000000000")

col3, col4 = st.columns(2)
with col3:
    patient_age = st.number_input("גיל", min_value=0, max_value=120, value=None,
                                   placeholder="גיל המטופל")
with col4:
    patient_gender = st.selectbox("מין", ["בחר...", "זכר", "נקבה", "אחר"])

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# שלב 2 – מטרת ההפניה
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### 🎯 מטרת ההפניה")
referral_purpose = st.radio(
    "מהי מטרת בדיקת ה-VEEG?",
    options=[
        "אבחנה ראשונית – בירור אירועים לא ברורים",
        "הערכה טרום-ניתוחית (Pre-surgical evaluation)",
        "מיפוי סוג ומוקד ההתקפים",
        "בקרת טיפול תרופתי",
        "אחר",
    ],
    index=None,
)

if referral_purpose == "אחר":
    referral_other = st.text_input("פרט את מטרת ההפניה:")
else:
    referral_other = ""

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# שלב 3 – תדירות ואופי התקפים
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### ⚡ התקפים")

seizure_frequency = st.select_slider(
    "תדירות ההתקפים",
    options=[
        "פחות מפעם בשנה",
        "כמה פעמים בשנה",
        "כמה פעמים בחודש",
        "כמה פעמים בשבוע",
        "פעם ביום",
        "מספר פעמים ביום",
    ],
)

last_seizure = st.date_input(
    "תאריך ההתקף האחרון",
    value=None,
    max_value=date.today(),
    help="השאר ריק אם לא ידוע",
)

seizure_type = st.multiselect(
    "סוג ההתקפים (ניתן לבחור יותר מאחד)",
    options=[
        "מוקדי (פוקאלי) ללא אובדן הכרה",
        "מוקדי עם אובדן הכרה",
        "מוכלל (טוניק-קלוני / גרנד מל)",
        "אבסנס (פטיט מל)",
        "מיוקלוני",
        "Drop attack (נפילה פתאומית)",
        "לא ברור / לא מאובחן",
    ],
)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# שלב 4 – טיפול תרופתי
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### 💊 טיפול תרופתי")

current_meds_count = st.number_input(
    "כמה תרופות אנטי-אפילפטיות אתה נוטל כרגע?",
    min_value=0, max_value=10, value=0,
    help="תרופות כמו למוטריג'ין, קרבמזפין, ולפרואט, לקוסמיד וכו'"
)

total_meds_tried = st.number_input(
    "כמה תרופות שונות ניסית בסך הכל (כולל עבר)?",
    min_value=0, max_value=15, value=0,
)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# שלב 5 – סיכון בטיחותי
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### ⚠️ סיכון בטיחותי")

safety_risks = st.multiselect(
    "סמן את כל מה שרלוונטי:",
    options=[
        "פציעות גופניות בגלל התקפים (נפילות, חבלות)",
        "סטטוס אפילפטיקוס בעבר (התקף ממושך > 5 דקות)",
        "אשפוז דחוף בגלל התקפים ב-12 החודשים האחרונים",
        "נהיגה / עבודה בסיכון בשל ההתקפים",
    ],
)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# שלב 6 – לוגיסטיקה
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📅 לוגיסטיקה")

col_a, col_b = st.columns(2)
with col_a:
    short_notice = st.checkbox(
        "✅ זמין להגעה בהתראה קצרה (מהיום למחר)",
        help="במידה ויש ביטול, ניצור קשר."
    )
with col_b:
    prev_rambam = st.checkbox(
        "🏥 ביצעתי בדיקת EEG קודמת ברמב\"ם",
    )

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# כפתור שליחה
# ═══════════════════════════════════════════════════════════════════════════════
col_btn, col_warn = st.columns([1, 3])
with col_btn:
    submit_btn = st.button("📤 שלח שאלון", type="primary", use_container_width=True)
with col_warn:
    if not api_key:
        st.warning("⬅️ הכנס Groq API Key ב-Sidebar", icon="⚠️")

# ═══════════════════════════════════════════════════════════════════════════════
# ניתוח ותוצאות
# ═══════════════════════════════════════════════════════════════════════════════
if submit_btn:
    # ── ולידציה בסיסית ────────────────────────────────────────────────────────
    errors = []
    if not patient_name.strip():
        errors.append("חסר שם מטופל.")
    if not referral_purpose:
        errors.append("יש לבחור מטרת הפניה.")
    if not api_key:
        errors.append("חסר Groq API Key.")

    if errors:
        for e in errors:
            st.error(e)
        st.stop()

    # ── בניית תקציר השאלון לשליחה למודל ──────────────────────────────────────
    days_since = None
    if last_seizure:
        days_since = (date.today() - last_seizure).days

    questionnaire_summary = f"""
נתוני שאלון מטופל:
- שם: {patient_name}
- גיל: {patient_age if patient_age else 'לא צוין'}
- מין: {patient_gender}
- מטרת הפניה: {referral_purpose}{(' – ' + referral_other) if referral_other else ''}
- תדירות התקפים: {seizure_frequency}
- תאריך התקף אחרון: {last_seizure if last_seizure else 'לא צוין'}{f' (לפני {days_since} ימים)' if days_since is not None else ''}
- סוגי התקפים: {', '.join(seizure_type) if seizure_type else 'לא צוין'}
- תרופות נוכחיות: {current_meds_count}
- תרופות שנוסו בסך הכל: {total_meds_tried}
- סיכוני בטיחות: {', '.join(safety_risks) if safety_risks else 'ללא'}
- זמינות מהיום למחר: {'כן' if short_notice else 'לא'}
- בדיקה קודמת ברמב"ם: {'כן' if prev_rambam else 'לא'}
"""

    with st.spinner("מנתח שאלון ומחשב ציון דחיפות..."):
        try:
            client = Groq(api_key=api_key)
            completion = client.chat.completions.create(
                model=model_choice,
                max_tokens=1024,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": questionnaire_summary},
                ],
            )
            raw = completion.choices[0].message.content.strip()

            # ניקוי חזק – מוצא את ה-JSON גם אם יש טקסט סביבו
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)
            else:
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

            result = json.loads(raw)

        except json.JSONDecodeError:
            st.error("שגיאה: המודל לא החזיר JSON תקין. נסה שוב.")
            st.code(raw, language="text")
            st.stop()
        except AuthenticationError:
            st.error("מפתח API שגוי. בדוק ב-console.groq.com")
            st.stop()
        except Exception as e:
            st.error(f"שגיאה: {e}")
            st.stop()

    # ── הצגת תוצאות ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown("## 📋 סיכום טריאז'")

    score = int(result.get("urgency_score", 0))
    if score <= 3:
        css_class, emoji = "score-low", "🟢"
    elif score <= 6:
        css_class, emoji = "score-mid", "🟡"
    else:
        css_class, emoji = "score-high", "🔴"

    # כרטיס ציון
    avail_html = '<span class="avail-badge">✅ זמין מהיום למחר</span>' if short_notice else ""
    rambam_html = '<span style="font-size:13px; color:#555; margin-right:10px;">🏥 בדיקה קודמת ברמב"ם</span>' if prev_rambam else ""

    st.markdown(f"""
    <div class="score-card {css_class}">
        <h2 style="margin:0;">{emoji} ציון דחיפות: {score}/10</h2>
        <p style="margin:6px 0 2px; font-size:16px; font-weight:600;">{result.get('score_label','')}</p>
        <p style="margin:4px 0 8px; font-size:14px; opacity:.85;">{result.get('patient_summary','')}</p>
        {avail_html}{rambam_html}
    </div>
    """, unsafe_allow_html=True)

    # מטריקות
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("תדירות", seizure_frequency.split(" ")[0] + ("..." if len(seizure_frequency) > 8 else seizure_frequency[8:]))
    m2.metric("תרופות נוכחיות", current_meds_count)
    m3.metric("תרופות שנוסו", total_meds_tried)
    m4.metric("ימים מהתקף אחרון", days_since if days_since is not None else "?")

    st.divider()

    # נקודות קליניות
    highlights = result.get("clinical_highlights", [])
    if highlights:
        st.subheader("🔍 ממצאים קליניים מרכזיים")
        for h in highlights:
            st.markdown(f"- {h}")

    st.subheader("📝 הנמקה קלינית")
    st.warning(result.get("clinical_justification", ""))

    logistics = result.get("logistics_note", "")
    if logistics:
        st.subheader("📌 הערה למזכירות")
        st.info(logistics)

    # JSON גולמי
    with st.expander("📄 הצג JSON גולמי"):
        st.json(result)

    # הורדה
    export_data = {
        "patient_name": patient_name,
        "patient_id": patient_id,
        "questionnaire": {
            "referral_purpose": referral_purpose,
            "seizure_frequency": seizure_frequency,
            "last_seizure": str(last_seizure) if last_seizure else None,
            "seizure_type": seizure_type,
            "current_meds": current_meds_count,
            "total_meds_tried": total_meds_tried,
            "safety_risks": safety_risks,
            "short_notice_available": short_notice,
            "prev_rambam": prev_rambam,
        },
        "triage_result": result,
    }
    st.download_button(
        label="⬇️ הורד דוח JSON",
        data=json.dumps(export_data, ensure_ascii=False, indent=2),
        file_name=f"veeg_triage_{patient_name.replace(' ','_')}.json",
        mime="application/json",
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("כלי זה הוא עזר בלבד ואינו מחליף שיקול דעת רפואי.")
