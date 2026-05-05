"""
VEEG Triage App - ניתוח הפניות לבדיקת וידאו-EEG
מופעל על ידי Groq Cloud
הרץ עם: streamlit run veeg_triage_app.py
"""

import streamlit as st
from groq import Groq, AuthenticationError
import json

# ── הגדרות עמוד ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VEEG Triage",
    page_icon="🧠",
    layout="centered",
)

# ── כותרת ────────────────────────────────────────────────────────────────────
st.title("🧠 VEEG Triage – ניתוח הפניות")
st.caption("מופעל על ידי Groq Cloud | הדבק טקסט הפניה ← קבל ציון דחיפות קליני + JSON מובנה")
st.divider()

# ── הגדרת ה-Prompt למודל ──────────────────────────────────────────────────────
SYSTEM_PROMPT = """
אתה עוזר רפואי מומחה בתחום האפילפסיה והנוירופיזיולוגיה הקלינית.
תפקידך לנתח הפניות רפואיות ליחידת וידאו-EEG ולבצע טריאז' על בסיס נתונים קליניים.

קריטריונים לתיעדוף:
1. תדירות התקפים: תדירות יומית מעלה דחיפות.
2. עמידות תרופתית: כישלון ≥2 AEDs = חשד לאפילפסיה עמידה.
3. מטרת הבדיקה: אבחנה מבדלת דחופה / סטטוס נון-קונבולסיבי / הערכה טרום-ניתוחית -> דחיפות גבוהה.
4. סיכון בטיחותי: פציעות, drop attacks, סטטוס אפילפטיקוס בעבר.

החזר JSON בלבד, ללא backticks וללא טקסט נוסף:
{
  "patient_summary": "...",
  "seizure_frequency": "...",
  "medications_count": <מספר>,
  "seizure_type": "...",
  "monitoring_reason": "...",
  "urgency_score": <1-10>,
  "clinical_justification": "..."
}
אם חסר מידע קריטי, ציין זאת ב-clinical_justification וקבע ציון שמרני.
"""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ הגדרות")

    api_key = st.text_input(
        "Groq API Key",
        type="password",
        placeholder="gsk_...",
        help="קבל מפתח חינמי בכתובת: console.groq.com",
    )

    model_choice = st.selectbox(
        "מודל",
        options=[
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
        ],
        help="llama-3.3-70b מומלץ לדיוק קליני. llama-3.1-8b מהיר יותר.",
    )

    st.info("המפתח נשמר רק בזיכרון הסשן, לא מועלה לשרת.", icon="🔒")
    st.divider()
    st.markdown("**מדריך הציון:**")
    st.markdown("🟢 1–3 — דחיפות נמוכה")
    st.markdown("🟡 4–6 — דחיפות בינונית")
    st.markdown("🔴 7–10 — דחיפות גבוהה")

# ── תיבת הפניה ───────────────────────────────────────────────────────────────
referral_text = st.text_area(
    "📋 טקסט ההפניה",
    height=200,
    placeholder="""דוגמה:
חולה בת 34, אפילפסיה מגיל 12. התקפים מוקדיים עם הכללה משנית.
ניסינו קרבמזפין ולמוטריג'ין ללא שיפור. כ-3 התקפים בשבוע.
רוצה להעריך לקראת ניתוח.""",
)

# ── כפתור ניתוח ──────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 3])
with col1:
    analyze_btn = st.button("🔍 נתח הפניה", type="primary", use_container_width=True)
with col2:
    if not api_key:
        st.warning("⬅️ הכנס Groq API Key ב-Sidebar תחילה", icon="⚠️")

# ── לוגיקת ניתוח ─────────────────────────────────────────────────────────────
if analyze_btn:
    if not api_key:
        st.error("חסר API Key – הזן אותו ב-Sidebar.")
    elif not referral_text.strip():
        st.error("אנא הכנס טקסט הפניה.")
    else:
        with st.spinner(f"מנתח הפניה עם {model_choice}..."):
            try:
                client = Groq(api_key=api_key)

                completion = client.chat.completions.create(
                    model=model_choice,
                    max_tokens=1024,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": referral_text},
                    ],
                )

                raw = completion.choices[0].message.content.strip()
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                result = json.loads(raw)

            except json.JSONDecodeError:
                st.error("שגיאה: המודל לא החזיר JSON תקין. נסה שוב.")
                st.code(raw, language="text")
                st.stop()
            except AuthenticationError:
                st.error("מפתח API שגוי. בדוק את המפתח ב-console.groq.com")
                st.stop()
            except Exception as e:
                st.error(f"שגיאה: {e}")
                st.stop()

        # ── הצגת תוצאות ──────────────────────────────────────────────────────
        st.divider()
        score = int(result.get("urgency_score", 0))

        if score <= 3:
            color, label, emoji = "green", "דחיפות נמוכה", "🟢"
        elif score <= 6:
            color, label, emoji = "orange", "דחיפות בינונית", "🟡"
        else:
            color, label, emoji = "red", "דחיפות גבוהה", "🔴"

        st.markdown(
            f"""
            <div style="background:#f8f9fa; border-left: 6px solid {color};
                        border-radius:8px; padding:16px 20px; margin-bottom:16px;">
                <h2 style="margin:0; color:{color};">{emoji} {score}/10 — {label}</h2>
                <p style="margin:6px 0 0; color:#444;">{result.get('patient_summary', '')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("תדירות", result.get("seizure_frequency", "לא צוין"))
        m2.metric("מספר תרופות", result.get("medications_count", "?"))
        m3.metric("סוג התקף", result.get("seizure_type", "לא צוין"))
        m4.metric("ציון דחיפות", f"{score}/10")

        st.divider()

        st.subheader("מטרת הניטור")
        st.info(result.get("monitoring_reason", "לא צוין"))

        st.subheader("הנמקה קלינית")
        st.warning(result.get("clinical_justification", ""))

        with st.expander("📄 הצג JSON גולמי"):
            st.json(result)

        st.download_button(
            label="⬇️ הורד JSON",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name="veeg_triage_result.json",
            mime="application/json",
        )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("כלי זה הוא עזר בלבד ואינו מחליף שיקול דעת רפואי.")
