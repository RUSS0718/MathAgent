# Issue tracker: GitHub

Issues and specs for this project live in GitHub Issues at `RUSS0718/MathAgent`. Pass the repository explicitly with `gh -R RUSS0718/MathAgent` for every issue operation.

## Conventions

- Create: `gh issue create -R RUSS0718/MathAgent --title "..." --body "..."`.
- Read: `gh issue view <number> -R RUSS0718/MathAgent`.
- List: `gh issue list -R RUSS0718/MathAgent --state open`.
- Comment: `gh issue comment <number> -R RUSS0718/MathAgent --body "..."`.
- Close: `gh issue close <number> -R RUSS0718/MathAgent`.

Pull requests are not used as an issue-triage surface.

## REST fallback when `gh` is not authenticated

On this machine `gh` is not logged in, but the Git credential manager holds a GitHub token. Use the REST API directly:

- Read operations need no token: `curl -s https://api.github.com/repos/RUSS0718/MathAgent/issues/<n>` (public repo).
- Get the token without printing it: `TOKEN=$(printf "protocol=https\nhost=github.com\n\n" | git credential fill | sed -n 's/^password=//p')`; never echo or commit it, `unset TOKEN` when done.
- Comment: write the JSON body to a file first (`{"body":"..."}) and `curl -X POST -H "Authorization: token $TOKEN" --data-binary @file .../issues/<n>/comments`. Inline `-d` with a long Chinese body once failed with 400 (shell escaping); the body file is the verified path.
- Close: `curl -X PATCH -H "Authorization: token $TOKEN" -d '{"state":"closed"}' .../issues/<n>` (expect 200).
- Verify the final state through the public no-token GET with a cache-buster (`?_=$(date +%s)`); a plain GET right after PATCH can return a cached `"open"`.
