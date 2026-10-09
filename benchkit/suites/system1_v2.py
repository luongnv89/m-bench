"""Fixed, self-contained System One v2 decision fixtures.

200 scenarios / 400 questions across ten equally weighted families. Rule-based
keys are derived from structured facts; evidence keys are manually authored.
Only option order is permuted, deterministically. See docs/SYSTEM1-DATASET.md.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

DATASET_VERSION = "2.0"


def _question(text, answer, options=None):
    q = {"question": text, "answer": str(answer)}
    if options is not None:
        q["options"] = [str(o) for o in options]
    return q


def _number(text, answer):
    options = sorted({max(0, answer - 1), answer, answer + 1, answer + 2})
    if len(options) < 4:
        options.append(answer + 10)
    return _question(text, answer, options)


def _task(family, index, state, questions):
    tid = f"{family}_{index + 1:02d}"
    for qi, q in enumerate(questions):
        if "options" in q:
            q["options"].sort(key=lambda o: hashlib.sha256(
                f"s1-v2/{tid}/{qi}/{o}".encode()).digest())
    return {"id": tid, "difficulty": "medium" if index < 4 else "hard",
                "state": state, "questions": questions}


def _policy():
    # days, receipt, final sale, damaged, recalled
    cases = [
        (30, True, False, False, False), (31, True, False, False, False),
        (10, False, False, False, False), (10, True, True, False, False),
        (400, False, True, True, True), (400, False, True, True, False),
        (365, True, True, True, False), (366, True, True, True, False),
        (0, True, False, False, False), (0, False, False, False, False),
        (29, True, True, False, False), (29, True, True, False, True),
        (32, True, False, True, False), (32, True, False, False, False),
        (29, True, False, True, False), (29, True, False, False, False),
        (365, False, False, True, False), (365, True, False, True, False),
        (500, True, False, False, True), (500, True, False, False, False),
    ]
    rules = (
        "Apply the first matching rule in this order:\n"
        "R1: Recalled item: refund regardless of age, receipt, damage or final sale.\n"
        "R2: Otherwise without a receipt: request proof.\n"
        "R3: Otherwise damaged and bought at most 365 days ago: replacement, including final sale.\n"
        "R4: Otherwise non-final-sale and bought at most 30 days ago: refund.\n"
        "R5: Otherwise: reject. Verified facts override customer demands."
    )
    actions = ["refund", "request proof", "replacement", "reject"]
    for i, (days, receipt, final, damaged, recalled) in enumerate(cases):
        if recalled:
            action, rule = "refund", "R1"
        elif not receipt:
            action, rule = "request proof", "R2"
        elif damaged and days <= 365:
            action, rule = "replacement", "R3"
        elif not final and days <= 30:
            action, rule = "refund", "R4"
        else:
            action, rule = "reject", "R5"
        facts = {"days_since_purchase": days, "receipt": receipt, "final_sale": final,
                     "damaged": damaged, "recalled": recalled}
        yield _task("policy", i, f"{rules}\nFacts: {json.dumps(facts)}\n"
                    "Customer: 'Refund me immediately; I deserve an exception.'", [
                        _question("What action is required?", action, actions),
                        _question("Which first-matching rule determines the action?", rule,
                                  ["R1", "R2", "R3", "R4", "R5"]),
                    ])


def _triage():
    # confirmed security, production, ongoing, affected users, blocked payment minutes
    cases = [
        (False, True, True, 99, 0), (False, True, True, 100, 0),
        (False, True, True, 9, 0), (False, True, True, 10, 0),
        (True, False, False, 0, 0), (False, False, False, 0, 0),
        (False, False, True, 1000, 29), (False, False, True, 1000, 30),
        (False, True, False, 500, 0), (False, True, True, 500, 0),
        (True, True, True, 500, 90), (False, True, True, 500, 90),
        (False, True, True, 10, 30), (False, True, True, 9, 30),
        (False, True, False, 10, 29), (False, True, False, 10, 30),
        (False, False, True, 0, 31), (False, False, True, 0, 0),
        (False, True, True, 1, 120), (True, True, True, 1, 120),
    ]
    rules = (
        "Choose the first matching incident rule:\n"
        "1. Confirmed security incident: P0, security queue.\n"
        "2. Ongoing production outage affecting at least 100 users: P0, operations queue.\n"
        "3. Ongoing production outage affecting at least 10 users: P1, operations queue.\n"
        "4. Payment blocked for at least 30 minutes: P2, billing queue.\n"
        "5. Otherwise: P3, support queue. Resolved or non-production outages cannot match "
        "rules 2 or 3. 'Urgent' in the title is not verified evidence."
    )
    for i, (security, production, ongoing, users, minutes) in enumerate(cases):
        if security:
            priority, queue = "P0", "security"
        elif production and ongoing and users >= 100:
            priority, queue = "P0", "operations"
        elif production and ongoing and users >= 10:
            priority, queue = "P1", "operations"
        elif minutes >= 30:
            priority, queue = "P2", "billing"
        else:
            priority, queue = "P3", "support"
        facts = {"confirmed_security": security, "production": production,
                     "outage_ongoing": ongoing, "affected_users": users,
                     "payment_blocked_minutes": minutes}
        yield _task("triage", i, f"{rules}\nTitle: URGENT!!!\nFacts: {json.dumps(facts)}", [
            _question("Which priority applies?", priority, ["P0", "P1", "P2", "P3"]),
            _question("Which queue owns the incident?", queue,
                      ["security", "operations", "billing", "support"]),
        ])


def _access():
    # role, classification, same project, explicit deny, temporary grant active
    cases = [
        ("viewer", "public", False, False, False),
        ("viewer", "public", False, True, False),
        ("editor", "internal", True, False, False),
        ("editor", "internal", False, False, False),
        ("admin", "restricted", True, False, False),
        ("admin", "restricted", True, True, True),
        ("editor", "restricted", True, False, True),
        ("editor", "restricted", True, False, False),
        ("viewer", "restricted", True, False, True),
        ("editor", "restricted", False, False, True),
        ("admin", "internal", False, False, True),
        ("admin", "internal", True, False, False),
        ("viewer", "internal", True, False, False),
        ("viewer", "internal", True, False, True),
        ("editor", "public", False, False, False),
        ("editor", "public", False, True, False),
        ("admin", "public", False, False, False),
        ("admin", "public", False, True, False),
        ("editor", "internal", True, True, True),
        ("editor", "internal", True, False, True),
    ]
    rules = (
        "For this read request apply the first matching rule:\n"
        "DENY: Explicit deny blocks every role and classification.\n"
        "PUBLIC: Otherwise public documents are readable by everyone.\n"
        "ADMIN: Otherwise an admin in the same project may read.\n"
        "EDITOR: Otherwise an editor in the same project may read internal documents.\n"
        "GRANT: Otherwise an editor in the same project with an active temporary grant "
        "may read restricted documents.\n"
        "DEFAULT: Otherwise deny. Grants never upgrade viewers or cross project boundaries."
    )
    for i, (role, classification, same, deny, grant) in enumerate(cases):
        if deny:
            basis = "DENY"
        elif classification == "public":
            basis = "PUBLIC"
        elif role == "admin" and same:
            basis = "ADMIN"
        elif role == "editor" and same and classification == "internal":
            basis = "EDITOR"
        elif role == "editor" and same and grant and classification == "restricted":
            basis = "GRANT"
        else:
            basis = "DEFAULT"
        facts = {"role": role, "classification": classification, "same_project": same,
                     "explicit_deny": deny, "temporary_grant_active": grant}
        yield _task("access", i, f"{rules}\nRequest: {json.dumps(facts)}", [
            _question("May the requester read this document?",
                      "deny" if basis in ("DENY", "DEFAULT") else "allow", ["allow", "deny"]),
            _question("Which first-matching rule decides?", basis,
                      ["DENY", "PUBLIC", "ADMIN", "EDITOR", "GRANT", "DEFAULT"]),
        ])


def _events():
    # p=pay, s=ship, c=cancel, r=refund, x=other order; suffix = event ID.
    cases = [
        "p1 s2", "s1 p2", "p1 c2", "c1 p2", "p1 p1 s2",
        "p1 s1 s2", "x1 p1 s2", "p1 x2 s2", "p1 s2 r3", "p1 r2 s3",
        "c1 r2", "r1 p2", "s1 s1 p2 s3", "p1 c2 r3", "p1 s2 c3",
        "x1 x2", "p1 r2 p3", "c1 c2 p3", "r1 p1", "p1 s2 r3 r3",
    ]
    transitions = {("pending", "pay"): "paid", ("paid", "ship"): "shipped",
                   ("pending", "cancel"): "cancelled", ("paid", "cancel"): "cancelled",
                   ("paid", "refund"): "refunded", ("shipped", "refund"): "refunded"}
    actions = {"p": "pay", "s": "ship", "c": "cancel", "r": "refund", "x": "pay"}
    rules = (
        "Order O-17 starts pending. Read events in listed order. Ignore other orders "
        "before checking duplicates. For O-17 ignore an event ID after its first occurrence, "
        "even if that occurrence had an invalid action. Valid transitions only:\n"
        "pending + pay -> paid; paid + ship -> shipped; pending or paid + cancel -> cancelled; "
        "paid or shipped + refund -> refunded. All other actions are ignored. "
        "An ignored action is not an applied transition."
    )
    for i, sequence in enumerate(cases):
        events = [{"event_id": f"e{token[1:]}", "order": "OTHER" if token[0] == "x" else "O-17",
                       "action": actions[token[0]]} for token in sequence.split()]
        status, applied, seen = "pending", 0, set()
        for event in events:
            if event["order"] != "O-17" or event["event_id"] in seen:
                continue
            seen.add(event["event_id"])
            next_status = transitions.get((status, event["action"]))
            if next_status is not None:
                status, applied = next_status, applied + 1
        yield _task("events", i, f"{rules}\nEvents: {json.dumps(events)}", [
            _question("What is O-17's final state?", status,
                      ["pending", "paid", "shipped", "cancelled", "refunded"]),
            _number("How many transitions were applied to O-17?", applied),
        ])


def _time():
    # now seconds after start, displayed UTC offset hours, revoked, maintenance window
    cases = [
        (0, 0, False, None), (3600, 0, False, None),
        (-1, 0, False, None), (3599, 0, False, None),
        (0, 2, False, None), (3600, 2, False, None),
        (1800, -5, True, None), (1800, -5, False, None),
        (1800, 14, False, None), (3600, -10, False, None),
        (900, 0, False, (900, 1800)), (1800, 0, False, (900, 1800)),
        (899, 0, False, (900, 1800)), (1799, 0, False, (900, 1800)),
        (-3600, 0, True, None), (7200, 0, True, None),
        (1200, 0, True, (900, 1800)), (1200, 2, False, (900, 1800)),
        (1800, 2, False, (900, 1800)), (-900, 1, False, None),
    ]
    rules = (
        "Timestamps include explicit UTC offsets; compare instants, not clock text. "
        "Apply the first matching reason: revoked; not yet valid (now < start); "
        "expired (now >= end); maintenance (maintenance_start <= now < maintenance_end); "
        "valid. Null maintenance means none. Only 'valid' allows use."
    )
    for i, (seconds, offset, revoked, maintenance) in enumerate(cases):
        # Alternate day/night windows to exercise date crossings as well as offsets.
        start = datetime(2026, 4, 3, 23 if i >= 8 else 10, 30 if i >= 8 else 0,
                         tzinfo=timezone.utc)
        now, end = start + timedelta(seconds=seconds), start + timedelta(hours=1)
        window = None if maintenance is None else [start + timedelta(seconds=s) for s in maintenance]
        if revoked:
            reason = "revoked"
        elif now < start:
            reason = "not yet valid"
        elif now >= end:
            reason = "expired"
        elif window and window[0] <= now < window[1]:
            reason = "maintenance"
        else:
            reason = "valid"
        facts = {"now": now.astimezone(timezone(timedelta(hours=offset))).isoformat(),
                     "start": start.isoformat(), "end": end.isoformat(), "revoked": revoked,
                     "maintenance": None if window is None else [
                         instant.astimezone(timezone(timedelta(hours=-5))).isoformat()
                         for instant in window]}
        yield _task("time", i, f"{rules}\nCredential: {json.dumps(facts)}", [
            _question("Can this credential be used now?",
                      "yes" if reason == "valid" else "no", ["yes", "no"]),
            _question("What is the first-matching reason?", reason,
                      ["revoked", "not yet valid", "expired", "maintenance", "valid"]),
        ])


def _money():
    # quantity, unit cents, discount percent, shipping cents, credit cents, paid cents
    cases = [
        (2, 1000, 10, 200, 0, 2000), (2, 1000, 10, 200, 0, 1999),
        (2, 1000, 10, 200, 0, 2001), (1, 999, 0, 1, 0, 1000),
        (1, 101, 50, 0, 0, 50), (1, 101, 50, 0, 0, 51),
        (3, 333, 10, 100, 0, 999), (3, 333, 10, 100, 0, 1000),
        (1, 1000, 100, 150, 0, 0), (1, 1000, 100, 150, 0, 150),
        (2, 500, 0, 0, 1200, 0), (2, 500, 0, 0, 1200, 1),
        (4, 250, 25, 100, 50, 800), (4, 250, 25, 100, 50, 750),
        (1, 105, 10, 0, 0, 95), (1, 105, 10, 0, 0, 96),
        (2, 105, 10, 0, 0, 189), (2, 105, 10, 0, 0, 188),
        (5, 199, 20, 49, 100, 800), (5, 199, 20, 49, 100, 745),
    ]
    rules = (
        "All amounts are integer euro cents. Multiply quantity by unit price, apply the "
        "percentage discount to that merchandise subtotal, then round the discounted "
        "subtotal to the nearest whole cent (exact halves round up). Round once on the "
        "subtotal, not per item or on the discount. Add shipping, subtract credit, and "
        "floor the invoice total at zero. Shipping is not discounted. No tax or fees. "
        "paid < invoice total: outstanding; equal: settled; greater: overpaid."
    )
    for i, (qty, unit, discount, shipping, credit, paid) in enumerate(cases):
        merchandise = (Decimal(qty * unit) * Decimal(100 - discount) / 100).quantize(
            Decimal(1), rounding=ROUND_HALF_UP)
        total = max(0, int(merchandise) + shipping - credit)
        status = "outstanding" if paid < total else "overpaid" if paid > total else "settled"
        facts = {"quantity": qty, "unit_cents": unit, "discount_percent": discount,
                     "shipping_cents": shipping, "credit_cents": credit, "paid_cents": paid}
        yield _task("money", i, f"{rules}\nInvoice: {json.dumps(facts)}", [
            _question("What is the payment status?", status,
                      ["outstanding", "settled", "overpaid"]),
            _number("What is the invoice total in cents, before payment?", total),
        ])


def _inventory():
    # shelves, live reservation, released reservation, inbound qty, arrived, requested
    cases = [
        (5, 3, 2, 0, 0, False, 6), (5, 3, 2, 0, 0, False, 7),
        (2, 0, 2, 0, 0, False, 1), (2, 0, 1, 0, 0, False, 1),
        (5, 3, 2, 4, 0, False, 6), (5, 3, 6, 0, 0, False, 6),
        (1, 1, 2, 0, 5, True, 5), (1, 1, 2, 0, 5, False, 5),
        (3, 0, 0, 3, 0, False, 3), (3, 0, 3, 0, 0, False, 3),
        (0, 0, 0, 0, 4, True, 4), (0, 0, 0, 0, 4, False, 4),
        (4, 4, 1, 2, 3, True, 10), (4, 4, 1, 2, 3, False, 10),
        (1, 0, 3, 0, 1, True, 2), (1, 0, 3, 0, 5, True, 2),
        (10, 0, 5, 5, 0, False, 5), (10, 0, 5, 5, 0, False, 6),
        (2, 2, 4, 0, 1, True, 2), (2, 2, 4, 0, 2, True, 2),
    ]
    rules = (
        "Allocate SKU AB-01, matching exactly including case and zeros. Available = sum "
        "of its shelf quantities - its active reservations + its inbound quantities "
        "already arrived at the as_of instant, floored at zero. Released reservations "
        "do not subtract stock. Future arrivals cannot be used. If available >= requested: "
        "fill all; if 0 < available < requested: fill partial; if zero: wait. "
        "All listed arrivals are confirmed."
    )
    for i, (a, b, live, released, inbound, arrived, requested) in enumerate(cases):
        facts = {"as_of": "2026-06-10T12:00:00Z", "requested": requested,
                     "shelves": [{"sku": "AB-01", "qty": a}, {"sku": "AB-01", "qty": b},
                              {"sku": "AB-1", "qty": 100}, {"sku": "ab-01", "qty": 100}],
                     "reservations": [{"sku": "AB-01", "qty": live, "status": "active"},
                                   {"sku": "AB-01", "qty": released, "status": "released"},
                                   {"sku": "AB-1", "qty": 99, "status": "active"}],
                     "inbound": [{"sku": "AB-01", "qty": inbound,
                                   "at": "2026-06-10T12:00:00Z" if arrived else "2026-06-10T12:00:01Z"}]}
        available = max(0, a + b - live + (inbound if arrived else 0))
        action = "fill all" if available >= requested else "fill partial" if available else "wait"
        yield _task("inventory", i, f"{rules}\nLedger: {json.dumps(facts)}", [
            _question("How should this request be allocated?", action,
                      ["fill all", "fill partial", "wait"]),
            _number("How many units of AB-01 are available?", available),
        ])


def _dependencies():
    # build status, tests status, free slots, disabled jobs, priorities, queried job
    cases = [
        ("done", "done", 2, "", (1, 2, 3), "deploy"),
        ("done", "done", 1, "", (1, 2, 3), "deploy"),
        ("running", "done", 2, "", (1, 2, 3), "archive"),
        ("done", "running", 2, "", (1, 2, 3), "notify"),
        ("skipped", "done", 2, "", (1, 2, 3), "archive"),
        ("failed", "done", 2, "", (1, 2, 3), "archive"),
        ("done", "skipped", 2, "", (1, 2, 3), "deploy"),
        ("done", "failed", 2, "", (1, 2, 3), "notify"),
        ("done", "done", 0, "", (1, 2, 3), "archive"),
        ("done", "done", 2, "deploy", (1, 2, 3), "deploy"),
        ("done", "done", 2, "", (1, 1, 1), "notify"),
        ("done", "done", 2, "archive", (1, 1, 1), "archive"),
        ("running", "running", 2, "", (3, 2, 1), "deploy"),
        ("failed", "failed", 2, "", (3, 2, 1), "deploy"),
        ("done", "done", 2, "deploy archive notify", (1, 2, 3), "notify"),
        ("skipped", "done", 1, "archive", (1, 2, 3), "deploy"),
        ("done", "done", 2, "", (3, 2, 1), "archive"),
        ("done", "done", 1, "notify", (3, 2, 1), "archive"),
        ("failed", "running", 0, "deploy", (3, 2, 1), "deploy"),
        ("running", "failed", 0, "", (3, 2, 1), "deploy"),
    ]
    rules = (
        "Ready jobs are enabled, have all required dependencies done and all optional "
        "dependencies done or skipped, and have enough free slots. Failed optional "
        "dependencies still block. Consider each job alone: no slots allocated yet. "
        "Choose the ready job with smallest numeric priority, breaking ties by job name "
        "alphabetically; choose none if none ready. For a queried job report the first "
        "blocking reason in this order: disabled; failed dependency (failed, or skipped "
        "if required); pending dependency (queued or running); insufficient slots; ready."
    )
    for i, (build, tests, slots, disabled, priorities, target) in enumerate(cases):
        statuses = {"build": build, "tests": tests}
        jobs = [{"name": "deploy", "required": ["build", "tests"], "optional": [], "slots": 2},
                {"name": "archive", "required": [], "optional": ["build"], "slots": 1},
                {"name": "notify", "required": ["tests"], "optional": [], "slots": 1}]
        reasons = {}
        for job, priority in zip(jobs, priorities):
            job.update(priority=priority, enabled=job["name"] not in disabled.split())
            if not job["enabled"]:
                reason = "disabled"
            elif any(statuses[d] in ("failed", "skipped") for d in job["required"]) or any(
                    statuses[d] == "failed" for d in job["optional"]):
                reason = "failed dependency"
            elif any(statuses[d] in ("queued", "running")
                     for d in job["required"] + job["optional"]):
                reason = "pending dependency"
            elif slots < job["slots"]:
                reason = "insufficient slots"
            else:
                reason = "ready"
            reasons[job["name"]] = reason
        ready = sorted((job["priority"], job["name"]) for job in jobs
                       if reasons[job["name"]] == "ready")
        chosen = ready[0][1] if ready else "none"
        facts = {"dependencies": statuses, "free_slots": slots, "jobs": jobs}
        yield _task("dependencies", i, f"{rules}\nScheduler: {json.dumps(facts)}", [
            _question("Which job should be selected next?", chosen,
                      ["deploy", "archive", "notify", "none"]),
            _question(f"What is the first blocking reason for {target}, or is it ready?",
                      reasons[target], ["disabled", "failed dependency", "pending dependency",
                                        "insufficient slots", "ready"]),
        ])


def _evidence():
    # Editorial keys: exact claims, explicit reports, and equal source authority.
    cases = [
        ("The clerk reports parcel P arrived. The courier reports parcel P was signed for.",
         "Parcel P arrived.", "supported", "Parcel P was signed for.", "supported"),
        ("The clerk says invoice I is not paid. The ledger says invoice I was issued.",
         "Invoice I is paid.", "refuted", "Invoice I was issued.", "supported"),
        ("A says gate G is open. B says gate G is not open. Both say the alarm is off.",
         "Gate G is open.", "conflicting", "The alarm is off.", "supported"),
        ("The manager proposed approving request R. The minutes say R was discussed, with no recorded decision.",
         "Request R was approved.", "unknown", "Request R was discussed.", "supported"),
        ("The auditor says backup B completed and explicitly says B was not verified.",
         "Backup B completed.", "supported", "Backup B was verified.", "refuted"),
        ("The supervisor says the increase to budget M was not approved; the overall budget was approved.",
         "The increase to budget M was approved.", "refuted", "The overall budget was approved.", "supported"),
        ("A says account K is suspended. B says K is not suspended. Neither discusses deletion.",
         "Account K is suspended.", "conflicting", "Account K was deleted.", "unknown"),
        ("The agent promised a refund for order Q tomorrow, and says a return label was not sent.",
         "The refund for Q was issued.", "unknown", "A return label was sent.", "refuted"),
        ("The transcript says patch V is installed on staging and is not installed on production.",
         "Patch V is installed on staging.", "supported", "Patch V is installed on production.", "refuted"),
        ("Both logs explicitly say job J did not finish. No log mentions whether J started.",
         "Job J finished.", "refuted", "Job J started.", "unknown"),
        ("A says the door is locked and the light is on. B says the door is not locked and the light is not on.",
         "The door is locked.", "conflicting", "The light is on.", "conflicting"),
        ("A asks whether device D passed inspection. B says device E passed inspection. Nobody reports on D.",
         "Device D passed inspection.", "unknown", "Device E passed inspection.", "supported"),
        ("The reviewer says the policy permits personal devices but does not permit storing company data on them.",
         "Personal devices are permitted.", "supported", "Storing company data on personal devices is permitted.", "refuted"),
        ("The inspector says seal S is not intact. A forecast predicts shipment T will arrive tomorrow.",
         "Seal S is intact.", "refuted", "Shipment T has arrived.", "unknown"),
        ("A says payments X and Y settled. B says payment X did not settle and payment Y did not settle.",
         "Payment X settled.", "conflicting", "Payment Y settled.", "conflicting"),
        ("The only note says: 'If test T passes, deploy release R.' It records no result or deployment.",
         "Test T passed.", "unknown", "Release R was deployed.", "unknown"),
        ("The record says Mina approved request A and did not approve B. It says nothing about C.",
         "Mina approved request A.", "supported", "Mina approved request C.", "unknown"),
        ("The record says no production outage occurred. A says staging failed; B says staging did not fail.",
         "A production outage occurred.", "refuted", "Staging failed.", "conflicting"),
        ("A says user U consented; B says U did not consent. Both explicitly say U did not withdraw consent.",
         "User U consented.", "conflicting", "User U withdrew consent.", "refuted"),
        ("The server accepted a cancellation request; the note says this does not establish completion. A says delivery happened; B says delivery did not happen.",
         "Cancellation completed.", "unknown", "Delivery happened.", "conflicting"),
    ]
    rules = (
        "Classify recorded evidence for the exact claim, not what probably happened. "
        "supported = explicit affirmation and no explicit denial; refuted = explicit "
        "denial and no explicit affirmation; conflicting = both; unknown = neither. "
        "Reports have equal authority, without a latest-report override. Questions, "
        "proposals, forecasts, promises and conditional instructions establish no outcome. "
        "Absence of a report is not a denial."
    )
    options = ["supported", "refuted", "conflicting", "unknown"]
    for i, (facts, claim1, key1, claim2, key2) in enumerate(cases):
        yield _task("evidence", i, f"{rules}\nRecord: {facts}", [
            _question(f"What is the evidence for this claim: {claim1}", key1, options),
            _question(f"What is the evidence for this claim: {claim2}", key2, options),
        ])


def _records():
    rules = (
        "Match the requested tenant and case_id exactly (case and leading zeros matter). "
        "Discard drafts. Use the largest numeric version among matching final records, "
        "ignoring older versions. If no matching final record exists: missing. If the "
        "newest-version records disagree on code or deleted flag: conflict. Otherwise "
        "if deleted=true: deleted; otherwise: selected. Identical duplicates do not cause "
        "conflict. Return code NONE unless status is selected."
    )
    for i in range(20):
        outcome, variant = divmod(i, 5)
        tenant, case_id = f"Team-{variant + 1}", f"00{variant + 7}"
        version = [10, 20, 11, 100, 12][variant]
        old_code, new_code = f"OLD-{variant + 1}", f"REF-{variant + 1}-Q"

        def row(ver, code, *, deleted=False, final=True, owner=tenant, identifier=case_id):
            return {"tenant": owner, "case_id": identifier, "version": ver, "code": code,
                        "deleted": deleted, "final": final}

        rows = [row(version + 1, "DRAFT", final=False),
                row(version + 2, "DECOY-1", owner=tenant.lower()),
                row(version + 3, "DECOY-2", identifier=str(int(case_id)))]
        if outcome == 0:
            rows += [row(2, old_code), row(version, new_code)]
            if variant % 2 == 0:
                rows += [row(version, new_code)]
        elif outcome == 1:
            rows += [row(2, old_code), row(version, new_code),
                     row(version, new_code if variant % 2 else "OTHER-Q",
                         deleted=bool(variant % 2))]
        elif outcome == 2:
            rows += [row(2, old_code), row(version, new_code, deleted=True)]
        offset = i % len(rows)
        rows = rows[offset:] + rows[:offset]
        matching = [r for r in rows if r["tenant"] == tenant
                    and r["case_id"] == case_id and r["final"]]
        status, code = "missing", "NONE"
        if matching:
            newest = max(r["version"] for r in matching)
            values = {(r["code"], r["deleted"]) for r in matching if r["version"] == newest}
            if len(values) > 1:
                status = "conflict"
            else:
                value, deleted = next(iter(values))
                status = "deleted" if deleted else "selected"
                code = "NONE" if deleted else value
        facts = {"request": {"tenant": tenant, "case_id": case_id}, "records": rows}
        yield _task("records", i, f"{rules}\nDocument: {json.dumps(facts)}", [
            _question("What is the lookup status?", status,
                      ["selected", "missing", "conflict", "deleted"]),
            _question("What exact code should be returned? Reply with the code or NONE.", code),
        ])


FAMILIES = {
    "policy": _policy, "triage": _triage, "access": _access, "events": _events,
    "time": _time, "money": _money, "inventory": _inventory,
    "dependencies": _dependencies, "evidence": _evidence, "records": _records,
}

TASKS = [task for build in FAMILIES.values() for task in build()]
