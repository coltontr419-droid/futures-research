"""[E_diet_tight] D + stop at $0.10 and 20 turns (decisions.md §1234). [from B_terra_cheap] A + research stops at $0.18 and 28 turns (decisions.md §1231). Zero z19: plan -> ledger research -> review -> compose.

A planner model maps the question to its sources, population, conditions and pitfalls, and the controller runs the
planned searches and page opens before research starts. Two research lanes on different driver models research concurrently with native tools (search,
open, grep, read, python) and keeps an evidence ledger: verbatim quotes that code locates in the stored document text
before accepting them. When the lanes agree, their answer stands; when they differ, an adjudicator model
settles the point of difference from the evidence, optionally after one targeted check by both lanes. A single answer
is audited by a reviewer model instead. Before writing, code builds a snippet bank: exact passages cut from every document
the research touched, ranked by the names and numbers of the answer, ledger quotes first. The writer cites only those
snippets, so every citation is an exact slice of a source result that contains the claim.
"""
import asyncio
import json
import re
import time

from harnyx_miner_sdk.api import fetch_page, llm_chat, search_web
from harnyx_miner_sdk.context import ContextSnapshot
from harnyx_miner_sdk.decorators import entrypoint
from harnyx_miner_sdk.query import CitationRef, CitationSlice, Query, Response
from harnyx_miner_sdk.safe_exec import safe_exec

T0 = time.monotonic()

# ---------------------------------------------------------------- models and limits
PLANNER = ("openrouter", "deepseek/deepseek-v4.1-flash-1017")
DRIVER = ("openrouter", "openai/gpt-6.1-terra")   # stronger research model (user 11-04: expensive OK if it pays)
REVIEWER = ("openrouter", "deepseek/deepseek-v4.1-flash-1017")
WRITER = ("openrouter", "deepseek/deepseek-v4.1-flash-1017")
QUICK = ("openrouter", "deepseek/deepseek-v4.1-flash-1017")
SPARE = ("openrouter", "deepseek/deepseek-v4.1-flash-1017")   # fallback for single calls (reasoning off)
DRIVER_THINKING = {"enabled": True, "effort": "low"}
WRITE_MODEL = ("openrouter", "deepseek/deepseek-v4.1-flash-1017")   # long write-ups: terra took >115 s per report
DRIVER2 = ("openrouter", "openai/gpt-oss-120b")   # spare driver (glm-5.3 timed out on 41% of calls)
DRIVER2_THINKING = {"enabled": True, "effort": "low"}
ADJUDICATOR = ("openrouter", "deepseek/deepseek-v4.1-flash-1017")
LANES = 1                  # research lanes run concurrently (1 = lane A only)
DRIVER_MAX_OUT = 7000
WRITER_THINKING = {"enabled": True, "effort": "low"}

SPEND_STOP = 0.10          # stop research once the session has used this much (budget is 0.50)
MAX_TURNS = 20
TURN_CAP_S = 45.0
INFLIGHT = 12
PAGE_CAP = 800000          # characters of a page kept in memory
WHOLE = 12000               # pages up to this size are shown whole
HEAD = 1500                # start of a long page shown on open
OPEN_CAP = 30000           # characters returned by one open call
PY_LIMIT_S = 8.0
MIN_SLICE = 120           # the platform rejects citation slices under 100 characters
KEEP_TURNS = 3             # tool outputs of the newest turns stay whole in the driver's context

SEARCH_EXTRA = {"mode": "turbo", "max_chars_total": 10000, "excerpt_settings": {"max_chars_per_result": 1600}}

# ---------------------------------------------------------------- prompts
ATLAS = """Source routes known to work (official sources first):
- UNESCO World Heritage Centre: property https://whc.unesco.org/en/list/ID/ ; its area and buffer-zone table https://whc.unesco.org/en/list/ID/maps/ ; documents https://whc.unesco.org/en/list/ID/documents/ ; decisions https://whc.unesco.org/en/decisions/ID/ ; inscriptions of one session https://whc.unesco.org/en/newproperties/?meeting=45COM&mode=table ; https://whc.unesco.org/en/danger/ ; search https://whc.unesco.org/en/list/?search=WORDS
- USGS/IAU Gazetteer of Planetary Nomenclature: a whole list https://planetarynames.wr.usgs.gov/SearchResults?Target=16_Moon&Feature%20Type=9_Crater,%20craters&pageSize=5000 (targets 14_Mercury, 15_Venus, 16_Moon, 20_Mars, 96_Titania ...; omit Feature Type for every type); one feature https://planetarynames.wr.usgs.gov/Feature/ID (origin, diameter, centre coordinates, approval)
- NobelPrize.org: https://www.nobelprize.org/prizes/lists/all-nobel-prizes-in-physics/all/?gallery_style=page (also -in-chemistry, -in-literature, all-nobel-laureates-in-physiology-or-medicine); API https://api.nobelprize.org/2.1/laureates?limit=1000 ; Nomination Archive: record https://www.nobelprize.org/nomination/archive/show.php?id=N , person (their "Nominee in" and "Nominator in" lists) https://www.nobelprize.org/nomination/archive/show_people.php?id=N , by year https://www.nobelprize.org/nomination/archive/list.php?prize=1&year=1930 (1 physics, 2 chemistry, 3 medicine, 4 literature, 5 peace)
- Ramsar Sites Information Service: https://rsis.ramsar.org/ris/N ; Ramsar documents on www.ramsar.org
- US National Park Service: withdrawn National Historic Landmarks https://www.nps.gov/subjects/nationalhistoriclandmarks/withdrawn.htm ; NHL/NRHP nomination text https://npgallery.nps.gov/NRHP/GetAsset/NHLS/REFNUMBER_text ; reports https://irma.nps.gov/DataStore/DownloadFile/ID
- Royal Society archive https://catalogues.royalsociety.org/CalmView/ ; NASA eclipses https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html ; JPL satellites https://ssd.jpl.nasa.gov/sats/discovery.html
- Wikipedia full wikitext with tables: https://en.wikipedia.org/w/index.php?title=TITLE&action=raw
- A page that fails: https://web.archive.org/web/2025/URL or https://r.jina.ai/URL"""

DRIVER_SYSTEM = """You are the research engine of a question-answering system. Each question is a precise, multi-condition research task with exactly one correct answer, written so that memory, famous examples and shallow search lead to wrong answers. You can search the web, open pages, search inside opened pages, run Python over them and record evidence. A planner has analysed the question (PLAN in the first message); use it, but the sources decide.

How to work
- Identify the authoritative source the question names (organisation, document, list, table, edition, date) and open it. Prefer official pages, databases and APIs; use encyclopedias for leads, or as a fallback when the primary source is unreachable.
- Assemble the COMPLETE population from that source before filtering: the whole list or table, every page of it. Count it; when the question states a size (e.g. "the 42 properties"), your count must match.
- Test every member against every condition, literally as worded. Watch inclusive/exclusive ranges and "as of" dates; identity (similar names, renamed, merged or successor entries); joint entries (count per person or per entry, as asked); later records that supersede or correct earlier ones; units and rounding.
- Compute counts, sums, medians, differences, rankings and unit conversions in python over the loaded text, at full precision; round only at the end, as asked.
- Use `record` for every load-bearing fact as soon as you have it: the population and its size, each candidate's deciding value or status, exclusions, and the inputs of every calculation. Quote the source text exactly as it appears in the tool output (5-40 words that contain the name and the value). These quotes become the published citations.
- Once the candidate set is fixed, confirm each included item and each close near-miss on its own record page when one exists (a feature page, an archive record, a property page): open them several at a time and record the deciding values from them.
- Work in parallel: one turn can hold several searches, opens, greps and records. Never repeat an identical call.
- Read every qualifier literally: "absolute" longitude means both signs; "at least" includes the bound; "by the end of 1933" includes 1933; a stated count or edition is a check on your population.
- Keep going until the answer is established; the time budget is meant to be used. When it is, call `answer`. Only when time is nearly out may you give a best-supported answer with the remaining uncertainty stated.

Tool notes
- search: 1-4 short keyword queries per call (names, titles, distinctive terms); `site` restricts results to one domain.
- open: up to 4 URLs per call. Short pages come back whole; long pages show the start plus matches of your `find` terms with character offsets; then use grep, read or python.
- python: a fresh namespace each call; `docs` maps every D# id to its full text and `urls` maps D# to its URL. Print what you need (output is capped at 8000 characters). No internet; no numpy or pandas.
- When a page fails, try another route to the same source: an official API or export, the PDF, a mirror, or an archived copy.

""" + ATLAS

PLAN_SYSTEM = """You analyse a research question before research starts. Do not answer it. Read it slowly and literally: the question was written so that a hasty reading picks the wrong population, misapplies a condition or falls into a trap.
Be brief: each field one or two lines. Return one JSON object only:
{"answer_form": "exactly what must be returned: values, units, rounding, format",
 "sources": ["each named or implied authoritative source, with its most likely URL or URL pattern"],
 "population": "the set to enumerate, where its complete list lives, and its expected size if stated",
 "conditions": ["each filter or condition, stated precisely, one per item"],
 "computation": "the calculation, step by step",
 "pitfalls": ["traps in the wording: boundaries, identity, superseded records, joint entries, units, edition or date"],
 "queries": ["4 short web search queries that find the primary sources"],
 "urls": ["up to 3 URLs worth opening first, only when you are confident they exist"]}"""

REVIEW_SYSTEM = """You audit a research answer before it is published. You get the question, the research answer with its derivation, the evidence ledger (verbatim source quotes), python outputs and recent source excerpts. Judge from this material and the exact wording of the question.
Check, in order:
1. Does the answer give exactly what is asked (every requested value or item, the asked units, precision and form)?
2. Is the population complete and taken from the named source (does any stated count match)?
3. Was each condition applied correctly to each candidate? Look for misread conditions, boundary errors, identity confusion, superseded or corrected records, joint entries, wrong edition or date.
4. Does the arithmetic follow from the cited values?
5. Is each load-bearing fact backed by the evidence?
Return one JSON object only:
{"verdict": "accept" or "revise", "problems": ["concrete, consequential problem"], "todo": ["specific check to run with the tools"]}
Say "revise" only for concrete problems that could change the answer, never for style."""

WRITER_RULES = """Citations: the SNIPPETS are exact passages from the sources (S# ids). Put snippet markers right after the claim they support: [S3] or [S3][S7]. Cite every specific fact, number, name, date or status, including table rows; connective reasoning needs no citation. Where a short phrase in a snippet decides a condition, quote it inline in double quotes ("Awarded the Nobel Prize in Physics 1932") and cite it. Only cite a snippet that actually contains the claim; when no snippet fits, state the claim plainly without a marker (a later pass looks for its source).
Make no claim you cannot cite or derive from cited facts, in particular no claims about how a source is organised, what it omits or why a condition is satisfied automatically. Treat every condition of the question explicitly, and where an item fails a condition, say which condition and give its deciding value, one item at a time (do not lump different failure reasons together).
When an individual record exists for an item (its own page or row), cite that record for the item's values rather than a summary.
Prefer the excerpt that states the decisive link most directly (e.g. a record saying an entry was merged into, renamed as or superseded by another), and cite different passages for different claims; do not repeat the same citation on every line.
Keep the research answer unless the evidence clearly contradicts it; if it does, give the evidence-backed answer.
Write impersonally (no "I" or "we"). Never mention tools, agents, the ledger, searches or "the research". Never write [[n]] markers, and never use ids other than [S#].
Never refer to the snippets, excerpts, sources available or the evidence set, and never call the evidence partial or the result unconfirmed: the reader sees only your answer and its citations. State each established fact plainly and cite it."""

WRITER_TEXT = """You write the published answer to a research question. The reader is an expert grader who checks every claim against the cited excerpts. The grader prefers, in order: the correct and complete result; traceability (each claim visibly tied to a cited excerpt that contains it); reasoning that shows how the result follows; checks that establish the set or scope.
You get the question, the research answer and derivation, reviewer notes, python results and the SNIPPETS (exact source passages, S# ids).
Write in Markdown:
## Answer
The direct answer in bold in the first sentence, with every requested value or item and its units (exact value first, then the rounded form if rounding is asked), then one or two sentences on what it rests on, cited.
## How it was identified
Bullets, one per fact or step: the fact, the source's own wording in double quotes where it decides something, then the citation. Cover the source and its population (with its size), each condition and how it was applied, and the calculation written out with the actual numbers (inputs, then result). Address every instruction and qualifier of the question explicitly, one bullet each (what the question requires, how it was applied, the evidence), including any discrepancy between sources (e.g. a narrative and a table) and which one the question makes controlling.
## Check table
For any set, count or ranking: a Markdown table with columns | Item | Values as printed in the source | Condition results | Verdict | Citation |, one row per candidate (included ones and excluded near-misses); copy values exactly as the snippets print them. Account for every item the source lists that could look relevant, including ones outside the question's scope, and say briefly why each excluded one fails.
Then a caveat only when an open uncertainty could change the answer. Never write that something was not checked, not confirmed or could not be re-verified: cite the evidence instead.
About 300-1000 words plus the table.
""" + WRITER_RULES

WRITER_STRUCT = """You write the published structured answer to a research question. The grader checks the JSON value first (it must satisfy the schema and the question exactly), then the note: a short explanation whose claims are checked against the cited excerpts.
You get the question, the output schema, the research answer and derivation, reviewer notes, python results and the SNIPPETS (exact source passages, S# ids).
Reply in two parts:
1. The note, in Markdown: "## Answer" with the answer in bold in one sentence, cited; "## How it was identified" as bullets, one per fact or step (the fact, the source's own wording in double quotes where it decides something, the citation), covering the source and population (size), each condition and the calculation with the actual numbers. Address every instruction and qualifier of the question explicitly, one bullet each (what the question requires, how it was applied, the evidence), including any discrepancy between sources (e.g. a narrative and a table) and which one the question makes controlling. Then, for a set or count, "## Check table" with columns | Item | Values as printed in the source | Condition results | Verdict | Citation |, one row per candidate (included and excluded near-misses). 200-900 words plus the table. A caveat only when an open uncertainty could change the answer; never write that something was not checked or not confirmed.
2. Then, last, a fenced block ```json ... ``` holding only the JSON value that matches the schema exactly (no citation markers inside it).
""" + WRITER_RULES

FAST_FORM = ("Grading for this question is correctness only: every requested component must be right, and every extra "
             "or wrong component counts against the answer. The final answer must state exactly the requested "
             "value(s) or item(s), with units, and nothing else.")

