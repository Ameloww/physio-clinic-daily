import streamlit as st
import google.generativeai as genai
from docxtpl import DocxTemplate
from io import BytesIO
import json
import re

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="USM Physio Clinic", page_icon="🏥", layout="centered")

st.title("🏥 Daily Physio Report AI")
st.caption("USM Sports & Recreation Centre - Clinical Documentation System")
st.markdown("---")

# --- AUTO DETECT API KEY ---
api_key = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.sidebar.header("⚙️ Settings")
    api_key = st.sidebar.text_input("Enter Gemini API Key:", type="password")

# --- CASE TYPE SELECTION ---
st.subheader("📌 Step 1: Select Case Type")
case_type = st.radio(
    "Choose assessment type:",
    ["🆕 New Case (Full Assessment)", "🔄 Follow-Up / Summary"],
    horizontal=True
)

st.markdown("---")

# --- PROMPT SYSTEM FOR NEW CASE ---
PROMPT_NEW_CASE = """
You are a Lead Sports Physiotherapist at USM Sports & Recreation Centre.
Analyze the audio recording of a NEW PATIENT ASSESSMENT and extract information into structured JSON.

INSTRUCTIONS:
1. CONVERT all extracted notes into formal, professional Clinical English.
2. Use standard physiotherapy terms (e.g., NPRS, ROM, MMT, anatomical landmarks).
3. If detail is missing, put "Not specified".

CRITICAL: Output ONLY a valid JSON object matching these exact keys:
{
    "name": "[Patient Name]",
    "id_num": "[Matrix or Staff Number]",
    "age": "[Age]",
    "gender": "[Gender]",
    "date": "[Date of Assessment]",
    "diagnosis": "[Doctor Diagnosis]",
    "therapist": "[In-Charge Physiotherapist]",
    "complaint": "[Presenting Problem / Patient Complaint]",
    "pain_scale": "[Pain Rating 1-10]",
    "area": "[Pain Area]",
    "nature": "[Pain Nature e.g., Sharp, Dull, Aching]",
    "aggravating": "[Aggravating Factors]",
    "easing": "[Easing Factors]",
    "twenty_four_hours": "[24 Hours Pain Pattern]",
    "irritability": "[Irritability: High / Medium / Low]",
    "history": "[Current / Past History of Injury]",
    "gen_health": "[General Health]",
    "pmh_surgery": "[Past Medical History / Surgeries]",
    "radiology": "[MRI / X-Ray Findings]",
    "medication": "[Medication / Steroid Intake]",
    "occupation": "[Occupation]",
    "social_hx": "[Social History / Sports Activity]",
    "observation": "[Visual Inspection & Posture]",
    "palpation": "[Palpation & Muscle Texture]",
    "rom": "[Range of Motion]",
    "muscle_power": "[Muscle Power / Strength]",
    "joint_circ": "[Joint Circumference Measurements]",
    "special_test": "[Special Tests Findings]",
    "pain_mgmt": "[Pain Management Plan]",
    "exercise_rx": "[Exercise Therapy & Plan]"
}
"""

# --- PROMPT SYSTEM FOR FOLLOW-UP ---
PROMPT_FOLLOWUP = """
You are a Lead Sports Physiotherapist at USM Sports & Recreation Centre.
Analyze the audio recording of a FOLLOW-UP PATIENT SESSION and extract information into structured JSON.

INSTRUCTIONS:
1. CONVERT all extracted notes into formal, professional Clinical English.
2. Use standard physiotherapy terms (e.g., NPRS, ROM, MMT).
3. If detail is missing, put "Not specified".

CRITICAL: Output ONLY a valid JSON object matching these exact keys:
{
    "name": "[Patient Name]",
    "date": "[Date of Visit]",
    "complaint": "[Patient Complaint / Current Symptoms]",
    "pain_scale": "[Pain Scale 1-10]",
    "observation": "[Observation / Palpation Findings]",
    "rom": "[Range of Motion]",
    "mmt": "[Manual Muscle Testing / Strength]",
    "others": "[Other Special Tests / Findings]",
    "intervention": "[Intervention / Modalities Provided]",
    "evaluation": "[Re-evaluation After Treatment]",
    "review": "[Review Plan / Follow-up Date]"
}
"""

# --- DYNAMIC CHECKLIST DISPLAY ---
st.subheader("🎙️ Step 2: Record Voice Note")

