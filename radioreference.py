"""Reading RadioReference exports as they actually come off the website.

A person with a RadioReference account can download three different things,
and this reads all of them, from wherever they were put:

* `trs_sites_<id>.csv` - a trunked system's towers. TowerWitch already
  wanted this one, under a single hardcoded name at the top of the repo.
* `trs_tg_<id>.csv` - that system's talkgroups. Never heard of before.
* `ctid_<county>_<when>.csv` - everything on the air in one county: the
  ham repeaters, the airport, the school buses, the power co-op, and the
  individual channels of whatever trunked systems reach it. A different
  question from the other two - those describe a system, this describes a
  place.

**The files are told apart by their header, not their name.** A file that
has been through a download folder twice is `trs_tg_3508 (1).csv`, and one
somebody tidied is `armer talkgroups.csv`. The first line says which it is
and that is a better question to ask.

**One column in the county file is five different things.** What addresses
a channel depends on what kind of channel it is, and RadioReference puts
all of them in the tone column: `CSQ` for no tone at all, `123.0 PL` for a
CTCSS tone, `043 DPL` for a DCS code, `CC 1|TG 1001|SL 1` for DMR's colour
code, talkgroup and timeslot, and `004 NAC` for a P25 network access code.
Read apart by :func:`parse_tone`, which keeps the original text beside
what it made of it, and calls anything it does not recognise "other"
rather than raising - an unknown tone is still a channel you can tune.

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
# The county list - `ctid_<county>_<when>.csv`. Everything on the air in
# one county: the ham repeaters, the airport, the school buses, the power
# co-op, and the individual channels of the trunked systems.
FREQUENCIES_HEADER = ("frequencyoutput", "frequencyinput", "fcccallsign",
                      "alphatag", "mode")

SITES = "sites"
TALKGROUPS = "talkgroups"
FREQUENCIES = "frequencies"

# A control channel is marked with a trailing c in the frequency column.
CONTROL = "c"
# The number in the name RadioReference gives a download, which follows
# the prefix and nothing else. Anchored there on purpose: a county file is
# `ctid_1327_1790122872.csv`, and simply taking the last run of digits
# picked "2872" out of the timestamp and called it the system.
SYSTEM_IN_NAME = re.compile(r"^(?:trs_sites|trs_tg|ctid)_(\d+)", re.I)
ANY_NUMBER = re.compile(r"(\d{3,6})")


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
    if all(want in fields for want in FREQUENCIES_HEADER):
        return FREQUENCIES
    return None


def system_id(path):
    """The number in the file's name, or None.

    `trs_tg_3508.csv` is system 3508, and `ctid_1327_....csv` is county
    1327 - for a county file this is a place, not a system, which is why
    the summary says "county" there. Taken from straight after the prefix
    rather than from anywhere in the name, because a county file carries
    a download timestamp as well and the last digits in it are not an id
    at all.

    A file somebody renamed falls back to the first number that looks
    like an id, and then to None - which is not a fault, it only means
    the files cannot be filed together automatically.
    """
    name = os.path.basename(path)
    match = SYSTEM_IN_NAME.match(name)
    if match:
        return match.group(1)
    found = ANY_NUMBER.findall(name)
    return found[0] if found else None


def split_line(line):
    """One line into fields, by a rule that fits this file.

    A quoted field ends at the first quote followed by a comma or by the
    end of the line. A doubled quote is an escaped one - that is proper
    CSV and is not a fault. Any *other* quote is a stray the export
    failed to escape, kept as part of the text, which is what lets
    `"West Metro "2500" Dispatch"` come back whole. Returns the fields
    and whether a stray was found.
    """
    line = line.rstrip("\r\n")
    fields, i, n, repaired = [], 0, len(line), False
    while i <= n:
        if i == n:
            fields.append("")
            break
        if line[i] == '"':
            i += 1
            piece = []
            while i < n:
                if line[i] == '"' and line[i + 1:i + 2] == '"':
                    piece.append('"')        # an escaped quote: proper CSV
                    i += 2
                    continue
                if line[i] == '"' and (i + 1 >= n or line[i + 1] == ","):
                    break                    # the field ends here
                if line[i] == '"':
                    repaired = True          # a quote the export did not escape
                piece.append(line[i])
                i += 1
            fields.append("".join(piece))
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

    One parser for every line - see split_line(). csv.reader was used
    first for a while and had to go: it reads a stray-quote line without
    complaining and hands back something subtly different, so using both
    meant two readers that disagreed about the same line, which is the
    bug this module exists to stop. It also could not tell a stray quote
    from a properly escaped one, so the module's own export would not
    survive being read back.
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
        fields, strays = split_line(line)
        if strays:
            report["repaired"].append({"line": number, "fields": fields})
        out.append((number, fields))
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
        decimal, hexid, alpha, mode, description, tag, agency = row[:7]
        try:
            decimal = int(decimal.strip())
        except ValueError:
            _note(report, number, f"talkgroup {decimal!r} is not a number", row)
            continue
        mode = (mode or "").strip()
        record = {
            "decimal": decimal,
            "hex": (hexid or "").strip().lower(),
            "alpha_tag": (alpha or "").strip(),
            "description": (description or "").strip(),
            "tag": (tag or "").strip(),
            # The export leaves a trailing space on a good many of these.
            "agency": (agency or "").strip(),
            "mode": mode.upper(),
            "encrypted": "e" in mode.lower(),
        }
        if decimal in seen:
            report["duplicates"].append({"decimal": decimal, "line": number,
                                         "first": seen[decimal],
                                         "alpha_tag": record["alpha_tag"]})
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


def parse_tone(text):
    """The squelch column, which is five different things wearing one hat.

    RadioReference puts whatever addresses the channel in here, and what
    that is depends on the mode:

        CSQ                  carrier squelch - open, no tone
        123.0 PL             a CTCSS tone, in hertz
        043 DPL              a DCS code, which is octal and keeps its
                             leading zero because that is how it is dialled
        CC 1|TG 1001|SL 1    DMR: colour code, talkgroup, timeslot
        004 NAC              a P25 network access code, hexadecimal

    Returns a dict with `kind` and whatever that kind carries, or None
    for an empty column. Never raises: a value nobody here recognises
    comes back as {"kind": "other", "text": ...} rather than an
    exception, because an unknown tone is a channel you can still tune.
    """
    text = (text or "").strip()
    if not text:
        return None
    upper = text.upper()
    if upper == "CSQ":
        return {"kind": "csq", "text": text}
    if "|" in text and "CC" in upper:
        out = {"kind": "dmr", "text": text}
        for part in text.split("|"):
            bits = part.strip().split()
            if len(bits) != 2:
                continue
            what, value = bits[0].upper(), bits[1]
            try:
                value = int(value)
            except ValueError:
                continue
            out.update({"CC": {"color_code": value}, "TG": {"talkgroup": value},
                        "SL": {"slot": value}}.get(what, {}))
        return out
    if upper.endswith("NAC"):
        try:                                   # hexadecimal, as on a site
            return {"kind": "nac", "nac": int(text.split()[0], 16), "text": text}
        except (ValueError, IndexError):
            return {"kind": "other", "text": text}
    if upper.endswith("DPL") or upper.endswith("DCS"):
        # Kept as written: a DCS code is octal and 043 is not 43.
        return {"kind": "dcs", "code": text.split()[0], "text": text}
    if upper.endswith("PL") or upper.endswith("CTCSS"):
        try:
            return {"kind": "ctcss", "hz": float(text.split()[0]), "text": text}
        except (ValueError, IndexError):
            return {"kind": "other", "text": text}
    return {"kind": "other", "text": text}


def read_frequencies(path):
    """A county's frequencies, and a report. Returns (records, report).

    Everything on the air in one county, which is a different question
    from the two system exports: those describe one trunked system, this
    describes a place. The rows tagged TRS are the individual channels of
    whatever trunked systems reach the county, so an ARMER site turns up
    here as its frequencies where trs_sites describes it as a site.

    An input frequency of 0 means there is no input - the channel is
    simplex, or it is something that only ever transmits, like an
    airport's weather. It comes back as None rather than as 0 Hz, which
    would read as a real frequency at the bottom of the spectrum.
    """
    report = _blank_report(path, FREQUENCIES)
    rows = _rows(path, report)
    if report["fatal"]:
        return [], report

    out = []
    for number, row in rows[1:]:
        report["read"] += 1
        if len(row) < 11:
            _note(report, number, f"{len(row)} fields, wanted 11", row)
            continue
        output_hz, _ = parse_frequency(row[0])
        if output_hz is None:
            _note(report, number, f"output frequency {row[0]!r} is not a number", row)
            continue
        input_hz, _ = parse_frequency(row[1])
        out.append({
            "output_hz": output_hz,
            # 0.00000 is how the export writes "there isn't one".
            "input_hz": input_hz or None,
            # A callsign of one space is how it writes "none of anybody's".
            "callsign": (row[2] or "").strip(),
            "agency": (row[3] or "").strip(),
            "description": (row[4] or "").strip(),
            "alpha_tag": (row[5] or "").strip(),
            "tone_out": parse_tone(row[6]),
            "tone_in": parse_tone(row[7]),
            "mode": (row[8] or "").strip(),
            "station_class": (row[9] or "").strip(),
            "tag": (row[10] or "").strip(),
        })
        report["kept"] += 1
    return out, report


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
    elif kind == FREQUENCIES:
        records, report = read_frequencies(path)
    else:
        report = _blank_report(path, None)
        report["fatal"] = ("not a RadioReference export - the first line is "
                           "not a sites, talkgroups or county header")
        return None, [], report
    return kind, records, report


def summary(report):
    """The report as lines somebody can read. The caller decides where."""
    name = os.path.basename(report["path"])
    if report["fatal"]:
        return [f"[ERROR] {name}: {report['fatal']}"]

    # A county file's number is a place, not a system.
    what = "county" if report["kind"] == FREQUENCIES else "system"
    out = [f"[OK] {name}: {report['kept']} {report['kind']} of "
           f"{report['read']} rows"
           + (f", {what} {report['system']}" if report["system"] else "")]
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


# ------------------------------------------------------------ writing

SITES_COLUMNS = ["RFSS", "Site Dec", "Site Hex", "Site NAC", "Description",
                 "County Name", "Lat", "Lon", "Range", "Frequencies"]
TALKGROUPS_COLUMNS = ["Decimal", "Hex", "Alpha Tag", "Mode", "Description",
                      "Tag", "Category"]


def _hertz_text(hertz, control):
    """A frequency the way the export writes it: megahertz to six places,
    with a trailing c if it is a control channel."""
    return f"{hertz / 1_000_000:.6f}" + (CONTROL if control else "")


def write_sites_csv(path, records):
    """Sites back out, in the shape they came in.

    Written with csv.writer, so what leaves here is *correct* CSV: a quote
    inside a description is escaped the way the standard says, which is
    the one thing the RadioReference export does not do. What we write
    reads back through this module unchanged, and through anybody else's
    csv reader as well - which the file we were given does not.
    """
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(SITES_COLUMNS)
        for site in records:
            control = set(site.get("control_hz") or [])
            row = [
                site.get("rfss", ""),
                f"{int(site['site']):03d}" if site.get("site") is not None else "",
                site.get("site_hex", ""),
                f"{site['nac']:X}" if site.get("nac") is not None else "",
                site.get("description", ""),
                site.get("county", ""),
                "" if site.get("lat") is None else site["lat"],
                "" if site.get("lon") is None else site["lon"],
                "" if site.get("range_mi") is None else site["range_mi"],
            ]
            row += [_hertz_text(hz, hz in control)
                    for hz in site.get("all_hz") or []]
            out.writerow(row)
    return len(records)


def write_talkgroups_csv(path, records):
    """Talkgroups back out, in the shape they came in - and properly
    quoted, so `West Metro "2500" Dispatch` survives the round trip the
    original file could not make."""
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(TALKGROUPS_COLUMNS)
        for tg in records:
            out.writerow([tg.get("decimal", ""), tg.get("hex", ""),
                          tg.get("alpha_tag", ""), tg.get("mode", ""),
                          tg.get("description", ""), tg.get("tag", ""),
                          tg.get("agency", "")])
    return len(records)


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
        if kind == FREQUENCIES and records:
            trunked = sum(1 for r in records if r["tag"].upper() == "TRS")
            print(f"       {len(records) - trunked} conventional channels and "
                  f"{trunked} trunked-system frequencies; "
                  f"{len({r['tag'] for r in records})} tags")
        if kind == TALKGROUPS and records:
            encrypted = sum(1 for r in records if r["encrypted"])
            print(f"       {encrypted} are encrypted; "
                  f"{len({r['agency'] for r in records})} agencies")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
