# Corporate RM AI Assistant

## Overview

This repository demonstrates an AI-powered deal readiness and mandate fit assistant designed for Corporate and Wholesale Relationship Managers.

The tool consolidates existing credit ratings (Credit Lens / Moody’s), eligibility criteria, strategic sector priorities, and high-level financial signals into a single, RM-friendly view.

Through a guided interface and natural-language AI interaction, the solution helps RMs quickly understand:

- Whether a deal aligns with EDB’s mandate
- Why it does or does not fit today
- What actions could improve deal readiness

The solution is intended for front-office productivity and decision support only and does not replace existing credit or risk approval systems.

---

## What this solution does

- Consolidates rating, eligibility, and sector alignment into a single deal summary
- Interprets financial performance using RM-friendly signals (not raw analysis)
- Highlights mandate fit, strengths, and gaps
- Provides RM action guidance to progress or reshape deals
- Enables natural-language Q&A over deal readiness
- Improves origination efficiency and consistency for Corporate RMs

---

## Intended users

- Relationship Managers / Business teams – early deal assessment and preparation
- Credit Analysts – structured inputs, risk drivers, and consistency
- Risk / Portfolio teams – transparency and future monitoring use cases

---

## Solution architecture (high level)

Input
- Credit ratings from Credit Lens / Moody’s
- Eligibility score (0–6) and strategic sector classification
- High-level financial signals (trend-based)
- Qualitative RM inputs (optional)

Deal Summary Engine
- Interprets rating, eligibility, sector alignment, and financial signals
- Identifies deal strengths, constraints, and mandate alignment
- Produces a structured Deal Summary object

AI-assisted outputs
- Deal readiness classification (Strong / Conditional / Weak)
- Mandate fit and eligibility interpretation
- RM action guidance and talking points
- Natural-language Q&A over deal readiness

Interface
- Web-based RM interface (React + Vite)
- FastAPI backend
- Single-URL serving option

---

## AI Reasoning & Decision Support Logic

The solution does not generate or replace formal credit ratings.

Instead, it uses AI-driven reasoning to interpret existing rating outputs, eligibility scores, strategic sector alignment, and financial signals to produce a structured Deal Summary.

This Deal Summary forms the basis for:

- Deal readiness classification
- Identification of key constraints and strengths
- RM-focused guidance and talking points
- Natural-language AI responses

All outputs are advisory and designed to support front-office discussions and preparation.

---

## Governance and controls

- Decision-support only; no automated approvals
- Human review required for all outputs
- Explainable risk drivers for transparency
- Model versioning and validation required prior to production use
- Designed for alignment with internal credit policy and MRM frameworks

---

## Key features
- Consolidated deal readiness summary for Corporate RMs
- Eligibility and strategic sector alignment insights
- Financial performance interpretation using RM-friendly signals
- Identification of deal strengths and constraints
- RM action guidance to improve deal readiness
- Natural-language Q&A for deal explanation and preparation
- Input validation and safety controls

---

## Technology stack

Backend: FastAPI
- Core endpoints: /score, /demo/score

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

## AI Challenge context

This project demonstrates how AI can be practically embedded into a
Corporate and Wholesale Banking workflow to improve front-office productivity.

The solution focuses on:
- Faster deal screening and preparation
- Improved consistency in mandate alignment assessment
- Better RM readiness for internal and client discussions
- Responsible use of AI for interpretation and guidance, not decision-making

The emphasis is on usability, clarity, and governance-aware design.

---

📜 License

MIT



