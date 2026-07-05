# Oncollama: LLM-Based Oncology Entity Recognition Analysis

> **Document Version:** 1.0
> **Analysis Date:** January 2026
> **Application:** Oncollama V3 Test GUI
> **Model:** Fine-tuned Llama 3.1 8B for Oncology

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Fine-tuned Model Implementation](#3-fine-tuned-model-implementation)
4. [Oncology Entity Recognition](#4-oncology-entity-recognition)
5. [Key Code Components](#5-key-code-components)
6. [Input/Output Flow](#6-inputoutput-flow)
7. [Example Walkthrough](#7-example-walkthrough)
8. [Technical Insights](#8-technical-insights)

---

## 1. Executive Summary

Oncollama is a medical entity recognition application that uses a **fine-tuned Llama 3.1 8B model** specialized for extracting structured data from oncology clinical documents. The application provides a desktop GUI for testing and validating the model's ability to recognize cancer-related entities including:

- Cancer diagnoses (topography, morphology, staging)
- Molecular biomarkers (EGFR, ALK, BRCA, PD-L1, etc.)
- Treatment timelines and responses
- Disease progression and metastatic spread
- Patient clinical findings and performance status

### Key Statistics

| Metric | Value |
|--------|-------|
| Total Python Code | 282 lines |
| Core Modules | 3 files |
| Example Test Cases | 15 oncology documents |
| External Dependencies | 6 packages |
| Development Status | Pre-release testing |

---

## 2. Architecture Overview

### 2.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Oncollama Application                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌───────────────────────────┐   │
│  │   main.py   │───▶│   gui.py    │───▶│        utils.py           │   │
│  │ (Entrypoint)│    │ (DearPyGUI) │    │  (API + Data Processing)  │   │
│  └─────────────┘    └─────────────┘    └───────────────────────────┘   │
│                            │                        │                   │
│                            ▼                        ▼                   │
│                    ┌───────────────┐    ┌───────────────────────────┐   │
│                    │ endpoints.yaml│    │  External: oncollamaschemav3│
│                    │(Model configs)│    │  - Schema (Pydantic)      │   │
│                    └───────────────┘    │  - Prompt Templates       │   │
│                                         │  - Validation Logic       │   │
│                                         └───────────────────────────┘   │
│                                                     │                   │
│                                                     ▼                   │
│                                         ┌───────────────────────────┐   │
│                                         │   OpenPipe API Service    │   │
│                                         │   (Fine-tuned Llama 3.1)  │   │
│                                         └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Summary

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| **Entry Point** | `main.py` | 15 | Initializes and launches the GUI application |
| **User Interface** | `gui.py` | 184 | DearPyGUI-based desktop interface with input/output panes |
| **Backend Logic** | `utils.py` | 83 | API communication, config loading, JSON extraction |
| **Model Config** | `endpoints.yaml` | 3 | Defines available OncoLlama model endpoints |
| **External Package** | `oncollamaschemav3` | ~17KB | Pydantic schema, prompts, and validation logic |

### 2.3 Data Flow: Document to Entities

```
┌──────────────────┐
│ Oncology Document│  (Clinical note, pathology report, etc.)
│   (Plain Text)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  parse_escape_   │  Handle \n, \t formatting from GUI input
│  sequences()     │  [gui.py:18-25]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ create_system_   │  Load prompt template + inject Pydantic schema
│ prompt()         │  [oncollamaschemav3/prompt.py]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  OpenPipe API    │  Fine-tuned Llama 3.1 8B inference
│  Inference       │  temperature=0, max_tokens=8000
│                  │  [utils.py:62-75]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ extract_output_  │  Parse JSON from <output>...</output> tags
│ json()           │  [utils.py:45-59]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ validate_json()  │  Pydantic schema validation against OncoLlamaModel
│                  │  [oncollamaschemav3/validate.py]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Structured JSON  │  Validated oncology entities ready for use
│ Output           │
└──────────────────┘
```

---

## 3. Fine-tuned Model Implementation

### 3.1 Model Serving Architecture

The application uses **OpenPipe** as the model serving infrastructure. OpenPipe hosts the fine-tuned Llama 3.1 8B model and provides an OpenAI-compatible API interface.

**Code Reference - `utils.py:62-83`:**

```python
def call_openpipe_api(api_key, model, user_text):
    try:
        client = OpenAI(openpipe={"api_key": api_key})
        system_prompt = create_system_prompt('infer_prompt.txt')

        completion = client.chat.completions.create(
            model=model,                              # "openpipe:oncollama-v3-prerelease2"
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            max_tokens=8000,
            temperature=0                             # Deterministic output
        )

        response_text = completion.choices[0].message.content
        formatted_json = extract_output_json(response_text)

        return True, formatted_json

    except Exception as e:
        return False, f"API Error: {e}"
```

### 3.2 Inference Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Serving Platform** | OpenPipe (serverless) | Cloud-hosted fine-tuned model |
| **API Compatibility** | OpenAI-compatible | Standard client interface |
| **Model ID** | `openpipe:oncollama-v3-prerelease2` | Latest pre-release version |
| **Temperature** | 0 | Deterministic extraction for consistency |
| **Max Tokens** | 8000 | Large limit for comprehensive JSON output |

### 3.3 Available Model Endpoints

**From `endpoints.yaml`:**

```yaml
endpoints:
  - openpipe:oncollama-v3-prerelease2   # Latest version
  - openpipe:oncollama-v3-prerelease    # Previous version
```

The GUI provides a dropdown selector allowing users to switch between model versions for A/B testing and comparison during the pre-release evaluation phase.

### 3.4 Connection Management

**Code Reference - `utils.py:31-42`:**

```python
def test_connection(api_key, model):
    try:
        client = OpenAI(openpipe={"api_key": api_key})
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=10,
            temperature=0
        )
        return True, "Connected"
    except Exception as e:
        return False, f"Connection failed: {e}"
```

---

## 4. Oncology Entity Recognition

### 4.1 Entity Types Overview

The schema defines comprehensive oncology entities using **Pydantic models** with strict typing:

#### A. Anatomical Sites (TopographyType)

| Category | Entity Types |
|----------|-------------|
| **Respiratory** | LUNG, BRONCHUS, TRACHEA, PLEURA |
| **Gastrointestinal** | ESOPHAGUS, STOMACH, COLON, RECTUM, LIVER, PANCREAS, GALLBLADDER, SMALL_INTESTINE |
| **Genitourinary** | KIDNEY, BLADDER, PROSTATE, TESTIS, PENIS |
| **Gynecological** | OVARY, UTERUS, CERVIX, VULVA, VAGINA |
| **CNS** | BRAIN, MENINGES, SPINAL_CORD |
| **Head/Neck** | ORAL_CAVITY, OROPHARYNX, LARYNX, THYROID, SALIVARY_GLAND |
| **Other** | SKIN, SOFT_TISSUE, BONE, BREAST, UNKNOWN_PRIMARY |

#### B. Histological Classifications (MorphologyType)

| Category | Entity Types |
|----------|-------------|
| **Carcinomas** | ADENOCARCINOMA, SQUAMOUS_CELL, SMALL_CELL, LARGE_CELL, TRANSITIONAL_CELL |
| **Sarcomas** | OSTEOSARCOMA, CHONDROSARCOMA, LEIOMYOSARCOMA, LIPOSARCOMA, EWING_SARCOMA |
| **Hematological** | LYMPHOMA, LEUKEMIA, MYELOMA, MDS, MPN |
| **CNS Tumors** | GLIOBLASTOMA, MENINGIOMA, ASTROCYTOMA, OLIGODENDROGLIOMA |
| **Germ Cell** | SEMINOMA, NON_SEMINOMA, TERATOMA |
| **Pediatric** | NEUROBLASTOMA, WILMS_TUMOR, RETINOBLASTOMA |

#### C. Molecular Biomarkers (MolecularBiomarkerType)

| Cancer Type | Biomarkers |
|-------------|------------|
| **Lung Cancer** | EGFR, ALK, ROS1, MET, KRAS, BRAF, PD_L1, NTRK |
| **Colorectal** | KRAS, NRAS, BRAF, MSI, HER2 |
| **Breast** | ER, PR, HER2, BRCA1, BRCA2, PIK3CA |
| **General/Pan-Cancer** | TP53, PTEN, PIK3CA, NTRK, TMB, ctDNA |
| **Cholangiocarcinoma** | IDH1, FGFR2 |

#### D. Biomarker Status Values

```python
class BiomarkerStatus(str, Enum):
    ALTERED = "altered"          # Mutation/amplification/fusion detected
    NEGATIVE = "negative"        # Wild-type/no alteration found
    EQUIVOCAL = "equivocal"      # Borderline/indeterminate result
    HYPOTHETICAL = "hypothetical" # Suspected but not yet tested
```

#### E. Disease Spread (SpreadType)

```
LYMPH_NODE, LIVER, LUNG, BONE, BRAIN, ADRENAL,
PERITONEUM, PLEURA, SKIN, SOFT_TISSUE, DISTANT_OTHER
```

#### F. Timeline Events (TimelineEventType)

| Category | Event Types |
|----------|-------------|
| **Treatment** | CHEMOTHERAPY, RADIOTHERAPY, SURGERY, IMMUNOTHERAPY, TARGETED_THERAPY |
| **Response** | COMPLETE_RESPONSE, PARTIAL_RESPONSE, STABLE_DISEASE, MIXED_RESPONSE |
| **Progression** | LOCAL_RECURRENCE, DISTANT_METASTASIS, BIOCHEMICAL_PROGRESSION |
| **Toxicity** | ADVERSE_EVENT, DOSE_REDUCTION, TREATMENT_DISCONTINUATION |
| **Trial** | CLINICAL_TRIAL_ENROLLMENT, CLINICAL_TRIAL_COMPLETION |

#### G. Patient Findings (PatientFindingType)

| Category | Finding Types |
|----------|--------------|
| **Comorbidities** | DIABETES, HYPERTENSION, RENAL_DISEASE, CARDIAC_DISEASE, COPD |
| **Symptoms** | PAIN, FATIGUE, WEIGHT_LOSS, DYSPNEA, NAUSEA |
| **Physical Exam** | ASCITES, LYMPHADENOPATHY, HEPATOMEGALY, PLEURAL_EFFUSION |
| **Functional** | ECOG_PERFORMANCE_STATUS, KARNOFSKY_SCORE |
| **Mental State** | COGNITIVE_IMPAIRMENT, DEPRESSION, ANXIETY |

### 4.2 Schema Field Naming Conventions

The schema employs standardized suffixes for semantic clarity:

| Suffix | Purpose | Example |
|--------|---------|---------|
| `*_type` | Enum classification | `topography_type: "LUNG"` |
| `*_status` | Status enumeration | `biomarker_status: "ALTERED"` |
| `*_name_desc` | Direct clinical text extraction | `treatment_name_desc: "FOLFOX"` |
| `*_desc` | Verbatim document excerpt | `staging_desc: "pT3N1M0"` |
| `*_summary` | Concise summary | `context_summary: "..."` |
| `*_numeric_value` | Numeric-only data | `ca125_numeric_value: 420` |
| `*_year`, `*_month` | Temporal fields | `diagnosis_year: 2024` |
| `*_flag` | Boolean indicator | `recurrence_flag: true` |

### 4.3 Prompt Engineering Approach

The system uses a **template-substitution approach** where the complete Pydantic schema is injected into the system prompt.

**From `oncollamaschemav3/prompt.py`:**

```python
def get_schema_code():
    """Retrieves the source code of the schema using inspect module"""
    return inspect.getsource(oncollamaschemav3)

def load_prompt_template(filename):
    """Loads template from prompts/ subdirectory"""
    prompts_dir = Path(__file__).parent / "prompts"
    return (prompts_dir / filename).read_text()

def create_system_prompt(filename='infer_prompt.txt'):
    """Constructs the final system prompt with schema injection"""
    prompt = load_prompt_template(filename)    # Load template
    schema = get_schema_code()                 # Get full Pydantic schema
    return prompt.replace("{SCHEMA}", schema)  # Inject schema into prompt
```

The system prompt includes:
1. **Task description**: Extract structured oncology data from clinical text
2. **Complete schema definition**: All Pydantic classes and enums (injected via `{SCHEMA}` placeholder)
3. **Field guidelines**: Instructions for populating each field type
4. **Output format specification**: JSON wrapped in `<output>` tags for reliable parsing

### 4.4 How Fine-Tuning Enhances Oncology Understanding

| Capability | How Fine-Tuning Helps |
|------------|----------------------|
| **Medical Abbreviations** | Recognizes `pt`, `dx`, `hx`, `c/o`, `abd`, `susp`, `diff`, etc. |
| **Staging Systems** | Understands TNM staging, AJCC editions, group staging conventions |
| **Biomarker Interpretation** | Correctly classifies mutation status, VAF values, actionability |
| **Temporal Reasoning** | Tracks disease recurrences, treatment timelines, response durations |
| **Schema Compliance** | Outputs valid JSON matching exact Pydantic schema structure |
| **Negative Recognition** | Correctly identifies non-cancer documents (adversarial cases) |
| **Multi-Cancer Cases** | Distinguishes primary vs. secondary cancers, synchronous malignancies |

---

## 5. Key Code Components

### 5.1 main.py - Application Entry Point

**File:** `main.py` (15 lines)

```python
"""
main.py - Entrypoint
"""

from gui import OpenPipeGUI


def main():
    app = OpenPipeGUI()
    app.create_gui()
    app.run()


if __name__ == "__main__":
    main()
```

**Purpose:** Simple entry point that instantiates the GUI class and runs the application.

### 5.2 gui.py - User Interface (OpenPipeGUI Class)

**File:** `gui.py` (184 lines)

#### Class Structure

```python
class OpenPipeGUI:
    def __init__(self):
        self.api_key = None      # OpenPipe API key
        self.model = None        # Selected model endpoint
        self.connected = False   # Connection status
        self.endpoints = []      # Available endpoints
```

#### Key Methods

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__()` | 12-16 | Initialize state variables |
| `parse_escape_sequences()` | 18-25 | Convert `\n`, `\t` to actual characters |
| `on_endpoint_changed()` | 27-34 | Handle model selection dropdown changes |
| `initialise()` | 36-62 | Load config, test API connection |
| `on_input_changed()` | 64-70 | Update formatted preview as user types |
| `on_infer_clicked()` | 72-107 | Execute inference and validation |
| `create_gui()` | 109-178 | Build complete DearPyGUI interface |
| `run()` | 182-184 | Start GUI event loop |

#### Inference and Validation Logic

**Code Reference - `gui.py:72-107`:**

```python
def on_infer_clicked(self):
    """Handle button click: Infer"""
    if not self.connected:
        dpg.set_value("output_text", "Error: Not connected to API")
        return

    input_text = dpg.get_value("input_text")
    input_text = self.parse_escape_sequences(input_text)

    if not input_text.strip():
        dpg.set_value("output_text", "Error: Please enter some text")
        return

    dpg.set_value("output_text", "Processing...")
    dpg.configure_item("infer_button", enabled=False)

    success, result = call_openpipe_api(self.api_key, self.model, input_text)

    dpg.set_value("output_text", result)
    dpg.configure_item("infer_button", enabled=True)

    if success:
        is_valid, validation_msg, _ = validate_json(result)
        if is_valid:
            dpg.set_value("validation_status", "Output Validation Succeeded")
            dpg.configure_item("validation_status", color=(0, 255, 0))  # Green
        else:
            dpg.set_value("validation_status", f"Output Validation Failed: {validation_msg}")
            dpg.configure_item("validation_status", color=(255, 0, 0))  # Red
```

### 5.3 utils.py - Backend Operations

**File:** `utils.py` (83 lines)

#### Function Summary

| Function | Lines | Purpose |
|----------|-------|---------|
| `load_env_vars()` | 17-19 | Load `OPENPIPE_API_KEY` from `.env` file |
| `load_endpoints()` | 22-28 | Parse endpoints from `endpoints.yaml` |
| `test_connection()` | 31-42 | Verify API connectivity with test message |
| `extract_output_json()` | 45-59 | Parse and format JSON from `<output>` tags |
| `call_openpipe_api()` | 62-83 | Main inference function |

#### JSON Extraction Logic

**Code Reference - `utils.py:45-59`:**

```python
def extract_output_json(text):
    """
    Extract JSON from <output> tags
    """
    pattern = r'<output>(.*?)</output>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
        try:
            # parse, reformat
            parsed = json.loads(json_str)
            return json.dumps(parsed, indent=4)
        except json.JSONDecodeError as e:
            return f"Error parsing JSON: {e}\n\nRaw content:\n{json_str}"
    return text  # Return original if no tags found
```

### 5.4 External Package: oncollamaschemav3

**Repository:** `github.com/londonaicentre/oncollamaschemav3`

| Module | Size | Purpose |
|--------|------|---------|
| `oncollamaschemav3.py` | 17.4 KB | Pydantic schema definitions (all enums, models) |
| `prompt.py` | ~1 KB | System prompt construction with schema injection |
| `validate.py` | ~1 KB | JSON parsing and Pydantic validation |
| `prompts/infer_prompt.txt` | 8.5 KB | Inference prompt template |

#### Validation Function

```python
def validate_json(json_string):
    """
    Validates JSON string against OncoLlamaModel schema.
    Returns: (success: bool, message: str, data: dict | None)
    """
    try:
        data = json.loads(json_string)
        OncoLlamaModel(**data)  # Pydantic validation
        return True, "Validation successful", data
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}", None
    except ValidationError as e:
        return False, f"Schema validation error: {e}", None
    except Exception as e:
        return False, f"Unexpected error: {e}", None
```

---

## 6. Input/Output Flow

### 6.1 Supported Document Types

The `/examples` folder contains 15 test cases representing various oncology document types:

| Example | Document Type | Challenge Tested |
|---------|--------------|------------------|
| `01_complex_multi_cancer.txt` | Multi-tumor consultation | Synchronous malignancies (colorectal + lung + prostate) |
| `02_ambiguous_contradictory.txt` | Referral note | Conflicting/ambiguous information |
| `03_poor_quality_abbreviations.txt` | ED/clinic note | Heavy medical abbreviations |
| `04_incomplete_minimal.txt` | Brief referral | Minimal data extraction |
| `05_adversarial_non_cancer.txt` | Cardiology note | Non-cancer document (negative case) |
| `06_temporal_recurrences.txt` | Progress note | Multiple recurrences over time |
| `07_cancer_unknown_primary.txt` | Tumor board | CUP (Cancer of Unknown Primary) |
| `08_rare_extensive_molecular.txt` | Molecular tumor board | Comprehensive genomic profiling |
| `09_pseudoprogression.txt` | Treatment response | Complex response patterns |
| `10_mixed_contradictory.txt` | Mixed clinical note | Contradictory findings |
| `11-15_poor_format_*.txt` | Various | Poor formatting across cancer types |

### 6.2 Output JSON Schema Structure

The root `OncoLlamaModel` schema produces the following structure:

```json
{
  "document_has_primary_cancer_flag": true,
  "primary_cancer_confirmed_flag": true,
  "primary_cancer": {
    "facts": {
      "topography_type": "LUNG",
      "morphology_type": "ADENOCARCINOMA",
      "tnm_staging_desc": "cT2aN2M0",
      "group_staging_type": "STAGE_IIIA",
      "diagnosis_year": 2024,
      "diagnosis_month": 10,
      "recurrence_flag": false
    },
    "tumour_facts": {
      "msi_status": "MSS",
      "tmb_status": null,
      "biomarkers": [
        {
          "biomarker_type": "EGFR",
          "biomarker_status": "NEGATIVE"
        },
        {
          "biomarker_type": "ALK",
          "biomarker_status": "NEGATIVE"
        },
        {
          "biomarker_type": "PD_L1",
          "biomarker_status": "ALTERED",
          "expression_numeric_value": 65,
          "expression_desc": "TPS 65%"
        }
      ]
    },
    "spread": [
      {
        "spread_type": "LYMPH_NODE",
        "spread_desc": "mediastinal lymphadenopathy station 4R"
      }
    ],
    "timeline_events": [
      {
        "event_type": "CHEMOTHERAPY",
        "event_name_desc": "concurrent chemoradiation",
        "event_year": 2024,
        "event_month": 12
      }
    ]
  },
  "performance_status": {
    "ecog_score": 1,
    "ecog_desc": "Restricted in physically strenuous activity"
  },
  "other_cancers": [
    {
      "facts": {
        "topography_type": "COLON",
        "morphology_type": "ADENOCARCINOMA",
        "group_staging_type": "STAGE_IIA"
      }
    }
  ],
  "patient_findings": [
    {
      "finding_type": "COMORBIDITY",
      "finding_name_desc": "hypertension",
      "finding_status": "PRESENT"
    }
  ],
  "future_plans": [
    {
      "plan_type": "IMMUNOTHERAPY",
      "plan_name_desc": "durvalumab consolidation"
    }
  ],
  "context_summary": {
    "doc_context": "oncology consultation letter",
    "doc_summary": "67-year-old male with synchronous malignancies..."
  }
}
```

### 6.3 Key Schema Design Principles

1. **Required enums have no defaults** - Forces explicit classification
2. **Optional fields default to None** - Distinguishes absence from "OTHER"
3. **`other_` prefix** - Denotes secondary/historical cancers separate from primary
4. **Temporal validation** - Year/month fields have validation rules
5. **Direct text extraction** - `*_desc` fields preserve verbatim clinical language

---

## 7. Example Walkthrough

### 7.1 Example: Complex Multi-Cancer Case

**Input File:** `examples/01_complex_multi_cancer.txt`

```
PATIENT: 67-year-old male
DATE: December 2024

HISTORY OF PRESENT ILLNESS:
Patient presents with synchronous malignancies. Originally diagnosed with
stage IIA (pT3N0M0) adenocarcinoma of the sigmoid colon in March 2023...

Additionally, recent diagnosis of low-grade (Gleason 3+3=6) prostate
adenocarcinoma detected on screening PSA (6.8 ng/mL)...

CURRENT STATUS:
1. Colorectal adenocarcinoma - stage IIA, disease-free at 20 months
2. Lung adenocarcinoma - stage IIIA (cT2aN2M0), EGFR wild-type, PD-L1 65%
3. Prostate adenocarcinoma - stage T2a, Gleason 3+3=6, active surveillance
```

**Expected Entity Extraction:**

| Entity | Value |
|--------|-------|
| `document_has_primary_cancer_flag` | `true` |
| Primary Cancer | Lung adenocarcinoma (most active disease) |
| Primary Topography | `LUNG` |
| Primary Morphology | `ADENOCARCINOMA` |
| Primary Staging | `cT2aN2M0`, Stage IIIA |
| EGFR Status | `NEGATIVE` (wild-type) |
| PD-L1 Status | `ALTERED` with value 65 |
| Other Cancers | Array with colorectal and prostate entries |

### 7.2 Example: Abbreviation-Heavy Note

**Input File:** `examples/03_poor_quality_abbreviations.txt`

```
pt 72F w/ hx HTN, DM2, came to ED c/o abd pain x 3wks, wt loss ~15lbs

CT abd/pelv showed lg pancreatic mass ~5cm in head, dilated biliary tree,
mult liver lesions susp for mets. CA 19-9 elevatd at 850

EUS-FNA done -> path came bck as panc ductal adenoca, poorly diff.
```

**Model Interpretation Challenge:**

| Abbreviation | Meaning |
|--------------|---------|
| `pt` | patient |
| `w/` | with |
| `hx` | history |
| `HTN` | hypertension |
| `DM2` | diabetes mellitus type 2 |
| `c/o` | complaining of |
| `abd` | abdominal |
| `susp` | suspicious |
| `mets` | metastases |
| `adenoca` | adenocarcinoma |
| `diff` | differentiated |

The fine-tuned model correctly interprets these abbreviations and extracts structured entities.

### 7.3 Example: Adversarial Non-Cancer Case

**Input File:** `examples/05_adversarial_non_cancer.txt`

```
CARDIOLOGY CONSULTATION NOTE

PATIENT: 55-year-old male
CHIEF COMPLAINT: Chest pain and dyspnea on exertion

CARDIAC WORKUP:
- Stress test: Positive for inducible ischemia
- Coronary angiography: Severe triple vessel disease
```

**Expected Output:**

```json
{
  "document_has_primary_cancer_flag": false,
  "primary_cancer_confirmed_flag": false,
  "primary_cancer": null,
  "performance_status": null,
  "other_cancers": null,
  "patient_findings": null,
  "future_plans": null,
  "context_summary": {
    "doc_context": "cardiology consultation",
    "doc_summary": "This is a cardiovascular case, not an oncology document."
  }
}
```

The model correctly identifies this is NOT an oncology case and returns appropriate null values.

### 7.4 Example: Extensive Molecular Profiling

**Input File:** `examples/08_rare_extensive_molecular.txt`

```
COMPREHENSIVE GENOMIC PROFILING (Foundation Medicine):
Tumor Mutational Burden: 15 mutations/Mb (TMB-High)
Microsatellite status: MSS

ALTERATIONS DETECTED:
1. IDH1 R132C mutation (VAF 42%) - potentially actionable
2. FGFR2-BICC1 fusion (exon 17-exon 1) - actionable
3. TP53 R248W mutation (VAF 38%)
...
GERMLINE TESTING (Invitae):
Pathogenic variant identified: BRCA2 c.5946delT (p.Ser1982fs) - germline
```

**Expected Biomarker Extraction:**

```json
{
  "tumour_facts": {
    "msi_status": "MSS",
    "tmb_status": "HIGH",
    "biomarkers": [
      {
        "biomarker_type": "IDH1",
        "biomarker_status": "ALTERED",
        "alteration_desc": "R132C mutation",
        "vaf_numeric_value": 42
      },
      {
        "biomarker_type": "FGFR2",
        "biomarker_status": "ALTERED",
        "alteration_desc": "FGFR2-BICC1 fusion"
      },
      {
        "biomarker_type": "TP53",
        "biomarker_status": "ALTERED",
        "alteration_desc": "R248W mutation",
        "vaf_numeric_value": 38
      },
      {
        "biomarker_type": "BRCA2",
        "biomarker_status": "ALTERED",
        "alteration_desc": "c.5946delT germline pathogenic variant"
      }
    ]
  }
}
```

---

## 8. Technical Insights

### 8.1 Architecture Design Patterns

| Pattern | Implementation |
|---------|---------------|
| **MVC-Style Separation** | GUI (view) → OpenPipeGUI methods (controller) → utils.py (model/API) |
| **External Schema Package** | Decouples domain knowledge from application logic |
| **Configuration-Driven** | Endpoints defined in YAML, credentials in .env |
| **Template Substitution** | Schema injected into prompt via `{SCHEMA}` placeholder |

### 8.2 Fine-Tuning Benefits Summary

1. **Domain Vocabulary**: Understands medical abbreviations, staging systems, biomarker nomenclature
2. **Schema Compliance**: Outputs valid JSON matching exact Pydantic definitions
3. **Contextual Reasoning**: Handles multi-cancer, temporal, and ambiguous cases
4. **Negative Detection**: Correctly identifies non-cancer documents
5. **Structured Extraction**: Consistent field population across varied input formats

### 8.3 Prompt Engineering Techniques

| Technique | Purpose |
|-----------|---------|
| **Full Schema Injection** | Model has complete type definitions for valid output |
| **Structured Output Tags** | `<output>` tags enable reliable JSON extraction |
| **Zero Temperature** | Deterministic extraction for reproducibility |
| **High Token Limit** | 8000 tokens allows comprehensive entity extraction |

### 8.4 Validation Strategy

- **Two-Stage Validation**: JSON parsing followed by Pydantic schema validation
- **Real-Time Feedback**: Color-coded status indicator (green/red) in GUI
- **Error Reporting**: Descriptive validation failure messages for debugging

### 8.5 Limitations and Considerations

| Consideration | Notes |
|---------------|-------|
| **API Dependency** | Requires OpenPipe cloud service connectivity |
| **Pre-Release Status** | Model endpoints marked as "prerelease" |
| **No Local Inference** | Cannot run without API access |
| **English Only** | Schema and prompts designed for English clinical text |

---

## Appendix A: File Structure

```
oncollamatest - Claude Code/
├── main.py                          # Application entry point (15 lines)
├── gui.py                           # DearPyGUI interface (184 lines)
├── utils.py                         # Backend operations (83 lines)
├── endpoints.yaml                   # Model endpoint configuration
├── requirements.txt                 # Python dependencies
├── README.md                        # Project documentation
├── .env.example                     # Environment variable template
├── .gitignore                       # Version control exclusions
└── examples/                        # Test oncology documents (15 files)
    ├── 01_complex_multi_cancer.txt
    ├── 02_ambiguous_contradictory.txt
    ├── 03_poor_quality_abbreviations.txt
    ├── 04_incomplete_minimal.txt
    ├── 05_adversarial_non_cancer.txt
    ├── 06_temporal_recurrences.txt
    ├── 07_cancer_unknown_primary.txt
    ├── 08_rare_extensive_molecular.txt
    ├── 09_pseudoprogression.txt
    ├── 10_mixed_contradictory.txt
    ├── 11_poor_format_breast_trial.txt
    ├── 12_poor_format_lung_toxicity.txt
    ├── 13_poor_format_colon_molecular.txt
    ├── 14_poor_format_pancreas_pain.txt
    └── 15_poor_format_ovarian_recurrence.txt
```

## Appendix B: Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `dearpygui` | Latest | Desktop GUI framework |
| `python-dotenv` | Latest | Environment variable loading |
| `requests` | Latest | HTTP client |
| `openpipe` | Latest | OpenPipe API client |
| `pyyaml` | Latest | YAML configuration parsing |
| `oncollamaschemav3` | Git | Oncology schema and validation |

---

*Document generated through comprehensive codebase analysis of the Oncollama application.*
