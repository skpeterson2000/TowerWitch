#!/usr/bin/env python3
"""Reading RadioReference exports as they actually come off the website.

    python3 test_radioreference.py

The two things this is really about are both ways a file can be wrong
without saying so.

RadioReference does not escape the quotes inside a quoted field, so the
State Patrol's district talkgroups arrive as `"West Metro "2500" Dispatch"`.
Python's csv module reads that without complaining and hands back
`West Metro 2500" Dispatch"` - a quote moved and a character appeared, and
nothing anywhere said a word. So the repair is pinned here, and so is the
fact that it announces itself.

And Site NAC is hexadecimal. Read as decimal it turned 0x400 into 0x190 and
raised on every site whose NAC had a letter in it - `40B`, `40a`, `40F` -
which a bare `continue` then swallowed, dropping the site. Both halves are
pinned: the value is right, and the rows come back.
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radioreference as rr          # noqa: E402
import armer_state_store             # noqa: E402

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}: {got!r}"
          + ("" if ok else f"  (wanted {want!r})"))
    if not ok:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="tw-rr-")


def written(name, text):
    path = os.path.join(TMP, name)
    io.open(path, "w", encoding="utf-8", newline="").write(text)
    return path


TG = written("trs_tg_3508.csv", """Decimal,Hex,Alpha Tag,Mode,Description,Tag,Category
2,002,"SW IA MA 1","D","Interagency Mutual Aid 1","Interop","Statewide Interoperability "
54,036,"MSP 2500 DSP","D","West Metro "2500" Dispatch","Law Dispatch","MSP"
172,0ac,"DOC INVEST 2","De","Office of Special Investigations 2","Corrections","DOC"
2305,901,"EMMRC 2 W","D","West EMRCC","Hospital","Metro EMS"
2305,901,"EMSHE-N-MAIN","D","M Health Fairview North","EMS Dispatch","M Health"
nope,xxx,"Bad","D","Not a talkgroup","x","y"
""")

SITES = written("trs_sites_3508.csv", """RFSS,Site Dec,Site Hex,Site NAC,Description,County Name,Lat,Lon,Range,Frequencies
1,001,1,400,"Minneapolis City Center Simulcast","Hennepin",44.9799654,-93.26383610,40,856.237500,858.237500c,860.237500c
2,090,5A,40F,"Holland","Pipestone",44.11378,-96.10219,20,851.750000c,852.450000c,852.962500
2,096,60,40B,"Madison","Lac Qui Parle",45.00917,-96.17778,20,851.425000,855.212500c
2,098,62,40a,"Milan","Chippewa",45.10097,-95.81664,20,853.500000c,851.950000
1,006,6,,"Chisago - Isanti Simulcast","Chisago",45.48,-93,32,851.600000,853.050000c
9,999,F,400,"Nowhere","Nowhere",,,20,851.000000c
""")


print("\nthe two files are told apart by their header, not their name")
check("a sites export", rr.kind_of(SITES), "sites")
check("  a talkgroups export", rr.kind_of(TG), "talkgroups")
check("  something else entirely",
      rr.kind_of(written("notes.csv", "a,b,c\n1,2,3\n")), None)
check("  a file that is not there", rr.kind_of(os.path.join(TMP, "gone.csv")), None)
check("and the system's number comes off the name", rr.system_id(SITES), "3508")
check("  a renamed file simply has none",
      rr.system_id(written("armer.csv", "x\n")), None)


print("\nquotes inside a quoted field are put back, not left mangled")
tgs, report = rr.read_talkgroups(TG)
by_id = {t["decimal"]: t for t in tgs}
check("the description is whole",
      by_id[54]["description"], 'West Metro "2500" Dispatch')
check("  which is what csv.reader gets wrong", True, True)
import csv as _csv
mangled = next(_csv.reader(['54,036,"a","D","West Metro "2500" Dispatch","x","y"']))
check("  csv.reader gives this instead", mangled[4], 'West Metro 2500" Dispatch"')
check("and the repair announces itself", len(report["repaired"]), 1)
check("  naming the line", report["repaired"][0]["line"], 3)
check("  and it is in what a person is shown",
      any("quotes inside" in line for line in rr.summary(report)), True)

print("\n  an ordinary row is left alone")
check("no repair claimed for it",
      by_id[2]["description"], "Interagency Mutual Aid 1")
check("  and the export's trailing space is taken off the agency",
      by_id[2]["agency"], "Statewide Interoperability")


print("\nthe mode's E means encrypted, in whatever case it arrives")
check("upper", by_id[172]["mode"], "DE")
check("  and lower-case De is still encrypted", by_id[172]["encrypted"], True)
check("  a plain D is not", by_id[2]["encrypted"], False)


print("\nrows that cannot be read are skipped, and said")
check("a talkgroup that is not a number goes", len(report["skipped"]), 1)
check("  the line is named", report["skipped"][0]["line"], 7)
check("  and the reason", "not a number" in report["skipped"][0]["why"], True)
check("the good rows all came through", report["kept"], 5)

print("\n  and the same id twice is kept twice, and reported")
check("both are there", len([t for t in tgs if t["decimal"] == 2305]), 2)
check("  and it is noticed", len(report["duplicates"]), 1)
check("  naming the second line", report["duplicates"][0]["line"], 6)


print("\nSite NAC is hexadecimal")
check("a NAC with a letter in it", rr.parse_nac("40B"), 0x40B)
check("  in either case", rr.parse_nac("40a"), 0x40A)
check("  one with no letters is hex too, not decimal",
      rr.parse_nac("400"), 0x400)
check("  an empty one is nothing, and is not a fault", rr.parse_nac(""), None)
check("  and nonsense is nothing rather than a raise", rr.parse_nac("zz"), None)

sites, sreport = rr.read_sites(SITES)
check("every site with a letter in its NAC came through", sreport["kept"], 6)
by_key = {(s["rfss"], s["site"]): s for s in sites}
check("  Holland's NAC", by_key[(2, 90)]["nac"], 0x40F)
check("  Madison's", by_key[(2, 96)]["nac"], 0x40B)
check("  Milan's", by_key[(2, 98)]["nac"], 0x40A)
check("  and Minneapolis is 0x400, not 0x190",
      by_key[(1, 1)]["nac"], 0x400)
check("  a site with no NAC keeps its place", by_key[(1, 6)]["nac"], None)

print("\n  a site with no position is kept, and said")
# It cannot be mapped or sorted by distance, but OP25 wants its NAC and
# its control channels and neither of those is a coordinate - and the
# store this feeds has always kept it. The reader does not get to make
# that call on the caller's behalf.
check("nothing was skipped for it", len(sreport["skipped"]), 0)
check("  it is noted instead", len(sreport["no_position"]), 1)
check("  naming it", sreport["no_position"][0]["description"], "Nowhere")
check("  and a person is told",
      any("no position" in line for line in rr.summary(sreport)), True)
check("  it is in the records, without a position",
      [s["lat"] for s in sites if s["description"] == "Nowhere"], [None])


print("\nthe frequencies are every column to the end of the line")
check("a control channel is marked with a trailing c",
      rr.parse_frequency("858.237500c"), (858237500, True))
check("  and a plain one is not", rr.parse_frequency("856.237500"), (856237500, False))
check("  an empty column is nothing", rr.parse_frequency(""), (None, False))
check("  and so is a column that is not a number", rr.parse_frequency("x"), (None, False))
check("Minneapolis has three frequencies", len(by_key[(1, 1)]["all_hz"]), 3)
check("  two of which are control channels", len(by_key[(1, 1)]["control_hz"]), 2)
check("  and they are the ones that were marked",
      by_key[(1, 1)]["control_hz"], [858237500, 860237500])


print("\nnothing here raises on a file it cannot use")
kind, records, bad = rr.read(written("junk.csv", "not,a,csv,at,all\n"))
check("a file of the wrong kind", kind, None)
check("  says so rather than raising", bool(bad["fatal"]), True)
check("  and reads as an error", rr.summary(bad)[0].startswith("[ERROR]"), True)
kind, records, gone = rr.read(os.path.join(TMP, "missing.csv"))
check("a file that is not there", bool(gone["fatal"]), True)


print("\nand the site store gets the sites it was dropping")
state = armer_state_store.bootstrap_from_csv(SITES, os.path.join(TMP, "state.json"))
check("all six rows, the position-less one included",
      len(state["sites"]), 6)
check("  Holland is there now", "2-90" in state["sites"], True)
check("  with its NAC the right way round",
      state["sites"]["2-90"]["nac"], "0x40f")
check("  and Minneapolis is 0x400", state["sites"]["1-1"]["nac"], "0x400")


print("\n" + ("FAILED: " + ", ".join(FAILS) if FAILS else "all ok"))
sys.exit(1 if FAILS else 0)
