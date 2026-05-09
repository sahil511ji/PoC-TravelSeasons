**EKAM APPS · INTERNAL**

**Travel Seasons**

Proof-of-Concept Brief

*Three PoCs to validate technical approach before the build*

| Owner | Nitin Gupta · Ekam Apps |
| :---- | :---- |
| **Audience** | Internal — developer working on Travel Seasons app |
| **Client** | Travel Seasons Pvt Ltd |
| **Date** | 9 May 2026 |
| **Phase** | Pre-build (Proof of Concept) |
| **Outcome** | Confirm technical feasibility and tooling choices for three risky features |

# **1\. Project background**

Travel Seasons is a tour operator focused on senior travellers (60+). They run curated group tours and FIT (private) trips across India and abroad — roughly 50 trips a year, average group size 20\.

We at Ekam Apps are building their mobile app and admin console. The customer-facing app is a senior-friendly trip companion: pre-trip planning, live in-trip experience, post-trip memories, and a loyalty programme. The admin console handles trip management, customer 360, payments (offline), and content.

After our 8 May 2026 alignment meeting with Travel Seasons, three features stood out as needing focused PoC work — they involve approaches we have not built before in this combination, and we want to validate the technical path before committing to the production build.

### **Why we are doing PoCs**

* Validate that each feature is technically feasible with the tools we'd pick

* Confirm the right service/API choice for each (e.g. Rekognition vs alternatives)

* Surface UX trade-offs we'd have to accept (e.g. AI video quality)

* Discover edge cases that would otherwise hit us in the build phase

* Establish the integration pattern (auth, storage, callbacks) so the build is mechanical

*These are not throwaway prototypes. We expect to lift code from these PoCs into the production build, so write them with that in mind — but PoC quality, not production quality. Don't over-engineer.*

# **2\. Common context for all PoCs**

| Aspect | Detail |
| :---- | :---- |
| End users | 60+ senior travellers, low tech-comfort, high trust in TS team |
| Geography | India-based business and customers; data residency in India preferred |
| Compliance | DPDP Act 2023 applies to all PII (passports, photos, contact details) |
| Languages | English in V1; Hindi added later |
| Platforms | iOS \+ Android (cross-platform OK; final stack TBD post-PoC) |
| Cloud preference | AWS Mumbai (ap-south-1). Open to alternatives if justified. |
| Existing prototype | https://travelseasons.ekamapps.com/v2/ — wireframes for all flows |

### **What is in scope for every PoC**

* A working demo (live link or recorded video walkthrough)

* Source code in a private repo with a clear README

* Brief written observations: what surprised you, what's risky, what you'd change

* Open questions you need answered before the production build can start

### **What is NOT in scope for any PoC**

* Production-grade error handling, observability, monitoring

* Final UX polish — wireframes already exist in the prototype

* Test coverage beyond "it works" (unit/integration tests come later)

* Backend at production scale — local or single-instance is fine

* App-store submission, code signing, CI/CD

# **3\. PoC 1 — AI Daily Recap Video Pipeline**

*Feature IDs: F102 (customer side), A033 (admin video review)*

### **Why**

Each evening of a trip, we want to publish a short (20-40 second) recap video to the customer's "Live trip" view in the app. The video summarises that day's highlights — places visited, group photos, a brief voiceover, gentle music.

The Tour Manager (TM) uploads raw footage and photos throughout the day. AI cuts it into something watchable. An admin reviews and approves before the customer sees it. Customers only see published videos.

### **Business value**

* Daily emotional touchpoint during the trip — high delight

* Reusable as marketing asset (with consent) — content team gets free reels

* Differentiator vs other senior-tour operators — no one in India does this

### **What we are testing with this PoC**

* Is AI-generated video quality acceptable for a senior audience that judges on "feels personal"?

* How much TM upload effort is realistic in the field (slow internet, mobile only)?

* Total turnaround from raw clips to published video?

* Which pipeline tool gives us the best output quality with the least custom code?

### **Goal of the PoC**

