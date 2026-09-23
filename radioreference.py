"""Reading RadioReference exports as they actually come off the website.

A person with a RadioReference account can download their system as CSV,
and gets two files: `trs_sites_<id>.csv`, the towers, and `trs_tg_<id>.csv`,
the talkgroups. TowerWitch already wanted the first, under one hardcoded
name at the top of the repo, and had never heard of the second. This reads
both, from wherever they were put, and says what it found.

**The files are told apart by their header, not their name.** A file that
has been through a download folder twice is `trs_tg_3508 (1).csv`, and one
somebody tidied is `armer talkgroups.csv`. The first line says which it is
and that is a better question to ask.

**They are not quite CSV.** RadioReference does not escape the quotes
inside a quoted field, so the State Patrol's district talkgroups come off
the site like this:

    54,036,"MSP 2500 DSP","D","West Metro "2500" Dispatch",...

Python's csv module reads that without complaining and hands back
`West Metro 2500" Dispatch"` - the quote moved, a character appeared at the
end, and nothing anywhere said so. That is the worst way for a file to be
wrong. So a line whose fields do not come out right is read again by a
rule that fits the file: **a quoted field ends at the first quote that is
followed by a comma or by the end of the line**, and any quote inside it is
part of the text. Every line repaired that way is counted and listed in the
report, because a silent repair is the same sin as a silent corruption.

**Site NAC is hexadecimal.** It is written `400`, `40B`, `40a` - values
with a letter in them can only be hex, and the ones without are hex too. It
was being read as decimal, which turned NAC 0x400 into 0x190 and threw away
every site whose NAC had a letter in it, because `int("40B")` raises and
the row was skipped by a bare `continue`. Both are fixed here.

**Nothing here prints or writes anything on its own.** Reading returns the
records and a *report* - the counts, and every line that was repaired,
skipped or looked wrong, with its number. The caller decides whether that
goes to a log, a window or a test. An import that half worked can then say
exactly which half.
"""

import csv
import io
import os
import re

# What the first line looks like for each kind. Matched loosely - lower
# case, no spaces - because the export has changed capitalisation before
# and a header is not worth being strict about.
SITES_HEADER = ("rfss", "sitedec", "sitehex", "sitenac", "description")
TALKGROUPS_HEADER = ("decimal", "hex", "alphatag", "mode", "description")

SITES = "sites"
TALKGROUPS = "talkgroups"

# A control channel is marked with a trailing c in the frequency column.
CONTROL = "c"
# The system's number, off the end of the name RadioReference gives it.
SYSTEM_IN_NAME = re.compile(r"(\d{3,6})")


