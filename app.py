import streamlit as st
import google.generativeai as genai
from docxtpl import DocxTemplate
from io import BytesIO
import json
import re

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="USM Physio Clinic", page_icon="🏥", layout="centered")

st.title("🏥 Daily Physio Report AI")
st.caption("USM Sports & Recreation Centre - Smart Clinical Documentation")
st.markdown("---")

# --- AUTO DETECT API KEY ---
api_key = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.sidebar.header("⚙️ Settings")
    api_key = st.sidebar.text_input("Enter Gemini API Key:", type="password")

# --- INITIALIZE SESSION STATE FOR EDITABLE FORM ---
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = None
if "active_case_type" not in st.session_state:
    st.session_state.active_case_type = None

# --- CASE TYPE SELECTION ---
st.subheader("📌 Step 1: Select Case Type")
case_type = st.radio(
    "Choose assessment type:",
    ["🆕 New Case (Full Assessment)", "🔄 Follow-Up / Summary"],
    horizontal=True
)

st.markdown("---")

# --- PROMPTS ---
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
    "review": "[Review Plan / Follow-up Date]",
    "attending therapist": "[Physiotherapist Name]"
}
"""

# --- VOICE CHECKLIST ---
st.subheader("🎙️ Step 2: Record Voice Note")

if case_type == "🆕 New Case (Full Assessment)":
    with st.expander("💡 **Voice Checklist: NEW CASE (Full Assessment)**", expanded=True):
        st.markdown("""
        * **1. Patient Info:** Name, Matrix/Staff No, Age, Gender, Date, Doctor Diagnosis, Physio Name
        * **2. Subjective & Pain:** Complaint, Pain Scale (1-10), Area, Nature, Aggravating/Easing Factors, 24-hr Pattern, Irritability, History
        * **3. Special Questions:** General Health, Surgery Hx, Radiology, Medication, Occupation, Social Hx
        * **4. Objective Exam:** Observation, Palpation, ROM, Muscle Power, Joint Circumference, Special Tests
        * **5. Treatment Plan:** Pain Management, Exercise Therapy
        """)
else:
    with st.expander("💡 **Voice Checklist: FOLLOW-UP SESSION**", expanded=True):
        st.markdown("""
        * **1. Basic Info:** Patient Name, Date, Attending Therapist Name
        * **2. Status Today:** Complaint, Pain Scale (1-10)
        * **3. Objective Exam:** Observation/Palpation, ROM, MMT, Others
        * **4. Progress & Plan:** Intervention Given, Evaluation, Review Plan
        """)

audio_input = st.audio_input("Tap microphone to start recording:")

if audio_input:
    if not api_key:
        st.error("⚠️ API Key missing! Configure GEMINI_API_KEY in Streamlit Secrets.")
    else:
        st.success("✅ Voice recording captured!")
        
        if st.button("🧠 Process Audio with AI", type="primary"):
            with st.spinner("AI is analyzing and synthesizing clinical data..."):
                try:
                    genai.configure(api_key=api_key)
                    audio_bytes = audio_input.getvalue() if hasattr(audio_input, "getvalue") else audio_input.read()
                    mime_type = getattr(audio_input, "type", "audio/wav") or "audio/wav"
                    
                    active_prompt = PROMPT_NEW_CASE if case_type == "🆕 New Case (Full Assessment)" else PROMPT_FOLLOWUP
                    
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
                    
                    st.session_state.extracted_data = json.loads(clean_json)
                    st.session_state.active_case_type = case_type
                    st.toast("🎉 AI Processing Complete! Scroll down to review & edit.")
                    
                except json.JSONDecodeError:
                    st.error("❌ AI failed to format JSON correctly. Please re-record audio clearly.")
                except Exception as e:
                    st.error(f"System Error: {e}")

# --- EDITABLE FORM SECTION ---
if st.session_state.extracted_data is not None:
    st.markdown("---")
    st.subheader("✏️ Step 3: Review & Edit Clinical Summary")
    st.info("💡 You can edit any field below before generating the final Word document.")
    
    data = st.session_state.extracted_data
    edited_data = {}
    
    # ------------------ FORM FOR NEW CASE ------------------
    if st.session_state.active_case_type == "🆕 New Case (Full Assessment)":
        st.markdown("### 👤 Patient Demographics")
        col1, col2 = st.columns(2)
        with col1:
            edited_data["name"] = st.text_input("Patient Name", data.get("name", ""))
            edited_data["id_num"] = st.text_input("Matrix / Staff No", data.get("id_num", ""))
            edited_data["age"] = st.text_input("Age", data.get("age", ""))
            edited_data["gender"] = st.text_input("Gender", data.get("gender", ""))
        with col2:
            edited_data["date"] = st.text_input("Assessment Date", data.get("date", ""))
            edited_data["diagnosis"] = st.text_input("Doctor Diagnosis", data.get("diagnosis", ""))
            edited_data["therapist"] = st.text_input("In-Charge Therapist", data.get("therapist", ""))

        st.markdown("### 🗣️ Subjective & Pain Assessment")
        edited_data["complaint"] = st.text_area("Patient Complaint", data.get("complaint", ""), height=70)
        col3, col4 = st.columns(2)
        with col3:
            edited_data["pain_scale"] = st.text_input("Pain Scale (NPRS)", data.get("pain_scale", ""))
            edited_data["area"] = st.text_input("Pain Area", data.get("area", ""))
            edited_data["nature"] = st.text_input("Pain Nature", data.get("nature", ""))
            edited_data["twenty_four_hours"] = st.text_input("24-Hour Pattern", data.get("twenty_four_hours", ""))
        with col4:
            edited_data["aggravating"] = st.text_input("Aggravating Factors", data.get("aggravating", ""))
            edited_data["easing"] = st.text_input("Easing Factors", data.get("easing", ""))
            edited_data["irritability"] = st.text_input("Irritability Level", data.get("irritability", ""))
        edited_data["history"] = st.text_area("Current / Past History", data.get("history", ""), height=70)

        st.markdown("### 🔍 Medical & Social History")
        col5, col6 = st.columns(2)
        with col5:
            edited_data["gen_health"] = st.text_input("General Health", data.get("gen_health", ""))
            edited_data["pmh_surgery"] = st.text_input("Past Medical / Surgery Hx", data.get("pmh_surgery", ""))
            edited_data["radiology"] = st.text_input("Radiology (MRI/X-Ray)", data.get("radiology", ""))
        with col6:
            edited_data["medication"] = st.text_input("Medication / Steroid", data.get("medication", ""))
            edited_data["occupation"] = st.text_input("Occupation", data.get("occupation", ""))
            edited_data["social_hx"] = st.text_input("Social / Sports History", data.get("social_hx", ""))

        st.markdown("### 🔬 Physical Examination (Objective)")
        edited_data["observation"] = st.text_area("Observation", data.get("observation", ""), height=70)
        edited_data["palpation"] = st.text_area("Palpation", data.get("palpation", ""), height=70)
        col7, col8 = st.columns(2)
        with col7:
            edited_data["rom"] = st.text_area("Range of Motion (ROM)", data.get("rom", ""), height=70)
            edited_data["joint_circ"] = st.text_area("Joint Circumference", data.get("joint_circ", ""), height=70)
        with col8:
            edited_data["muscle_power"] = st.text_area("Muscle Power (MMT)", data.get("muscle_power", ""), height=70)
            edited_data["special_test"] = st.text_area("Special Tests", data.get("special_test", ""), height=70)

        st.markdown("### 🩹 Plan of Treatment")
        edited_data["pain_mgmt"] = st.text_area("Pain Management Plan", data.get("pain_mgmt", ""), height=70)
        edited_data["exercise_rx"] = st.text_area("Exercise Therapy Plan", data.get("exercise_rx", ""), height=70)

        template_file = "template_newcase.docx"
        out_filename = f"NewCase_{edited_data['name'].replace(' ', '_')}.docx"

    # ------------------ FORM FOR FOLLOW-UP ------------------
    else:
        col1, col2 = st.columns(2)
        with col1:
            edited_data["name"] = st.text_input("Patient Name", data.get("name", ""))
            edited_data["complaint"] = st.text_area("Patient Complaint", data.get("complaint", ""), height=70)
            edited_data["observation"] = st.text_area("Observation / Palpation", data.get("observation", ""), height=70)
            edited_data["mmt"] = st.text_area("MMT / Strength", data.get("mmt", ""), height=70)
            edited_data["intervention"] = st.text_area("Intervention Given", data.get("intervention", ""), height=70)
        with col2:
            edited_data["date"] = st.text_input("Assessment Date", data.get("date", ""))
            edited_data["pain_scale"] = st.text_input("Pain Scale (NPRS)", data.get("pain_scale", ""))
            edited_data["rom"] = st.text_area("Range of Motion (ROM)", data.get("rom", ""), height=70)
            edited_data["others"] = st.text_area("Others / Special Tests", data.get("others", ""), height=70)
            edited_data["evaluation"] = st.text_area("Post-Treatment Evaluation", data.get("evaluation", ""), height=70)
        
        col3, col4 = st.columns(2)
        with col3:
            edited_data["review"] = st.text_input("Review Plan / Next Follow-up", data.get("review", ""))
        with col4:
            edited_data["attending therapist"] = st.text_input(
                "Attending Therapist", 
                data.get("attending therapist", data.get("attending_therapist", ""))
            )

        template_file = "template_followup.docx"
        out_filename = f"FollowUp_{edited_data['name'].replace(' ', '_')}.docx"

    st.markdown("---")
    st.subheader("📥 Step 4: Download Formatted Word Report")
    
    if st.button("📄 Generate & Download Word Document (.docx)", type="primary"):
        try:
            doc = DocxTemplate(template_file)
            doc.render(edited_data)
            
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            st.download_button(
                label=f"⬇️ Click Here to Download ({out_filename})",
                data=buffer,
                file_name=out_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            st.balloons()
            st.success("✅ Report generated successfully with your edited entries!")
        except FileNotFoundError:
            st.error(f"❌ Error: File '{template_file}' not found in GitHub repository.")
        except Exception as e:
            st.error(f"System Error: {e}")
