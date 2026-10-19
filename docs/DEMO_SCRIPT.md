# Demo video script, 3–5 minutes (live run, no slides)

**Setup before recording**
- Terminal in the `triage-agent` folder, font size 16+, dark theme. Run `rm -r out` (or delete the `out` folder) first.
- `GEMINI_API_KEY` already set in this terminal. Don't show it on screen.
- Second window: VS Code with `triage_agent/tools.py` and `guardrails.py` open.
- Record with OBS Studio or Loom (free), mic on. Upload to YouTube as **Unlisted**.

| Time | On screen | What to say (your own words; this is a guide) |
|---|---|---|
| 0:00–0:25 | README top | "This is TriageAgent. My inbox mixes paying clients, campus notices, GitHub alerts and lots of promo mail. Every morning I lost time finding the two emails that mattered. This agent sorts them, drafts replies, and sends me one short briefing, and it never sends anything on its own." |
| 0:25–0:45 | `fixtures/inbox_sample.json` scrolled | "For the demo I'm using a sample inbox of ten emails that mirror my real one: a client bug, a quote request, an exam notice, a phishing mail, newsletters." (With Gmail set up: "this is my real inbox, read-only.") |
| 0:45–1:45 | Run `python -m triage_agent --provider gemini --verbose` | Narrate while it runs: "Each email goes through a security check first, then the model returns strict JSON: category, summary, deadline, whether to reply. Here the client bugfix is URGENT_CLIENT with tomorrow 9 AM as the deadline, and it drafted a reply. The phishing email went straight to SUSPICIOUS, and the model wasn't even asked." |
| 1:45–2:30 | Briefing output + open `out/drafts/m01.txt` and `out/tasks.json` | "This is what I'd get on Telegram at 8:30: security first, then clients by deadline, then campus. Newsletters are collapsed into one line. The drafts are just files or Gmail drafts. I read them and press send myself." |
| 2:30–3:15 | `tools.py`, then `guardrails.py` (`safe_draft`) | **Design decision:** "Safety is in the code, not just the prompt. There's no send, delete or open-link function at all, so the agent can't do those even if a prompt tricks it. And if a client asks about price or a delivery date, any draft that commits to a number is replaced with a neutral 'I'll reply personally', and the email is flagged for me." Show the Budi quote email: draft is neutral, flag `contract_change`. |
| 3:15–3:50 | Run `python -m evals.run_evals --provider gemini` | "I test it on 12 cases, the 5 from my design plus 7 I added after building. It checks categories and which tools ran, and that no password or price leaks into a draft. With Gemini it scores 12 out of 12, while the rules-only baseline gets 11." (Re-run on camera; say the number you actually see.) |
| 3:50–4:30 | `evals/RESULTS_rules.md`, TC-07 row | **Limitation:** "The rules baseline gets 11 of 12. It misses this one, a client sending staging access with no obvious client words. That's why the model is there for intent. Another limit: my test set is 12 hand-written emails, not a month of real mail, so I treat the score as 'the logic works', not 'it's always right'. The Gmail permission is also broader than I'd like." |
| 4:30–4:50 | README "How AI was used" | "I built this with Claude from my own design spec. I chose the categories, guardrails and tests, and I checked the outputs myself. Code and README are on GitHub. Thanks!" |

**Checklist the reviewer will look for:** live run (not slides) ✓ · 3–5 min ✓ · narration ✓ · one design decision ✓ · one limitation ✓.

---

## Commands, in order (Windows PowerShell)

### A. Before you hit record (off camera)
```powershell
cd "C:\Flyrank\Portofolio Flyrank\Documentation and Demo Video\triage-agent"
Set-Alias python "C:\Users\Kevin\AppData\Local\Programs\Python\Python311\python.exe"

# Type the key hidden: only asterisks show, the key never appears on screen or in history
$k = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($k))
Remove-Variable k

Remove-Item -Recurse -Force out -ErrorAction SilentlyContinue   # start from an empty output folder
Clear-History; cls                                               # wipe the screen and the command history
```

### B. On camera
| Step | Command | What it shows |
|---|---|---|
| 1 | `python -m triage_agent --list-models` | Key works (lists models), and no key is printed. Good "is it connected?" opener. |
| 2 | `python -m unittest discover -s tests` | 9 offline tests pass (guardrails: no send, no secret leak, no price commitment). |
| 3 | `code fixtures\inbox_sample.json` (or `notepad`) | The 10 sample emails. |
| 4 | `python -m triage_agent --provider gemini --verbose` | The live run plus the briefing. If you see `→ trying next model`, say: "the first model is overloaded, so it falls back automatically." |
| 5 | `notepad out\drafts\m06.txt` | Budi's quote email: a neutral draft, no price. |
| 6 | `notepad out\tasks.json` | Tasks with deadlines. |
| 7 | `code triage_agent\tools.py` then `code triage_agent\guardrails.py` | Design decision: no send/delete function exists, and `safe_draft`. |
| 8 | `python -m evals.run_evals --provider gemini` | Score live (takes about 1–2 min, so you can talk over it or cut the wait in editing). |
| 9 | `notepad evals\RESULTS_rules.md` | Limitation: the rules baseline misses TC-07. |

Tips:
- Never run `$env:GEMINI_API_KEY` or `echo $env:GEMINI_API_KEY` on camera.
- Don't press ↑ (arrow up) to reuse commands from before recording. `Clear-History` already removed them, but stay safe.
- The eval takes a while because calls are paced for the free tier. Cut that wait out in editing if you like, but keep the final score on screen.
