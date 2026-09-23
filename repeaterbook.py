"""repeaterbook.py - reading a RepeaterBook export.

RadioReference describes systems and places; RepeaterBook describes
amateur repeaters and nothing else, and it is the better source for them
because it is maintained by the people who own the machines. A county
export from RadioReference carries whatever ham rows somebody thought to
file there - eight, for Crow Wing - where a RepeaterBook export carries
the repeaters themselves, with the county and state beside each one.

Its export is plain CSV with a header, quoted where it needs to be, and
unlike RadioReference's it escapes its quotes properly, so there is no
repair to do here.

    Output Freq,Input Freq,Offset,Uplink Tone,Downlink Tone,Call,
    "Location",County,State,Modes,Digital Access

The records come back under those same column names rather than being
renamed, because TowerWitch already has a reader for this shape and the
point of coming in through the Import button is to land where the rest
of the program already looks.

What it does not carry is a position. Neither does RadioReference. The
band tabs place a repeater by the town named in Location, and one they
cannot place is listed without a distance rather than put somewhere
convenient.
"""

import csv
import io
import os

HEADER = ("outputfreq", "inputfreq", "offset", "uplinktone", "downlinktone",
          "call", "location", "county", "state")
COLUMNS = ["Output Freq", "Input Freq", "Offset", "Uplink Tone",
           "Downlink Tone", "Call", "Location", "County", "State", "Modes",
           "Digital Access"]

REPEATERBOOK = "repeaterbook"


def _normal(name):
    """A column name with the spaces and case taken out, for comparing."""
    return "".join((name or "").split()).lower().strip('"')


def looks_like(first_line):
    """Whether this is a RepeaterBook export, read off its header.

    By the header and not the filename: a file that has been through a
    download folder twice is "RB_2605011724 (1).csv", and the name it was
    given says nothing anyway.
    """
    try:
        columns = next(csv.reader([first_line]))
    except (csv.Error, StopIteration):
        return False
    seen = [_normal(c) for c in columns]
    return all(wanted in seen for wanted in HEADER)


def _blank_report(path):
    return {"path": path, "name": os.path.basename(path), "kind": REPEATERBOOK,
            "read": 0, "kept": 0, "skipped": [], "repaired": [],
            "duplicates": [], "states": {}, "system": None, "fatal": None}


def _note(report, line, why, row):
    report["skipped"].append({"line": line, "why": why, "row": row})


def read(path):
    """A RepeaterBook export, and a report. Returns (records, report).

    A row without a usable output frequency is the only row dropped: it
    is not a repeater, whatever else it is. Everything else is kept,
    every state of it - filtering a national export down to one state
    here would throw away the only copy we have of the rest.
    """
    report = _blank_report(path)
    try:
        with io.open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except OSError as exc:
        report["fatal"] = f"could not be opened ({exc})"
        return [], report
    except csv.Error as exc:
        report["fatal"] = f"could not be read as CSV ({exc})"
        return [], report

    if not rows:
        report["fatal"] = "the file is empty"
        return [], report

    header = [_normal(c) for c in rows[0]]
    if not all(wanted in header for wanted in HEADER):
        report["fatal"] = ("not a RepeaterBook export - the first line is not "
                           "its header")
        return [], report

    index = {name: position for position, name in enumerate(header)}

    def field(row, name):
        position = index.get(_normal(name))
        if position is None or position >= len(row):
            return ""
        return (row[position] or "").strip()

    out = []
    for number, row in enumerate(rows[1:], start=2):
        report["read"] += 1
        if not any(cell.strip() for cell in row):
            continue                     # a blank line is not a complaint
        output = field(row, "Output Freq")
        try:
            if float(output) <= 0:
                raise ValueError(output)
        except ValueError:
            _note(report, number, f"output frequency {output!r} is not a "
                                  f"frequency", row)
            continue
        record = {name: field(row, name) for name in COLUMNS}
        state = record["State"] or "(none)"
        report["states"][state] = report["states"].get(state, 0) + 1
        out.append(record)
        report["kept"] += 1
    return out, report


def write_csv(path, records):
    """The repeaters back out, under the column names they came in with,
    so the loader that already reads this shape needs to learn nothing."""
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(COLUMNS)
        for record in records:
            out.writerow([record.get(name, "") for name in COLUMNS])
    return len(records)


def summary(report):
    """The lines to print about one file, in the house shape."""
    name = report["name"]
    if report["fatal"]:
        return [f"[ERROR] {name}: {report['fatal']}"]
    lines = [f"[OK] {name}: {report['kept']} repeaters of {report['read']} "
             f"rows, {len(report['states'])} states"]
    if report["states"]:
        best = sorted(report["states"].items(), key=lambda kv: (-kv[1], kv[0]))
        lines.append("       " + ", ".join(f"{state} {count}"
                                           for state, count in best[:5]))
    if report["skipped"]:
        first = report["skipped"][0]
        lines.append(f"[WARN] {name}: {len(report['skipped'])} rows skipped, "
                     f"first at line {first['line']} ({first['why']})")
    return lines
