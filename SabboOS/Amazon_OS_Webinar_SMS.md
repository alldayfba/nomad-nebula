# Amazon OS — Webinar SMS Sequences
> **Total Messages:** 8
> **CRM:** GoHighLevel (GHL)
> **Merge Fields:** {{first_name}}, {{webinar_link}}, {{replay_link}}, {{application_link}}
> **Brand:** 24/7 Profits — AI Amazon Scaling
> **Last Updated:** 2026-03-23

---

## Timing Table

| # | Message | Trigger | Delay | Segments |
|---|---------|---------|-------|----------|
| S1 | Pre-webinar reminder | Registration | -24 hours before event | 1 |
| S2 | 2-hour reminder | Event time | -2 hours | 1 |
| S3 | 15-min reminder | Event time | -15 minutes | 1 |
| S4 | Attended follow-up | Webinar ended (attended) | +30 minutes | 1 |
| S5 | No-show follow-up | Webinar ended (no-show) | +1 hour | 1 |
| S6 | Replay urgency | Webinar ended | +24 hours | 1 |
| S7 | Pre-call confirm | Call booked | -24 hours before call | 1 |
| S8 | Morning-of confirm | Call booked | Morning of call day | 1 |

---

## Messages

### S1 — Pre-Webinar, 24 Hours Before
**Trigger:** Registration confirmed, fires 24 hours before event start

```
{{first_name}}! Quick reminder — AI Amazon training TOMORROW 8PM EST. Save your spot: {{webinar_link}}
```
_Characters: ~105_

---

### S2 — Pre-Webinar, 2 Hours Before
**Trigger:** 2 hours before event start

```
We go live in 2 hours! Join 100+ people learning the AI Amazon system tonight: {{webinar_link}}
```
_Characters: ~93_

---

### S3 — Pre-Webinar, 15 Minutes Before
**Trigger:** 15 minutes before event start

```
Starting in 15 min! Jump in now: {{webinar_link}}
```
_Characters: ~50_

---

### S4 — Post-Webinar (Attended), +30 Minutes
**Trigger:** Webinar ended, registrant marked as attended, +30 min delay

```
Thanks for showing up tonight! Replay + bonuses (expires 48hrs): {{replay_link}}
```
_Characters: ~78_

---

### S5 — Post-Webinar (No-Show), +1 Hour
**Trigger:** Webinar ended, registrant did NOT attend, +1 hour delay

```
Missed the training? No worries — replay is live for 48hrs: {{replay_link}}
```
_Characters: ~72_

---

### S6 — Post-Webinar, +24 Hours
**Trigger:** 24 hours after webinar ended (all registrants)

```
Replay of the AI Amazon training expires tomorrow. Watch before it's gone: {{replay_link}}
```
_Characters: ~87_

---

### S7 — Pre-Call, 24 Hours Before
**Trigger:** Strategy call booked, fires 24 hours before scheduled call
**Merge field:** {{call_time}} — pull from GHL calendar booking

```
{{first_name}} — strategy call tomorrow at {{call_time}}. Still good? Reply YES to confirm
```
_Characters: ~85_

---

### S8 — Pre-Call, Morning Of
**Trigger:** Morning of call day (9:00 AM local time)
**Merge field:** {{call_time}} — pull from GHL calendar booking

```
{{first_name}}! It's Sabbo from 24/7 Profits. We still good for {{call_time}} today?
```
_Characters: ~78_

---

## GHL Implementation Notes

1. **Workflow setup:** Create one GHL workflow per trigger type (registration, event start, event end, call booked)
2. **Branching:** S4 vs S5 requires an attended/no-show tag or custom field — set this via webinar platform webhook (e.g., EverWebinar, WebinarKit)
3. **Merge fields:** Ensure {{webinar_link}}, {{replay_link}}, and {{call_time}} are mapped as custom contact fields in GHL
4. **Send window:** Restrict all SMS to 9 AM - 9 PM recipient local time (TCPA compliance)
5. **Phone number:** Use a local or toll-free number registered with A2P 10DLC campaign

## Compliance

- All messages must include opt-out language in the initial registration confirmation (not in every SMS)
- Registration confirmation (separate from this sequence) must include: _"Reply STOP to unsubscribe. Msg&data rates may apply."_
- Honor all STOP replies immediately — GHL handles this automatically when configured
- Maintain consent records: registration form = express written consent for SMS
