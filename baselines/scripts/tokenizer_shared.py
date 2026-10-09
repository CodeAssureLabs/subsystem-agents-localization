"""Tokenizer shared by the lexical baselines (identical to the original BM25 baseline)."""
import re

STOPWORDS = set("""
a an the and or but if then else when while for of in on at to from by with as is are was were be been being
do does did done not no yes that this these those it its his her their there here so such which what who whom
how why where when than into about over under between among across through self def class import return yield
true false none null pass raise except try finally with as global nonlocal lambda print str int float bool list
dict set tuple type len range map filter open read write close call test will would should could may might can
issue file files use using used uses make makes made get gets got set sets way ways one two three new old
""".split())

CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
SPLIT = re.compile(r"[^A-Za-z0-9]+")

def tokenize(text: str):
    if not text:
        return []
    # camelCase -> spaces
    text = CAMEL.sub(" ", text)
    toks = SPLIT.split(text.lower())
    return [t for t in toks if t and t not in STOPWORDS and len(t) > 1]

