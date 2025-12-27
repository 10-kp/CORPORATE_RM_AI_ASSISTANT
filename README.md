# Corporate RM Deal Readiness & Mandate Fit Assistant

🔗 **Live demo:** https://corporate-rm-ai-assistant.onrender.com/

---

## Overview

This repository contains an AI-powered **Deal Readiness & Mandate Fit Assistant** designed for **Corporate and Wholesale Relationship Managers (RMs)**.

The tool supports **early-stage deal screening and preparation** by consolidating:
- Existing credit ratings (e.g. Credit Lens / Moody’s)
- Eligibility and strategic sector alignment
- High-level financial signals
- Qualitative RM inputs

into a **single, structured, and explainable deal summary**.

> ⚠️ **Important:**  
> This is a **decision-support prototype for Relationship Managers**.  
> It does **not** generate credit ratings, approve facilities, or replace risk or credit committees.

---

## What problem this solves (for judges & beginners)

In Corporate Banking, RMs often:
- Rely on fragmented information across systems
- Struggle to articulate *why* a deal fits or does not fit mandate
- Spend time reworking deals late in the approval process

This assistant helps RMs **earlier**, by answering:
- *Is this deal aligned with the bank’s mandate?*
- *What are the key strengths and constraints today?*
- *What needs to improve before formal credit submission?*

---

## What the solution does

- Produces a **Deal Readiness classification** (Strong / Conditional / Weak)
- Interprets eligibility and sector alignment
- Translates financial performance into **RM-friendly signals**
- Highlights **key strengths and constraints**
- Generates **RM action guidance** to progress or reshape the deal
- Enables **natural-language Q&A** over deal readiness and risks

All outputs are **explainable, transparent, and advisory**.

---

## Intended users

- **Relationship Managers**  
  Early deal screening, mandate alignment, client discussions

- **Credit / Risk teams**  
  Structured inputs, consistent framing, transparency

- **Management / Portfolio teams**  
  Standardised front-office assessment signals

---

## How it works (high-level)

### 1. Inputs
- Credit rating anchor (external or internal)
- Eligibility score (0–6) and strategic sector
- High-level financial signals (trend-based, not raw modelling)
- Optional qualitative RM notes

### 2. Deal Summary Engine
- Interprets mandate alignment and financial signals
- Identifies strengths, constraints, and readiness
- Produces a structured **Deal Summary object**

### 3. AI-assisted outputs
- Deal readiness classification
- Mandate fit explanation
- RM action guidance
- Natural-language Q&A for preparation and discussion

---

## AI reasoning & governance

The AI layer **does not replace credit analysis**.

It is used to:
- Interpret structured inputs
- Generate consistent explanations
- Support RM understanding and communication

### Governance principles
- Decision-support only (no automated approvals)
- Human review required
- Explainable drivers surfaced
- Designed for alignment with internal credit policy and MRM frameworks

---

## Technology stack (simple explanation)

**Frontend**
- React + Vite
- Single-page RM interface
- Input validation and guardrails

**Backend**
- FastAPI
- Structured assessment endpoints
- AI explanation and Q&A endpoints

**Deployment**
- Single-URL web service
- Production-style SPA + API setup

---

## Repository structure

```text
.
├── api/                 # FastAPI backend
├── frontend/            # React (Vite) UI
├── notebooks/           # Analysis and experimentation
├── src/                 # Domain logic (deal summary, signals)
├── configs/             # Configuration placeholders
├── .github/workflows/   # CI pipeline
├── README.md
├── requirements.txt

```

## License

MIT

