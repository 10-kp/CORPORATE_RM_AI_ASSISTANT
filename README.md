# AI-Enabled SME Credit Decision Support Tool
(FastAPI + React, Single-URL Deployment)

## Overview

This repository demonstrates an AI-enabled SME credit assessment solution designed to support Business and Credit teams during early-stage deal evaluation.

The tool estimates Probability of Default (PD), highlights key risk drivers, and generates structured inputs for credit write-ups through a simple web interface.

The solution is designed as a decision-support tool only. All credit decisions remain with authorized approvers.


---

## What this solution does

- Estimates SME Probability of Default (PD)
- Highlights key drivers of credit risk
- Supports deal pre-screening for Relationship Managers
- Generates structured narrative inputs for credit memoranda
- Provides a usable web interface suitable for internal deployment
- Supports single-URL deployment for simplified IT integration

---

## Intended users

- Relationship Managers / Business teams – early deal assessment and preparation
- Credit Analysts – structured inputs, risk drivers, and consistency
- Risk / Portfolio teams – transparency and future monitoring use cases

---

## Solution architecture (high level)

Input
- Financial and business data (manual entry; document extraction supported by design)

Analytics
- PD scoring engine (baseline implementation)
- Transparent risk-driver logic
- Modular design for ML PD models and explainability

AI-assisted outputs
- Risk driver summaries
- Structured credit narrative inputs
- Product and covenant suggestions (rule-based)

Interface
- Web-based UI (React + Vite)
- FastAPI backend
- Single-URL serving option

---

## Model overview
The current implementation includes a baseline PD scoring engine with transparent risk drivers and a modular architecture that allows:

- Integration of calibrated ML-based PD models (e.g. LightGBM)
- Addition of explainability techniques (e.g. SHAP)
- Scenario and sensitivity analysis extensions

Model interfaces, inputs, and outputs are intentionally designed to align with banking Model Risk Management (MRM) standards and to support future validation and production hardening.

---

## Governance and controls

- Decision-support only; no automated approvals
- Human review required for all outputs
- Explainable risk drivers for transparency
- Model versioning and validation required prior to production use
- Designed for alignment with internal credit policy and MRM frameworks

---

## Key features
- PD estimation with risk banding
- Top risk driver identification
- Structured credit narrative generation
- Product and covenant recommendations
- Input validation and safety controls
- Optional authentication for non-demo paths

---

## Technology stack

Backend: FastAPI
- Core endpoints: /score, /demo/score, /auth/login

Frontend: React + Vite
- Single-page wizard UI
- Input validation using Zod

Auth: JWT (email/password)
- Demo paths do not require authentication

Safety:
- Rate limiting
- CORS restrictions

Deployment:
- Two-server (dev) or single-URL deployment (production-style)

---

📂 Repo layout

```
.
├── api/                 # FastAPI backend
├── frontend/            # React (Vite) UI
├── notebooks/           # Data analysis and model development
├── src/                 # Model and scoring logic
├── configs/             # Configuration placeholders
├── .github/workflows/   # CI pipeline
├── README.md
├── README-QUICKSTART.md
└── requirements.txt

```

---

## Running the demo
For quick setup and local execution, follow:

README-QUICKSTART.md

No MLOps or cloud deployment is required to run the prototype locally.

---

AI Challenge context

This project demonstrates how ML and AI techniques can be practically embedded into an SME credit workflow to:

- Reduce preparation time
- Improve consistency of submissions
- Increase transparency of risk assessment
- Provide a scalable foundation for future enhancements

The focus is on practical usability and governance-aware design, rather than academic modeling

---

📜 License

MIT



