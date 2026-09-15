# Handoff: Portfolio UX/UI Design Review & Mobile-First Modernization

**Target Tool / Role:** Claude (Design & UX Review)  
**Author:** Antigravity (Pair Programming Agent)  
**Audience:** Rob Bagley (Associate Director of Career Services, Ensign College)  
**Date:** September 9, 2026  
**Primary Focus App:** **Career Fair Coach** (`ensign-career-fair-coach` / port `5040`)  
**Secondary Scope:** Full Ensign College AI Suite Portfolio (`5010`, `5015`, `5020`, `5025`, `5030`, `5035`, `5045`, `5046`, `5050`)

---

## 1. Executive Summary & Objective

Rob wants **Claude** to analyze and design-audit the applications across his local AI agent portfolio, proposing tactile, high-impact **mobile-first UX/UI enhancements**. 

The goal is to elevate these apps from functional internal prototypes into polished, delightful, institutional-grade web applications that Ensign College students and mentors love using on their phones and laptops.

We are starting specifically with **Career Fair Coach** as the pilot app for this design pass.

---

## 2. Context & Repository Architecture

### Workspace Locations on Mac Studio
- **Career Fair Coach (Standalone)**: `/Users/robbagley/CCowork-Local-Apps/ensign-career-fair-coach`
  - GitHub: `https://github.com/robbagley-afk/ensign-career-fair-coach` (main branch)
  - Vercel Deployment ready: both `static/` and `public/` directories must always stay strictly in sync.
- **Monorepo**: `/Users/robbagley/CCowork-Local-Apps/AI AGENTS LOCAL LLM`
  - GitHub: `https://github.com/robbagley-afk/ai-agents-local-llm` (main branch)
  - Career Fair Coach directory inside monorepo: `Corey - Ensign Career Fair Coach/`
- **Active Port**: `http://127.0.0.1:5040/` (Reverse proxy on Tailscale Funnel at `/career-fair/`)

---

## 3. Career Fair Coach — Current Architecture & Interaction Flow

### Purpose
Career Fair Coach is an interactive coaching web app designed for Ensign College students preparing for the bi-annual campus Career Fair. It guides students through:
1. Researching employers attending the fair.
2. Developing their "Me in 30 Seconds" elevator pitch.
3. Practicing their pitch live against an AI recruiter persona (via text or on-device voice recording + transcription).
4. Generating smart, tailored questions to ask recruiters at company booths.

### Key Functional Components on the Page
1. **Top Navbar**:
   - Branding: "Career Fair Coach — ENSIGN COLLEGE"
   - Action: "🔄 New chat" button.
2. **4-Step Navigation Tabs**:
   - `[1] Research` | `[2] Me in 30s` | `[3] Practice` | `[4] Questions`
   - Switching steps switches the AI system prompt persona and injects contextual prompt suggestions.
3. **Handshake Quick Actions Bar**:
   - `Handshake ↗` (`https://ensign.joinhandshake.com/stu/schools/771`)
   - `Handshake Sign Up Help ↗` (`https://www.ensign.edu/creating-a-handshake-account`)
4. **Desktop Hero Banner**:
   - Photo banner of students engaging recruiters at an Ensign Career Fair (hidden on mobile `<860px` to conserve viewport space).
5. **AI Chat & Coaching Container**:
   - Chat feed with speech bubbles (Assistant green-tinted, Student dark green).
   - Horizontal suggestion chips (e.g. *"Help me create Handshake account"*, *"Research company coming to fair"*, *"Resume help"*).
6. **Voice Pitch Practice Module (Step 3)**:
   - Visual audio waveform canvas indicator.
   - 3-step action buttons: `(1) Start Recording` ➔ `(2) Stop / Done` ➔ `(3) Send Pitch to Coach`.
   - Client-side recording uses MediaRecorder API sending audio blobs to the local Whisper transcription endpoint (`/api/transcribe`), populating the composer.
7. **"Chat Here" Composer Guidance Bar & Textarea**:
   - Header bar with `💬 Chat Here` and microcopy: *"Type your message or edit transcribed voice pitch"*.
   - Rounded text input + prominent Send button.