def _slug(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def kind_of(path):
    """Which of the two this file is, by its header, or None.

    Never raises: a file that cannot be opened or read is not one of ours,
    which is the answer the caller wants rather than an exception.
    """
    try:
        with io.open(path, encoding="utf-8-sig", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return None
    fields = [_slug(f) for f in next(csv.reader([first]), [])]
    if not fields:
        return None
    if all(want in fields for want in SITES_HEADER):
        return SITES
    if all(want in fields for want in TALKGROUPS_HEADER):
        return TALKGROUPS
    return None


def system_id(path):
    """The system's number, from the file's name, or None.

    `trs_tg_3508.csv` is system 3508. A file somebody renamed has no
    number in it and gets None, which is not a fault - it only means the
    two files cannot be filed together automatically.
    """
    found = SYSTEM_IN_NAME.findall(os.path.basename(path))
    return found[-1] if found else None


def split_line(line):
    """One line into fields, by a rule that fits this file.

    A quoted field ends at the first quote followed by a comma or by the
    end of the line. Any other quote is part of the text, which is what
    lets `"West Metro "2500" Dispatch"` come back whole. Returns the
    fields and whether the line needed this at all.
    """
    line = line.rstrip("\r\n")
    fields, i, n, repaired = [], 0, len(line), False
    while i <= n:
        if i == n:
            fields.append("")
            break
        if line[i] == '"':
            i += 1
            start = i
            while i < n:
                if line[i] == '"' and (i + 1 >= n or line[i + 1] == ","):
                    break
                if line[i] == '"':
                    repaired = True          # a quote inside the text
                i += 1
            fields.append(line[start:i])
            i += 2                            # past the closing quote and comma
        else:
            end = line.find(",", i)
            if end < 0:
                fields.append(line[i:])
                break
            fields.append(line[i:end])
            i = end + 1
    return fields, repaired


def _rows(path, report):
    """Every line of the file as fields, repairing the ones that need it.

    csv.reader first, because it is right for every well-formed line and
    understands a field with a newline in it. A line it disagrees with -
    by field count, or by leaving a quote stranded in the text - is read
    again by split_line() and counted as repaired.
    """
    try:
        with io.open(path, encoding="utf-8-sig", errors="replace", newline="") as handle:
            lines = handle.readlines()
    except OSError as exc:
        report["fatal"] = f"could not be read ({exc})"
        return []

    out = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        plain = next(csv.reader([line]), [])
        if any('"' in field for field in plain):
            fixed, _ = split_line(line)
            report["repaired"].append({"line": number, "was": plain, "now": fixed})
            out.append((number, fixed))
        else:
            out.append((number, plain))
    return out


def _blank_report(path, kind):
    return {"path": path, "kind": kind, "system": system_id(path),
            "read": 0, "kept": 0, "repaired": [], "skipped": [],
            "duplicates": [], "no_position": [], "fatal": None}


def _note(report, number, why, row):
    report["skipped"].append({"line": number, "why": why,
                              "row": ",".join(row)[:120]})


def read_talkgroups(path):
    """The talkgroups, and a report. Returns (records, report).

    A record carries the decimal id the radio uses, the hex the system
    uses, the short tag a display has room for, the description, the
    service tag, the agency, and whether it is encrypted - which is the
    E on the mode, in whatever case the export felt like using that day.
    """
    report = _blank_report(path, TALKGROUPS)
    rows = _rows(path, report)
    if report["fatal"]:
        return [], report

    seen, out = {}, []
    for number, row in rows[1:]:                 # the header is row one
        report["read"] += 1
        if len(row) < 7:
            _note(report, number, f"{len(row)} fields, wanted 7", row)
            continue
        decimal, hexid, tag, mode, description, service, agency = row[:7]
        try:
            decimal = int(decimal.strip())
        except ValueError:
            _note(report, number, f"talkgroup {decimal!r} is not a number", row)
            continue
        mode = (mode or "").strip()
        record = {
            "decimal": decimal,
            "hex": (hexid or "").strip().lower(),
            "tag": (tag or "").strip(),
            "description": (description or "").strip(),
            "service": (service or "").strip(),
            # The export leaves a trailing space on a good many of these.
            "agency": (agency or "").strip(),
            "mode": mode.upper(),
            "encrypted": "e" in mode.lower(),
        }
        if decimal in seen:
            report["duplicates"].append({"decimal": decimal, "line": number,
                                         "first": seen[decimal],
                                         "tag": record["tag"]})
        else:
            seen[decimal] = number
        out.append(record)
        report["kept"] += 1
    return out, report


def parse_nac(text):
    """A site's NAC, as the number it is. Hexadecimal - see the module note.

    Returns None for an empty one, which plenty of sites have and which is
    not a fault.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None


def parse_frequency(token):
    """One frequency column as (hertz, is_control), or (None, False).

    `858.237500c` is a control channel at 858.2375 MHz. The marker is a
    trailing c, and it is the only reason the column is not just a number.
    """
    token = (token or "").strip()
    if not token:
        return None, False
    control = token.lower().endswith(CONTROL)
    if control:
        token = token[:-1]
    try:
        return int(round(float(token) * 1_000_000)), control
    except ValueError:
        return None, False


def read_sites(path):
    """The tower sites, and a report. Returns (records, report).

    The frequencies are not one column: they are every column from the
    tenth to the end of the line, and a site has as many as it has. Each
    is read into hertz, and the ones marked as control channels are kept
    apart, because those are the ones a receiver is told to sit on.
    """
    report = _blank_report(path, SITES)
    rows = _rows(path, report)
    if report["fatal"]:
        return [], report

    seen, out = {}, []
    for number, row in rows[1:]:
        report["read"] += 1
        if len(row) < 10:
            _note(report, number, f"{len(row)} fields, wanted at least 10", row)
            continue
        try:
            rfss = int(row[0].strip())
            site = int(row[1].strip())          # zero padded in the export
        except ValueError:
            _note(report, number, "RFSS or site is not a number", row)
            continue

        def number_or_none(text):
            try:
                return float(text.strip())
            except (ValueError, AttributeError):
                return None

        control, every = [], []
        for token in row[9:]:
            hertz, is_control = parse_frequency(token)
            if hertz is None:
                continue
            every.append(hertz)
            if is_control:
                control.append(hertz)

        record = {
            "rfss": rfss, "site": site,
            "site_hex": (row[2] or "").strip(),
            "nac": parse_nac(row[3]),
            "description": (row[4] or "").strip(),
            "county": (row[5] or "").strip(),
            "lat": number_or_none(row[6]),
            "lon": number_or_none(row[7]),
            "range_mi": number_or_none(row[8]),
            "control_hz": control,
            "all_hz": every,
        }
        # A site with no position is kept. It cannot be put on a map or
        # sorted by distance, but OP25 wants its NAC and its control
        # channels and neither of those is a coordinate - and the store
        # this feeds has always kept them. Noted rather than dropped, so
        # a caller that needs a position can pass over it knowingly.
        if record["lat"] is None or record["lon"] is None:
            report["no_position"].append({"line": number,
                                          "description": record["description"]})
        if not every:
            _note(report, number, "no frequencies", row)
            continue

        key = (rfss, site)
        if key in seen:
            report["duplicates"].append({"rfss": rfss, "site": site,
                                         "line": number, "first": seen[key],
                                         "description": record["description"]})
        else:
            seen[key] = number
        out.append(record)
        report["kept"] += 1
    return out, report


def read(path):
    """Whichever kind this file is. Returns (kind, records, report)."""
    kind = kind_of(path)
    if kind == SITES:
        records, report = read_sites(path)
    elif kind == TALKGROUPS:
        records, report = read_talkgroups(path)
    else:
        report = _blank_report(path, None)
        report["fatal"] = ("not a RadioReference export - the first line is "
                           "neither a sites header nor a talkgroups one")
        return None, [], report
    return kind, records, report


def summary(report):
    """The report as lines somebody can read. The caller decides where."""
    name = os.path.basename(report["path"])
    if report["fatal"]:
        return [f"[ERROR] {name}: {report['fatal']}"]

    out = [f"[OK] {name}: {report['kept']} {report['kind']} of "
           f"{report['read']} rows"
           + (f", system {report['system']}" if report["system"] else "")]
    if report["repaired"]:
        out.append(f"[WARN] {name}: {len(report['repaired'])} rows had quotes "
                   f"inside a quoted field and were read again - the export "
                   f"does not escape them; first at line "
                   f"{report['repaired'][0]['line']}")
    for skip in report["skipped"][:10]:
        out.append(f"[WARN] {name}: line {skip['line']} skipped, {skip['why']}")
    if len(report["skipped"]) > 10:
        out.append(f"[WARN] {name}: and {len(report['skipped']) - 10} more "
                   f"rows skipped")
    if report.get("no_position"):
        out.append(f"[WARN] {name}: {len(report['no_position'])} sites have no "
                   f"position and cannot be mapped or sorted by distance; "
                   f"they are kept for their NAC and control channels")
    if report["duplicates"]:
        first = report["duplicates"][0]
        out.append(f"[WARN] {name}: {len(report['duplicates'])} entries appear "
                   f"twice, first at line {first['line']}; both are kept")
    return out


def main(argv=None):
    """Read the files named on the command line and say what is in them.

        python3 radioreference.py trs_sites_3508.csv trs_tg_3508.csv
    """
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("\n    python3 radioreference.py <csv> [<csv> ...]\n")
        return 2
    worst = 0
    for path in argv:
        kind, records, report = read(path)
        for line in summary(report):
            print(line)
        if report["fatal"]:
            worst = 1
            continue
        if kind == SITES and records:
            with_cc = sum(1 for r in records if r["control_hz"])
            print(f"       {with_cc} of them name a control channel; "
                  f"{sum(len(r['all_hz']) for r in records)} frequencies in all")
        if kind == TALKGROUPS and records:
            encrypted = sum(1 for r in records if r["encrypted"])
            print(f"       {encrypted} are encrypted; "
                  f"{len({r['agency'] for r in records})} agencies")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
