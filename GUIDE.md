# MESA Validation Protocol

This is a suggested document-level validation guide for the NHS R&D "OncoLlama" project


## Document Selection

For each cancer type, a targeted query is used to identify relevant clinical documents:

- **Query A** -> Cancer type A documents
- **Query B** -> Cancer type B documents
- **Query C** -> Cancer type C documents
- ... etc.

From each query result set, **50 documents are randomly sampled** with the constraint that each document must be from a unique patient (no patient can appear multiple times in the sample).

**Total validation corpus**: If there are *n* queries, the total corpus size is *n* × 50 documents.

All sampled documents are imported into MESA-Validate for human review.

## Fields Selected for Validation

Please use the following schema elements for validation:

### Individual Fields
- `PrimaryCancerFacts.topography`
- `PrimaryCancerFacts.topography_name_desc`
- `PrimaryCancerFacts.morphology`
- `PrimaryCancerFacts.morphology_name_desc`
- `PrimaryCancerFacts.diagnosis_year`
- `PrimaryCancerFacts.diagnosis_month`
- `PrimaryCancerFacts.tnm_stage`

### Entire Classes
- `MolecularBiomarkerProfile` (entire class)
- `PerformanceStatus` (entire class)

### Enum Values
- `TimelineEventType.experienced_toxicity_or_complication_related_to_treatment`
- `TimelineEventType.evidence_of_metastatic_progression`
- `TimelineEventType.radiology_evidence_of_disease_progression`
- `TimelineEventType.experienced_treatment_reduction_or_stop`

## Validation Guidelines

### Binary Validation (Single Fields & Non-repeating Blocks)

Where individual fields and entire classes that appear at most once per document.

**Mark as Correct** if the extracted content is accurate and complete.

**Mark as Incorrect** if the content is wrong, incomplete, or missing when it should be present. For entire class blocks, if any field within the block is incorrect, mark the entire block as Incorrect.

### List Validation (Repeating Blocks & Enum Filtering)

Where classes can appear multiple times or for enum value filtering.

**Mark each extracted item as Correct**: if extracted content is accurate and complete

**Mark each extracted item as Incorrect**: if extracted content is if wrong or incomplete.

**Missed count**: Enter the number of items that exist in the document but were not extracted by the model. This allows calculation of both precision (accuracy of extractions) and recall (completeness of extraction).

## Metrics

- **Binary validation**: Calculates TP, TN, FP, FN, Precision, Recall, F1, and Accuracy
- **List validation**: Calculates Precision, Recall, and F1 based on item-level correctness and missed items