if case_type == "🆕 New Case (Full Assessment)":
    with st.expander("💡 **Voice Checklist: NEW CASE (Full Assessment)**", expanded=True):
        st.markdown("""
        * **1. Patient Info:** Name, Matrix/Staff No, Age, Gender, Date, Doctor Diagnosis, Physio Name
        * **2. Subjective & Pain:** Complaint, Pain Scale (1-10), Area, Nature, Aggravating & Easing Factors, 24-hr Pattern, Irritability (High/Med/Low), Injury History
        * **3. Special Questions:** General Health, Surgery Hx, MRI/X-Ray, Medication, Occupation, Social Hx
        * **4. Physical Exam:** Observation, Palpation, ROM, Muscle Power, Joint Circumference, Special Tests
        * **5. Treatment Plan:** Pain Management Plan, Exercise Therapy
        """)
else:
    with st.expander("💡 **Voice Checklist: FOLLOW-UP SESSION**", expanded=True):
        st.markdown("""
        * **1. Basic Info:** Patient Name, Date
        * **2. Status Today:** Patient Complaint, Pain Scale (1-10)
        * **3. Objective Exam:** Observation/Palpation, ROM, MMT, Others (Special Tests)
        * **4. Treatment & Progress:** Intervention Administered, Evaluation (Re-assessment), Review Plan / Next Appointment
        """)

audio_input = st.audio_input("Tap microphone to start recording:")

if audio_input:
    if not api_key:
        st.error("⚠️ API Key missing! Configure GEMINI_API_KEY in Streamlit Secrets.")
    else:
        st.success("✅ Voice recording captured!")
        
        btn_label = "✨ Generate New Case Report (.docx)" if case_type == "🆕 New Case (Full Assessment)" else "✨ Generate Follow-up Report (.docx)"
        
        if st.button(btn_label, type="primary"):
            with st.spinner("AI is analyzing and synthesizing clinical documentation..."):
                try:
                    genai.configure(api_key=api_key)
                    audio_bytes = audio_input.getvalue() if hasattr(audio_input, "getvalue") else audio_input.read()
                    mime_type = getattr(audio_input, "type", "audio/wav") or "audio/wav"
                    
                    # Choose Prompt & Template File based on Case Type
                    if case_type == "🆕 New Case (Full Assessment)":
                        active_prompt = PROMPT_NEW_CASE
                        template_file = "template_newcase.docx"
                        output_filename = "NewCase_Assessment_Report.docx"
                    else:
                        active_prompt = PROMPT_FOLLOWUP
                        template_file = "template_followup.docx"
                        output_filename = "FollowUp_Clinical_Report.docx"
                    
                    # Model selector
                    all_models = [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
                    valid_models = [m for m in all_models if "2.5" not in m and "1.0" not in m and "pro" not in m]
                    valid_models.sort(key=lambda x: ("2.0" in x, "flash" in x), reverse=True)
                    
                    if not valid_models:
                        valid_models = ["gemini-2.0-flash", "models/gemini-2.0-flash"]
                    
                    response = None
                    last_error = None
                    
                    for m_name in valid_models:
                        try:
                            model = genai.GenerativeModel(m_name)
                            response = model.generate_content([
                                active_prompt,
                                {"mime_type": mime_type, "data": audio_bytes}
                            ])
                            if response and response.text:
                                break
                        except Exception as e:
                            last_error = e
                            continue
                            
                    if not response:
                        raise last_error or Exception("Failed to get response from AI.")
                    
                    raw_text = response.text
                    clean_json = re.sub(r'```json|```', '', raw_text).strip()
                    patient_data = json.loads(clean_json)
                    
                    st.markdown("---")
                    st.subheader("📋 Clinical Assessment Preview")
                    st.json(patient_data)
                    
                    # Render Word Document
                    doc = DocxTemplate(template_file)
                    doc.render(patient_data)
                    
                    buffer = BytesIO()
                    doc.save(buffer)
                    buffer.seek(0)
                    
                    st.markdown("---")
                    st.subheader("📥 Step 3: Download Document")
                    st.download_button(
                        label=f"📄 Download {output_filename}",
                        data=buffer,
                        file_name=output_filename,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                    st.balloons()
                    
                except FileNotFoundError:
                    st.error(f"❌ Error: File '{template_file}' not found in GitHub repository. Please upload it.")
                except json.JSONDecodeError:
                    st.error("❌ Error: AI failed to parse JSON structure. Please re-record audio clearly.")
                except Exception as e:
                    st.error(f"System Error: {e}")