Take 20-30 raw clips (mix of phone videos \+ photos, \~2-5 min total raw material) from one tour day. Produce a 30-second narrated recap that we'd be willing to ship to a paying customer.

Show the full pipeline:

* TM uploads media (REST endpoint OK; mobile-friendly UI is a bonus)

* Backend processes: scene cuts, voiceover, music, captions

* Admin reviews video at "approve / regenerate / reject" level

* On approve, video is hosted, URL surfaced via API

### **Suggested approach**

Pick one of these stacks. We are testing feasibility and output quality, not engineering range.

| Option | How | Pros | Cons |
| :---- | :---- | :---- | :---- |
| **A · Shotstack (recommended)** | API-first video editing. Submit a JSON timeline, get rendered MP4 back. Pair with ElevenLabs/Google TTS for voiceover. | Predictable output. Mature. Fast iteration. Pay-per-render only. | You build the AI logic that generates the timeline. |
| **B · RunwayML / Pika** | Generative video models — full video from prompt \+ clips. | Less custom logic. Higher "wow" potential. | Slow, generation cost varies, quality unpredictable. |
| **C · FFmpeg \+ custom Python** | Open-source. OpenCV scene detection, Whisper transcription, TTS for voice. | Full creative control. No third-party rendering dependency. | Significantly more custom code. Infra maintenance forever. |

Recommendation: try Option A first. Fall back to C only if Shotstack output is not acceptable. Avoid B — too unpredictable for our use case.

### **Acceptance criteria**

* One end-to-end run from raw clips to a published video URL

* Video is at least "watchable" — not jarring cuts, decent audio level, basic visual coherence

* Admin review UI exists, even if rough — preview, approve, reject, regenerate buttons

* Pipeline can be re-run with new footage and produce a different recap

### **Out of scope for this PoC**

* Multi-language voiceover

