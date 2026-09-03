# 🎓 Ensign College Career Fair Coach AI

A mobile-first AI coach built specifically for Ensign College students preparing for career fairs.

## 🎯 Key Features
- **4 Preparation Modes**:
  1. **Employer Research**: Analyze company and role details.
  2. **Me in 30 Seconds**: Draft and polish an authentic personal introduction.
  3. **Recruiter Role-Play**: Interactive back-and-forth practice with a realistic recruiter.
  4. **Recruiter Questions**: High-impact questions to ask company reps.
- **Privacy First**: Built-in guardrails block SSNs, credit cards, and credentials before reaching the model.
- **Interactive Feedback**: Anonymous 👍 Helpful / 👎 Suggested Improvement feedback store.
- **Dual Runtime**: Runs locally via `python3 app.py` and globally on Vercel Serverless Edge CDN.

## 🚀 1-Click Vercel Deployment
1. Import this repository in Vercel.
2. Set Environment Variables:
   - `GEMINI_API_KEY`: *(your Google AI Studio key)*
   - `GEMINI_MODEL`: `gemini-2.5-flash`
3. Deploy!
