#!/usr/bin/env python3
"""
Give every member a logo the dashboard can show, so initials appear only for
a company that genuinely has no logo anywhere.

fdca.fi is the master. Its members page carries FDCA's own square logo for
most members, and when that page has a logo for a member it always wins over
any other source. Only a member the page does not cover gets a logo from the
company's own website, and that one is judged by a person, not guessed.

    --fdca      match the fdca.fi members page to the registry and write the
                FDCA logo for every member it covers. A member whose current
                logo is still on that page is left alone.
    --review    for every member still without a working logo, collect
                candidates from its homepage and write logo-review.json plus
                logo-review.html, a contact sheet rendered with the
                dashboard's own greyscale filter.
    --confirm   apply the picks from logo-review.json.
    --verify    load every logo_url and report the ones that fail.

Why a person picks. The candidates a homepage offers are not subtle failures:
a client's logo from a reference strip (Microsoft for Carlsson RPS, ANRA for
Flyby Guys), a cookie-banner badge, a feature photo in the header. Each one
reads as a fact once it is in the JSON, so nothing reaches the registry
without a verdict.

White logos. The dashboard greys every logo and shows it on a light card, so
a white-on-transparent logo is invisible. When a site publishes only a white
version, the review offers it through the images.weserv.nl proxy with its
colours negated, which turns it dark and keeps the transparency.

Usage:
    python3 SKILL/scripts/fetch_logos.py --fdca [--check]
    python3 SKILL/scripts/fetch_logos.py --review
    python3 SKILL/scripts/fetch_logos.py --confirm [--check]
    python3 SKILL/scripts/fetch_logos.py --verify
"""

import argparse
import base64
import concurrent.futures
import html
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from probe_missing import NOISE, claims, norm

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "INPUT" / "fdca-member-registry.json"
REVIEW_PATH = ROOT / "OUTPUT" / "logo-review.json"
SHEET_PATH = ROOT / "OUTPUT" / "logo-review.html"
MEMBERS_PAGE = "https://www.fdca.fi/fdca-members/our-members/"
FDCA_UPLOADS = "fdca.fi/wp-content/uploads/"
NEGATE_PROXY = "https://images.weserv.nl/?url={}&filt=negate"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "en,fi;q=0.8",
}
TIMEOUT = 20
MAX_CANDIDATES = 6
MAX_INLINE_SVG = 20_000  # bytes; a larger inline SVG is an illustration, not a logo

# Logo text on fdca.fi -> the registry official_name, for the logos whose text
# names no word of the member. Every pair was checked by hand, 2026-09-21.
LOGO_ALIASES = {
    "GE Vernova FDCA": "GRID SOLUTIONS OY",  # Grid Solutions is fully owned by GE Vernova
    "Hedengren FDCA": "Oy Hedtec Ab",  # Hedtec is a Hedengren group company
    "Jensen Hughes FDCA": "L2 Paloturvallisuus Oy, a Jensen Hughes Company",
    "Power Deriva FDCA": "PD Power Oy",  # PD Power's homepage is power-deriva.fi
    "Vihti FDCA": "Vihdin kunta",
    "Carrier QuantumLeap FDCA": "Carrier OY",
    "Zauner Group FDCA": "Zauner Mission Critical",
}

# Words in a logo file name that mark a version drawn for a dark background,
# or an image that is not the member's own logo.
WHITE_WORDS = ("white", "nega", "negative", "inverse", "reverse")
NOT_OURS = ("partner", "client", "customer", "reference", "sponsor", "award",
            "cert", "iso", "badge", "gdpr", "cookie", "flag", "facebook",
            "linkedin", "instagram", "youtube", "twitter")


def nfc(text: str) -> str:
    """fdca.fi mixes decomposed and composed letters; compare in one form."""
    return unicodedata.normalize("NFC", text or "")


