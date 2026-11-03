# Technical Environment Document: Fair Trade USA Producer Exchange Agent

## Project Technical Summary

- **Project Name**: Fair Trade USA Producer Exchange Agent (MVP)

- **Primary Runtime Environment**: Cloud

- **Cloud Provider**: AWS

- **Target Deployment Model**: Serverless. A Strands Agents SDK agent on Amazon Bedrock AgentCore Runtime, with AWS Lambda for API and write-back functions, DynamoDB and S3 for storage. No long-running compute. This mirrors FTUSA's stated planned expansion from one-shot Bedrock calls to an agentic architecture on Strands and AgentCore.

- **Customer Team Experience**: FTUSA has run its core technology on AWS since 2020 with a serverless-first posture (Lambda and Step Functions over anything long-running; Redshift, internally "Atlas," as the warehouse). Python is the default for data engineering (Glue jobs, data science); Node is the default for cloud engineering, existing API backends, and the Lambda/Step Functions automations behind AI summarization and scoring. Bedrock (Claude Sonnet) is in production powering Stories of Impact summarization and scoring; Comprehend and Translate run in warehouse ETL. The team includes data architects and engineers with 6+ years on AWS, several AI and/or AWS-certified, plus a Director of AI & Business Intelligence. They have an existing five-metric-family evaluation harness and a correction queue owned by Impact, Research & Learning. Strands and AgentCore are new to the team and are the main learning objective of the workshop.

## Programming Languages

### Required Languages

| **Language**         | **Version**                  | **Purpose**                                                                                                                                  | **Rationale**                                                                                                           |
|----------------------|------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| Python               | 3.12+                        | Strands agent, agent tools, synthetic data generator, evaluation harness, open-data preparation                                              | Strands Agents SDK is Python-first; Python is FTUSA's default for data engineering and data science                     |
| TypeScript / Node.js | Node 20.x LTS, TS 5.x        | Lambda API handlers (chat endpoint, write-back, review view API) and infrastructure code                                                     | Node is FTUSA's default for cloud engineering, existing API backends, and Lambda automations; keeps the handoff aligned |
| SQL                  | Athena / Redshift-compatible | Stand-in warehouse queries over synthetic Premium, survey, and certification tables; demonstrating the join to the agent-conversation record | Target system of record is Redshift; write Redshift-compatible SQL so queries port                                      |

### Permitted Languages

| **Language**                        | **Conditions for Use**                                                                                                                                                              |
|-------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| TypeScript / JavaScript (front end) | Approved for the minimal web chat and review view, built with Vue (see Required Frameworks)                                                                                         |
| Python for Lambda                   | Approved where a Lambda is a thin wrapper around agent or data code already written in Python (e.g., write-back triggered from the agent); avoid duplicating logic in two languages |
| Bash                                | Build, deploy, and data-loading scripts only                                                                                                                                        |

## Frameworks and Libraries

### Required Frameworks

| **Framework/Library**                       | **Version**            | **Domain**                                                                             | **Rationale**                                                                                                                                                                              |
|---------------------------------------------|------------------------|----------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Strands Agents SDK                          | Current                | Agent definition, tool registration, multi-step reasoning                              | FTUSA's named target agent framework                                                                                                                                                       |
| Amazon Bedrock AgentCore Runtime            | Current                | Hosting the agent, session management (an exchange may span multiple turns and pauses) | FTUSA's named target runtime; sessions are durable per the architecture diagram                                                                                                            |
| Amazon Bedrock Guardrails                   | Current                | Responsible-AI and data-sovereignty constraints on model I/O                           | Named in FTUSA's planned expansion as the governance layer                                                                                                                                 |
| AWS CDK                                     | 2.x (TypeScript)       | Infrastructure as Code for the sandbox stack                                           | Confirmed as the IaC tool for the build unless FTUSA directs otherwise; reproducible deploy is a handoff requirement, and CDK in TypeScript matches FTUSA's Node cloud-engineering default |
| AWS SDK (boto3 / AWS SDK for JavaScript v3) | Current                | Bedrock, DynamoDB, S3, Athena access                                                   | Native AWS integration                                                                                                                                                                     |
| Vue.js                                      | 3.x (TypeScript, Vite) | Front end for the minimal web chat and reviewer view                                   | FTUSA's preferred front-end framework; keeps the handoff aligned with FTUSA's web stack                                                                                                    |
| pytest                                      | 8.x                    | Agent tool tests, negative scope tests, evaluation harness runner                      | Standard Python test runner                                                                                                                                                                |

