"""test_county_import.py - a county export, from the file to the band tab.

Run it:  python3 test_county_import.py

The three RadioReference exports each end somewhere different. The sites
file ends in the ARMER tree, the talkgroup file in talkgroups.json, and
this one - a county, not a system - ends in the amateur band tabs, but
only the rows tagged Ham. This walks that path on the real file and
checks what arrives, because the column that decides it is the eleventh
one and was read as the sixth until recently.
"""

import io
import os
import sys
import tempfile

import frequency_store
import radioreference

FAILURES = []


def ok(label, got, want):
    same = got == want
    print(f"  {'ok  ' if same else 'FAIL'}  {label}: {got!r}")
    if not same:
        print(f"        wanted {want!r}")
        FAILURES.append(label)


SAMPLE = '''"Frequency Output","Frequency Input","FCC Callsign",Agency/Category,Description,"Alpha Tag","PL Output Tone","PL Input Tone",Mode,"Class Station Code",Tag
145.130000,144.53000,W0UJ,"Amateur Radio","Brainerd ARC - VHF","W0UJ VHF BRD",CSQ,"123.0 PL",FM,RM,Ham
147.030000,147.63000,W0UJ,"Amateur Radio",Crosslake,"W0UJ CRS LK",CSQ,CSQ,FM,RM,Ham
147.090000,147.69000,W0REA,"Amateur Radio","Pequot Lakes","W0REA PQ LKS",CSQ,"123.0 PL",FM,RM,Ham
446.000000,0.00000,,"Amateur Radio","Nowhere Junction","SIMPLEX",CSQ,CSQ,FM,M,Ham
154.130000,158.77000,KCA123,"Fire Dispatch","County Fire","CW FIRE","131.8 PL","131.8 PL",FM,RM,"Fire Dispatch"
851.012500,806.01250,WPXY123,"MN ARMER","Site 036 Crosby","",CSQ,CSQ,P25,RM,TRS
'''


def main():
    folder = tempfile.mkdtemp(prefix="towerwitch-county-")
    csv_path = os.path.join(folder, "ctid_1327_1790122872.csv")
    io.open(csv_path, "w", encoding="utf-8", newline="").write(SAMPLE)
    store = os.path.join(folder, "county_frequencies.json")

    print("\nthe file is recognised as a county, not a system")
    kind, records, report = radioreference.read(csv_path)
    ok("kind", kind, radioreference.FREQUENCIES)
    ok("  county id from the name, not the timestamp", report["system"], "1327")
    ok("  every row kept", report["kept"], 6)

    print("\nthe eleventh column is the Tag, the sixth is the alpha tag")
    first = records[0]
    ok("tag", first["tag"], "Ham")
    ok("  alpha tag", first["alpha_tag"], "W0UJ VHF BRD")
    ok("  description is the place", first["description"], "Brainerd ARC - VHF")

    print("\nthe store keeps a county and answers by tag")
    frequency_store.save(store, report["system"], records, source=csv_path)
    ok("counties held", [c["county"] for c in frequency_store.counties(store)],
       ["1327"])
    ok("  Ham rows", len(frequency_store.frequencies(store, tag="Ham")), 4)
    ok("  matched without regard to case",
       len(frequency_store.frequencies(store, tag="HAM")), 4)
    ok("  a tag nobody uses returns nothing, not everything",
       frequency_store.frequencies(store, tag="Curling"), [])
    ok("  the breakdown the import reports",
       frequency_store.tags(store),
       {"Ham": 4, "Fire Dispatch": 1, "TRS": 1})
    ok("  fire and trunked rows are held, not thrown away",
       len(frequency_store.frequencies(store)), 6)

    print("\nand the band tabs get them shaped their way")
    import TowerWitch_Tkinter as tw

    class Bare:
        """The two methods under test read no widget and no Tk state."""
        town_position = tw.TowerWitchTkinter.town_position
        county_amateur_repeaters = tw.TowerWitchTkinter.county_amateur_repeaters

    tw.COUNTY_JSON = store
    shaped = Bare().county_amateur_repeaters()
    ok("only the Ham rows arrive", len(shaped), 4)

    by_call = {r["location"]: r for r in shaped}
    vhf = by_call["Brainerd ARC - VHF"]
    ok("  the input tone is the one shown - it opens the machine",
       vhf["tone"], "123.0")
    ok("  Brainerd is placed from its name", (vhf["lat"], vhf["lon"]),
       (46.358, -94.201))
    ok("  Crosslake is not answered by a shorter town inside it",
       (by_call["Crosslake"]["lat"], by_call["Crosslake"]["lon"]),
       (46.66, -94.107))
    ok("  Pequot Lakes, which the table did not have before",
       by_call["Pequot Lakes"]["lat"], 46.6027)
    ok("  a town nobody has is listed anyway, without a position",
       (by_call["Nowhere Junction"]["lat"],
        by_call["Nowhere Junction"]["output"]), (None, "446.0000"))
    ok("  and its CSQ stays CSQ", by_call["Crosslake"]["tone"], "CSQ")

    print("\nthe columns render without inventing a frequency or a tone")
    mhz, tone = tw.TowerWitchTkinter._mhz, tw.TowerWitchTkinter._tone_text
    ok("an output frequency", mhz("145.1300"), "145.1300 MHz")
    ok("  no input means simplex, not 0.0000 MHz",
       mhz("", blank="simplex"), "simplex")
    ok("  a tone in hertz", tone("123.0"), "123.0 Hz")
    ok("  CSQ is not a number of hertz", tone("CSQ"), "CSQ")
    ok("  and neither is nothing at all", tone(""), "CSQ")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
        return 1
    print("all ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