8. **Bottom Callout & Admin Access**:
   - Orange Career Services booking callout button.
   - Discreet floating bottom-right `🔒 Admin` button (password `Sistergroom2026`) for reviewing and approving student feedback submissions.

---

## 4. Antigravity's Technical Baseline Verification

Before handing off, Antigravity completed a baseline mobile audit and initial fixes:
- **360px Viewport Zero-Overflow**: Ensured `scrollWidth == innerWidth` on narrow devices (iPhone SE / Galaxy S20).
- **Step Nav Grid**: Updated from rigid column widths to `grid-template-columns: repeat(4, minmax(0, 1fr))` with clean text truncation.
- **Header Flex**: Added wrapping rules to the top navigation and "Chat Here" indicator to prevent horizontal blowout.

---

## 5. Scope & Prompt for Claude: What to Design & Improve

Please review the code in `/Users/robbagley/CCowork-Local-Apps/ensign-career-fair-coach` (specifically `static/index.html`, `static/styles.css`, and `static/app.js`) and propose/implement **Mobile-First UX/UI Improvements**:

### Core Areas to Address for Career Fair Coach:
1. **Visual Hierarchy & Vertical Rhythm (Mobile Viewport)**:
   - How can we make the 4-step preparation flow feel like a seamless, gamified or guided progress wizard on mobile?
   - On a phone screen, between the header, steps, Handshake banner, and chat container, vertical space is precious. Evaluate whether sticky headers, collapsible accordions, or drawer patterns could optimize screen real estate.
2. **The Dual Input Dilemma (Voice vs. Text Composer)**:
   - When in Step 3 (Practice Mode), students see both the Voice Practice recording panel and the text chat composer.
   - Explore cleaner UX patterns: e.g. a toggle tab between `[🎙️ Voice Pitch]` and `[⌨️ Type Pitch]`, or an integrated audio recording button directly inside the chat composer bar (similar to iMessage / WhatsApp / ChatGPT mobile voice mode).
3. **Empty States & Onboarding Micro-interactions**:
   - When a student first opens the app, provide welcoming, high-confidence guidance without overwhelming them with text blocks.
   - Modernize suggestion chips with category pills, icons, and smooth horizontal scrolling or carousel snaps.
4. **Touch Ergonomics & Accessibility**:
   - Ensure all touch targets meet Apple HIG / Material 3 guidelines (minimum 44x44px or 48x48px).
   - Review font scale, contrast ratios against the Ensign Forest Green (`#004937` / `#006b4e`) palette, and haptic/visual feedback on button taps.
5. **Brand Polish & Emotional Design**:
   - Infuse modern touches: subtle glassmorphism (`backdrop-filter`), smooth spring transitions, refined typography (Inter / System font stack), and clean elevation shadows that feel native to iOS and Android.

---

## 6. Portfolio-Wide Design Context (For Future Phases)

Once Career Fair Coach is polished, Claude will extend these design conventions to the rest of the portfolio:
- **Major & Career Explorer Coach (Student & Mentor)** (`:5045`, `:5046`): Already features a carousel and video accordion; needs parallel UX sync.
- **Resume & Cover Letter Coach** (`:5010`): Document upload & Socratic critique interface.
- **Interview Practice** (`:5015`): Timed question prompt cards and microphone response flow.
- **Academic Advisor** (`:5030`): Degree audit tables, semester block schedule maps, and floating drawer AI chat.
- **ENS 101 Mentor Desk** (`:5050`): Mentor consultation checklist & appointment guide.

---

## 7. Operational Rules for Claude

1. **Vercel Double-Sync**: Always keep `static/` and `public/` files identical in `ensign-career-fair-coach`.
2. **Monorepo Double-Sync**: Also sync changes into `AI AGENTS LOCAL LLM/Corey - Ensign Career Fair Coach/`.
3. **Git Hygiene**: Run `git status`, commit with descriptive messages (`git commit -m "Career Fair Coach: mobile UX overhaul"`), and push.
4. **Process Restart**: After modifying Python or static files, restart via `.run/careerfair.pid` or `start_all_agents.sh`.
