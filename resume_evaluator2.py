import os
import json
from pathlib import Path
import time
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from pypdf import PdfReader
from docx import Document

# --- Setup and Authentication ---
load_dotenv()
my_api_key = os.getenv("GROQ_API_KEY")

if not my_api_key:
    raise ValueError("GROQ_API_KEY is not fetchable.")

client = Groq(api_key=my_api_key)
model = "openai/gpt-oss-120b"

# --- Define Pydantic Models (Schemas) ---
class JobD(BaseModel):
    role: str
    required_technical_skills: list[str] = []
    required_soft_skills: list[str] = []
    preferred_skills: list[str] = []
    minimum_experience: float | None = None
    education_requirements: list[str] = []
    responsibilities: list[str] = []

class Experience(BaseModel):
    company: str | None = None
    role: str | None = None
    duration: str | None = None
    description: str | list[str] | None = None
    skills_used: list[str] = []

class Resume(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    total_experience: float | None = None
    skills: list[str] = []
    experience: list[Experience] = []
    project: list[str] = []   
    certifications: list[str] = []

# This is how MatchDetails is used! It forces the LLM to use these exact keys.
class MatchDetails(BaseModel):
    candidate_name: str
    matching_technical_skills: list[str] = []
    matching_soft_skills: list[str] = []
    missing_critical_skills: list[str] = []
    experience_requirement_met: bool | str
    overall_match_percentage: float
    final_verdict: str

# Nest MatchDetails inside MatchResult
class MatchResult(BaseModel):
    score: float
    details: MatchDetails

# --- Helper Functions ---
def parse_resume(resume_text):
    resume_schema = Resume.model_json_schema()
    system_prompt = f"""
    You are a expert resume parser.
    Extract information from the resume based on its meaning, not only based on exact headings.
    Different resumes may use different headings (e.g., Work History, Internships, Employment).
    
    Return only valid JSON matching schema:
    {resume_schema}

    Important rules:
    1. Do not invent information.
    2. If a value is not available return null.
    3. If a list has no information return an empty list.
    4. Include internships inside Experiences.
    5. Extract skills mentioned in the entire resume.
    """
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Parse the following resume : {resume_text}"}
    ]
    
    response = client.chat.completions.create(
        model=model, 
        messages=messages, 
        response_format={"type": "json_object"}
    )
    
    data = json.loads(response.choices[0].message.content)
    return Resume(**data)

def read_pdf(file_path):
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + '\n'
    return text

def read_docs(file_path):
    reader = Document(file_path)
    text = ""
    for paragraph in reader.paragraphs:
        if paragraph.text.strip():
            text += paragraph.text + "\n"

    for table in reader.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    text += cell.text + "\n"
    return text

def read_resume(file_path):
    if file_path.suffix.lower() == ".pdf":
        return read_pdf(file_path)
    elif file_path.suffix.lower() == ".docx": # Removed .doc to prevent crashes
        return read_docs(file_path)
    else:
        return None

def final_score(job, resume):
    match_schema = MatchResult.model_json_schema()
    prompt = f"""
    You are a highly accurate technical recruiter. Compare the job description with the provided resume.

    EVALUATION RULES:
    1. Technical Skills (Strict): Scan the entire resume for required_technical_skills. Treat synonyms as matches (e.g., "AWS Cloud" = "AWS"). 
    2. Soft Skills (Inferred): Do not require exact keyword matches for required_soft_skills. If a candidate successfully built complex systems, optimized workflows, or collaborated on cross-functional teams, award them matches for "problem-solving," "analytical thinking," or "teamwork" respectively.
    3. Experience: Academic projects and student clubs do not count as Enterprise/Professional Experience unless the JD allows for freshers/interns.

    JOB DESCRIPTION: {job.model_dump_json(indent=2)}
    RESUME: {resume.model_dump_json(indent=2)}
    
    Return your response strictly as a JSON object matching this schema:
    {match_schema}
    """
    
    messages = [{"role": "user", "content": prompt}]
    
    response = client.chat.completions.create(
        model=model, 
        messages=messages, 
        response_format={"type": "json_object"}
    )
    
    data = json.loads(response.choices[0].message.content)
    return MatchResult(**data)

