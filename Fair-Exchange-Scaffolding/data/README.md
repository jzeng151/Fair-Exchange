# data/

Loaders that prepare data for the agent and for Athena. Source files live in `docs/olena_data/` in the team repo.

| Module | Purpose | Issue |
|---|---|---|
| `src/fx_data/sample_data.py` | Producer accounts, Premium projects, survey (safe fields only) → Parquet in S3 + Glue tables | #28 |
| `src/fx_data/standards.py` | APS/FPS Excel → clean clause records (ID, objective, module) for grounding | #9 |
| `src/fx_data/regional.py` | Regional fact table (CHIRPS, Aqueduct, World Bank prices), labeled as a stand-in | #8 |
| `src/fx_data/synthetic.py` | Synthetic producers and conversation records for demos | #7, #37 |

**Survey fields:** only farming practices, water access and farm size are used. Never harassment/discrimination, schooling, borrowing, medical or unsafe-work answers.
