"""Test classifier after CoQA + TREC retraining."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from src.extraction.classifier import QueryClassifier

c = QueryClassifier()
c.classify("test")  # ensure ML loaded

queries = [
    ("When did I meet Alice?", "temporal"),
    ("Who is my manager?", "factual"),
    ("Why did the project fail?", "multi-hop"),
    ("Do you remember our last meeting?", "conversational"),
    ("What about the budget proposal?", "conversational"),
    ("You mentioned Alice — any updates?", "conversational"),
    ("Following up on our discussion about the merger", "conversational"),
    ("Update my contact information", "update"),
    ("Change the deadline to Friday", "update"),
    ("Set John's role to manager", "update"),
    ("How many employees work at Acme?", "factual"),
    ("What is the capital of France?", "factual"),
    ("How far is it from Denver to Aspen?", "factual"),
    ("When was Ozzy Osbourne born?", "temporal"),
    ("How long does it take to boil an egg?", "temporal"),
    ("Why do heavier objects travel downhill faster?", "multi-hop"),
    ("Wann habe ich Alice getroffen?", "temporal"),
    ("Wer ist mein Kunde?", "factual"),
    ("Warum haben wir das Projekt gestoppt?", "multi-hop"),
    ("Worüber haben wir gestern gesprochen?", "conversational"),
    ("Aktualisiere meinen Namen", "update"),
]

header = f"{'Query':50s} | {'ML label':16s} {'ML conf':>7s} | {'Final':16s} {'Conf':>5s} | {'Src':6s} | {'OK'}"
print(header)
print("-" * 115)
ok = 0
for q, exp in queries:
    ml_label, ml_conf = c._ml.classify(q)
    final_label, final_conf = c.classify(q)
    src = "ML" if ml_conf >= 0.6 else "regex"
    correct = "✓" if final_label == exp else "✗"
    if correct == "✓":
        ok += 1
    print(f"{q:50s} | {str(ml_label):16s} {ml_conf:7.3f} | {final_label:16s} {final_conf:5.2f} | {src:6s} | {correct}")

print(f"\nAccuracy: {ok}/{len(queries)}")
print(f"Model size: {os.path.getsize('docs/data/classifier_model.pkl')} bytes")