# --- Main Execution Block ---
def main():
    job_description= """About the job
🤖 Machine Learning InternCompany: Nexal IITLocation: Remote | Duration: Up to 6 Months💰 Performance-Based Stipend: Up to ₹10,000📅 Batch Starts: 15th September⏰ Application Deadline: 3rd September🚀 Learn. Build. Predict.Want to build a career in Machine Learning & AI? Join Nexal IIT and gain hands-on experience working on real-world ML projects, from data preparation to model development and evaluation.💻 What You'll Work On
Clean, prepare & analyze datasets
Perform data preprocessing & feature engineering
Build & train Machine Learning models
Evaluate & improve model performance
Work with Python, Pandas & NumPy
Apply ML to solve real-world problems
👥 Who Can Apply?Anyone interested in Machine Learning!Students • Freshers • Self-Taught Learners • Bootcamp Graduates • Career Switchers • Working ProfessionalsNo specific degree required — curiosity, analytical thinking, and willingness to learn matter most.🎯 What You Get✅ Real-world ML project experience✅ Portfolio-ready projects✅ Industry mentorship & guidance✅ Certificate of Completion✅ Letter of Recommendation for active contributors✅ Flexible Remote Work🔥 Start Your Machine Learning Journey!Apply before 14th September and join the 5th September batch.👉 Don't just learn Machine Learning — build real models, solve real problems, and gain real experience. Apply Now!

"""
   

    # 1. Parse the Job Description
    job_schema = JobD.model_json_schema()
    system_prompt = f"""
    You are an expert HR Data Engineer. Analyze the job description and extract structured information.
    Return strictly valid JSON matching this schema: {job_schema}
    
    EXTRACTION RULES:
    1. 'required_technical_skills': Extract HARD skills (e.g., programming languages, tools, software, cloud platforms, hardware).
    2. 'required_soft_skills': Extract SOFT skills (e.g., communication, leadership, problem-solving, analytical thinking).
    3. Separate embedded lists (e.g., "Python and C++" becomes ["Python", "C++"]).
    4. Do not invent minimum_experience if it is not explicitly stated in years.
    """
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Analyse the following job description:\n{job_description}"}
    ]
    
    response = client.chat.completions.create(
        model=model, 
        messages=messages, 
        temperature=0.0, 
        response_format={"type": "json_object"}
    )
    
    job_data = json.loads(response.choices[0].message.content)
    job = JobD(**job_data)
    
    print("=== Job Requirements Parsed ===")
    print(f"Role: {job.role}")
    print(f"Required Technical Skills: {job.required_technical_skills}")
    print(f"Required Soft Skills: {job.required_soft_skills}")
    print(f"Preferred Skills: {job.preferred_skills}")

    # 2. Process all resumes
    resume_folder = Path("resumes")
    all_results = []
    
    if not resume_folder.exists():
        print(f"Directory {resume_folder} does not exist.")
        return

    for file_path in resume_folder.iterdir():
        if file_path.suffix.lower() not in [".pdf", ".docx"]:
            continue

        print(f"\nProcessing file : {file_path.name}")
        resume_text = read_resume(file_path)
        
        if not resume_text:
            continue
            
        parsed_resume = parse_resume(resume_text)
        time.sleep(2) # Changed to 2 seconds for efficiency
        
        result = final_score(job, parsed_resume)
        time.sleep(2)
        
        print(f"Score : {result.score}%")
        all_results.append({
            "name": parsed_resume.name or file_path.stem,
            "score": result.score,
            "details": result.details,
        })

    # 3. Sort and Output Results
    all_results.sort(key=lambda candidate: candidate['score'], reverse=True)
    
    top_2 = all_results[:2]
    worst_2 = all_results[-2:]

    print("\n" + "="*40)
    print("Top 2 Candidates :")
    print("="*40)
    for candidate in top_2:
        print(f"{candidate['name']} - {candidate['score']}%")
        # Use .model_dump() to convert the MatchDetails object into a clean dictionary
        print(json.dumps(candidate['details'].model_dump(), indent=2, ensure_ascii=False))
        print("\n")

    print("="*40)
    print("Lowest 2 Candidates :")
    print("="*40)
    for candidate in worst_2:
        print(f"{candidate['name']} - {candidate['score']}%")
        print(json.dumps(candidate['details'].model_dump(), indent=2, ensure_ascii=False))
        print("\n")

if __name__ == "__main__":
    main()