### Preferred Libraries

| **Library**                                                          | **Purpose**                                                                                    | **Use When**                                                                                                                                           |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| Amazon Bedrock AgentCore Evaluations                                 | Scoring agent decisions (tag accuracy, citation presence, tone) against a labeled set          | Named in the grant as the evaluation mechanism; use it if available in the sandbox region, otherwise a pytest-based harness producing the same metrics |
| Amazon Bedrock AgentCore Observability                               | Tracing every tool call and decision with reasoning                                            | Logging reasoning per decision is a stated FTUSA commitment; enable from the start                                                                     |
| Amazon Bedrock AgentCore Gateway                                     | Exposing tools as governed endpoints                                                           | Use if time allows; direct Strands tools are acceptable for the MVP                                                                                    |
| Amazon Comprehend (DetectPiiEntities)                                | PII detection on producer input                                                                | Named in the grant for PII detection; flag for review, never auto-redact                                                                               |
| Amazon Translate                                                     | Input/output translation                                                                       | Only if Claude's native Spanish quality is insufficient; FTUSA already uses Translate in ETL                                                           |
| Pydantic                                                             | Schemas for tool inputs/outputs and the write-back record                                      | Any structured data crossing a tool boundary or being persisted; enforces per-claim citation fields                                                    |
| AWS Lambda Powertools (Python and TypeScript)                        | Structured logging, tracing, idempotency for Lambda handlers                                   | All Lambda functions                                                                                                                                   |
| Amazon Athena + AWS Glue Data Catalog                                | Querying synthetic Premium, survey, and certification Parquet/CSV in S3 as a Redshift stand-in | Demonstrating the join between the agent-conversation record and existing structured data                                                              |
| Amazon Bedrock Knowledge Bases (S3 vectors or OpenSearch Serverless) | Retrieval over certification standards text and comparable project descriptions                | Standards grounding and peer-example tools; a simple embedded-search or keyword approach over a small corpus is acceptable if faster                   |

### Prohibited Libraries

| **Library**                                                                   | **Reason**                                                                                                                                     | **Alternative**                                                                       |
|-------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| LangChain, LlamaIndex, CrewAI, AutoGen, or other agent frameworks             | FTUSA's target is Strands on AgentCore; a different framework would have to be rewritten                                                       | Strands Agents SDK                                                                    |
| Direct calls to third-party model APIs (OpenAI, Anthropic direct, Google)     | All model access must go through Amazon Bedrock for governance, data sovereignty, and the single model-call choke point described in the grant | Amazon Bedrock                                                                        |
| Any library that lets the model supply producer ID or location to a data tool | Scope must be enforced in the tool from session context, not in the prompt                                                                     | Tools read producer ID and location from the AgentCore session / request context only |
| Auto-redaction libraries (e.g., Presidio anonymizer mode)                     | FTUSA policy is to flag PII for human review, not auto-redact                                                                                  | Comprehend DetectPiiEntities to flag; redaction is a reviewer decision                |
| Web scraping of open-data portals at runtime                                  | Latency and fragility in a demo; licensing uncertainty                                                                                         | Pre-extract open data to S3 before the event                                          |

### Data and Security Baseline (sandbox)

- All data is synthetic, FTUSA-anonymized sample, or public open data. No real producer PII enters the sandbox.

- Encryption at rest with KMS (AWS-managed keys acceptable); Secrets Manager for any secrets; least-privilege IAM per Lambda and for the AgentCore execution role.

- Bedrock Guardrails applied to agent model calls with a denied-topics / PII policy configured to flag, not block, so the review flow is exercised.

- CloudWatch Logs and AgentCore Observability retain every tool call and the agent's stated reasoning for the demo and for the handoff review.

- CloudTrail on by default in the sandbox. FTUSA production controls (Okta SSO, WAF, Organizations) are documented but not reproduced.
