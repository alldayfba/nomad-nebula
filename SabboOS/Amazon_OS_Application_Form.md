# Amazon OS / 24/7 Profits Inner Circle — Application Form Spec

Post-webinar application form for the Amazon OS coaching program. Collects applicant info, qualifies leads automatically, and routes to the correct next step.

---

## Form Fields

| # | Field | Type | Required | Options / Notes |
|---|---|------|----------|-----------------|
| 1 | **Full Name** | text | Yes | — |
| 2 | **Email** | email | Yes | — |
| 3 | **Phone** | tel | Yes | Helper text: "We'll text you confirmation, not spam" |
| 4 | **Current Amazon Experience** | dropdown | Yes | See options below |
| 5 | **Available Capital to Invest** | dropdown | Yes | See options below |
| 6 | **What's your biggest challenge or goal with Amazon?** | textarea | Yes | Max 500 characters |
| 7 | **How did you hear about us?** | dropdown | No | See options below |
| 8 | **Are you ready to invest in yourself and start within the next 30 days?** | radio | Yes | See options below |

### Field 4 — Current Amazon Experience

- "Complete beginner — haven't started yet"
- "I have an Amazon account but haven't sold"
- "Selling but under $5K/month"
- "Selling $5K-$20K/month"
- "Selling $20K+/month"

### Field 5 — Available Capital to Invest

- "Under $3,000"
- "$3,000 - $5,000"
- "$5,000 - $10,000"
- "$10,000 - $20,000"
- "$20,000+"

### Field 7 — How did you hear about us?

- "Webinar"
- "YouTube"
- "Instagram"
- "TikTok"
- "Friend/Referral"
- "Other"

### Field 8 — Ready to Invest?

- "Yes — I'm ready to start"
- "Maybe — I have questions"
- "Just exploring"

---

## Qualification Criteria (Internal — NOT shown to applicant)

### Auto-Qualify (Green — Book Immediately)

| Condition | Requirement |
|-----------|-------------|
| Capital | >= $5,000 |
| Experience | Any level |
| Ready | "Yes — I'm ready to start" OR "Maybe — I have questions" |

Action: Redirect to calendar booking page immediately.

### Warm Lead (Yellow — Nurture)

| Condition | Requirement |
|-----------|-------------|
| Capital | $3,000 - $5,000 |
| Ready | "Maybe — I have questions" OR "Just exploring" |

Action: Send to nurture sequence. Do NOT book a call yet.

### Disqualify (Red — Do NOT Book)

| Condition | Requirement |
|-----------|-------------|
| Capital | Under $3,000 |

Action: Send to free content funnel, NOT a sales call. Show resource page instead.

---

## Post-Submit Routing

### Qualified (Green)

Redirect to calendar booking page (Cal.com embed or Calendly link).

**Page message:**
> "You're qualified! Book your free strategy call below."

### Warm (Yellow)

Redirect to confirmation page.

**Page message:**
> "Thanks for applying! We'll review your application and reach out within 24 hours."

### Disqualified (Red)

Redirect to free resources page.

**Page message:**
> "Thanks for your interest! Here are some free resources to get started..."

Include links to:
- YouTube channel
- Free training content
- Starter guides

---

## Form Design Notes

- **Layout:** Progressive disclosure (one question at a time, Typeform-style) OR clean single-page form
- **Mobile-first:** Fully responsive, optimized for phone completion post-webinar
- **Progress bar:** Visible at top showing completion percentage

### Brand Colors

| Element | Color | Hex |
|---------|-------|-----|
| Background | Dark purple | `#1A0A2E` |
| Text | White | `#FFFFFF` |
| Accent / Buttons | Purple | `#6B2FA0` |
| CTA highlight | Gold | `#FFD700` |

### Trust Element

Below the form, display:

> "Your information is 100% private. We'll never share it."
