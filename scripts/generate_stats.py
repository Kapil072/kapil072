"""Generate self-hosted GitHub stats and top-language SVG cards.

Usage: GITHUB_TOKEN=... python scripts/generate_stats.py <user> <out_dir>
"""
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

BG, BORDER, TITLE, TEXT, MUTED, ACCENT = "#0b1120", "#1e293b", "#f8fafc", "#cbd5e1", "#64748b", "#38bdf8"
FONT = "Segoe UI, -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif"
WIDTH, HEIGHT = 440, 200


def graphql(variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch(login):
    user, cursor, repos = None, None, []
    while True:
        page = graphql({"login": login, "cursor": cursor})
        user = user or page
        repos += page["repositories"]["nodes"]
        info = page["repositories"]["pageInfo"]
        if not info["hasNextPage"]:
            break
        cursor = info["endCursor"]
    return user, repos


def card(title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(title)}">
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" fill="{BG}" stroke="{BORDER}"/>
  <text x="24" y="38" font-family="{FONT}" font-size="17" font-weight="700" fill="{TITLE}">{escape(title)}</text>
  <rect x="24" y="48" width="36" height="3" rx="1.5" fill="{ACCENT}"/>
{body}
</svg>
"""


def stats_card(user, repos):
    cc = user["contributionsCollection"]
    rows = [
        ("Total stars earned", sum(r["stargazerCount"] for r in repos)),
        ("Contributions (last year)", cc["contributionCalendar"]["totalContributions"]),
        ("Commits (last year)", cc["totalCommitContributions"]),
        ("Pull requests", cc["totalPullRequestContributions"]),
        ("Public repositories", user["repositories"]["totalCount"]),
    ]
    body = []
    for i, (label, value) in enumerate(rows):
        y = 82 + i * 24
        body.append(
            f'  <circle cx="30" cy="{y - 5}" r="3" fill="{ACCENT}"/>'
            f'<text x="44" y="{y}" font-family="{FONT}" font-size="14" fill="{TEXT}">{escape(label)}</text>'
            f'<text x="{WIDTH - 24}" y="{y}" font-family="{FONT}" font-size="14" font-weight="700" fill="{TITLE}" text-anchor="end">{value:,}</text>'
        )
    return card("GitHub Stats", "\n".join(body))


def languages_card(repos, top=6):
    totals = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size, color = totals.get(name, (0, edge["node"]["color"] or MUTED))
            totals[name] = (size + edge["size"], color)
    ranked = sorted(totals.items(), key=lambda kv: kv[1][0], reverse=True)
    langs = ranked[:top]
    rest = sum(size for _, (size, _) in ranked[top:])
    if rest:
        langs.append(("Other", (rest, "#475569")))
    grand = sum(size for _, (size, _) in langs) or 1

    bar_x, bar_w, x = 24, WIDTH - 48, 24.0
    body = [f'  <clipPath id="bar"><rect x="{bar_x}" y="70" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">']
    for _, (size, color) in langs:
        w = bar_w * size / grand
        body.append(f'    <rect x="{x:.2f}" y="70" width="{w + 0.5:.2f}" height="10" fill="{color}"/>')
        x += w
    body.append("  </g>")
    for i, (name, (size, color)) in enumerate(langs):
        col, row = i % 2, i // 2
        lx, ly = 24 + col * 200, 112 + row * 26
        body.append(
            f'  <circle cx="{lx + 5}" cy="{ly - 5}" r="5" fill="{color}"/>'
            f'<text x="{lx + 18}" y="{ly}" font-family="{FONT}" font-size="14" fill="{TEXT}">{escape(name)}</text>'
            f'<text x="{lx + 180}" y="{ly}" font-family="{FONT}" font-size="13" fill="{MUTED}" text-anchor="end">{100 * size / grand:.1f}%</text>'
        )
    return card("Most Used Languages", "\n".join(body))


def main():
    login, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    user, repos = fetch(login)
    for name, svg in (("stats.svg", stats_card(user, repos)), ("languages.svg", languages_card(repos))):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(svg)
    print(f"Wrote stats for {login}: {len(repos)} repos")


if __name__ == "__main__":
    main()