def load_registry() -> list:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(members: list) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(members, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def is_fdca(url: str) -> bool:
    return FDCA_UPLOADS in (url or "")


def looks_white(url: str) -> bool:
    """True when the file name marks a version drawn for a dark background.

    Whole words only, so "whitewatergroup" is not a white logo; "valk"
    (Finnish, white) is matched inside words because Finnish compounds it.
    """
    if url.startswith(("data:", NEGATE_PROXY[:28])):
        return False
    name = url.lower().rsplit("/", 1)[-1]
    return "valk" in name or bool(re.search(
        r"(^|[^a-z])(" + "|".join(WHITE_WORDS) + r")([^a-z]|$)", name))


def negated(url: str) -> str:
    return NEGATE_PROXY.format(quote(url, safe=""))


# --- the master pass -------------------------------------------------------


def fdca_logos() -> list:
    """(logo text, url) for every member logo on the fdca.fi members page."""
    page = requests.get(MEMBERS_PAGE, headers=HEADERS, timeout=TIMEOUT)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    out = []
    for img in soup.select(".member-image img"):
        # Older uploads leave `alt` empty and carry the name in `title`.
        text = nfc(img.get("alt") or img.get("title") or "")
        if img.get("src"):
            out.append((text, img["src"]))
    return out


def logo_core(text: str) -> list:
    """The words of a logo's text that name the company."""
    words = [w for w in norm(text) if w != "fdca" and not w.isdigit()]
    return [w for w in words if w not in NOISE] or words


def fdca_pass(members: list, check: bool) -> None:
    logos = fdca_logos()
    print(f"{len(logos)} member logos on {MEMBERS_PAGE}")
    on_page = {url for _, url in logos}
    by_official = {nfc(m.get("official_name")): m for m in members if m.get("official_name")}

    # A logo a member already holds is claimed by that member, whatever its
    # text says — "Borenius netti" and "HW_POS_RBG_Vertical" name no one.
    held = {m.get("logo_url") for m in members}

    changed, unclaimed, ambiguous = [], [], []
    for text, url in logos:
        if url in held:
            continue
        if text in LOGO_ALIASES:
            hits = [by_official[nfc(LOGO_ALIASES[text])]]
        else:
            core = logo_core(text)
            hits = [m for m in members if claims(m, core)]
        if not hits:
            unclaimed.append((text, url))
            continue
        if len(hits) > 1:
            ambiguous.append((text, [m["display_name"] for m in hits]))
            continue
        member = hits[0]
        # A member whose logo is still on the page keeps it: the page can hold
        # two versions of one logo, and re-picking on every run would flap.
        if member.get("logo_url") in on_page or member.get("logo_url") == url:
            continue
        changed.append((member, member.get("logo_url"), url))

    for member, was, now in changed:
        print(f"  {member['display_name']:40s} {'fills' if not was else 'replaces'} -> {now.split('uploads/')[-1]}")
        member["logo_url"] = now
    print(f"\n{len(changed)} logos written from fdca.fi")
    if ambiguous:
        print(f"\n{len(ambiguous)} logos match several members — add a LOGO_ALIASES entry:")
        for text, names in ambiguous:
            print(f"  {text!r}: {names}")
    if unclaimed:
        print(f"\n{len(unclaimed)} logos no member claims — a former member, or a LOGO_ALIASES entry to add:")
        for text, url in unclaimed:
            print(f"  {text!r}  {url}")
    if check:
        print("\n--check: nothing written")
        return
    if changed:
        save_registry(members)
        print(f"wrote {REGISTRY_PATH.name}")


# --- loading checks --------------------------------------------------------


def loads(url: str) -> bool:
    """True when the url returns an image, as a browser would request it."""
    if url.startswith("data:image/"):
        return True
    try:
        r = requests.get(url, headers={**HEADERS, "Referer": "https://claude.ai/"},
                         timeout=TIMEOUT)
    except requests.RequestException:
        return False
    ctype = r.headers.get("content-type", "")
    return r.status_code == 200 and (
        ctype.startswith("image/") or r.content[:300].lstrip().startswith((b"<svg", b"<?xml"))
    )


def needs_logo(members: list) -> list:
    """Members the dashboard would show as initials, or as an invisible logo."""
    with_logo = [m for m in members if m.get("logo_url")]
    with concurrent.futures.ThreadPoolExecutor(16) as pool:
        ok = dict(zip((id(m) for m in with_logo), pool.map(lambda m: loads(m["logo_url"]), with_logo)))
    return [
        m for m in members
        if not m.get("logo_url")
        or not ok[id(m)]
        or (not is_fdca(m["logo_url"]) and looks_white(m["logo_url"]))
    ]


def verify(members: list) -> None:
    todo = needs_logo(members)
    print(f"{len(members) - len(todo)} of {len(members)} members show a logo")
    for m in todo:
        reason = "no logo" if not m.get("logo_url") else (
            "white logo" if looks_white(m["logo_url"]) else "does not load")
        print(f"  {m['display_name']:40s} {reason}  {m.get('logo_url') or ''}"[:160])


# --- the review queue ------------------------------------------------------


def homepage_candidates(member: dict) -> tuple:
    """Ranked logo candidates from the member's own homepage."""
    home = member.get("url")
    if not home:
        return [], "no homepage in the registry"
    try:
        page = requests.get(home, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as error:
        return [], f"homepage unreachable: {type(error).__name__}"
    if page.status_code != 200:
        return [], f"homepage HTTP {page.status_code}"
    soup = BeautifulSoup(page.text, "html.parser")
    found = []

    def add(src, how, score):
        if not src or src.startswith("data:"):
            return
        url = urljoin(page.url, src.strip().split(" ")[0])
        if any(word in url.lower() for word in NOT_OURS):
            return
        found.append((score, url, how))

    for img in soup.find_all("img"):
        own = " ".join(str(img.get(k) or "") for k in ("class", "id", "alt", "src")).lower()
        near = " ".join(" ".join(p.get("class", [])) + " " + (p.get("id") or "")
                        for p in list(img.parents)[:4]).lower()
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or \
            (img.get("srcset") or "").split(",")[0]
        in_header = bool(img.find_parent(["header", "nav"])) or "header" in near
        if "logo" in own or "logo" in near or "brand" in own:
            add(src, "logo in header" if in_header else "logo image", 100 + 30 * in_header)
        elif in_header and img.find_parent("a"):
            add(src, "header link image", 70)
    for link in soup.find_all("link", rel=True):
        if "apple-touch-icon" in " ".join(link["rel"]).lower():
            add(link.get("href"), "touch icon", 30)
    for meta in soup.find_all("meta"):
        if (meta.get("property") or "").lower() == "og:image":
            add(meta.get("content"), "og:image", 20)

    ranked, seen = [], set()
    for score, url, how in sorted(found, key=lambda item: -item[0]):
        if url in seen:
            continue
        seen.add(url)
        if looks_white(url):
            url, how = negated(url), how + ", colours negated"
        if loads(url):
            ranked.append({"url": url, "found_as": how})
        if len(ranked) >= MAX_CANDIDATES:
            break

    # A logo drawn inline has no file to link, so it is carried as a data URI.
    for svg in soup.find_all("svg"):
        if len(ranked) >= MAX_CANDIDATES:
            break
        text = str(svg)
        if not svg.find_parent(["header", "a"]) or not 600 < len(text) < MAX_INLINE_SVG:
            continue
        if not svg.get("xmlns"):
            svg["xmlns"] = "http://www.w3.org/2000/svg"
        data = base64.b64encode(str(svg).encode()).decode()
        ranked.append({"url": f"data:image/svg+xml;base64,{data}", "found_as": "inline svg"})
    return ranked, None


def review(members: list) -> None:
    todo = needs_logo(members)
    print(f"collecting candidates for {len(todo)} members …")
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        results = list(pool.map(homepage_candidates, todo))
    rows = [
        {
            "official_name": m.get("official_name"),
            "display_name": m["display_name"],
            "homepage": m.get("url"),
            "current_logo": m.get("logo_url"),
            "problem": problem,
            "candidates": candidates,
            "pick": "",
        }
        for m, (candidates, problem) in zip(todo, results)
    ]
    REVIEW_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SHEET_PATH.write_text(contact_sheet(rows), encoding="utf-8")
    print(f"wrote {REVIEW_PATH.name} and {SHEET_PATH.name}")
    print("\nOpen the contact sheet, then set each row's `pick` to:")
    print("  0, 1, …   the candidate at that position")
    print("  a url     a logo found elsewhere (wrap a white one with the negate proxy)")
    print("  none      the company has no logo anywhere; initials stay")
    print("\nthen run: python3 SKILL/scripts/fetch_logos.py --confirm")


def contact_sheet(rows: list) -> str:
    """Every candidate, rendered as the dashboard renders a logo."""
    style = (
        "body{font:12px system-ui,sans-serif;background:#f7f6f2;margin:16px}"
        ".r{display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-bottom:1px solid #ddd;padding:6px 0}"
        ".r b{width:200px;flex:none}.c{width:150px;text-align:center;background:#fff;padding:4px}"
        ".c img{width:140px;height:60px;object-fit:contain;filter:grayscale(1);opacity:.88}"
    )
    body = []
    for row in rows:
        cells = "".join(
            f'<div class=c><img src="{html.escape(c["url"])}"><br><small>{i} · {html.escape(c["found_as"])}</small></div>'
            for i, c in enumerate(row["candidates"])
        ) or f"<i>{html.escape(row['problem'] or 'no candidates')}</i>"
        body.append(f'<div class=r><b>{html.escape(row["display_name"])}</b>{cells}</div>')
    return f"<title>Logo review</title><style>{style}</style>" + "".join(body)


def confirm(members: list, check: bool) -> None:
    if not REVIEW_PATH.exists():
        raise SystemExit(f"{REVIEW_PATH.name} not found — run --review first")
    rows = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    by_name = {m["display_name"]: m for m in members}
    applied, blank, none, bad = [], 0, 0, []
    for row in rows:
        pick = str(row.get("pick") or "").strip()
        member = by_name.get(row["display_name"])
        if member is None:
            bad.append((row["display_name"], "no member with this display_name"))
        elif not pick:
            blank += 1
        elif pick.lower() == "none":
            none += 1
        elif is_fdca(member.get("logo_url")) and loads(member["logo_url"]):
            bad.append((row["display_name"], "has a working fdca.fi logo, which is the master"))
        else:
            if pick.isdigit():
                if int(pick) >= len(row["candidates"]):
                    bad.append((row["display_name"], f"no candidate {pick}"))
                    continue
                pick = row["candidates"][int(pick)]["url"]
            if not loads(pick):
                bad.append((row["display_name"], f"picked logo does not load: {pick[:80]}"))
                continue
            applied.append((member, pick))

    print(f"{len(applied)} ready, {none} none, {blank} blank, {len(bad)} rejected")
    for name, why in bad:
        print(f"  REJECTED {name}: {why}")
    if bad:
        raise SystemExit("\nfix those rows; nothing written")
    for member, url in applied:
        member["logo_url"] = url
        print(f"  {member['display_name']:40s} -> {url[:90]}")
    if check:
        print("\n--check: nothing written")
        return
    save_registry(members)
    print(f"\nwrote {REGISTRY_PATH.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fdca", action="store_true", help="write logos from the fdca.fi members page")
    mode.add_argument("--review", action="store_true", help="queue homepage candidates for a person")
    mode.add_argument("--confirm", action="store_true", help="apply the picked candidates")
    mode.add_argument("--verify", action="store_true", help="report members without a working logo")
    parser.add_argument("--check", action="store_true", help="with --fdca or --confirm: write nothing")
    args = parser.parse_args()

    members = load_registry()
    if args.fdca:
        fdca_pass(members, args.check)
    elif args.review:
        review(members)
    elif args.confirm:
        confirm(members, args.check)
    else:
        verify(members)


if __name__ == "__main__":
    main()
