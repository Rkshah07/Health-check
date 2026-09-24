import os
import json
from groq import Groq

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        return Groq(api_key=api_key)
    except Exception:
        return None

def explain_risk(payload: dict) -> dict:
    client = get_groq_client()
    if not client:
        raise Exception("Groq client not configured or API key missing.")

    prompt = f"""You are a healthcare explanation assistant inside a clinical decision-support visualization.
Your job is ONLY to explain an existing machine-learning readmission-risk prediction in simple language.
You are NOT a doctor.
You must NOT:
- diagnose diseases
- prescribe medication
- recommend changing medication
- recommend starting or stopping treatment
- invent laboratory abnormalities
- invent patient history
- change the model's risk probability
- change the model's risk category
- claim that a factor caused readmission
- make unsupported medical claims

The provided prediction and model contribution values come from another machine-learning model. Treat them as fixed facts.
Explain what the model output means.
For every important factor provide:
1. A simple explanation.
2. Why the model may have considered it influential.
3. A safe topic to discuss with a healthcare professional.

Use phrases such as:
- 'The model estimates...'
- 'This factor had a strong influence on the model prediction.'
- 'This may be worth discussing with your healthcare team.'
- 'The model does not establish that this factor caused the risk.'

Do not use:
- 'You have...'
- 'You should take...'
- 'You need this medicine...'
- 'Stop your medicine...'
- 'This will prevent readmission...'

If a factor is a laboratory value, do not interpret it as normal/abnormal unless an appropriate reference range is explicitly provided.
If a factor is age, explain that it is a model input and not something that can be changed.
If a factor is previous admissions, suggest reviewing recent admission history and follow-up planning.
If a factor is length of stay, suggest discussing the recent hospitalization and discharge/follow-up plan.
If a factor is medication count, suggest medication reconciliation/review with a healthcare professional rather than recommending medication changes.
If information is insufficient, explicitly say that the information is insufficient rather than inventing an answer.
Keep the explanation concise, clear and understandable to a non-technical user.

INPUT DATA:
{json.dumps(payload, indent=2)}

You MUST return a valid JSON object matching this schema exactly:
{{
  "summary": "The model estimates a X% probability...",
  "important_factors": [
    {{
      "factor": "name of factor",
      "influence": "strong | moderate | lower | minimal",
      "explanation": "Simple explanation of the factor's influence.",
      "discussion_point": "Safe topic to discuss with care team."
    }}
  ],
  "next_steps": [ "Step 1", "Step 2" ],
  "questions_for_care_team": [ "Question 1", "Question 2" ],
  "disclaimer": "This explanation describes model behavior and is not a diagnosis or treatment recommendation."
}}
"""
    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

def chat_risk(payload: dict) -> str:
    client = get_groq_client()
    if not client:
        raise Exception("Groq client not configured or API key missing.")

    messages_history = payload.get("messages", [])
    if not messages_history:
        return "No message provided."

    last_user_message = messages_history[-1]["content"]

    # STEP 1: Health Topic Check
    check_prompt = f"""You are a strict guardrail classifier. 
Determine if the following user query is related to healthcare, clinical data, medical conditions, or explaining a patient's readmission risk.
Reply ONLY with the exact word 'YES' if it is related, or 'NO' if it is unrelated (e.g. asking about programming, general knowledge, or weather).

User Query: "{last_user_message}"
"""
    check_response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": check_prompt}],
    )
    
    classification = check_response.choices[0].message.content.strip().upper()
    if "NO" in classification and "YES" not in classification:
        return "I can only answer healthcare related questions."

    # STEP 2: Health AI Response
    patient_data = payload.get("patient", {})
    prediction = payload.get("prediction", {})
    risk_factors = payload.get("risk_factors", [])

    system_prompt = f"""You are a helpful healthcare explanation AI assistant inside a clinical dashboard.
You are helping the user (who might be a clinician or patient) understand a machine-learning readmission-risk prediction.
You are NOT a doctor. DO NOT diagnose, prescribe, or give medical advice.
Always remind the user to consult their healthcare team for medical decisions.
If the user asks something completely unrelated to healthcare, refuse to answer.

Context Data:
Patient Data: {json.dumps(patient_data)}
Model Prediction: {json.dumps(prediction)}
Risk Factors: {json.dumps(risk_factors)}

Answer the user's questions clearly, concisely, and safely based ONLY on this context."""

    api_messages = [{"role": "system", "content": system_prompt}]
    for m in messages_history:
        api_messages.append({"role": m["role"], "content": m["content"]})

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=api_messages,
    )
    
    return response.choices[0].message.content
