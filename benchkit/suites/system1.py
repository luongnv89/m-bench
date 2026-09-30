"""System One decision tasks: a `state` plus typed `questions` per task.

This is the request shape System One decision endpoints take — models like
Laya (convaiinnovations/laya) or Bespoke-Nimble (bespokelabs/Bespoke-Nimble-9B)
that read a state document and answer typed questions with a short typed
answer instead of generating prose. Each question becomes one chat generation
scored by exact match against `answer` (the option letter or the full option
text both count), so the suite's solve rate *is* its accuracy and its
per-question latency is the speed signal.

`options` may be omitted for an open short-answer question. There is no
executable reference: `bench validate --suite system1` lints the data instead
(every answer must be one of its own options). Difficulty: easy / medium /
hard.
"""

TASKS = [
    # ------------------------------------------------------------- easy ---
    dict(
        id="spam_email", difficulty="easy",
        state="Email received at 03:12:\n"
              "From: winner@prize-claims.example\n"
              "Subject: CONGRATULATIONS!!! You have won $1,000,000\n\n"
              "Dear winner, to claim your prize send your bank details and "
              "a $50 processing fee to the account below.",
        questions=[
            dict(question="Is this email spam or a scam?",
                 options=["yes", "no"], answer="yes"),
            dict(question="Should this email reach the user's inbox?",
                 options=["yes", "no"], answer="no"),
        ],
    ),
    dict(
        id="refund_eligible", difficulty="easy",
        state="Store policy: items may be returned for a full refund within "
              "30 days of purchase with a receipt.\n\n"
              "Customer request: 'I bought these headphones 12 days ago and "
              "I have the receipt. I would like a refund please.'",
        questions=[
            dict(question="Is the customer eligible for a refund under the policy?",
                 options=["yes", "no"], answer="yes"),
            dict(question="Which team should handle this request?",
                 options=["returns", "technical support", "sales", "legal"],
                 answer="returns"),
        ],
    ),
    dict(
        id="glowing_review", difficulty="easy",
        state="Product review: 'Absolutely love this keyboard — best purchase "
              "of the year. It types like a dream.'",
        questions=[
            dict(question="What is the review's sentiment?",
                 options=["negative", "neutral", "positive"], answer="positive"),
            dict(question="Is the reviewer likely to recommend this product?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="museum_hours", difficulty="easy",
        state="Visitor notice: 'The museum is closed on Mondays. It is open "
              "9:00–17:00 on all other days.'",
        questions=[
            dict(question="Is the museum open on Monday?",
                 options=["yes", "no"], answer="no"),
            dict(question="Is the museum open on Wednesday at 10:00?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="fruit_basket", difficulty="easy",
        state="A basket holds 3 apples and 4 oranges.",
        questions=[
            dict(question="How many pieces of fruit are in the basket?",
                 options=["6", "7", "8", "9"], answer="7"),
            dict(question="If you eat one apple, how many apples remain?",
                 options=["1", "2", "3", "4"], answer="2"),
        ],
    ),
    dict(
        id="capital_japan", difficulty="easy",
        state="Answer these general-knowledge questions about Japan.",
        questions=[
            dict(question="What is the capital of Japan?",
                 options=["Kyoto", "Osaka", "Tokyo", "Seoul"], answer="Tokyo"),
            dict(question="Which language is primarily spoken in Japan?",
                 options=["Mandarin", "Japanese", "Korean", "Thai"],
                 answer="Japanese"),
        ],
    ),
    dict(
        id="threat_comment", difficulty="easy",
        state="User comment on a forum post: 'I will find out where you live "
              "and hurt you.'",
        questions=[
            dict(question="Does this comment threaten violence?",
                 options=["yes", "no"], answer="yes"),
            dict(question="Should the comment be removed immediately?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="product_spec", difficulty="easy",
        state="Product spec sheet: 'Waterproof to 50 m. Battery lasts "
              "20 hours. No GPS on board.'",
        questions=[
            dict(question="Does this product have GPS?",
                 options=["yes", "no"], answer="no"),
            dict(question="Is the product waterproof?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="language_french", difficulty="easy",
        state="Incoming message: 'Bonjour, je voudrais réserver une table "
              "pour deux.'",
        questions=[
            dict(question="Which language is the message written in?",
                 options=["English", "French", "Spanish", "German"],
                 answer="French"),
            dict(question="Is the sender asking for something?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="golden_retriever", difficulty="easy",
        state="Answer these questions about the animal 'golden retriever'.",
        questions=[
            dict(question="A golden retriever is a kind of what?",
                 options=["dog", "cat", "bird", "fish"], answer="dog"),
            dict(question="Is a golden retriever a mammal?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="ref_code", difficulty="easy",
        state="Ticket header:\nREF: ZX-4821-Q\nReceived: 2026-09-30",
        questions=[
            # open short answer — no options on purpose
            dict(question="What is the ticket's reference code?",
                 answer="ZX-4821-Q"),
            dict(question="On what date was the ticket received?",
                 options=["2026-09-29", "2026-09-30", "2026-10-01"],
                 answer="2026-09-30"),
        ],
    ),
    # ----------------------------------------------------------- medium ---
    dict(
        id="sale_item_refund", difficulty="medium",
        state="Store policy: full-price items may be returned within 30 days "
              "with a receipt. Items marked 'sale' are final sale and cannot "
              "be returned.\n\n"
              "Three requests arrived:\n"
              "A) a sale item, bought 5 days ago, with receipt\n"
              "B) a full-price item, bought 10 days ago, with receipt\n"
              "C) a full-price item, bought 40 days ago, with receipt",
        questions=[
            dict(question="Can request A get a refund?",
                 options=["yes", "no"], answer="no"),
            dict(question="Can request B get a refund?",
                 options=["yes", "no"], answer="yes"),
            dict(question="Can request C get a refund?",
                 options=["yes", "no"], answer="no"),
        ],
    ),
    dict(
        id="ticket_billing", difficulty="medium",
        state="Support ticket #4471:\n"
              "Subject: charged twice\n"
              "Body: 'My card shows two identical charges for this month's "
              "subscription renewal. Please fix it.'",
        questions=[
            dict(question="Which queue should own this ticket?",
                 options=["billing", "technical support", "sales", "legal"],
                 answer="billing"),
            dict(question="Will the customer most likely need a refund or credit?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="chat_resolved", difficulty="medium",
        state="Support chat transcript:\n"
              "customer: my invoice shows two charges for order 991\n"
              "agent: I can see the duplicate charge and I've issued a refund "
              "for it\n"
              "customer: thanks!",
        questions=[
            dict(question="What problem did the customer report?",
                 options=["duplicate charge", "late delivery", "damaged item",
                          "wrong size"], answer="duplicate charge"),
            dict(question="Was the problem resolved within the conversation?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="json_order", difficulty="medium",
        state='Order document:\n{"id": 8842, "items": [{"sku": "TEE-BLU-M", '
              '"qty": 2}], "status": "shipped"}',
        questions=[
            dict(question="What is the order's status?",
                 options=["pending", "shipped", "delivered", "cancelled"],
                 answer="shipped"),
            dict(question="How many units of TEE-BLU-M were ordered?",
                 options=["1", "2", "3", "4"], answer="2"),
        ],
    ),
    dict(
        id="height_order", difficulty="medium",
        state="Maria is taller than Jo. Jo is taller than Sam.",
        questions=[
            dict(question="Who is the tallest?",
                 options=["Maria", "Jo", "Sam"], answer="Maria"),
            dict(question="Who is the shortest?",
                 options=["Maria", "Jo", "Sam"], answer="Sam"),
        ],
    ),
    dict(
        id="bag_allowance", difficulty="medium",
        state="Airline notice: 'No more than 2 cabin bags per passenger. "
              "Cabin bags over 10 kg cost extra.'",
        questions=[
            dict(question="May a passenger bring 3 cabin bags?",
                 options=["yes", "no"], answer="no"),
            dict(question="Is a cabin bag weighing 8 kg within the weight allowance?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="cafe_hours", difficulty="medium",
        state="Café door sign: 'Mon–Fri 9:00–18:00 · Sat 10:00–14:00 · "
              "closed Sundays.'",
        questions=[
            dict(question="Is the café open on Sunday?",
                 options=["yes", "no"], answer="no"),
            dict(question="Is the café open on Saturday at noon?",
                 options=["yes", "no"], answer="yes"),
            dict(question="Is the café open on Friday at 20:00?",
                 options=["yes", "no"], answer="no"),
        ],
    ),
    dict(
        id="harsh_review", difficulty="medium",
        state="App-store review: 'Terrible. Crashes on launch every single "
              "time. Uninstalled and demanded a refund.'",
        questions=[
            dict(question="On a scale of 1 to 5, what rating best matches this review?",
                 options=["1", "2", "3", "4", "5"], answer="1"),
            dict(question="Is the reviewer complaining about stability?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    # ------------------------------------------------------------- hard ---
    dict(
        id="error_log", difficulty="hard",
        state="Log line from a batch job:\n"
              "'2026-09-01 14:22 ERROR db_writer: connection refused "
              "(attempt 3 of 3)'",
        questions=[
            dict(question="Did the operation ultimately succeed?",
                 options=["yes", "no", "cannot determine"],
                 answer="cannot determine"),
            dict(question="How many attempts were made?",
                 options=["1", "2", "3"], answer="3"),
            dict(question="Was this the final allowed attempt?",
                 options=["yes", "no"], answer="yes"),
        ],
    ),
    dict(
        id="budget_veto", difficulty="hard",
        state="Meeting minutes: 'Although the committee approved the overall "
              "budget, the chair vetoed the proposed increase to the "
              "marketing budget specifically.'",
        questions=[
            dict(question="Was the overall budget approved?",
                 options=["yes", "no"], answer="yes"),
            dict(question="Was the marketing budget increase approved?",
                 options=["yes", "no"], answer="no"),
        ],
    ),
    dict(
        id="device_policy", difficulty="hard",
        state="IT policy: 'The company does not prohibit employees from using "
              "personal devices at work, but it does prohibit storing company "
              "data on them.'",
        questions=[
            dict(question="May employees use personal devices at work?",
                 options=["yes", "no"], answer="yes"),
            dict(question="May employees store company data on personal devices?",
                 options=["yes", "no"], answer="no"),
        ],
    ),
    dict(
        id="borderline_comment", difficulty="hard",
        state="User comment under a match report: 'The referee is blind. "
              "This league is a joke.'",
        questions=[
            dict(question="Does this comment contain a violent threat?",
                 options=["yes", "no"], answer="no"),
            dict(question="Is the comment civil and respectful?",
                 options=["yes", "no"], answer="no"),
        ],
    ),
]