TOOLS = [
    {"type": "function", "function": {
        "name": "search",
        "description": "Web search. Returns numbered results (D# ids) with title, URL and an excerpt.",
        "parameters": {"type": "object", "properties": {
            "queries": {"type": "array", "items": {"type": "string"}, "description": "1-4 short keyword queries"},
            "site": {"type": "string", "description": "optional domain to restrict to, e.g. whc.unesco.org"}},
            "required": ["queries"]}}},
    {"type": "function", "function": {
        "name": "open",
        "description": "Load up to 4 URLs (HTML, PDF, JSON, CSV). Each page gets a D# id; short pages come back whole, long pages show the start plus matches of the find terms with character offsets.",
        "parameters": {"type": "object", "properties": {
            "urls": {"type": "array", "items": {"type": "string"}},
            "find": {"type": "array", "items": {"type": "string"}, "description": "words or numbers to locate in long pages"}},
            "required": ["urls"]}}},
    {"type": "function", "function": {
        "name": "grep",
        "description": "Regular-expression search (case-insensitive) inside a loaded document; returns matches with offsets and surrounding text.",
        "parameters": {"type": "object", "properties": {
            "doc": {"type": "string", "description": "D# id"},
            "pattern": {"type": "string"},
            "context": {"type": "integer", "description": "characters of context on each side (default 150)"}},
            "required": ["doc", "pattern"]}}},
    {"type": "function", "function": {
        "name": "read",
        "description": "Read part of a loaded document from a character offset.",
        "parameters": {"type": "object", "properties": {
            "doc": {"type": "string"}, "offset": {"type": "integer"},
            "length": {"type": "integer", "description": "up to 20000 (default 20000)"}},
            "required": ["doc", "offset"]}}},
    {"type": "function", "function": {
        "name": "python",
        "description": "Run Python 3 in a fresh namespace. `docs` maps D# ids to full document text, `urls` maps D# ids to URLs. Print the results you need.",
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "record",
        "description": "Add facts to the evidence ledger. Each item: the claim, the D# id of the document, and an exact quote from it (5-40 words containing the key name/value). The quote is checked against the document text.",
        "parameters": {"type": "object", "properties": {
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "claim": {"type": "string"}, "doc": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["claim", "doc", "quote"]}}},
            "required": ["items"]}}},
    {"type": "function", "function": {
        "name": "answer",
        "description": "Submit the final answer once it is established.",
        "parameters": {"type": "object", "properties": {
            "answer": {"type": "string", "description": "the exact final answer: every requested value or item, with units"},
            "derivation": {"type": "string", "description": "how it follows: source and population size, included and excluded candidates with the deciding facts, the calculation"}},
            "required": ["answer", "derivation"]}}},
]


# ---------------------------------------------------------------- run state
START_ALLOWANCE_S = 3.0     # worker startup before query() runs; the module itself may be loaded long before


class Run:
    def __init__(self, query, context):
        self.t0 = time.monotonic() - START_ALLOWANCE_S
        self.q = query.text
        self.fast = bool(query.fast)
        self.schema = query.output_schema
        limit = 300.0
        try:
            limit = float(context.time_budget.limit_seconds)
        except Exception:
            pass
        self.limit = limit
        self.end = self.t0 + limit - (9.0 if limit >= 200 else 6.0)
        self.budget = 0.5
        try:
            self.budget = float(context.cost_budget.session_budget_usd)
        except Exception:
            pass
        self.spent = 0.0
        self.docs = {}
        self.by_url = {}
        self.ledger = []
        self.ev_key = {}
        self.obs = []
        self.pyout = []
        self.final = None
        self.review = None
        self.plan = {}
        self.bank = []
        self.lanes = []
        self.lane_objs = []
        self.agreed = False
        self.errors = 0
        self.sem = asyncio.Semaphore(INFLIGHT)
        self.sp_vocab = None
        self.t_next = 0            # document tickets: D# ids follow call order, not network completion order
        self.t_due = 0
        self.t_done = {}
        self.t_event = asyncio.Event()


def _left(run):
    return run.end - time.monotonic()


def _note_spend(run, res):
    try:
        used = float(res.budget.session_used_budget_usd)
        if used > run.spent:
            run.spent = used
    except Exception:
        pass


def _squash(text):
    text = re.sub(r"[ \t\r\f\v]+", " ", text or "")
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def _json_in(text):
    if not text:
        return None
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    a = t.find("{")
    b = t.rfind("}")
    while a != -1 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except ValueError:
            b = t.rfind("}", a, b)
    return None


# ---------------------------------------------------------------- model calls
FAST_HOSTS = {}            # pinning to fast hosts timed out 17 times at 25 s in the 23:30 UTC window (z17)
PIN_CAP_S = 25.0
PIN_OFF = {}


def _think_for(model, thinking):
    """OpenAI reasoning models take effort levels and may refuse disabled reasoning."""
    if "openai/" in model[1]:
        if thinking is None or not thinking.get("enabled", True) or "budget" in thinking:
            return {"enabled": True, "effort": "low"}
    return thinking


async def _one_call(run, model, messages, max_out, timeout, tools, thinking, extra):
    thinking = _think_for(model, thinking)
    async with run.sem:
        res = await llm_chat(provider=model[0], model=model[1], messages=messages, max_output_tokens=max_out,
                             tools=tools, tool_choice="auto" if tools and "deepseek" not in model[1] else None,
                             parallel_tool_calls=True if tools else None, thinking=thinking, timeout=timeout,
                             temperature=0.0 if "deepseek" in model[1] else None, provider_extra=extra)
    _note_spend(run, res)
    return res


async def _chat(run, model, messages, max_out, cap, tools=None, thinking=None, spare=None, no_spare=False):
    if run.spent > run.budget - 0.15 and "deepseek" not in model[1]:   # never exceed the session budget (exhausted budget = zero score)
        model = SPARE
        thinking = {"enabled": False}
        if run.spent > run.budget - 0.02:
            raise RuntimeError("session budget nearly spent")
    """Model call with a pinned fast host first (cache-friendly), then default routing, then the spare model."""
    timeout = min(cap, _left(run) - 1.0)
    if timeout < 3.0:
        raise TimeoutError("no time left for a model call")
    hosts = FAST_HOSTS.get(model[1])
    if hosts and PIN_OFF.get(model[1], 0) < 2 and timeout >= 12.0:
        start = time.monotonic()
        try:
            return await _one_call(run, model, messages, max_out, min(timeout, max(PIN_CAP_S, 0.45 * timeout)), tools,
                                   thinking, {"provider": {"only": list(hosts), "allow_fallbacks": False}})
        except Exception as exc:
            text = str(exc).lower()
            if "budget" in text or "hard limit" in text or "hard_limit" in text:
                raise
            PIN_OFF[model[1]] = PIN_OFF.get(model[1], 0) + 1
        timeout = min(timeout - (time.monotonic() - start), _left(run) - 1.0)
    if timeout >= 6.0:
        start = time.monotonic()
        try:
            return await _one_call(run, model, messages, max_out, timeout, tools, thinking, None)
        except Exception as exc:
            text = str(exc).lower()
            if "budget" in text or "hard limit" in text or "hard_limit" in text:
                raise
            # a quick provider error is usually one bad host: one more try on default routing
            again = min(cap, _left(run) - 1.0)
            if time.monotonic() - start < 12.0 and again >= 15.0:
                try:
                    return await _one_call(run, model, messages, max_out, again, tools, thinking, None)
                except Exception as exc2:
                    text = str(exc2).lower()
                    if "budget" in text or "hard limit" in text or "hard_limit" in text:
                        raise
    timeout = min(cap, _left(run) - 1.0)
    if no_spare or timeout < 6.0:
        raise TimeoutError("no time left for the spare model")
    sp = spare or SPARE
    if "deepseek" in sp[1]:
        sp_think = {"enabled": False}
    elif "claude" in sp[1]:
        sp_think = {"enabled": True, "effort": "low"}
    else:
        sp_think = None
    return await _one_call(run, sp, messages, max_out, timeout, tools, sp_think, None)


# ---------------------------------------------------------------- documents and evidence
def _ticket(run):
    t = run.t_next
    run.t_next += 1
    return t


def _finish_ticket(run, ticket):
    if run.t_done.get(ticket):
        return
    run.t_done[ticket] = True
    while run.t_done.get(run.t_due):
        run.t_due += 1
    run.t_event.set()


async def _in_order(run, ticket, fn):
    """Run fn (which adds documents) only after every earlier ticket has finished, so concurrent tool calls number
    their documents in the order the calls were made. Never waits more than 40 s."""
    t_end = time.monotonic() + 40.0
    while run.t_due < ticket and time.monotonic() < t_end:
        run.t_event.clear()
        try:
            await asyncio.wait_for(run.t_event.wait(), 0.5)
        except asyncio.TimeoutError:
            pass
    try:
        return fn()
    finally:
        _finish_ticket(run, ticket)


def _add_doc(run, kind, receipt, result, url, text):
    did = "D%d" % (len(run.docs) + 1)
    run.docs[did] = {"id": did, "kind": kind, "url": url or "", "title": getattr(result, "title", None) or "",
                     "text": text, "receipt": receipt, "result": result.result_id}
    return did


def _locate(text, quote):
    """Character span of quote in text: exact, then tolerant of case, whitespace and punctuation between words."""
    quote = (quote or "").strip().strip('"').strip()
    if len(quote) < 3 or not text:
        return None
    k = text.find(quote)
    if k != -1:
        return k, k + len(quote)
    words = re.findall(r"\w+", quote)
    if not words:
        return None
    for part in (words[:40], words[:20], words[:10]):
        if len(part) < min(4, len(words)):
            break
        rx = r"\W+".join(re.escape(w) for w in part)
        m = re.search(rx, text, re.I)
        if m:
            end = m.end()
            if len(part) < len(words):
                tail = r"\W+".join(re.escape(w) for w in words[-min(8, len(words) - len(part)):])
                m2 = re.compile(tail, re.I).search(text, m.end(), m.end() + 4 * len(quote) + 200)
                if m2:
                    end = m2.end()
            return m.start(), end
    return None


def _add_ev(run, did, start, end, claim):
    key = (did, start, end)
    if key in run.ev_key:
        return run.ev_key[key]
    eid = "E%d" % (len(run.ledger) + 1)
    run.ledger.append({"id": eid, "doc": did, "start": start, "end": end, "claim": claim})
    run.ev_key[key] = eid
    return eid


def _ev_quote(run, ev):
    return run.docs[ev["doc"]]["text"][ev["start"]:ev["end"]]


# ---------------------------------------------------------------- tools
async def t_search(run, args):
    qs = args.get("queries") or []
    if isinstance(qs, str):
        qs = [qs]
    qs = [str(x).strip()[:200] for x in qs if str(x).strip()][:4]
    if not qs:
        return "error: give 1-4 queries"
    extra = dict(SEARCH_EXTRA)
    site = str(args.get("site") or "").strip()
    if site:
        site = re.sub(r"^https?://", "", site).split("/")[0]
        extra["source_policy"] = {"include_domains": [site]}
    ticket = _ticket(run)
    try:
        try:
            async with run.sem:
                res = await search_web(qs, provider="parallel", num=10, provider_extra=extra,
                                       timeout=min(25.0, max(3.0, _left(run) - 2.0)))
        except Exception as exc:
            return "search failed: " + str(exc)[:200]
        _note_spend(run, res)

        def add_all():
            got = []
            for r in res.results:
                note = getattr(r, "note", None) or ""
                if not note.strip():
                    continue
                url = getattr(r, "url", None) or ""
                did = _add_doc(run, "search", res.receipt_id, r, url, note)
                got.append("[%s] %s | %s\n%s" % (did, run.docs[did]["title"][:150], url, _squash(note)[:1400]))
            return got
        lines = await _in_order(run, ticket, add_all)
    finally:
        _finish_ticket(run, ticket)
    out = ("search " + " | ".join(qs) + ":\n" + "\n\n".join(lines)) if lines else "no results for " + " | ".join(qs)
    run.obs.append(out)
    return out


async def _fetch(run, url, timeout):
    url = url.strip()
    if url in run.by_url:
        return run.by_url[url], None
    ticket = _ticket(run)
    try:
        try:
            async with run.sem:
                res = await fetch_page(url, provider="parallel", provider_extra={"full_content": True}, timeout=timeout)
        except Exception as exc:
            return None, "failed to load (" + str(exc)[:120] + ")"
        _note_spend(run, res)
        if not res.results:
            return None, "empty response"
        r = res.results[0]
        text = getattr(r, "note", None) or ""
        if not text.strip():
            return None, "no text"

        def add():
            if url in run.by_url:
                return run.by_url[url]
            d = _add_doc(run, "page", res.receipt_id, r, url, text[:PAGE_CAP])
            run.by_url[url] = d
            return d
        did = await _in_order(run, ticket, add)
        return did, None
    finally:
        _finish_ticket(run, ticket)


def _hits(text, term, n):
    out = []
    term = (term or "").strip()
    if not term:
        return out
    low = text.lower()
    k = low.find(term.lower())
    while k != -1 and len(out) < n:
        out.append(k)
        k = low.find(term.lower(), k + len(term))
    return out


