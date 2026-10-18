"""Create/update the expressly requested draft PR; never merge or change other PRs."""
import json
import os
import subprocess
import sys
import urllib.request
from .core import ROOT, LOCAL, write


def main():
    credential = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True,
                  text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never"), timeout=15, check=True)
    values = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + values["password"],
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "B0-research-delivery"}
    base = "https://api.github.com/repos/zhiguang127/c1_pilot"
    def request(path, method="GET", body=None):
        req = urllib.request.Request(base + path, method=method, headers=headers,
              data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    assert branch == "research/experiment-b0-sota"
    prs = request("/pulls?state=all&head=zhiguang127:research%2Fexperiment-b0-sota")
    assert len(prs) <= 1
    if "--write" in sys.argv:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        remote = request("/git/ref/heads/research/experiment-b0-sota")
        assert remote["object"]["sha"] == head, "Push exact current HEAD before PR delivery"
        body = (LOCAL / "pr-body.md").read_text(encoding="utf-8")
        title = "research: audit external SOTA baselines and run controlled B0 comparison"
        if prs:
            pr = request("/pulls/" + str(prs[0]["number"]))
            assert pr["state"] == "open" and pr["draft"] and not pr["merged"]
            pr = request("/pulls/" + str(pr["number"]), "PATCH", {"title": title, "body": body})
        else:
            # Stack on A to keep frozen A/P1 inputs outside the B0 diff.
            pr = request("/pulls", "POST", {"title": title, "body": body, "head": branch,
                         "base": "research/experiment-a-applicability", "draft": True})
    elif prs:
        pr = request("/pulls/" + str(prs[0]["number"]))
    else:
        print("No B0 PR yet")
        return
    assert pr["draft"] and pr["state"] == "open" and not pr["merged"]
    public = {k: pr[k] for k in ("number", "html_url", "state", "draft", "merged")}
    public.update(head_sha=pr["head"]["sha"], base=pr["base"]["ref"])
    write(LOCAL / "pr-delivery.json", public, True)
    print(json.dumps(public))


if __name__ == "__main__":
    main()
