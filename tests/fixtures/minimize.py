"""Trim a captured response down to the part the parser reads, so fixtures carry no requester data.

Usage: python3 tests/fixtures/minimize.py {youtube|x|github} < raw.html > trimmed.html

- youtube: keeps only <script>var ytInitialData = {...};</script>. Playback URLs inside it
  carry the requester's address as ip=..., which becomes ip=0.0.0.0, and visitorData becomes
  REDACTED. remoteHost, API keys and ytcfg sit outside the block and are dropped with the rest.
- x: keeps only the <script id="__NEXT_DATA__"> timeline payload.
- github: keeps only the <article class="Box-row"> blocks of the trending page.

Reddit RSS, Hacker News JSON and tweet-result JSON are small public API responses and are
stored as captured. Running the script on its own output gives the same output.
"""
import re
import sys

# The same patterns the parsers in sources/ match, so a trimmed fixture parses identically.
_YT_INITIAL = re.compile(r"var ytInitialData = ({.*?});</script>", re.S)
_X_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_GH_ARTICLE = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)

# ip= follows ?, & or the JSON escape & and runs to the next separator.
_IP_PARAM = re.compile(r"((?:[?&]|\\u0026)ip=)[^&\\\"\s]*")
_VISITOR_DATA = re.compile(r'("visitorData"\s*:\s*")[^"]*(")')


def youtube(html):
    m = _YT_INITIAL.search(html)
    if not m:
        raise ValueError("no ytInitialData block")
    block = _IP_PARAM.sub(r"\g<1>0.0.0.0", m.group(0))
    block = _VISITOR_DATA.sub(r"\g<1>REDACTED\g<2>", block)
    return "<script>" + block + "\n"


def x(html):
    m = _X_NEXT.search(html)
    if not m:
        raise ValueError("no __NEXT_DATA__ script")
    return m.group(0) + "\n"


def github(html):
    blocks = _GH_ARTICLE.findall(html)
    if not blocks:
        raise ValueError('no <article class="Box-row"> blocks')
    return "".join('<article class="Box-row">%s</article>\n' % b for b in blocks)


KINDS = {"youtube": youtube, "x": x, "github": github}


def main(argv):
    if len(argv) != 2 or argv[1] not in KINDS:
        sys.stderr.write("usage: minimize.py {%s} < raw > trimmed\n" % "|".join(KINDS))
        return 2
    try:
        # surrogateescape keeps any byte that is not UTF-8 exactly as captured.
        out = KINDS[argv[1]](sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))
    except ValueError as e:
        sys.stderr.write("minimize.py %s: %s, refusing to write an empty fixture\n" % (argv[1], e))
        return 1
    sys.stdout.buffer.write(out.encode("utf-8", "surrogateescape"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
