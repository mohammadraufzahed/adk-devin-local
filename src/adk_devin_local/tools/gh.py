"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import re
from .cli import CliTools

class GithubTools(CliTools):
    def gh_repo(self, repo: str = "") -> str:
        """Show GitHub repository metadata."""
        args = ["gh", "repo", "view"] + ([repo] if repo else []) + ["--json", "nameWithOwner,url,description,defaultBranchRef"]
        return self._run(args)

    def gh_issue_list(self, state: str = "open", limit: int = 20, repo: str = "") -> str:
        """List GitHub issues."""
        if state not in {"open", "closed", "all"}: return "Invalid issue state."
        args = ["gh", "issue", "list", "--state", state, "--limit", str(max(1, min(limit, 100))), "--json", "number,title,state,url"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_issue_view(self, number: int, repo: str = "") -> str:
        """View a GitHub issue and its comments."""
        args = ["gh", "issue", "view", str(number), "--json", "number,title,body,state,comments,url"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_issue_create(self, title: str, body: str, repo: str = "") -> str:
        """Create a GitHub issue; requires mutation opt-in."""
        denied = self._mutate("GitHub issue creation")
        if denied: return denied
        args = ["gh", "issue", "create", "--title", title[:250], "--body", body[:20_000]]
        if repo: args.extend(["--repo", repo])
        return self._run(args, timeout=90)

    def gh_pr_list(self, state: str = "open", limit: int = 20, repo: str = "") -> str:
        """List GitHub pull requests."""
        if state not in {"open", "closed", "merged", "all"}: return "Invalid PR state."
        args = ["gh", "pr", "list", "--state", state, "--limit", str(max(1, min(limit, 100))), "--json", "number,title,state,url,headRefName"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_pr_checks(self, number: int = 0, repo: str = "") -> str:
        """Show CI checks for a pull request."""
        args = ["gh", "pr", "checks"]
        if number: args.append(str(number))
        if repo: args.extend(["--repo", repo])
        return self._run(args, timeout=90)

    def gh_pr_view(self, number: int, repo: str = "", diff: bool = False) -> str:
        """View a pull request and optionally include its diff."""
        args=["gh","pr","view",str(number),"--json","number,title,body,state,url,headRefName,baseRefName,comments"]
        if repo:args.extend(["--repo",repo])
        result=self._run(args)
        if diff:
            diff_args=["gh","pr","diff",str(number)]
            if repo:diff_args.extend(["--repo",repo])
            return result+"\\n"+self._run(diff_args)
        return result

    def gh_pr_create(self, title: str, body: str = "", base: str = "", head: str = "", draft: bool = False, repo: str = "") -> str:
        """Create a pull request; requires host mutation opt-in."""
        denied=self._mutate("GitHub pull request creation")
        if denied:return denied
        args=["gh","pr","create","--title",title[:250],"--body",body[:20000]]
        if base:args.extend(["--base",base])
        if head:args.extend(["--head",head])
        if draft:args.append("--draft")
        if repo:args.extend(["--repo",repo])
        return self._run(args,timeout=120)

    def gh_pr_comment(self, number: int, body: str, repo: str = "") -> str:
        """Comment on a pull request; requires host mutation opt-in."""
        denied=self._mutate("GitHub PR comment")
        if denied:return denied
        args=["gh","pr","comment",str(number),"--body",body[:20000]]
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_pr_diff(self, number: int, repo: str = "") -> str:
        """Read a pull request's full diff for review."""
        args = ["gh", "pr", "diff", str(number)]
        if repo: args.extend(["--repo", repo])
        return self._run(args, timeout=90)

    def gh_pr_review(self, number: int, event: str = "comment", body: str = "", repo: str = "") -> str:
        """Submit a PR review (approve|request-changes|comment); requires host mutation opt-in."""
        denied = self._mutate("GitHub PR review")
        if denied: return denied
        event_map = {"approve": "--approve", "request-changes": "--request-changes", "comment": "--comment"}
        flag = event_map.get(event)
        if not flag: return "Invalid review event; use approve, request-changes, or comment."
        args = ["gh", "pr", "review", str(number), flag]
        if body: args.extend(["--body", body[:20000]])
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_comment_react(self, kind: str, id: int, reaction: str, repo: str = "") -> str:
        """Add a reaction to an issue, PR, or comment; requires host mutation opt-in."""
        denied = self._mutate("GitHub reaction")
        if denied: return denied
        valid = {"+1", "-1", "laugh", "hooray", "confused", "heart", "rocket", "eyes"}
        if reaction not in valid: return f"Invalid reaction; use one of {sorted(valid)}."
        if kind not in {"issue", "pr", "issue_comment", "review_comment"}: return "Invalid kind."
        base = repo or "{owner}/{repo}"  # gh api expands placeholders from cwd/GH_REPO
        if kind in {"issue", "pr"}:
            endpoint = f"repos/{base}/{'issues' if kind == 'issue' else 'pulls'}/{id}/reactions"
        else:
            endpoint = f"repos/{base}/{'issues' if kind == 'issue_comment' else 'pulls'}/comments/{id}/reactions"
        return self._run(["gh", "api", endpoint, "--method", "POST", "-f", f"content={reaction}"])

    def gh_comment_reply(self, number: int, body: str, in_reply_to: int = 0, repo: str = "") -> str:
        """Reply to a review comment (threaded) or comment on an issue/PR; requires host mutation opt-in."""
        denied = self._mutate("GitHub comment reply")
        if denied: return denied
        if in_reply_to:
            base = repo or "{owner}/{repo}"
            return self._run(["gh", "api", f"repos/{base}/pulls/{number}/comments/{in_reply_to}/replies", "--method", "POST", "-f", f"body={body[:20000]}"])
        args = ["gh", "pr", "comment", str(number), "--body", body[:20000]]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_pr_merge(self, number: int, method: str = "squash", repo: str = "") -> str:
        """Merge a pull request; requires host mutation opt-in."""
        denied=self._mutate("GitHub PR merge")
        if denied:return denied
        if method not in {"squash","merge","rebase"}:return "Invalid merge method."
        args=["gh","pr","merge",str(number),f"--{method}"]
        if repo:args.extend(["--repo",repo])
        return self._run(args,timeout=120)

    def gh_issue_comment(self, number: int, body: str, repo: str = "") -> str:
        """Comment on an issue; requires host mutation opt-in."""
        denied=self._mutate("GitHub issue comment")
        if denied:return denied
        args=["gh","issue","comment",str(number),"--body",body[:20000]]
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_issue_close(self, number: int, comment: str = "", repo: str = "") -> str:
        """Close an issue; requires host mutation opt-in."""
        denied=self._mutate("GitHub issue close")
        if denied:return denied
        args=["gh","issue","close",str(number)]
        if comment:args.extend(["--comment",comment[:10000]])
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_run_view(self, run_id: str, log: bool = False, repo: str = "") -> str:
        """Inspect a workflow run and optionally include failure logs."""
        if not re.fullmatch(r"[0-9]{1,20}",run_id):return "Invalid workflow run id."
        args=["gh","run","view",run_id]
        if log:args.append("--log-failed")
        if repo:args.extend(["--repo",repo])
        return self._run(args,timeout=120)

    def gh_release_list(self, repo: str = "") -> str:
        """List repository releases."""
        args=["gh","release","list","--limit","30"]
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_api(self, endpoint: str, method: str = "GET", fields: dict[str,str] | None = None) -> str:
        """Call GitHub REST API; writes are host-gated and endpoint/fields are constrained."""
        method=method.upper()
        if method not in {"GET","POST","PATCH","PUT","DELETE"}:return "Unsupported HTTP method."
        if not re.fullmatch(r"[A-Za-z0-9_./-]{1,300}",endpoint) or endpoint.startswith("-") or ".." in endpoint:return "Invalid API endpoint."
        if method!="GET":
            denied=self._mutate(f"GitHub API {method}")
            if denied:return denied
        args=["gh","api",endpoint,"--method",method]
        for key,value in list((fields or {}).items())[:20]:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",key):return "Invalid field name."
            args.extend(["-f",f"{key}={value[:4000]}"])
        return self._run(args,timeout=90)

    def gh_run_list(self, limit: int = 10, repo: str = "") -> str:
        """List recent GitHub Actions workflow runs."""
        args = ["gh", "run", "list", "--limit", str(max(1, min(limit, 100))), "--json", "databaseId,displayTitle,status,conclusion,headBranch,url"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)
