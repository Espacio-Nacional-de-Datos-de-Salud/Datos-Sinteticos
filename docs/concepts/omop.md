[<-- Back to Main Index](../../README.md)

# OMOP Common Data Model

## Introduction

The **OMOP Common Data Model (CDM)** is a standardized healthcare data schema developed by OHDSI. It provides a common structure for organizing and analyzing observational health data, enabling interoperability across different healthcare datasets and research environments. OMOP represents clinical observations in a relational format that normalizes patient visits, diagnoses, medications, procedures, measurements, and outcomes. The basis of the model is the patient id. For a complete visual representation of the OMOP schema and all table relationships, see the [OHDSI Entity-Relationship Diagram](https://ohdsi.github.io/CommonDataModel/images/erd.jpg).


## Core Tables

OMOP CDM consists of multiple tables organized into logical domains. The following tables are commonly used in our data synthesis workflows:

- **person**: Core patient demographics and identifiers
- **visit_occurrence**: Encounters at healthcare facilities (hospitalizations, outpatient visits, etc.)
- **condition_occurrence**: Diagnoses and the dates they were recorded
- **condition_era**: Episodes of condition (groups consecutive diagnoses)
- **drug_exposure**: Medication exposures with start/end dates
- **drug_era**: Episodes of medication use (continuous medication periods)
- **procedure_occurrence**: Medical procedures performed
- **measurement**: Laboratory and other clinical measurements
- **observation**: Miscellaneous clinical observations not captured elsewhere

## Adapting OMOP Data for Mostly AI

Mostly AI has specific requirements for synthetic data generation that require careful handling of OMOP data. The following sections document known issues and best practices for preparing OMOP datasets for use with synthcity.

### Table Selection & Filtering

During data preparation, it is common to remove tables that:

- **Insufficient Data**: Tables with too few records to train meaningful models
- **All Text Columns**: Tables containing only unstructured text force the language model to run, which is computationally expensive and often unnecessary

### Primary Key Requirements

Mostly AI requires all tables to have explicit primary keys. This presents a challenge with OMOP:

#### Issue 1: Missing Primary Keys

Some OMOP tables lack natural primary keys. Examples:
- **drug_strength**: Reference table without a natural key. Should not be generated anyways.
- **death**: Relies on person id. But mostly will not allow a PK to be a FK

In addition, this includes some common tables from synthea-generated datasets
- **assign_all_visit_ids**: An intermediate mapping table with no PK

**Solution**: Think about whether a table has a need to be anonimized, rather than choosing an entire directory of files. Add a surrogate key (e.g., `idx` or `death_id` column) to enable Mostly AI processing. In the future, depending on project input requirements, this can be automated.

#### Issue 2: Composite Primary Keys

OMOP uses compound keys in some tables. Depending on project requirements, these may need to be pre-processed to create a unique PK.


### Known Problematic Tables

| Table | Issue |
|-------|-------|
| death | Primary key = foreign key conflict |
| drug_strength | No natural primary key |
| assign_all_visit_ids | Intermediate mapping, no primary key |
| final_visit_ids | Intermediate mapping, no primary key |