* Face-aware cuts (always include the lead traveller's face)

* Music licensing for production — placeholder royalty-free track is fine

* Auto-captioning in regional languages

* Mobile upload UI for TM — web/REST upload acceptable

### **Deliverables**

* Working backend pipeline in one repo, with README on how to run

* Sample video output from real footage (we will provide \~30 clips from a Bhutan trip)

* Notes on output quality — what works, what looks artificial, what we'd accept

* Risk register: top 3 things that could go wrong in production

* Open questions for client decision (music style, voiceover gender, length)

# **4\. PoC 2 — Photo Gallery with Face Tagging**

*Feature IDs: A021-A024 (admin photo upload, AI tagging, distribution, retention), F018, F073, F081*

### **Why**

At the end of every tour, the TM has 200-500 photos shared across travellers. Today these get sent on WhatsApp or shared as one big folder. Customers complain they cannot easily find "photos of me" or "photos of my parents on this trip."

We want a Google-Photos-like experience: bulk admin upload, AI tags faces, each customer sees a personal album of "photos of me" plus a group view of "all photos from this trip."

### **Business value**

* Major delight feature — proven pattern in similar apps

* Easier WhatsApp shares \= organic marketing

* Foundation for AI recap reel (PoC 1\) — same face data feeds it

* Photos drive return-to-app behaviour months after the trip

### **What we are testing with this PoC**

* Face recognition accuracy on our user profile (Indian faces, mixed ages, varied lighting)

* Edge cases: group photos, look-alikes (e.g. siblings), poor selfies

* Privacy and consent flow under DPDP Act 2023 — what does the UX look like?

* End-to-end pipeline shape (upload → process → tag → display)

### **Goal of the PoC**

Demonstrate end-to-end:

* Customer uploads a selfie (existing PIF photo) → enrolled in face collection

* Admin uploads \~50-100 trip photos in bulk

* Backend detects faces in each photo, matches to enrolled customers

* Customer app shows: "Photos of you" filtered view \+ "All trip photos" group view

* Admin can override mis-tags (e.g. wrong face matched)

### **Suggested approach**

AWS Rekognition, strongly recommended. India region (ap-south-1) for data residency.

### **Stack**

* Storage: AWS S3 for originals, CloudFront for thumbnail delivery

* Metadata: DynamoDB or Postgres — photoId → tripId, userIds\[\], confidence scores

* Face matching: Rekognition Face Collections, IndexFaces and SearchFacesByImage APIs

* Processing: S3 PUT trigger → Lambda → Rekognition → metadata write — fully async, no UI blocking

* Frontend: re-use existing photo-album.html and admin/photos.html designs from prototype

### **Why NOT Google Vision or Azure**

* Google Cloud Vision dropped face identification capability

* Azure Face API restricted face identification to existing/approved customers since 2022

* Open-source alternatives (face\_recognition, InsightFace) are options if cloud is forbidden, but add significant infra work

### **Acceptance criteria**

* 5 test users enrolled with selfies of different ages and lighting conditions

* 100 trip photos uploaded and processed

* Each test user sees a correctly filtered "photos of me" view

* Confidence threshold tunable; reported on false positives and false negatives

* One admin override flow works (untag a wrong match)

* DPDP-aligned: explicit consent shown before face enrollment, deletion endpoint exists

### **Out of scope for this PoC**

* Production-grade upload UI — rough is OK

* Bulk download or WhatsApp share — just show in-app

* 90-day photo retention auto-delete (note implementation in README, don't actually run it)

* Mobile upload from TM device

* Auto-rotate, photo quality scoring, "best of" sorter

### **Deliverables**

* Working backend (S3 \+ Lambda \+ Rekognition \+ metadata DB)

* Simple admin web page for upload \+ tagging review

* Customer app demo screen (web is fine, doesn't need to be native)

* Test report: 100 photos × 5 users → accuracy percentage and edge cases observed

* DPDP compliance checklist: what's done, what's pending

* Risk register and open questions

# **5\. PoC 3 — Travel Games**

*Feature IDs: F101 (Travel Games), F084 (loyalty wallet integration)*

### **Why**

At the May 8 meeting we dropped most of the in-trip distractions — no SOS, no nearby places, no live menu translator. What stays in-trip is: AI daily video, destination guide, photos.

We identified an off-trip engagement opportunity instead — light games to keep the app top-of-mind between trips. Senior users have time, and travel-themed games reinforce the brand.

### **Business value**

* Ongoing engagement between trips — drives DAU

* Loyalty credit hook — score 4/5+ → \+50 credits, builds streak habit

* Travel-themed quizzes hint at destinations users haven't visited yet — soft marketing

### **Constraints**

* Senior-friendly: no timers, no popups, no ads, large fonts (16px+), high contrast

* Travel-themed where possible (reinforce TS brand)

* Earn loyalty credits on streaks — must integrate with the existing wallet

### **What we are testing with this PoC**

* Build in-house vs license a game SDK (we lean in-house, but want to confirm)

* Which free APIs power travel-themed quizzes well

* Engagement pattern — what does a senior user actually play?

* Loyalty integration end-to-end (mocked wallet OK)

### **Goal of the PoC**

Build TWO working games to a level we'd ship:

* Guess the Flag — multi-choice quiz with real flags via REST Countries API

* Cuisine Quiz — "this dish is from?" with photos via TheMealDB API

Plus integrate with a placeholder loyalty wallet — score ≥4/5 → \+50 credits, with a daily-streak bonus mocked at the API level.

Existing prototype game-flags.html is a non-functional mockup — treat as starting design only, replace with real API-driven version.

### **Suggested approach**

Recommended: build in-house. React or React Native components, free public APIs. No SDK lock-in, full control of UX.

### **APIs to use**

* https://restcountries.com/v3.1/all — country names, flags, capitals, currencies (free, no key)

* https://flagcdn.com/w320/{cca2}.png — flag image CDN, fast

* https://www.themealdb.com/api/json/v1/1/filter.php?a=Indian — cuisines (free, no key)

* Cache locally on first launch (\~250 KB), works offline after

### **Loyalty integration**

* POST to mock wallet endpoint on game completion: { userId, gameId, score, creditsAwarded }

* Response shows updated balance \+ streak count

* Idempotency key — same user can't double-claim by replaying

### **Alternative if in-house doesn't pan out**

GameDistribution iframe SDK (free, ad-supported). Not recommended for senior UX, but listed as fallback.

### **Acceptance criteria**

* Both games work end-to-end (5 questions each, with replay)

* Real API data, no hardcoded questions

* Score tracking, replay button, "view answers" review screen

* Loyalty credits awarded on score ≥4/5 (mocked endpoint OK)

* Offline mode: games still work after first load (cache hit)

* Senior-friendly: 16px+ fonts, high contrast, touch targets ≥44px

### **Out of scope for this PoC**

* Multiplayer or social features

* Difficulty levels (just one level)

* Backend leaderboard

* Music or sound effects

* More than 2 games (we'll add 4 more later)

* Native iOS/Android — web/PWA is fine for the PoC

### **Deliverables**

* Both working games as a single-page web app or React Native screens

* README with API integrations explained

* Performance note: load time, offline behaviour, cache size

* Engagement hypothesis: "We expect senior users will play X times/week because Y"

* Risk register and open questions

# **6\. Common deliverables across all PoCs**

For each PoC, please deliver the following:

* Live demo link (Vercel/Netlify/local-tunnel) OR a recorded screen capture (5-min walkthrough)

* Source code in a private GitHub repo with a clear README and run instructions

* Risk register — top 3 things that could blow up in production with proposed mitigation

* Open questions — anything where you need our (Ekam Apps \+ TS) decision before building further

* Notes on what surprised you, what was easier than expected, what felt risky

### **Format expectations**

* README in the repo answers: setup, run, expected output

* Risk register as a list with severity (high/medium/low) and proposed mitigation

* Send all deliverables via WhatsApp summary \+ repo link

# **7\. Suggested order and working style**

### **Order to do them in**

Do them in this order — quick wins first, builds confidence, surfaces blockers early.

* PoC 3 — Games. Quick win, validates the API approach, gives client something visible early.

* PoC 2 — Photo gallery \+ face tagging. Standard cloud build. Surfaces DPDP compliance work.

* PoC 1 — AI daily video. Most complex, highest unknown, gets the most focused attention.

### **Communication**

* Daily standup over WhatsApp text (no calls needed unless blocked)

* Demo as soon as a PoC is done — don't batch all three

* Blockers: flag immediately on WhatsApp, don't sit on them

### **What I am trying to avoid**

* "It works on my machine" demos with no clarity on what's real vs mocked

* Choosing fancy tech for engineering interest rather than fitness for purpose

* Spending time polishing PoC UI when wireframes already exist in the prototype

* Surprises in the production build because we missed something obvious during PoC

*The PoCs are about de-risking the build, not about being beautiful.*

# **8\. Reference material**

* Prototype gallery: https://travelseasons.ekamapps.com/v2/

* Repo: https://github.com/Ekam-Apps/travel-seasons-prototype

* Feature list (Excel): TravelSeasons\_App\_Feature\_List.xlsx — shared separately

* May 8 2026 meeting notes: shared separately

* Existing customer-side designs: see prototype/v2/ in the repo

* Existing admin designs: see prototype/v2/admin/ in the repo

### **Useful links per PoC**

**PoC 1 (AI video):**

* Shotstack: https://shotstack.io/docs/api/

* ElevenLabs TTS: https://elevenlabs.io/docs

* FFmpeg: https://ffmpeg.org/

**PoC 2 (Photo \+ face):**

* AWS Rekognition: https://docs.aws.amazon.com/rekognition/

* DPDP Act 2023 summary: https://www.meity.gov.in/data-protection-framework

**PoC 3 (Games):**

* REST Countries: https://restcountries.com/

* TheMealDB: https://www.themealdb.com/api.php

* Open Trivia DB: https://opentdb.com/

* FlagCDN: https://flagcdn.com/

*Questions? WhatsApp Nitin directly. Don't sit on a blocker — flag it the moment you hit it.*