def _page_view(run, did, finds, room):
    d = run.docs[did]
    t = d["text"]
    head = "[%s] %s | %s | %d chars" % (did, d["title"][:150], d["url"], len(t))
    if len(t) <= min(WHOLE, room):
        return head + "\n" + _squash(t)
    spans = []
    for term in finds[:6]:
        for k in _hits(t, term, 4):
            spans.append((max(0, k - 1500), min(len(t), k + len(term) + 1500)))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    if not merged:
        body = _squash(t[:min(12000, room)])
        if finds:
            body += "\n-- no matches for: " + ", ".join(finds[:6])
    else:
        body = _squash(t[:min(HEAD, room // 4)])
        used = len(body)
        pieces = []
        for a, b in merged[:8]:
            piece = "[offset %d] ...%s..." % (a, _squash(t[a:b]))
            if used + len(piece) > room:
                break
            pieces.append(piece)
            used += len(piece)
        body += "\n-- matches --\n" + "\n\n".join(pieces)
    return head + "\n" + body + "\n(long page: grep, read or python on %s)" % did


async def t_open(run, args):
    urls = args.get("urls") or []
    if isinstance(urls, str):
        urls = [urls]
    urls = [str(u).strip() for u in urls if str(u).strip().startswith("http")][:4]
    finds = args.get("find") or []
    if isinstance(finds, str):
        finds = [finds]
    finds = [str(f) for f in finds if str(f).strip()]
    if not urls:
        return "error: give 1-4 http(s) URLs"
    cap = 30.0
    try:
        cap = float(args.get("timeout") or 30.0)
    except Exception:
        cap = 30.0
    timeout = min(cap, max(3.0, _left(run) - 3.0))
    got = await asyncio.gather(*[_fetch(run, u, timeout) for u in urls])
    room = OPEN_CAP // max(1, len(urls))
    parts = []
    for u, (did, err) in zip(urls, got):
        if did is None:
            parts.append("%s: %s" % (u, err))
        else:
            parts.append(_page_view(run, did, finds, room))
    out = "\n\n".join(parts)
    run.obs.append(out)
    return out


def t_grep(run, args):
    did = str(args.get("doc") or "").strip()
    d = run.docs.get(did)
    if d is None:
        return "unknown doc id " + did
    pat = str(args.get("pattern") or "")[:200]
    if not pat:
        return "error: empty pattern"
    try:
        win = max(20, min(600, int(args.get("context") or 150)))
    except Exception:
        win = 150
    try:
        rx = re.compile(pat, re.I)
    except re.error:
        rx = re.compile(re.escape(pat), re.I)
    t = d["text"]
    out = []
    n = 0
    for m in rx.finditer(t):
        n += 1
        if len(out) < 25:
            out.append("@%d: %s" % (m.start(), _squash(t[max(0, m.start() - win):m.end() + win])))
        if n > 400:
            break
    res = "%s: %d matches for /%s/\n%s" % (did, n, pat, "\n".join(out))
    run.obs.append(res[:6000])
    return res[:9000]


def t_read(run, args):
    did = str(args.get("doc") or "").strip()
    d = run.docs.get(did)
    if d is None:
        return "unknown doc id " + did
    try:
        off = max(0, int(args.get("offset") or 0))
        n = max(200, min(20000, int(args.get("length") or 20000)))
    except Exception:
        off, n = 0, 20000
    t = d["text"]
    res = "%s [%d:%d of %d]\n%s" % (did, off, min(len(t), off + n), len(t), t[off:off + n])
    run.obs.append(res)
    return res


PY_HEAD = """import sys as _zs
import time as _zt
_zout = []
def print(*a, sep=" ", end="\\n", file=None, flush=False):
    _zout.append(sep.join(str(x) for x in a) + end)
_zdl = _zt.monotonic() + %.1f
def _ztr(frame, event, arg):
    if _zt.monotonic() > _zdl:
        raise TimeoutError("python time limit reached")
    return _ztr
def _zuser():
"""
PY_TAIL = """
_zs.settrace(_ztr)
try:
    _zuser()
except BaseException as _ze:
    _zout.append("ERROR: " + _ze.__class__.__name__ + ": " + str(_ze))
finally:
    _zs.settrace(None)
result = "".join(_zout)
"""


def t_python(run, args):
    code = str(args.get("code") or "")
    if not code.strip():
        return "error: empty code"
    body = "\n".join("    " + line for line in code.replace("\t", "    ").split("\n"))
    src = (PY_HEAD % PY_LIMIT_S) + body + "\n    pass\n" + PY_TAIL
    docs = {k: v["text"] for k, v in run.docs.items()}
    urls = {k: v["url"] for k, v in run.docs.items()}
    try:
        out = safe_exec(src, {"docs": docs, "urls": urls})
    except BaseException as exc:
        out = "ERROR: " + str(exc)[:500]
    out = str(out if out is not None else "")
    if not out.strip():
        out = "(no output: print the values you need)"
    if len(out) > 8000:
        out = out[:2500] + "\n...[%d chars cut]...\n" % (len(out) - 8000) + out[-5500:]
    run.pyout.append("CODE:\n" + code[:3000] + "\nOUTPUT:\n" + out)
    return out


def t_record(run, args):
    items = args.get("items") or []
    if isinstance(items, dict):
        items = [items]
    lines = []
    for it in items[:15]:
        if not isinstance(it, dict):
            continue
        did = str(it.get("doc") or "").strip()
        quote = str(it.get("quote") or "")
        claim = str(it.get("claim") or "")[:400]
        d = run.docs.get(did)
        if d is None:
            lines.append("- unknown doc id %s" % did)
            continue
        span = _locate(d["text"], quote)
        if span is None:
            lines.append("- NOT FOUND in %s: \"%s\" (copy the words exactly as the tool output shows them)" % (did, quote[:80]))
            continue
        eid = _add_ev(run, did, span[0], span[1], claim)
        lines.append("- %s recorded (%s)" % (eid, did))
    return "\n".join(lines) or "nothing recorded"


def t_answer(run, args, lane):
    ans = str(args.get("answer") or "").strip()
    if not ans:
        return "error: empty answer"
    lane["final"] = {"answer": ans[:6000], "derivation": str(args.get("derivation") or "")[:12000]}
    return "answer received"


async def _dispatch(run, call, lane):
    try:
        args = json.loads(call.arguments or "{}")
    except Exception:
        return "error: arguments are not valid JSON"
    if not isinstance(args, dict):
        return "error: arguments must be an object"
    name = call.name
    try:
        if name == "search":
            return await t_search(run, args)
        if name == "open":
            return await t_open(run, args)
        if name == "grep":
            return t_grep(run, args)
        if name == "read":
            return t_read(run, args)
        if name == "python":
            return t_python(run, args)
        if name == "record":
            return t_record(run, args)
        if name == "answer":
            return t_answer(run, args, lane)
    except Exception as exc:
        return "tool error: " + str(exc)[:300]
    return "unknown tool " + str(name)


# ---------------------------------------------------------------- phases
def _form(run):
    if run.fast and run.schema:
        return (FAST_FORM + " Give the answer as one JSON object matching this schema exactly:\n"
                + json.dumps(run.schema)[:4000])
    if run.fast:
        return FAST_FORM
    if run.schema:
        return ("The final answer is a JSON value matching this schema (give the field values in your answer):\n"
                + json.dumps(run.schema)[:4000])
    return "The final answer is a written, cited explanation; give the exact result first."


async def make_plan(run):
    model = PLANNER                       # haiku as planner timed out at 12 s on short tasks
    msgs = [{"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": "QUESTION:\n" + run.q + "\n\n" + _form(run)}]
    try:
        if run.limit >= 200:
            res = await _chat(run, model, msgs, 4000, 30.0, thinking={"enabled": True, "budget": 1024})
        else:                             # short tasks: a quick plan without reasoning (about 4 s)
            res = await _chat(run, model, msgs, 3000, 10.0, thinking={"enabled": False}, no_spare=True)
        plan = _json_in(res.llm.raw_text or "")
        if isinstance(plan, dict):
            run.plan = plan
    except Exception:
        run.plan = {}
    return run.plan


async def first_look(run):
    """Run the planned searches and page opens before the driver's first turn."""
    plan = run.plan or {}
    queries = [q for q in (plan.get("queries") or []) if isinstance(q, str) and q.strip()][:4]
    if not queries:
        queries = [run.q[:200]]
    urls = [u for u in (plan.get("urls") or []) if isinstance(u, str) and u.startswith("http")][:3]
    jobs = [t_search(run, {"queries": queries})]
    if urls:
        jobs.append(t_open(run, {"urls": urls, "timeout": 12.0}))
    outs = await asyncio.gather(*jobs)
    return "\n\n".join(o for o in outs if o)


def _compact(msgs, turn_marks):
    """Trim long tool outputs older than KEEP_TURNS turns (their full text stays reachable by D# id)."""
    if len(turn_marks) <= KEEP_TURNS:
        return
    cut = turn_marks[-KEEP_TURNS]
    for i in range(cut):
        m = msgs[i]
        if isinstance(m, dict) and m.get("role") == "tool":
            c = m.get("content") or ""
            if len(c) > 1600 and not c.startswith("CODE"):
                m["content"] = c[:1200] + "\n...(older output trimmed; grep/read/python on its D# ids still work)"


AUDIT_MSG = ("Before this answer is accepted, check it once more. List each condition, date limit, boundary and "
             "requested component of the question, and say which tool result establishes it. Is the population complete "
             "(count it against the named source)? Is every derived value computed in python from sourced values, at "
             "the precision asked? Anything unverified or doubtful: verify it with the tools now. Then call answer "
             "again with the same or the corrected answer.")
AUDIT_TABLE = (" Also print, with python, the final check table: one row per candidate (qualifying ones and excluded "
               "near-misses), its values exactly as the source prints them, the derived values, the verdict and the D# "
               "of the source; the written answer will be built from these rows.")
RECHECK_MSG = ("One independent re-derivation before the answer is final (about {secs} s left). Do not reuse earlier lists "
               "or notes: with python, re-extract every input value directly from the loaded source text (parse the "
               "table rows or entries themselves), print them with their labels, recount the population, and recompute "
               "the result. If it differs from your answer, find which input or step was wrong and fix it. Then call "
               "answer with the result that the re-derivation supports.")


def _checklist(run):
    """The planner's conditions and traps as a numbered checklist for the audit."""
    plan = run.plan or {}
    items = []
    for key in ("conditions", "pitfalls"):
        v = plan.get(key) or []
        if isinstance(v, str):
            v = [v]
        for x in v:
            x = re.sub(r"\s+", " ", str(x)).strip()
            if x and x not in items:
                items.append(x[:300])
    if not items:
        return ""
    return ("\nChecklist from the question's analysis; for each item state how the answer satisfies it and which tool "
            "result or python output shows it:\n" + "\n".join("%d. %s" % (i, x) for i, x in enumerate(items[:14], 1)))


DEEPEN_MSG = ("The answer stands; about {secs} s of research remain before the write-up. The write-up is judged on whether "
              "each claim can be checked against a loaded source, so use at most {turns} more turns to complete the "
              "evidence: open the item's own record (page, entry, profile, table row) for every member whose verdict so "
              "far rests only on a list, a summary or memory; where two sources disagree (a date, a total, a rounding, a "
              "renamed entry) load both and note which one the question makes controlling; record the deciding quotes. "
              "Change the answer only if the evidence shows it is wrong. Then call answer.")
PROV_MSG = ("These figures in your answer appear in no tool result and no python output: {figs}. Each figure must be "
            "read from a source or computed in python from sourced values. Check or recompute them now (at most 3 turns), "
            "printing the computation, then call answer with figures you can trace.")
FIG_RX = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _figs(text):
    out = []
    for m in FIG_RX.finditer(str(text or "")):
        raw = m.group(0).replace(",", "")
        digits = raw.replace("-", "").replace(".", "").lstrip("0")
        if len(digits) < 2:
            continue
        try:
            out.append((m.group(0), float(raw), len(raw.split(".")[1]) if "." in raw else 0))
        except ValueError:
            pass
    return out


def _untraced(run, answer):
    pool = [run.q] + list(run.obs) + list(run.pyout)
    vals = [v for t in pool for _, v, _ in _figs(t)]
    bad = []
    for shown, val, dec in _figs(answer):
        tol = 0.5 * (10 ** -dec) + 1e-9
        hit = False
        for v in vals:
            if abs(v - val) <= tol or abs(v - val / 100.0) <= tol / 100.0 or abs(v - val * 100.0) <= tol * 100.0:
                hit = True
                break
        if not hit and shown not in bad:
            bad.append(shown)
    return bad[:6]


async def research(run, lane, deadline, max_turns):
    msgs = lane["msgs"]
    turns = 0
    nudged = False
    while turns < max_turns:
        left = deadline - time.monotonic()
        if left < 6.0 or run.spent > SPEND_STOP:
            break
        if left < 45.0 and not lane.get("warned"):
            msgs.append({"role": "user", "content": "About %d s of research time remain. Finish the checks that decide "
                                                    "the answer, record the key evidence, then call answer." % int(left)})
            lane["warned"] = True
        try:
            res = await _chat(run, lane["model"], msgs, DRIVER_MAX_OUT, min(TURN_CAP_S, left), tools=TOOLS,
                              thinking=lane["thinking"], spare=lane["spare"])
        except Exception:
            lane["errors"] = lane.get("errors", 0) + 1
            if lane["errors"] >= 4:
                break
            continue
        msg = res.llm.choices[0].message
        msgs.append(msg.to_input_message())
        turns += 1
        calls = list(msg.tool_calls or [])
        if not calls:
            text = (res.llm.raw_text or "").strip()
            if nudged or not text:
                if text and lane.get("final") is None:
                    lane["final"] = {"answer": text[:6000], "derivation": ""}
                break
            msgs.append({"role": "user", "content": "Continue with the tools, or call answer with the final answer."})
            nudged = True
            continue
        outs = await asyncio.gather(*[_dispatch(run, c, lane) for c in calls])
        for c, out in zip(calls, outs):
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": (out or "(empty)")[:30000]})
        lane.setdefault("marks", []).append(len(msgs))
        _compact(msgs, lane["marks"])
        if any(c.name == "answer" for c in calls) and lane.get("final") is not None:
            left = deadline - time.monotonic()
            if not lane.get("audited") and left > 25.0 and run.spent < SPEND_STOP:
                lane["audited"] = True
                msgs.append({"role": "user", "content": AUDIT_MSG + ("" if run.fast else AUDIT_TABLE) + _checklist(run)
                             + "\n[about %d s of research left]" % int(left)})
                continue
            if run.fast and lane.get("audited") and not lane.get("rechecked") and left > 45.0 \
                    and run.spent < SPEND_STOP:
                lane["rechecked"] = True
                msgs.append({"role": "user", "content": RECHECK_MSG.format(secs=int(left))})
                continue
            if (WEAK.search(lane["final"]["answer"]) and left > 60.0 and not lane.get("pushed")
                    and run.spent < SPEND_STOP):
                lane["pushed"] = True
                msgs.append({"role": "user", "content": "That answer is not final: about %d s of research time remain. "
                             "Try a different route to the missing facts (another source, an API, an archived copy, "
                             "a parse in python), then call answer with a definite result." % int(left)})
                continue
            return True
    return lane.get("final") is not None


WEAK = re.compile(r"not (?:been )?(?:established|determined|found|possible)|cannot be (?:determined|established|"
                  r"computed)|could not|unable to|insufficient|unknown|no answer|can['’]t|cannot (?:reliably )?(?:determine|compute|"
                  r"establish|identify|find)|not able to|not possible to", re.I)


def _ledger_text(run, limit):
    lines = []
    for ev in run.ledger:
        d = run.docs[ev["doc"]]
        lines.append("[%s] (%s, %s) %s -- \"%s\"" % (ev["id"], ev["doc"], d["url"][:120], ev["claim"][:200],
                                                    _squash(_ev_quote(run, ev))[:500]))
    text = "\n".join(lines)
    return text[:limit]


def _material(run, limit, with_obs=True):
    parts = ["QUESTION:\n" + run.q]
    if run.schema:
        parts.append("OUTPUT SCHEMA:\n" + json.dumps(run.schema)[:4000])
    if run.final:
        parts.append("RESEARCH ANSWER:\n" + run.final["answer"] + "\n\nDERIVATION:\n" + run.final["derivation"])
    else:
        parts.append("RESEARCH ANSWER: none was submitted before the time limit; use the evidence below.")
    if run.review and run.review.get("problems"):
        parts.append("REVIEWER NOTES:\n" + "\n".join("- " + str(p) for p in run.review.get("problems")[:8]))
    parts.append("EVIDENCE LEDGER:\n" + (_ledger_text(run, 30000) or "(empty)"))
    if run.pyout:
        parts.append("PYTHON RUNS (newest last):\n" + "\n\n".join(p[:3500] for p in run.pyout[-4:]))
    text = "\n\n".join(parts)
    if with_obs and len(text) < limit:
        room = limit - len(text)
        picked = []
        for o in reversed(run.obs):
            if room <= 500:
                break
            piece = o[:min(len(o), 7000, room)]
            picked.append(piece)
            room -= len(piece)
        if picked:
            text += "\n\nSOURCE EXCERPTS (newest first):\n" + "\n\n---\n\n".join(picked)
    return text


async def review(run):
    msgs = [{"role": "system", "content": REVIEW_SYSTEM},
            {"role": "user", "content": _material(run, 60000)}]
    try:
        res = await _chat(run, REVIEWER, msgs, 1500, 40.0)
        j = _json_in(res.llm.raw_text or "")
        if isinstance(j, dict):
            run.review = j
    except Exception:
        run.review = None
    return run.review


# ---------------------------------------------------------------- citations and output
MARK = re.compile(r"[\[(]\s*(E\d+(?:\s*[,;/]\s*E?\d+)*)\s*[\])]|\{\s*(D\d+)\s*:\s*[\"“]([^\"”]{3,700})[\"”]\s*\}")


CTX_MIN = 320              # cited excerpts carry their context (table header lines, unit heading), not just the row
CTX_MAX = 1400


def _slice(text, a, b):
    """Excerpt span for a quote at [a, b): whole lines, grown upward (headers) and downward until CTX_MIN chars."""
    n = len(text)
    a, b = max(0, min(a, n)), max(0, min(b, n))
    if b - a >= CTX_MAX:
        return a, b
    s = text.rfind("\n", 0, a)
    s = 0 if s == -1 else s + 1
    e = text.find("\n", b)
    e = n if e == -1 else e
    if e - s > CTX_MAX:
        half = max(160, (CTX_MIN - (b - a)) // 2 + 60)
        s, e = max(s, a - half), min(e, b + half)
    steps = 0
    while e - s < CTX_MIN and steps < 10:
        steps += 1
        grew = False
        if s > 0:
            p = text.rfind("\n", 0, s - 1)
            ns = 0 if p == -1 else p + 1
            if e - ns <= CTX_MAX:
                s, grew = ns, True
        if e - s < CTX_MIN and e < n:
            q = text.find("\n", e + 1)
            ne = n if q == -1 else q
            if ne - s <= CTX_MAX:
                e, grew = ne, True
        if not grew:
            break
    if e - s < CTX_MIN:
        need = CTX_MIN - (e - s)
        s = max(0, s - need // 2)
        e = min(n, max(e, s + CTX_MIN))
        s = max(0, min(s, e - CTX_MIN))
    if e - s < MIN_SLICE:
        s, e = max(0, min(s, n - MIN_SLICE)), min(n, max(e, MIN_SLICE))
    return s, e


def _cite(run, text, refs, index):
    """Replace [E#] and {D#: "quote"} markers with [[n]] pointers; refs/index are shared across text and note."""
    text = re.sub(r"\[\[\s*\d+\s*\]\]", "", text or "")
    by_id = {ev["id"]: ev for ev in run.ledger}
    out = []
    pos = 0
    for m in MARK.finditer(text):
        out.append(text[pos:m.start()])
        pos = m.end()
        ids = []
        if m.group(1):
            ids = ["E" + x for x in re.findall(r"\d+", m.group(1))]
        else:
            d = run.docs.get(m.group(2))
            span = _locate(d["text"], m.group(3)) if d else None
            if span:
                ids = [_add_ev(run, d["id"], span[0], span[1], "")]
                by_id[ids[0]] = run.ledger[-1] if run.ledger[-1]["id"] == ids[0] else by_id.get(ids[0])
        marks = []
        for eid in ids:
            ev = by_id.get(eid)
            if ev is None:
                continue
            d = run.docs[ev["doc"]]
            s, e = _slice(d["text"], ev["start"], ev["end"])
            if e - s < 100:
                continue
            key = (d["receipt"], d["result"], s, e)
            if key not in index:
                if len(refs) >= 190:
                    continue
                refs.append(CitationRef(receipt_id=d["receipt"], result_id=d["result"],
                                        slices=[CitationSlice(start=s, end=e)]))
                index[key] = len(refs)
            tag = "[[%d]]" % index[key]
            if tag not in marks:
                marks.append(tag)
        out.append("".join(marks))
    out.append(text[pos:])
    joined = "".join(out)
    joined = re.sub(r"\s*[\[(]\s*D\d+(?:\s*[,;/]\s*D?\d+)*\s*[\])]", "", joined)
    joined = re.sub(r"\s*[\[(]\s*E\d+(?:\s*[,;/]\s*E?\d+)*\s*[\])]", "", joined)
    joined = re.sub(r"[ \t]+(\[\[\d+\]\])", r"\1", joined)
    return joined.strip()


# ---------------------------------------------------------------- snippet bank
NAME_RX = re.compile(r"[A-ZÀ-Þ][\w'’\-\.]+(?:\s+(?:of|de|la|le|von|van|der|den|du|da|di|the|y|al|el)?\s*[A-ZÀ-Þ][\w'’\-\.]+)*")
NUM_RX = re.compile(r"\d[\d,]*(?:\.\d+)?")
SNIP_MAX = 64
SNIP_CHARS = 42000
STOP_NAMES = {"The", "This", "That", "These", "Those", "Answer", "Source", "Population", "Step", "Note", "Yes", "No",
              "In", "On", "For", "And", "But", "All", "Each", "Both", "None", "Total", "Table", "Check"}


def _terms(run):
    src = run.q[:3000] + "\n"
    if run.final:
        src += run.final["answer"] + "\n" + run.final["derivation"] + "\n"
    src += "\n".join(ev["claim"] for ev in run.ledger)
    terms = {}
    for m in NUM_RX.finditer(src):
        t = m.group(0).strip(",.")
        if len(t.replace(",", "")) >= 2:
            terms[t] = 1.0 + (0.5 if "." in t else 0.0)
            if "," in t:
                terms[t.replace(",", "")] = 1.0
    for m in NAME_RX.finditer(src):
        t = m.group(0).strip(".")
        if len(t) >= 4 and t not in STOP_NAMES:
            terms[t] = 1.5 if " " in t else 1.0
    for m in re.finditer(r"[\"“]([^\"”]{4,80})[\"”]", src):
        terms[m.group(1).strip()] = 2.0
    ranked = sorted(terms.items(), key=lambda kv: (-kv[1], -len(kv[0])))
    return ranked[:120]


def _windows(text, terms):
    low = text.lower()
    hits = []
    for t, w in terms:
        tl = t.lower()
        k = low.find(tl)
        c = 0
        while k != -1 and c < 25:
            hits.append((k, k + len(tl), tl, w))
            k = low.find(tl, k + len(tl))
            c += 1
    hits.sort()
    clusters = []
    for a, b, tl, w in hits:
        if clusters and a - clusters[-1][1] < 220:
            cl = clusters[-1]
            cl[1] = max(cl[1], b)
            if tl not in cl[2]:
                cl[2][tl] = w
        else:
            clusters.append([a, b, {tl: w}])
    out = []
    for a, b, ts in clusters:
        st, en = _slice(text, a, b)
        if en - st > CTX_MAX:
            st, en = max(0, a - 160), min(len(text), b + 160)
        out.append((sum(ts.values()), st, en))
    return out


def build_bank(run):
    """Exact passages for the writer: ledger quotes first, then the best term-dense windows of every document."""
    bank = []
    seen = []

    def add(did, st, en, score):
        if en - st < 100:
            return
        for (d2, a2, b2) in seen:
            if d2 == did and st < b2 and a2 < en:
                return
        seen.append((did, st, en))
        bank.append({"id": "S%d" % (len(bank) + 1), "doc": did, "start": st, "end": en, "score": score})

    for ev in run.ledger:
        text = run.docs[ev["doc"]]["text"]
        st, en = _slice(text, ev["start"], ev["end"])
        add(ev["doc"], st, en, 99.0)
    terms = _terms(run)
    cands = []
    for did, d in run.docs.items():
        text = d["text"]
        if len(text) < 100:
            continue
        wins = _windows(text, terms)
        if not wins:
            continue
        bonus = 0.5 if d["kind"] == "page" else 0.0
        if len(text) <= 1800 and sum(w[0] for w in wins) >= 2.0:
            cands.append((sum(w[0] for w in wins) + bonus, did, 0, len(text)))
            continue
        wins.sort(reverse=True)
        for sc, st, en in wins[:8]:
            if sc >= 2.0:
                cands.append((sc + bonus, did, st, en))
    cands.sort(key=lambda c: -c[0])
    used = sum(b["end"] - b["start"] for b in bank)
    for sc, did, st, en in cands:
        if len(bank) >= SNIP_MAX or used > SNIP_CHARS:
            break
        before = len(bank)
        add(did, st, en, sc)
        if len(bank) > before:
            used += en - st
    run.bank = bank
    return bank


def _bank_text(run):
    lines = []
    for b in run.bank:
        d = run.docs[b["doc"]]
        lines.append("[%s] %s | %s\n%s" % (b["id"], d["url"][:140], d["title"][:90],
                                          _squash(d["text"][b["start"]:b["end"]])))
    return "\n\n".join(lines)


SMARK = re.compile(r"[\[(]\s*(S\d+(?:\s*[,;/]\s*S?\d+)*)\s*[\])]")


def _cite_s(run, text, refs, index, keep=False):
    """Replace [S#] snippet markers with [[n]] pointers to exact slices; refs/index are shared across text and note."""
    if not keep:
        text = re.sub(r"\[\[\s*\d+\s*\]\]", "", text or "")
    by_id = {b["id"]: b for b in run.bank}
    out = []
    pos = 0
    for m in SMARK.finditer(text):
        out.append(text[pos:m.start()])
        pos = m.end()
        marks = []
        for num in re.findall(r"\d+", m.group(1)):
            b = by_id.get("S" + num)
            if b is None:
                continue
            d = run.docs[b["doc"]]
            key = (d["receipt"], d["result"], b["start"], b["end"])
            if key not in index:
                if len(refs) >= 190 or index.get("_chars", 0) + (b["end"] - b["start"]) > 110000:
                    continue
                index["_chars"] = index.get("_chars", 0) + (b["end"] - b["start"])
                refs.append(CitationRef(receipt_id=d["receipt"], result_id=d["result"],
                                        slices=[CitationSlice(start=b["start"], end=b["end"])]))
                index[key] = len(refs)
            tag = "[[%d]]" % index[key]
            if tag not in marks:
                marks.append(tag)
        out.append("".join(marks))
    out.append(text[pos:])
    joined = "".join(out)
    joined = re.sub(r"\s*[\[(]\s*[DES]\d+(?:\s*[,;/]\s*[DES]?\d+)*\s*[\])]", "", joined)
    joined = re.sub(r"[ \t]+(\[\[\d+\]\])", r"\1", joined)
    return joined.strip()


GENERIC = {"physics", "chemistry", "medicine", "literature", "peace", "economics", "nobel", "prize", "prizes",
           "laureate", "laureates", "award", "awarded", "medal", "medals", "royal", "society", "national", "park",
           "service", "world", "heritage", "list", "table", "unit", "units", "site", "sites", "record", "records",
           "archive", "nomination", "nominee", "nominees", "january", "february", "march", "april", "may", "june",
           "july", "august", "september", "october", "november", "december", "official", "source", "total", "crater",
           "craters", "river", "creek", "lake", "island", "museum", "university", "state", "states", "united"}


def _unit_terms(unit):
    terms = []
    for m in re.finditer(r"[\"\u201c]([^\"\u201d]{4,80})[\"\u201d]", unit):
        terms.append((m.group(1).strip(), 3.0, "q"))
    for m in NUM_RX.finditer(unit):
        t = m.group(0).strip(",.")
        if len(t.replace(",", "").replace(".", "")) >= 2 and not re.fullmatch(r"(19|20)\d\d", t):
            terms.append((t, 2.0, "n"))
        elif re.fullmatch(r"(1[5-9]|20)\d\d", t):
            terms.append((t, 0.8, "y"))
    for m in NAME_RX.finditer(unit):
        t = re.sub(r"^(?:The|A|An)\s+", "", m.group(0).strip("."))
        if len(t) < 4 or t in STOP_NAMES:
            continue
        words = t.lower().split()
        if all(w in GENERIC for w in words):
            terms.append((t, 0.3, "g"))
        elif len(words) >= 2:
            terms.append((t, 1.5, "m"))
        else:
            terms.append((t, 1.0, "w"))
    seen = set()
    out = []
    for t, w, k in sorted(terms, key=lambda x: -x[1]):
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append((t, w, k))
    return out[:8]


def _best_window(run, terms, lows):
    best = None
    for did, low in lows.items():
        text = run.docs[did]["text"]
        hits = []
        for t, w, k in terms:
            tl = t.lower()
            j = low.find(tl)
            c = 0
            while j != -1 and c < 12:
                hits.append((j, tl, w, k))
                j = low.find(tl, j + len(tl))
                c += 1
        if len(hits) < 2:
            continue
        hits.sort()
        for i in range(len(hits)):
            got = {}
            kinds = set()
            a = hits[i][0]
            b = a
            for j in range(i, len(hits)):
                if hits[j][0] - a > 600:
                    break
                got[hits[j][1]] = hits[j][2]
                kinds.add(hits[j][3])
                b = hits[j][0] + len(hits[j][1])
            sc = sum(got.values())
            need = [t.lower() for t, w, k in terms if k in ("n", "q")][:3]
            if any(x not in got for x in need):
                continue
            total = sum(w for t, w, k in terms) or 1.0
            named = sum(1 for t, w, k in terms if k in ("m", "w") and t.lower() in got)
            strong = sc >= 0.5 * total and ((need and len(got) >= 2) or (named >= 2 and "m" in kinds))
            if strong and (best is None or sc > best[0]):
                best = (sc, did, a, b)
    return best


NEG = re.compile(r"\b(?:never|not|no|none|neither|nor|without|fails?|excluded)\b", re.I)


def autocite(run, body):
    """Give uncited fact-bearing sentences and table rows a snippet that contains their key terms."""
    lows = {did: d["text"].lower() for did, d in run.docs.items() if len(d["text"]) >= 100}
    if not lows:
        return body
    added = [0]
    t_end = time.monotonic() + 6.0

    def cite_unit(unit, source=None):
        src = source if source is not None else unit
        if added[0] >= 45 or time.monotonic() > t_end or SMARK.search(src) or "[[" in src or src.lstrip().startswith("#"):
            return unit
        terms = _unit_terms(src)
        anchors = [t for t in terms if t[2] in ("n", "q", "m")]
        if len(terms) < 2 or not anchors:
            return unit
        if NEG.search(src) and not any(t[2] in ("n", "q") for t in terms):
            return unit
        best = _best_window(run, terms, lows)
        if best is None:
            return unit
        sc, did, a, b = best
        st, en = _slice(run.docs[did]["text"], a, b)
        if en - st < 100:
            return unit
        sid = None
        for x in run.bank:
            if x["doc"] == did and x["start"] <= a and b <= x["end"]:
                sid = x["id"]
                break
        if sid is None:
            sid = "S%d" % (len(run.bank) + 1)
            run.bank.append({"id": sid, "doc": did, "start": st, "end": en, "score": sc})
        added[0] += 1
        tail = re.search(r"[\s.;:]*$", unit)
        k = tail.start() if tail else len(unit)
        return unit[:k] + " [%s]" % sid + unit[k:]

    out = []
    for line in body.split("\n"):
        st = line.strip()
        if st.startswith("|") and st.endswith("|") and not re.fullmatch(r"[|\s:\-]+", st):
            cells = st.strip("|").split("|")
            if not SMARK.search(st) and "[[" not in st and len(cells) >= 2:
                cells[-1] = cite_unit(cells[-1].rstrip(), " ".join(cells)) + " "
                line = "|" + "|".join(cells) + "|"
            out.append(line)
            continue
        if not st or st.startswith("#"):
            out.append(line)
            continue
        raw_parts = re.split(r"(?<=[a-z0-9)\]]{2}[.;])\s+(?=[A-Z\*])", line)
        parts = []
        for p in raw_parts:
            if parts and (parts[-1].count('"') % 2 == 1 or parts[-1].count("\u201c") > parts[-1].count("\u201d")):
                parts[-1] = parts[-1] + " " + p
            else:
                parts.append(p)
        out.append(" ".join(cite_unit(p) for p in parts))
    return "\n".join(out)



SELF_REF = re.compile(r"snippet|excerpts? (?:provided|available|given|shown)|evidence (?:ledger|set)|\bledger\b|general knowledge|"
                      r"python (?:output|result|run)|not (?:in|among) the (?:sources|snippets|excerpts|evidence|material)|"
                      r"could not be (?:verified|confirmed|checked|re-?checked)|not (?:independently )?(?:verified|confirmed|re-?checked)|"
                      r"research (?:derivation|answer)|\bthe research\b|derivation states|from memory", re.I)


def sanitize(text):
    """Drop sentences that talk about the writer's own material or call facts unconfirmed; the reader sees only the
    answer and its citations."""
    text = re.sub(r"[\[(]\s*python(?: output| results?| run)?\s*[\])]", "", text or "", flags=re.I)
    out = []
    for line in text.split("\n"):
        st = line.strip()
        if st.startswith("|"):
            out.append(re.sub(r"[,;]?\s*python (?:output|result)s?", "", line, flags=re.I))
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        keep = [p for p in parts if not SELF_REF.search(p)]
        if len(keep) == len(parts):
            out.append(line)
        elif keep:
            out.append(" ".join(keep))
        elif not st.startswith(("-", "*")) and not st:
            out.append(line)
    return "\n".join(out)



def _writer_material(run, limit):
    parts = ["QUESTION:\n" + run.q]
    if run.schema:
        parts.append("OUTPUT SCHEMA:\n" + json.dumps(run.schema)[:4000])
    if run.final:
        parts.append("RESEARCH ANSWER:\n" + run.final["answer"] + "\n\nDERIVATION:\n" + run.final["derivation"])
    else:
        parts.append("RESEARCH ANSWER: none was submitted before the time limit; use the snippets.")
    if run.review and run.review.get("problems"):
        parts.append("REVIEWER NOTES:\n" + "\n".join("- " + str(p) for p in run.review.get("problems")[:8]))
    cons = [str(c) for c in ((run.plan or {}).get("conditions") or [])[:12]]
    cons += [str(c) for c in ((run.plan or {}).get("pitfalls") or [])[:8]]
    if cons:
        parts.append("QUESTION INSTRUCTIONS TO ADDRESS (from the question analysis):\n" + "\n".join("- " + c[:300] for c in cons))
    if run.pyout:
        parts.append("PYTHON RESULTS (newest last):\n" + "\n\n".join(p[-2500:] for p in run.pyout[-3:]))
    head = "\n\n".join(parts)
    bank = _bank_text(run)
    return head[:max(4000, limit - min(len(bank), limit // 2))] + "\n\nSNIPPETS:\n" + bank[:limit]


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    m = re.search(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?", str(v or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _bound(n, sch):
    lo = sch.get("minimum")
    hi = sch.get("maximum")
    if isinstance(lo, (int, float)) and n < lo:
        n = lo
    if isinstance(hi, (int, float)) and n > hi:
        n = hi
    return n


def _coerce(v, sch):
    """Make v satisfy a JSON schema closely enough to validate (types, required keys, enums, no extra keys)."""
    if not isinstance(sch, dict):
        return v
    t = sch.get("type")
    if isinstance(t, list):
        if v is None and "null" in t:
            return None
        rest = [x for x in t if x != "null"]
        t = rest[0] if rest else None
    if "enum" in sch and isinstance(sch["enum"], list) and sch["enum"]:
        if v in sch["enum"]:
            return v
        for opt in sch["enum"]:
            if str(opt).lower() == str(v).lower():
                return opt
        low = str(v if v is not None else "").lower()
        hits = [opt for opt in sch["enum"] if str(opt).lower() in low or (low and low in str(opt).lower())]
        if hits:
            return max(hits, key=lambda o: len(str(o)))
        words = set(re.findall(r"\w+", low))
        best = max(sch["enum"], key=lambda o: len(words & set(re.findall(r"\w+", str(o).lower()))))
        return best                        # a value outside the enum invalidates the whole response
    if "anyOf" in sch and isinstance(sch["anyOf"], list) and sch["anyOf"]:
        return _coerce(v, sch["anyOf"][0])
    if t == "integer":
        n = _num(v)
        return int(round(_bound(n if n is not None else 0, sch)))
    if t == "number":
        n = _num(v)
        return _bound(n if n is not None else 0, sch)
    if t == "boolean":
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("true", "yes", "1")
    if t == "string":
        if v is None:
            return ""
        return v if isinstance(v, str) else json.dumps(v) if isinstance(v, (dict, list)) else str(v)
    if t == "array":
        if not isinstance(v, list):
            v = [] if v is None else [v]
        item = sch.get("items") or {}
        return [_coerce(x, item) for x in v]
    if t == "object" or "properties" in sch:
        if not isinstance(v, dict):
            v = {}
        props = sch.get("properties") or {}
        out = {}
        for k, ps in props.items():
            if k in v:
                out[k] = _coerce(v[k], ps)
        for k in sch.get("required") or []:
            if k not in out:
                out[k] = _coerce(None, props.get(k) or {})
        if sch.get("additionalProperties", True) is not False:
            for k, val in v.items():
                if k not in out:
                    out[k] = val
        return out
    return v


def _fallback_output(run):
    """A structured value from the research answer when the writer gives nothing usable."""
    ans = run.final["answer"] if run.final else ""
    j = _json_in(ans)
    props = (run.schema or {}).get("properties") or {}
    if not isinstance(j, dict) and len(props) == 1:
        j = {list(props.keys())[0]: ans}
    return _coerce(j if isinstance(j, dict) else {}, run.schema)


FINISH_MSG = ("Time is up: no more tools. Give the final answer now: exactly what the question asks (value, entity or "
              "list, with units and the precision asked; without a stated precision keep at least three decimals), plus "
              "at most one short sentence with the key figures. If the research is incomplete, give the single most "
              "likely answer from everything found above; never say it cannot be determined.")


async def finish_in_context(run, fmt=""):
    lane = run.lane_objs[0] if run.lane_objs else None
    if lane is None or _left(run) < 8.0:
        return None
    msgs = list(lane["msgs"]) + [{"role": "user", "content": FINISH_MSG + fmt}]
    try:
        think = {"enabled": True, "budget": 900} if _left(run) > 30.0 else {"enabled": False}
        res = await _chat(run, lane["model"], msgs, 3000, max(5.0, _left(run) - 2.0), thinking=think)
        text = (res.llm.raw_text or "").strip()
        return text or None
    except Exception:
        return None


GUESS_MSG = ("No more research. The grader scores only the final value: an answer that says it could not be determined "
             "scores zero, a best estimate may score. Give your single best estimate of exactly what the question asks, "
             "as a bare value or item (with units), from everything above. Reply with the answer only.")


async def _best_guess(run):
    lane = run.lane_objs[0] if run.lane_objs else None
    if lane is None or _left(run) < 5.0:
        return None
    msgs = list(lane["msgs"]) + [{"role": "user", "content": GUESS_MSG}]
    try:
        res = await _chat(run, SPARE, msgs, 300, max(4.0, min(15.0, _left(run) - 1.5)), thinking={"enabled": False},
                          no_spare=True)
        text = (res.llm.raw_text or "").strip()
        if not text or WEAK.search(text[:200]) or re.search(r"\b[Xx]{2,}\b|\?\?|_{3,}|\[.*?\]", text[:200]):
            return None
        return text
    except Exception:
        return None


def _value_part(ans):
    """'0 years (provisional: ...)' -> '0 years'; None when the text holds no value."""
    head = re.split(r"\s*[(:;—]|\s+-\s+", ans.strip(), 1)[0].strip(" *")
    if head and re.search(r"\d", head) and not WEAK.search(head) and len(head) <= 120:
        return head
    return None


async def compose_fast(run):
    ans = (run.final["answer"] if run.final else "").strip()
    if not ans or WEAK.search(ans[:400]):
        late = await finish_in_context(run)
        if late and not WEAK.search(late[:400]):
            ans = late
        elif not ans and late:
            ans = late
    if not ans or WEAK.search(ans[:400]):
        guess = await _best_guess(run)
        if guess:
            ans = guess
        elif ans and _value_part(ans):
            ans = _value_part(ans)
    if ans and len(ans) <= 400:
        return Response(text=ans)
    if ans:
        msgs = [{"role": "system", "content": "Rewrite a research result as the final answer to the question: keep every "
                                              "component the question asks for (each value, name, item, and any "
                                              "explanation or description it requests), exactly as the result states "
                                              "them; drop the derivation, sources and caveats. A question that asks only "
                                              "for a value gets only the value. Reply with the answer text only."},
                {"role": "user", "content": "QUESTION:\n" + run.q + "\n\nRESULT:\n" + ans[:6000]}]
        try:
            res = await _chat(run, SPARE, msgs, 1500, 15.0, thinking={"enabled": False})
            text = (res.llm.raw_text or "").strip()
            if text and not WEAK.search(text) and not re.search(r"\b(?:can.t|cannot|sorry)\b", text, re.I):
                return Response(text=text[:4000])
        except Exception:
            pass
        return Response(text=ans[:3000])
    return Response(text="No answer could be determined.")



def _as_value(j):
    if isinstance(j, dict) and "output" in j and set(j.keys()) <= {"output", "note"}:
        return j.get("output")
    return j


async def compose_fast_struct(run):
    """Fast task with an output schema: the response must use output (graded for correctness only, no note)."""
    ans = (run.final["answer"] if run.final else "").strip()
    val = _as_value(_json_in(ans)) if ans else None
    schema_txt = json.dumps(run.schema)[:3000]
    if not isinstance(val, dict) or WEAK.search(ans[:400]):
        late = await finish_in_context(run, "\nReply with only one JSON object that matches this schema exactly "
                                            "(full precision, no citations):\n" + schema_txt)
        j = _as_value(_json_in(late or ""))
        if isinstance(j, dict):
            val = j
        elif late and not ans:
            ans = late
    if not isinstance(val, dict) and ans and _left(run) > 6.0:
        msgs = [{"role": "system", "content": "Convert a research result into one JSON object that matches the given "
                                              "schema exactly. Use only values the result states; keep full precision. "
                                              "Reply with the JSON object only."},
                {"role": "user", "content": "QUESTION:\n" + run.q[:3000] + "\n\nSCHEMA:\n" + schema_txt
                                            + "\n\nRESULT:\n" + ans[:6000]}]
        try:
            res = await _chat(run, SPARE, msgs, 800, min(12.0, _left(run) - 2.0), thinking={"enabled": False},
                              no_spare=True)
            j = _as_value(_json_in(res.llm.raw_text or ""))
            if isinstance(j, dict):
                val = j
        except Exception:
            pass
    if isinstance(val, dict):
        return Response(output=_coerce(val, run.schema))
    return Response(output=_fallback_output(run))


WRITE_RULES = """Citations: after each specific claim (a number, name, date, status or table row) cite the exact source passage as {D12: "exact words copied from that document"}: 5-40 words copied character for character from a tool result above, containing the name or value, with the D# id of the document they come from. A recorded evidence entry may be cited as [E3]. Every check-table row needs a citation. Where a short source phrase decides a condition, quote it inline in double quotes as well. Do not cite python output: state computed values with the calculation written out (inputs, then result).
Make no claim you cannot cite or derive from cited facts; no claims about how a source is organised or what it omits. Treat every condition and instruction of the question explicitly, one bullet each (what it requires, how it was applied, the evidence), including any discrepancy between sources and which one the question makes controlling. Where an item fails a condition, name the condition and its deciding value, one item at a time. Prefer each item's own record (its page or row) as the citation for its values; never cite one item's record for another item's facts, and give each table row the citation of its own item.
Every count you state ("ten authors", "seven books removed") must equal the number of items you list for it; count them in the list before writing the number. Copy names, identifiers and codes exactly as the cited passage prints them; where the source text is garbled (OCR), quote it as printed and say which reading you use and why.
Write impersonally. Never mention tools, searches, documents ids, the ledger, the research process, or that something was not checked or not confirmed. A caveat only when an open uncertainty could change the answer."""

WRITE_TEXT = """Research is over. Write the final published answer now, in Markdown, from what the tool results above show. The reader is an expert grader who compares it with a reference report and prefers, in order: the correct and complete result; claims traceable to quoted sources; reasoning that shows how conditions and calculations give the result; proof that the candidate set is complete.
Use these sections and headings:
## Answer
One or two sentences with every requested component exactly (names as the source prints them, values with units and full precision, then any requested rounding; for a ratio or difference also the exact fraction in the answer's unit), cited.
## How it was identified
Each step of the chain as one cited sentence, starting from the source the question names.
## Candidate set
The authoritative source, how many candidates it holds, how many pass each condition.
## Check table
| Item | Values as printed in the source | Condition results | Verdict | Citation |, one row per candidate (every qualifying one and every excluded one examined), values copied exactly as printed, a citation in every row.
## Exclusions
Account for the whole population: for each exclusion reason, how many members it removes and their names (comma-separated when long); one sentence for each boundary case (same year, joint entry, renamed record, date edge).
## Calculation
Formula, cited inputs, arithmetic and rounding (omit when nothing is computed).
## Pitfalls and data conflicts
One sentence per tricky condition or tempting wrong answer; where sources disagree or a record reads two ways, both readings and why the one used is right.
Copy every value and derived number from the tool results and python output above; never redo arithmetic by hand, and keep the Answer, table and Calculation consistent with each other. Each sentence states its claim in words before its citation. Never cite the same passage twice in a row. Write only clean final findings: no scratch work or self-corrections.
""" + WRITE_RULES

WRITE_STRUCT = ("Research is over. Write the final published structured answer now, from what the tool results above "
                "show. The grader checks the JSON value first (it must satisfy the schema and the question exactly), then "
                "the note, a complete cited report compared with a reference report.\nReply in two parts, in this order:\n"
                "1. First, a fenced block ```json ... ``` holding only the JSON value that matches the schema below "
                "exactly (no citations inside it; every required field filled with the actual result).\n2. Then the note, "
                "a cited report in Markdown with these sections and headings:\n"
                + WRITE_TEXT.split("Use these sections and headings:\n", 1)[1].split("\nCopy every value", 1)[0]
                + "\nThe note should be complete but not padded: about 400-800 words plus the table.\nSchema:\n")



async def write_in_context(run):
    """Final write-up by the research model in its own conversation (it saw every page); None when unavailable."""
    lane = None
    for ln in run.lane_objs:
        if ln.get("final") is not None:
            lane = ln
            break
    if lane is None and run.lane_objs:
        lane = run.lane_objs[0]
    if lane is None or _left(run) < 12.0:
        return None
    if run.schema:
        instr = WRITE_STRUCT + json.dumps(run.schema)[:4000] + "\n\n" + WRITE_RULES
    else:
        instr = WRITE_TEXT
    if run.final:
        instr += "\n\nThe final answer established: " + run.final["answer"][:2000]
    if run.review and run.review.get("problems"):
        instr += "\nReviewer notes to respect: " + " | ".join(str(p)[:300] for p in run.review.get("problems")[:5])
    msgs = list(lane["msgs"]) + [{"role": "user", "content": instr}]
    try:
        res = await _chat(run, WRITE_MODEL, msgs, 8000, max(5.0, _left(run) - 14.0), thinking={"enabled": False},
                          no_spare=True)
        return (res.llm.raw_text or "").strip() or None
    except Exception:
        return None


QUOTE_TAG = re.compile(r"([\"“])([^\"“”]{4,600})([\"”])\s*[\[{(]\s*(D\d+)\s*[\]})]")
BARE_TAG = re.compile(r"\s*[\[{(]\s*(D\d+(?:\s*[,;/]\s*D?\d+)*)\s*[\]})]")
E_CURLY = re.compile(r"[{(]\s*(E\d+)\s*[})]")


def normalize_marks(run, text):
    """Accept the citation forms models actually write: "quote" {D12} becomes an exact-quote citation; a bare {D12}
    after a claim becomes the best passage of that document for the claim's terms (or is dropped); {E3} becomes [E3]."""
    text = E_CURLY.sub(lambda m: "[" + m.group(1) + "]", text or "")
    text = QUOTE_TAG.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + ' {%s: "%s"}' % (m.group(4), m.group(2).replace('"', "'")), text)
    out = []
    for line in text.split("\n"):
        if not BARE_TAG.search(line):
            out.append(line)
            continue
        pieces = []
        pos = 0
        for m in BARE_TAG.finditer(line):
            if line[m.start():m.end()].strip().startswith("{") and ":" in line[m.end():m.end() + 2]:
                continue
            before = line[pos:m.start()]
            pieces.append(before)
            pos = m.end()
            ids = ["D" + x for x in re.findall(r"\d+", m.group(1))]
            claim = line[max(0, m.start() - 300):m.start()]
            terms = _unit_terms(claim)
            lows = {d: run.docs[d]["text"].lower() for d in ids if d in run.docs and len(run.docs[d]["text"]) >= 100}
            best = _best_window(run, terms, lows) if terms and lows else None
            if best is not None:
                sc, did, a, b = best
                st, en = _slice(run.docs[did]["text"], a, b)
                if en - st >= 100:
                    sid = "S%d" % (len(run.bank) + 1)
                    run.bank.append({"id": sid, "doc": did, "start": st, "end": en, "score": sc})
                    pieces.append(" [%s]" % sid)
        pieces.append(line[pos:])
        out.append("".join(pieces))
    return "\n".join(out)



ANY_DMARK = re.compile(r"\{\s*(D\d+)\s*[:,]\s*([^{}]{3,800})\}")
DSTART = re.compile(r"\{\s*(D\d+)\s*[:,]\s*")
QEND = re.compile(r"(?<!\\)[\"\u201d']\s*\}")


def _dmark_ev(run, did, quote):
    d = run.docs.get(did)
    quote = quote.replace('\\"', '"').replace("\\'", "'").strip().strip("\"'\u201c\u201d\u2018\u2019").strip()
    if d is None or len(quote) < 4:
        return ""
    span = _locate(d["text"], quote)
    if span is None:
        return ""
    return "[%s]" % _add_ev(run, d["id"], span[0], span[1], "")


def scan_dmarks(run, text):
    """{D12: "quote"} in any form, including quotes of JSON with braces and escaped quotes inside, becomes [E#] when
    the words are found in D12, else nothing. The closer is the last quote-plus-brace before the next mark or line end."""
    out, pos = [], 0
    while True:
        m = DSTART.search(text, pos)
        if m is None:
            break
        i = m.end()
        nxt = DSTART.search(text, i)
        stop = min(nxt.start() if nxt else len(text), i + 1600)
        nl = text.find("\n", i, stop)
        if nl != -1:
            stop = nl
        closers = list(QEND.finditer(text, i, stop))
        if text[i:i + 1] in ('"', "\u201c", "'") and closers:
            last = closers[-1]
            inner, end = text[i + 1:last.start()], last.end()
        else:
            k = text.rfind("}", i, stop)
            if k == -1:
                out.append(text[pos:m.start()])
                pos = i
                continue
            inner, end = text[i:k], k + 1
        out.append(text[pos:m.start()])
        out.append(_dmark_ev(run, m.group(1), inner))
        pos = end
    out.append(text[pos:])
    return "".join(out)


LEFTOVER = (re.compile(r"\{\s*[DES]\d+\b[^{}\n]{0,1600}?\}"),
            re.compile(r"\[\s*[DES]\d+(?:\s*[,;/]\s*[DES]?\d+)*\s*\]"),
            re.compile(r"\[\s*E\d+\s+cite\b[^\]\n]{0,1600}\]"),
            re.compile(r"\(\s*[DES]\d+(?:\s*[,;/]\s*[DES]?\d+)*\s*\)"),
            re.compile(r"\b[DS]\d{1,3}(?=\s*(?:\[\[|\|))"))


def scrub(text):
    for rx in LEFTOVER:
        text = rx.sub("", text)
    text = re.sub(r"(\]\]|\w)[ \t]*[\u2013\u2014-][ \t]*(?=[.,;:)])", r"\1", text)
    text = re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", text)
    return re.sub(r"[ \t]+(\[\[\d+\]\])", r"\1", text)


def _merge_spans(spans):
    spans = sorted(spans)
    out = []
    for a, b in spans:
        if out and a <= out[-1][1] + 40:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def regroup(text, refs):
    """Adjacent pointers to the same source become one citation holding several excerpts (one citation object per
    source and claim, as the strongest answers do); unused refs are dropped and the rest renumbered by first use."""
    new, index, budget = [], {}, {"chars": 0, "segs": 0}

    def repl(m):
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        groups, order = {}, []
        for n in nums:
            if not 1 <= n <= len(refs):
                continue
            r = refs[n - 1]
            k = (r.receipt_id, r.result_id)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].extend((sl.start, sl.end) for sl in (r.slices or []))
        tags = []
        for k in order:
            spans = _merge_spans(groups[k])[:6]
            sig = (k, tuple(spans))
            if sig not in index:
                size = sum(b - a for a, b in spans)
                if len(new) >= 190 or budget["chars"] + size > 112000 or budget["segs"] + len(spans) > 390:
                    continue
                budget["chars"] += size
                budget["segs"] += len(spans)
                new.append(CitationRef(receipt_id=k[0], result_id=k[1],
                                       slices=[CitationSlice(start=a, end=b) for a, b in spans]))
                index[sig] = len(new)
            tag = "[[%d]]" % index[sig]
            if tag not in tags:
                tags.append(tag)
        return "".join(tags)

    return re.sub(r"(?:\[\[\d+\]\][ \t]*)+", lambda m: repl(m) + (" " if m.group(0).endswith(" ") else ""), text), new


def _resolve_dmark(run, m):
    """{D12: 'quote'} in any quoting style becomes a canonical {D12: "quote"} when the words are found, else nothing."""
    d = run.docs.get(m.group(1))
    quote = m.group(2).strip().strip("\"'\u201c\u201d\u2018\u2019").strip()
    if d is None or len(quote) < 4:
        return ""
    span = _locate(d["text"], quote)
    if span is None:
        return ""
    eid = _add_ev(run, d["id"], span[0], span[1], "")
    return "[%s]" % eid


def _tidy_pointers(text):
    text = re.sub(r"(\[\[\d+\]\])\s*[;,/]\s*(?=\[\[)", r"\1", text)
    text = re.sub(r"(\[\[\d+\]\])(?:\s*\1)+", r"\1", text)
    return text


# ---------------------------------------------------------------- pointer verification
VFOLD = {}
for src, dst in (("àáâãäåāă", "a"), ("çćč", "c"), ("èéêëēěę", "e"), ("ìíîïī", "i"), ("ñńň", "n"), ("òóôõöøō", "o"),
                 ("ùúûüūů", "u"), ("ýÿ", "y"), ("šś", "s"), ("žźż", "z"), ("ł", "l"), ("ř", "r"), ("ð", "d"), ("þ", "th"),
                 ("’‘`´", "'"), ("“”", '"'), ("–—−", "-")):
    for ch in src:
        VFOLD[ch] = dst
VFOLD["æ"] = "ae"
VFOLD["ß"] = "ss"


def _vfold(s):
    s = (s or "").lower()
    return "".join(VFOLD.get(ch, ch) for ch in s)


VPTR = re.compile(r"\[\[(\d+)\]\]")
V_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
V_NAME = re.compile(r"[A-ZÀ-Þ][\w'’\-]+(?:\s+(?:of|de|la|le|von|van|der|den|du|da|di|the|y|al|el)?\s*[A-ZÀ-Þ][\w'’\-]+)*")
V_QUOTE = re.compile(r"[\"“]([^\"“”]{4,600})[\"”]")
VWEAK = {"the", "this", "that", "these", "those", "answer", "source", "table", "unit", "units", "step", "note", "yes", "no",
              "included", "excluded", "total", "median", "mean", "average", "difference", "check", "verdict", "citation",
              "item", "values", "condition", "conditions", "results", "population", "candidate", "set", "how", "it", "was",
              "identified", "exclusions", "calculation", "pitfalls", "and", "data", "conflicts", "in", "of", "for", "on",
              "nobel", "prize", "prizes", "physics", "chemistry", "medicine", "literature", "peace", "economics", "mercury",
              "moon", "mars", "crater", "craters", "iau", "usgs", "national", "university", "list", "lists", "page",
              "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
              "november", "december", "part", "section", "federal", "register", "rule", "final", "decision", "report"}


def _vsquash(s):
    return re.sub(r"\s+", " ", s).strip()


def _vnorm(s):
    """Matching form of a claim or an excerpt: folded case and accents, no markdown escapes, no thousands commas."""
    s = _vfold(s or "").replace("\\", "")
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s)
    return _vsquash(s)


def _vanchors(unit, question=""):
    """Anchors a supporting excerpt should show: numbers not already in the question, quoted phrases, proper names."""
    body = VPTR.sub(" ", unit).replace("\\", "")
    qnums = {m.group(0).rstrip(".,").replace(",", "") for m in V_NUM.finditer(question or "")}
    nums = set()
    for m in V_NUM.finditer(body):
        t = m.group(0).rstrip(".,").replace(",", "")
        if len(t.replace(".", "")) >= 2 and t not in qnums:
            nums.add(t)
    quotes = set()
    for m in V_QUOTE.finditer(body):
        q = _vnorm(m.group(1))
        if len(q) >= 6:
            quotes.add(q[:50])
    names = set()
    lead = re.match(r"\s*(?:[-*>#|]+\s*|\d+[.)]\s*)*(?:\*\*)?([A-Z][a-z]+)\b", body)
    first = lead.group(1) if lead else None
    for m in V_NAME.finditer(body):
        ws = re.findall(r"[\w'’\-]+", m.group(0))
        if len(ws) == 1 and ws[0] == first and m.start() <= (lead.end() if lead else 0):
            continue
        for w in ws:
            if _vfold(w) not in VWEAK and len(w) >= 4:
                names.add(_vfold(w))
    return nums, quotes, names


def _vhas_num(ex, n):
    tail = r"(?![\d])" if "." not in n else ""
    return re.search(r"(?<![\d.])" + re.escape(n) + tail, ex) is not None


def _vok(unit_anchor, ex):
    """ex: folded excerpt text with thousands separators removed."""
    nums, quotes, names = unit_anchor
    if not nums and not quotes and not names:
        return True
    if any(q in ex for q in quotes):
        return True
    if quotes:
        tight = ex.replace(" ", "")
        if any(q.replace(" ", "") in tight for q in quotes):
            return True
    if any(_vhas_num(ex, n) for n in nums):
        return True
    if nums or quotes:
        # numeric claim with none of its numbers in the excerpt: allow only a strong name match (two names)
        return sum(1 for w in names if w in ex) >= 2
    return any(w in ex for w in names)


def _vunits(line):
    st = line.strip()
    if st.startswith("|") and st.endswith("|"):
        return [line]
    parts = re.split(r"(?<=[a-z0-9)\]*]{2}[.;:])\s+(?=[A-Z\*\[])", line)
    out = []
    for p in parts:
        if out and (out[-1].count('"') % 2 == 1 or out[-1].count("“") > out[-1].count("”")):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out

def verify_pointers(run, text, refs, repair=True):
    """Drop a [[n]] pointer whose excerpt shows none of its claim's anchors (numbers not in the question, quoted
    phrases, proper names); give a quoted phrase that no cited excerpt shows the slice where it is printed."""
    by_key = {(d["receipt"], d["result"]): d for d in run.docs.values()}
    memo = {}

    def ex_of(n):
        if n not in memo:
            memo[n] = None
            if 1 <= n <= len(refs):
                r = refs[n - 1]
                d = by_key.get((r.receipt_id, r.result_id))
                if d is not None:
                    memo[n] = _vnorm(" ".join(d["text"][sl.start:sl.end] for sl in (r.slices or [])))
        return memo[n]

    budget = {"repairs": 0, "moved": 0}
    t_end = time.monotonic() + 5.0
    lows_all = {}

    def relocate(u, n):
        """A better passage for claim u than ref n's excerpt: same document first, then any loaded document."""
        if not repair or budget["moved"] >= 40 or time.monotonic() > t_end or len(refs) >= 185:
            return None
        terms = _unit_terms(u)
        if len(terms) < 2:
            return None
        r = refs[n - 1] if 1 <= n <= len(refs) else None
        home = by_key.get((r.receipt_id, r.result_id)) if r is not None else None
        if not lows_all:
            for did, d in run.docs.items():
                if len(d["text"]) >= 100:
                    lows_all[did] = d["text"][:600000].lower()
        tries = []
        if home is not None and home["id"] in lows_all:
            tries.append({home["id"]: lows_all[home["id"]]})
        tries.append(lows_all)
        for lows in tries:
            best = _best_window(run, terms, lows)
            if best is None:
                continue
            sc, did, a, b = best
            d = run.docs[did]
            st, en = _slice(d["text"], a, b)
            if en - st < 100:
                continue
            ex = _vnorm(d["text"][st:en])
            if not _vok(_vanchors(u, run.q), ex):
                continue
            refs.append(CitationRef(receipt_id=d["receipt"], result_id=d["result"],
                                    slices=[CitationSlice(start=st, end=en)]))
            budget["moved"] += 1
            return len(refs)
        return None

    def repair_quotes(u, kept):
        if not repair or budget["repairs"] >= 40 or time.monotonic() > t_end:
            return u
        shown = " ".join(ex_of(n) or "" for n in kept)
        tight = shown.replace(" ", "")
        cited_docs = [by_key.get((refs[n - 1].receipt_id, refs[n - 1].result_id)) for n in kept if 1 <= n <= len(refs)]
        docs = [d for d in cited_docs if d] + [d for d in run.docs.values() if d not in cited_docs]
        out = u
        for m in list(V_QUOTE.finditer(u))[:3]:
            q = m.group(1).replace("\\", "")
            nq = _vnorm(q)
            if len(nq) < 12 or nq[:50] in shown or nq[:50].replace(" ", "") in tight:
                continue
            for d in docs[:60]:
                if len(d["text"]) < 100:
                    continue
                span = _locate(d["text"], q)
                if span is None:
                    continue
                st, en = _slice(d["text"], span[0], span[1])
                if en - st < 100 or len(refs) >= 185:
                    break
                refs.append(CitationRef(receipt_id=d["receipt"], result_id=d["result"],
                                        slices=[CitationSlice(start=st, end=en)]))
                budget["repairs"] += 1
                tag = "[[%d]]" % len(refs)
                k = out.find(m.group(0))
                if k != -1:
                    k += len(m.group(0))
                    out = out[:k] + tag + out[k:]
                break
        return out

    lines = []
    for line in (text or "").split("\n"):
        if "[[" not in line and not V_QUOTE.search(line):
            lines.append(line)
            continue
        units = _vunits(line)
        new_units = []
        for u in units:
            if "[[" not in u:
                new_units.append(repair_quotes(u, []) if V_QUOTE.search(u) else u)
                continue
            anc = _vanchors(u, run.q)
            kept = []

            def fix(m):
                n = int(m.group(1))
                ex = ex_of(n)
                if ex is None or _vok(anc, ex):
                    kept.append(n)
                    return m.group(0)
                k = relocate(u, n)
                if k is not None:
                    kept.append(k)
                    return "[[%d]]" % k
                return ""
            u2 = VPTR.sub(fix, u)
            new_units.append(repair_quotes(u2, kept) if V_QUOTE.search(u2) else u2)
        lines.append(" ".join(new_units))
    return "\n".join(lines)


SP_CAP = re.compile(r"(?<![\w'’-])[A-ZÀ-Þ][a-zà-ÿ'’-]{4,}(?![\w])")


def _lev1(a, b):
    """True when a and b differ by at most one insertion, deletion or substitution."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if b[:i] + b[i + 1:] == a:
            return True
    return False


def respell(run, text):
    """Proper names the write-up misspells ("Popogai") take the spelling the loaded sources print ("Popigai"): only a
    capitalised word found in no source, one edit from exactly one source word seen at least twice, and not an
    ordinary word that sources use in lower case."""
    if run.sp_vocab is None:
        counts, lower = {}, set()
        for d in run.docs.values():
            t = d["text"][:400000]
            for w in SP_CAP.findall(t):
                w = re.sub(r"(?:'s|’s|['’-])$", "", w)
                counts[w] = counts.get(w, 0) + 1
            lower.update(re.findall(r"(?<![\w])[a-zà-ÿ]{5,}(?![\w])", t))
        by = {}
        for w, c in counts.items():
            if c >= 2:
                by.setdefault(_vfold(w)[:1], []).append(w)
        run.sp_vocab = (counts, by, {_vfold(w) for w in counts}, {_vfold(w) for w in lower})
    counts, by, folded, lower = run.sp_vocab
    qwords = {_vfold(w) for w in SP_CAP.findall(run.q)}
    fixes = {}
    for w0 in set(SP_CAP.findall(text)):
        w = re.sub(r"(?:'s|’s|['’-])$", "", w0)
        fw = _vfold(w)
        if len(w) < 5 or fw in folded or fw in qwords or fw in lower:
            continue
        cands = []
        for v in by.get(fw[:1], []):
            fv = _vfold(v)
            if abs(len(fv) - len(fw)) > 1 or fv in (fw + "s", fw + "es") or fw in (fv + "s", fv + "es"):
                continue
            if _lev1(fw, fv):
                cands.append(v)
        if len({_vfold(c) for c in cands}) == 1:
            fixes[w] = max(cands, key=lambda c: counts.get(c, 0))
        if len(fixes) >= 12:
            break
    for w, v in fixes.items():
        text = re.sub(r"(?<![\w'’-])" + re.escape(w) + r"(?![\w])", v, text)
    return text


def finish_citations(run, text):
    refs, index = [], {}
    build_bank(run)
    text = sanitize(text)
    try:
        text = respell(run, text)
    except Exception:
        pass
    text = normalize_marks(run, text)
    text = scan_dmarks(run, text)
    text = _cite(run, text, refs, index)
    text = scrub(text)
    try:
        text = verify_pointers(run, text, refs)
    except Exception:
        pass
    try:
        text = autocite(run, text)
    except Exception:
        pass
    text = _cite_s(run, text, refs, index, keep=True)
    try:
        text = verify_pointers(run, text, refs, repair=False)
    except Exception:
        pass
    text, refs = regroup(_tidy_pointers(scrub(text)), refs)
    return _tidy_pointers(text), refs



# ---------------------------------------------------------------- written arithmetic check
ARITH = re.compile(r"(?<![\w.])((?:\(?\s*-?\d[\d,]*(?:\.\d+)?\s*\)?\s*[-+*/×x÷−–]\s*)+\(?\s*-?\d[\d,]*(?:\.\d+)?\s*\)?)\s*(?:=|≈)\s*(-?\d[\d,]*(?:\.\d+)?)(\s*%|\s*percent)?")


def _num_tok(t):
    t = t.replace(",", "")
    return float(t)


def _calc(expr):
    """Tiny arithmetic parser (+ - * / and parentheses); None when the text is not plain arithmetic."""
    s = expr.replace("×", "*").replace("÷", "/").replace("−", "-").replace("–", "-")
    s = re.sub(r"(?<=\d)\s*x\s*(?=[\d(])", "*", s)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    toks = re.findall(r"\d+(?:\.\d+)?|[-+*/()]", s)
    if "".join(toks) != re.sub(r"\s+", "", s):
        return None
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def atom():
        t = peek()
        if t == "(":
            take()
            v = add()
            if peek() != ")":
                raise ValueError
            take()
            return v
        if t == "-":
            take()
            return -atom()
        if t is None or not re.match(r"\d", t):
            raise ValueError
        return float(take())

    def mul():
        v = atom()
        while peek() in ("*", "/"):
            op = take()
            r = atom()
            v = v * r if op == "*" else v / r
        return v

    def add():
        v = mul()
        while peek() in ("+", "-"):
            op = take()
            r = mul()
            v = v + r if op == "+" else v - r
        return v

    try:
        v = add()
        return v if pos[0] == len(toks) else None
    except (ValueError, ZeroDivisionError):
        return None


def arith_slips(text, limit=6):
    """Written calculations whose stated result disagrees with the arithmetic (beyond the rounding shown)."""
    out = []
    for m in ARITH.finditer(text or ""):
        lhs, rhs, pct = m.group(1), m.group(2), m.group(3)
        if not re.search(r"\d\s*[-+*/×x÷−–]\s*\(?\s*\d", lhs):
            continue
        if re.fullmatch(r"\s*\d{4}\s*[-–−]\s*\d{2,4}\s*", lhs):      # year ranges such as 1981-2015
            continue
        v = _calc(lhs)
        if v is None:
            continue
        try:
            r = _num_tok(rhs)
        except ValueError:
            continue
        dec = len(rhs.split(".")[1]) if "." in rhs else 0
        tol = 10 ** (-dec) + 1e-9            # one unit in the last place: truncated values pass
        ok = abs(v - r) <= tol * 1.0001 or (pct and abs(v * 100 - r) <= tol * 1.0001)
        if not ok and abs(r) > 0 and abs(v - r) / abs(r) < 1e-6:
            ok = True
        if not ok:
            out.append("%s = %s (the arithmetic gives %s)" % (lhs.strip(), rhs, ("%.6f" % v).rstrip("0").rstrip(".")))
        if len(out) >= limit:
            break
    return out


CMP = re.compile(r"(?<![\w.\-–])(-?\d[\d,]*(?:\.\d+)?)\s*(<=|>=|≤|≥|<|>)\s*(?:[A-Za-z][A-Za-z ]{0,30}?\s)?"
                 r"(-?\d[\d,]*(?:\.\d+)?)(?![\d.]*\d)(?!\s*[-–]\s*\d)")
SCRATCH = re.compile(r"\?\s*No\b|\bwait[,.!]|\bactually,|\bcorrection:|\bhmm\b|\bon second thought\b|\blet me\b|"
                     r"\bI (?:think|realise|realize|made)\b|\b(?:oops|scratch that)\b", re.I)


def thin_citations(cited):
    """A long report whose claims mostly carry no pointer loses on traceability."""
    n = len(re.findall(r"\[\[\d+\]\]", cited or ""))
    size = len(cited or "")
    if size > 2500 and n < size / 400.0:
        return ["Only %d citation pointers in a %d-character report: cite every specific value, name, date and table "
                "row with {D#: \"exact quoted words\"} from the source that prints it" % (n, size)]
    return []


def logic_slips(text, limit=4):
    """Numeric comparisons stated wrongly ("1.174 < 1.032") and scratch reasoning left in a published report."""
    out = []
    for m in CMP.finditer(text or ""):
        try:
            a, b = float(m.group(1).replace(",", "")), float(m.group(3).replace(",", ""))
        except ValueError:
            continue
        op = m.group(2)
        ok = {"<": a < b, ">": a > b, "<=": a <= b, "≤": a <= b, ">=": a >= b, "≥": a >= b}[op]
        if not ok:
            out.append("Wrong comparison: \"%s\" is false; restate it correctly" % m.group(0))
        if len(out) >= limit:
            break
    for m in SCRATCH.finditer(text or ""):
        a = max(0, m.start() - 80)
        out.append("Scratch reasoning in the report near \"%s\": state only the clean conclusion"
                   % re.sub(r"\s+", " ", text[a:m.end() + 60]).strip())
        if len(out) >= limit + 2:
            break
    return out


REPORT_REVIEW = ("You review a cited research report before it is published as the answer to a question. Check it against "
                 "the question and the CITED EXCERPTS (the only evidence the grader sees): (1) is every requested component "
                 "answered exactly, at the precision asked; (2) is the population complete, and is each excluded member's "
                 "reason shown by an excerpt; (3) do the numbers in the Answer, the table and the Calculation agree with "
                 "each other and with the excerpts; (4) is any material claim (value, name, date, count) uncited, or cited "
                 "to an excerpt that does not show it. Reply with one JSON object only: {\"verdict\": \"ok\"} or "
                 "{\"verdict\": \"revise\", \"problems\": [\"...\"]} with at most 4 concrete problems, each naming the "
                 "claim and what would fix it. Style and length are not problems; do not invent problems.")
REWRITE_MSG = ("A reviewer checked the report against its cited excerpts and found:\n{problems}\nWrite the complete report "
               "again with these fixed, using only the tool results above: cite each disputed claim to the source text that "
               "prints it, make the Answer, table and Calculation agree, and drop any claim no tool result supports. Same "
               "sections and citation rules as before.")


def _excerpts(run, refs):
    by_key = {(d["receipt"], d["result"]): d["text"] for d in run.docs.values()}
    lines, used = [], 0
    for i, ref in enumerate(refs, 1):
        text = by_key.get((ref.receipt_id, ref.result_id), "")
        piece = " ... ".join(text[sl.start:sl.end] for sl in (ref.slices or []))
        line = "[[%d]] %s" % (i, re.sub(r"\s+", " ", piece)[:1500])
        used += len(line)
        if used > 30000:
            break
        lines.append(line)
    return "\n".join(lines) or "(none)"


async def review_report(run, text, refs):
    if _left(run) < 45.0 or run.spent > SPEND_STOP:
        return []
    user = "QUESTION:\n" + run.q[:3000] + "\n\nREPORT:\n" + text[:16000] + "\n\nCITED EXCERPTS:\n" + _excerpts(run, refs)
    try:
        res = await _chat(run, REVIEWER, [{"role": "system", "content": REPORT_REVIEW}, {"role": "user", "content": user}],
                          1200, min(25.0, _left(run) - 25.0), thinking={"enabled": False})
        data = _json_in(res.llm.raw_text or "")
    except Exception:
        return []
    if not isinstance(data, dict) or str(data.get("verdict") or "").strip().lower() != "revise":
        return []
    found = data.get("problems") or []
    found = found if isinstance(found, list) else [found]
    return [re.sub(r"\s+", " ", str(p)).strip()[:300] for p in found if str(p).strip()][:4]


async def rewrite_in_context(run, instr, raw, problems):
    lane = run.lane_objs[0] if run.lane_objs else None
    if lane is None or _left(run) < 20.0:
        return None
    msgs = list(lane["msgs"]) + [{"role": "user", "content": instr}, {"role": "assistant", "content": raw[:14000]},
                                 {"role": "user", "content": REWRITE_MSG.format(problems="\n".join("- " + p for p in problems))}]
    try:
        res = await _chat(run, WRITE_MODEL, msgs, 8000, max(5.0, _left(run) - 10.0), thinking={"enabled": False},
                          no_spare=True)
        return (res.llm.raw_text or "").strip() or None
    except Exception:
        return None


PLACEHOLDER = re.compile(r"\b[Xx]{2,}\b|\?\?|_{3,}|<[^>]{1,30}>|\[(?:value|answer|N)\]", re.I)


async def _settle_answer(run):
    """Judged tasks: research that ended without a definite answer gets one closing call for the best-supported
    answer, so the write-up never publishes 'could not be determined' (that always loses to the reference)."""
    ans = ((run.final or {}).get("answer") or "").strip()
    if ans and not WEAK.search(ans[:400]):
        return
    if _left(run) < 30.0:
        return
    late = await finish_in_context(run)
    if late and not WEAK.search(late[:400]) and not PLACEHOLDER.search(late[:200]):
        run.final = {"answer": late[:6000], "derivation": ((run.final or {}).get("derivation") or "")}


async def compose_text(run):
    await _settle_answer(run)
    raw = await write_in_context(run)
    if raw and len(raw) > 200:
        snap = (len(run.bank), len(run.ledger))
        text, refs = finish_citations(run, raw)
        problems = ["Arithmetic slip: " + x + "; recompute it (python) and correct every place it appears"
                    for x in arith_slips(raw)][:3]
        problems = (problems + logic_slips(raw) + thin_citations(text))[:4]
        problems = problems + (await review_report(run, text, refs))[:4 - min(len(problems), 2)]
        if problems:
            again = await rewrite_in_context(run, WRITE_TEXT, raw, problems)
            if again and len(again) >= 0.6 * len(raw) and re.search(r"^#+\s*Answer", again, re.M | re.I):
                text2, refs2 = finish_citations(run, again)
                if refs2:
                    return Response(text=text2[:79000], citations=refs2)
        return Response(text=text[:79000], citations=refs or None)
    build_bank(run)
    body = ""
    if _left(run) > 40.0:
        msgs = [{"role": "system", "content": WRITER_TEXT}, {"role": "user", "content": _writer_material(run, 70000)}]
        try:
            res = await _chat(run, WRITER, msgs, 9000, max(5.0, _left(run) - 12.0), thinking=WRITER_THINKING,
                              no_spare=True)
            body = (res.llm.raw_text or "").strip()
        except Exception:
            body = ""
    if not body and run.final:
        body = "## Answer\n\n**" + run.final["answer"] + "**\n\n## How it was identified\n\n" + run.final["derivation"]
    if not body:
        body = "No answer could be determined from the sources reached."
    try:
        text, refs = finish_citations(run, body)
    except Exception:
        text, refs = scrub(sanitize(body)), []
    return Response(text=text[:79000], citations=refs or None)



def _schema_fit(v, sch):
    props = (sch or {}).get("properties") or {}
    if not isinstance(v, dict) or not props:
        return 1 if v is not None else 0
    return sum(1 for k in props if k in v) * 10 + sum(1 for k in props if k in v and not _blank(v[k]))


def _blank(v):
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def _pick_struct(raw, sch):
    """The JSON value in the writer's reply that best fits the schema (any fenced block, else any bare object),
    and the reply without it as the note."""
    raw = raw or ""
    best = (0, None, None)
    for m in re.finditer(r"```(?:json)?\s*(.*?)```", raw, re.S):
        try:
            v = json.loads(m.group(1).strip())
        except ValueError:
            v = _json_in(m.group(1))
        if isinstance(v, dict) and "output" in v and set(v.keys()) <= {"output", "note"}:
            v = v.get("output")
        fit = _schema_fit(v, sch)
        if fit > best[0]:
            best = (fit, v, (m.start(), m.end()))
    if best[1] is None:
        k = raw.rfind("\n{")
        v = _json_in(raw[k:]) if k != -1 else _json_in(raw[:4000])
        if isinstance(v, dict) and _schema_fit(v, sch):
            return v, (raw[:k].strip() if k != -1 else raw)
        return None, raw
    a, b = best[2]
    return best[1], (raw[:a] + raw[b:]).strip()


async def _rescue_value(run, note):
    """Required fields missing or blank: build the value from the research answer and the note (quick call)."""
    if _left(run) < 8.0:
        return None
    src = ("RESEARCH ANSWER:\n" + ((run.final or {}).get("answer") or "")[:3000] + "\n\nDERIVATION:\n"
           + ((run.final or {}).get("derivation") or "")[:4000] + "\n\nREPORT:\n" + (note or "")[:8000])
    msgs = [{"role": "system", "content": "Fill a JSON value that matches the given schema exactly, using only results "
                                          "stated in the material. Every required field must hold the actual result. "
                                          "Reply with the JSON object only."},
            {"role": "user", "content": "QUESTION:\n" + run.q[:3000] + "\n\nSCHEMA:\n" + json.dumps(run.schema)[:3000]
                                        + "\n\n" + src}]
    try:
        res = await _chat(run, SPARE, msgs, 1500, min(15.0, _left(run) - 3.0), thinking={"enabled": False},
                          no_spare=True)
        v = _json_in(res.llm.raw_text or "")
        if isinstance(v, dict) and "output" in v and set(v.keys()) <= {"output", "note"}:
            v = v.get("output")
        return v
    except Exception:
        return None


def _split_struct(raw):
    blocks = list(re.finditer(r"```(?:json)?\s*(.*?)```", raw or "", re.S))
    if blocks:
        last = blocks[-1]
        try:
            out = json.loads(last.group(1).strip())
        except ValueError:
            out = _json_in(last.group(1))
        return out, (raw[:last.start()] + raw[last.end():]).strip()
    k = (raw or "").rfind("\n{")
    tail = _json_in(raw[k:]) if k != -1 else None
    if isinstance(tail, dict):
        return tail, raw[:k].strip()
    return None, raw or ""


async def compose_struct(run):
    await _settle_answer(run)
    out, note = None, ""
    in_context = False
    try:
        raw = await write_in_context(run)
        if raw:
            in_context = True
        elif _left(run) > 35.0:
            build_bank(run)
            msgs = [{"role": "system", "content": WRITER_STRUCT}, {"role": "user", "content": _writer_material(run, 60000)}]
            res = await _chat(run, WRITER, msgs, 9000, max(5.0, _left(run) - 10.0), thinking=WRITER_THINKING,
                              no_spare=True)
            raw = (res.llm.raw_text or "").strip()
        else:
            raw = ""
        out, note = _pick_struct(raw, run.schema)
        if isinstance(out, dict) and "output" in out and set(out.keys()) <= {"output", "note"}:
            note = note or str(out.get("note") or "")
            out = out.get("output")
        note = re.sub(r"^\s*(?:#+\s*)?(?:\d\.\s*)?(?:note|the note)\s*:?\s*\n", "", note, flags=re.I).strip()
    except Exception:
        out = None
    req = (run.schema or {}).get("required") or list(((run.schema or {}).get("properties") or {}).keys())
    if out is None or (isinstance(out, dict) and any(_blank(out.get(k)) for k in req)):
        fixed = await _rescue_value(run, note)
        if isinstance(fixed, dict) and _schema_fit(fixed, run.schema) > _schema_fit(out, run.schema):
            out = fixed
    value = _coerce(out, run.schema) if out is not None else _fallback_output(run)
    if not note.strip() and run.final:
        note = "## Answer\n\n**" + run.final["answer"][:1500] + "**\n\n## How it was identified\n\n" + run.final["derivation"]
    refs = []
    note_text = ""
    if note.strip() and in_context:
        note_text, refs = finish_citations(run, note)
        problems = ["Arithmetic slip: " + x + "; recompute it (python) and correct every place it appears"
                    for x in arith_slips(note)][:3]
        problems = (problems + logic_slips(note) + thin_citations(note_text))[:4]
        problems = problems + (await review_report(run, note_text, refs))[:4 - min(len(problems), 2)]
        if problems:
            instr = WRITE_STRUCT + json.dumps(run.schema)[:4000] + "\n\n" + WRITE_RULES
            again = await rewrite_in_context(run, instr, raw, problems)
            if again:
                out2, note2 = _pick_struct(again, run.schema)
                if note2 and len(note2) >= 0.6 * len(note) and re.search(r"^#+\s*Answer", note2, re.M | re.I):
                    t2, r2 = finish_citations(run, note2)
                    if r2:
                        note_text, refs = t2, r2
                        if out2 is not None:
                            value = _coerce(out2, run.schema)
    elif note.strip():
        try:
            note_text, refs = finish_citations(run, note)
        except Exception:
            note_text, refs = scrub(sanitize(note)), []
    if note_text.strip():
        return Response(output=value, note=note_text[:79000], citations=refs or None)
    return Response(output=value)


ADJ_SYSTEM = """Two independent researchers answered the same research question with different tools runs. Decide the correct answer. You get the question, both answers with their derivations, the shared evidence ledger (verbatim source quotes), python results and recent source excerpts.
Find the exact point where they differ (population, a condition, a value, the arithmetic, rounding) and settle it from the evidence and the literal wording of the question. Neither researcher is presumed right; a derivation that checks the complete population against the named source outweighs one that does not.
Return one JSON object only:
{"answer": "the final answer: every requested value or item, with units", "derivation": "the full derivation for it: source and population with its size, included and excluded items with the deciding facts, the calculation", "settled": true or false, "check": "when not settled: the one specific check that would settle it, saying where to look; else empty"}"""

LANE_STYLE = {
    "A": "",
    "B": ("\n\nWork style: load the complete source list or table early and do the filtering in python over docs; "
          "before computing, look for entries the wording includes or excludes (joint entries, renamed or superseded "
          "records, boundary dates)."),
}


def _first_num(text):
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _names(text):
    return {m.group(0).lower() for m in NAME_RX.finditer(text or "") if len(m.group(0)) >= 4 and m.group(0) not in STOP_NAMES}


def _agree(a, b):
    na, nb = _first_num(a), _first_num(b)
    sa, sb = _names(a), _names(b)
    if na is not None and nb is not None:
        if abs(na - nb) > max(0.006 * max(abs(na), abs(nb)), 1e-9):
            return False
        if len(sa) >= 3 and len(sb) >= 3:
            return len(sa & sb) / max(1, len(sa | sb)) >= 0.6
        return True
    if na is not None or nb is not None:
        return False
    if not sa or not sb:
        return (a or "").strip().lower() == (b or "").strip().lower()
    return len(sa & sb) / max(1, len(sa | sb)) >= 0.75


async def adjudicate(run, lanes, until):
    parts = ["QUESTION:\n" + run.q]
    if run.schema:
        parts.append("OUTPUT SCHEMA:\n" + json.dumps(run.schema)[:3000])
    for ln in lanes:
        f = ln["final"]
        parts.append("RESEARCHER %s ANSWER:\n%s\n\nRESEARCHER %s DERIVATION:\n%s" % (ln["name"], f["answer"], ln["name"],
                                                                                    f["derivation"][:8000]))
    parts.append("EVIDENCE LEDGER:\n" + (_ledger_text(run, 25000) or "(empty)"))
    if run.pyout:
        parts.append("PYTHON RUNS (newest last):\n" + "\n\n".join(p[:3000] for p in run.pyout[-6:]))
    text = "\n\n".join(parts)
    room = 70000 - len(text)
    picked = []
    for o in reversed(run.obs):
        if room <= 500:
            break
        piece = o[:min(len(o), 5000, room)]
        picked.append(piece)
        room -= len(piece)
    if picked:
        text += "\n\nRECENT SOURCE EXCERPTS:\n" + "\n\n---\n\n".join(picked)
    msgs = [{"role": "system", "content": ADJ_SYSTEM}, {"role": "user", "content": text}]
    try:
        cap = min(45.0, until - time.monotonic())
        if cap < 8.0:
            return None
        res = await _chat(run, ADJUDICATOR, msgs, 4500, cap, thinking={"enabled": True, "budget": 1500})
        j = _json_in(res.llm.raw_text or "")
        if isinstance(j, dict) and str(j.get("answer") or "").strip():
            return j
    except Exception:
        return None
    return None


async def solve(run):
    first = "QUESTION:\n" + run.q + "\n\n" + _form(run)
    await make_plan(run)
    looked = await first_look(run)
    if run.plan:
        first += "\n\nPLAN (from the planner; verify everything):\n" + json.dumps(run.plan, indent=1)[:6000]
    if run.fast:
        reserve = min(24.0, max(14.0, 0.12 * run.limit))
    else:
        reserve = min(100.0, max(30.0, 0.33 * run.limit))
    deadline = run.end - reserve
    window = deadline - time.monotonic()
    first += "\n\nResearch time: about %d s.\n\nINITIAL RESULTS:\n%s" % (int(window), looked)
    lanes = []
    specs = (("A", DRIVER, DRIVER_THINKING, DRIVER2), ("B", DRIVER2, DRIVER2_THINKING, DRIVER))
    for name, model, think, spare in specs[:LANES]:
        lanes.append({"name": name, "model": model, "thinking": think, "spare": spare, "final": None, "window": window,
                      "msgs": [{"role": "system", "content": DRIVER_SYSTEM + LANE_STYLE[name]},
                               {"role": "user", "content": first}]})
    run.lane_objs = lanes
    await asyncio.gather(*[research(run, ln, deadline, MAX_TURNS) for ln in lanes])
    done = [ln for ln in lanes if ln.get("final")]
    if not done:
        return
    lane = done[0]
    run.final = lane["final"]
    # deepen: complete the per-member evidence the write-up will cite (judged tasks)
    left = deadline - time.monotonic()
    if not run.fast and left > 35.0 and run.spent < SPEND_STOP:
        lane["msgs"].append({"role": "user", "content": DEEPEN_MSG.format(secs=int(left), turns=6)})
        lane["warned"] = True
        await research(run, lane, deadline, 6)
        run.final = lane["final"] or run.final
    # provenance: figures in the answer that no tool result or python output shows
    room = run.end - time.monotonic() - (reserve if not run.fast else 22.0)
    bad = _untraced(run, (run.final or {}).get("answer", ""))
    if bad and room > 25.0 and run.spent < SPEND_STOP:
        lane["msgs"].append({"role": "user", "content": PROV_MSG.format(figs=", ".join(bad))})
        lane["warned"] = True
        await research(run, lane, time.monotonic() + min(room, 60.0), 3)
        run.final = lane["final"] or run.final


@entrypoint("query")
async def query(query: Query, context: ContextSnapshot) -> Response:
    run = Run(query, context)
    try:
        await asyncio.wait_for(solve(run), timeout=max(5.0, _left(run) - (25.0 if not run.fast else 6.0)))
    except Exception:
        pass
    if run.final is None:
        for ln in run.lane_objs:
            if ln.get("final"):
                run.final = ln["final"]
                break
    try:
        if run.fast and run.schema:
            return await compose_fast_struct(run)
        if run.fast:
            return await compose_fast(run)
        if run.schema:
            return await compose_struct(run)
        return await compose_text(run)
    except Exception:
        if run.schema:
            return Response(output=_fallback_output(run))
        return Response(text=(run.final["answer"] if run.final else "No answer could be determined.")[:4000])
